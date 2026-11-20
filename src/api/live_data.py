"""Read latest HK quotes locally or from DynamoDB without polling the provider."""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.hk.live import symbol
from src.hk.live_paths import FUTURE_TOLERANCE_SECONDS, local_quote_directory
from src.live.hk import HKT, session_gate

ROOT = Path(__file__).resolve().parents[2]
STALE_AFTER_SECONDS = 60
MAX_LOCAL_BYTES = (
    2_000_000  # Latest-state files are bounded; never read growing history.
)


class LiveDataUnavailable(RuntimeError):
    """The configured quote store cannot currently supply a snapshot."""


def parse_time(value: str) -> datetime:
    """Require an aware ISO time so ages do not depend on the host timezone."""
    result = datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        raise ValueError("Quote timestamps need a timezone")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class LiveSettings:
    """Only public/configuration values; AWS credentials use the normal IAM chain."""

    mode: str = "local"
    directory: Path = ROOT / "data/live_hk_week4"
    roster: Path = ROOT / "config/hsi_constituents_2026-11-04.csv"
    region: str = "us-west-2"
    table: str = "indicatorlab-live-hk"
    auto_discover: bool = False

    @classmethod
    def from_env(cls) -> LiveSettings:
        """Read environment configuration; never silently switch to AWS or demo data."""
        mode = os.getenv("INDICATORLAB_LIVE_SOURCE", "local").lower()
        if mode not in {"local", "dynamodb"}:
            raise ValueError("INDICATORLAB_LIVE_SOURCE must be local or dynamodb")
        return cls(
            mode=mode,
            directory=local_quote_directory(),
            roster=Path(
                os.getenv("INDICATORLAB_HSI_ROSTER", str(cls.roster))
            ).expanduser(),
            region=os.getenv("AWS_REGION", "us-west-2"),
            table=os.getenv("INDICATORLAB_LIVE_HK_TABLE", "indicatorlab-live-hk"),
            auto_discover=not os.getenv("INDICATORLAB_LIVE_HK_DIR", "").strip(),
        )


class LiveStore:
    """A read-only bridge between the existing collector and the team API contract."""

    def __init__(self, settings: LiveSettings, *, table=None):
        self.settings, self._table = settings, table

    def roster(self) -> tuple[dict[str, str], str | None]:
        """Use the dated operational roster; do not reuse the strict benchmark source."""
        try:
            with self.settings.roster.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            names = {symbol(row["yahoo_ticker"]): row["company_name"] for row in rows}
            if not names or len(names) != len(rows):
                raise ValueError("Invalid roster")
            return names, rows[0].get("as_of")
        except (OSError, KeyError, ValueError) as exc:
            raise LiveDataUnavailable(
                "The configured HK roster is unavailable"
            ) from exc

    def rows(self) -> list[dict]:
        """Read one bounded latest file, or all DynamoDB scan pages using read IAM only."""
        if self.settings.mode == "local":
            directory = (
                local_quote_directory()
                if self.settings.auto_discover
                else self.settings.directory
            )
            path = directory / "latest.json"
            try:
                with path.open("rb") as handle:
                    raw = handle.read(MAX_LOCAL_BYTES + 1)
                if len(raw) > MAX_LOCAL_BYTES:
                    raise ValueError("Latest snapshot exceeds size bound")
                result = json.loads(raw)
                if not isinstance(result, list):
                    raise TypeError("Latest snapshot must be a list")
                return result
            except (OSError, ValueError, TypeError) as exc:
                raise LiveDataUnavailable(
                    "The HK quote snapshot is unavailable"
                ) from exc
        try:
            if self._table is None:
                import boto3
                from botocore.config import Config

                resource = boto3.resource(
                    "dynamodb",
                    region_name=self.settings.region,
                    config=Config(
                        connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}
                    ),
                )
                self._table = resource.Table(self.settings.table)
            rows, request = [], {}
            while True:
                page = self._table.scan(**request)
                rows.extend(page.get("Items", []))
                cursor = page.get("LastEvaluatedKey")
                if not cursor:
                    return rows
                request = {"ExclusiveStartKey": cursor}
        except Exception as exc:
            raise LiveDataUnavailable("The HK quote table is unavailable") from exc

    def snapshot(self, now: datetime | None = None) -> dict:
        """Return quotes, provenance and honest session/freshness metadata."""
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Snapshot clock must be timezone-aware")
        names, roster_as_of = self.roster()
        try:
            state, next_open = session_gate(now)
        except (ValueError, KeyError) as exc:
            raise LiveDataUnavailable(
                "The market calendar does not cover this date"
            ) from exc
        latest, invalid = {}, 0
        for row in self.rows():
            try:
                code = symbol(row["symbol"])
                if code not in names:
                    continue
                if any(
                    isinstance(row[key], bool)
                    for key in ("price", "change_pct", "volume")
                ):
                    raise ValueError("Boolean quote value")
                numeric = {
                    key: float(row[key]) for key in ("price", "change_pct", "volume")
                }
                if (
                    not all(math.isfinite(value) for value in numeric.values())
                    or numeric["price"] <= 0
                    or numeric["volume"] < 0
                ):
                    raise ValueError("Invalid quote value")
                exchange, received = (
                    parse_time(row["ts_exchange"]),
                    parse_time(row["ts_received"]),
                )
                if (
                    max(
                        (exchange - now).total_seconds(),
                        (received - now).total_seconds(),
                    )
                    > FUTURE_TOLERANCE_SECONDS
                ):
                    raise ValueError("Future quote timestamp")
                source = row["source"].strip() if isinstance(row["source"], str) else ""
                if not source:
                    raise ValueError("Missing provider")
                item = {
                    "symbol": code,
                    "name": names[code],
                    **numeric,
                    "ts_exchange": exchange.isoformat(),
                    "ts_received": received.isoformat(),
                    "source": source,
                    "last_trade_age_seconds": max(0, (now - exchange).total_seconds()),
                    "received_age_seconds": max(0, (now - received).total_seconds()),
                }
                previous = latest.get(code)
                if previous is None or (exchange, received) > (
                    parse_time(previous["ts_exchange"]),
                    parse_time(previous["ts_received"]),
                ):
                    latest[code] = item
            except (KeyError, ValueError, TypeError, OverflowError):
                invalid += 1
        quotes = sorted(latest.values(), key=lambda row: row["symbol"])
        as_of = max((row["ts_received"] for row in quotes), default=None)
        age = max((row["received_age_seconds"] for row in quotes), default=None)
        return {
            "market": "hk",
            "currency": "HKD",
            "quotes": quotes,
            "market_open": state == "open",
            "market_state": state,
            "market_time": now.astimezone(HKT).isoformat(),
            "server_time": now.astimezone(UTC).isoformat(),
            "next_open": next_open.astimezone(UTC).isoformat()
            if state != "open"
            else None,
            "as_of": as_of,
            "requested_count": len(names),
            "received_count": len(quotes),
            "missing_symbols": sorted(set(names) - set(latest)),
            "invalid_rows": invalid,
            "roster_as_of": roster_as_of,
            "source_mode": self.settings.mode,
            "is_stale": state == "open" and (age is None or age > STALE_AFTER_SECONDS),
            "stale_after_seconds": STALE_AFTER_SECONDS,
            "instruments": [
                {"symbol": code, "name": name} for code, name in names.items()
            ],
        }
