"""Resilient market-gated quote loop with interchangeable local and AWS sinks."""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import pandas as pd

LOG = logging.getLogger(__name__)
QUOTE_FIELDS = (
    "symbol",
    "price",
    "change_pct",
    "volume",
    "ts_exchange",
    "ts_received",
    "source",
)


class QuoteSource(Protocol):
    """Return valid quote items and isolated per-symbol errors."""

    def fetch(self, symbols: list[str]) -> tuple[list[dict], list[dict]]: ...


class QuoteSink(Protocol):
    """Persist changed quotes and the complete latest view once per minute."""

    def write(self, updates: list[dict], latest: list[dict], now: datetime) -> None: ...


def validate_quote(row: dict, expected: set[str], now: datetime) -> dict:
    """Validate identity, finite numbers and aware timestamps before persisting."""
    item = {key: row[key] for key in QUOTE_FIELDS}
    if item["symbol"] not in expected:
        raise ValueError("Unexpected quote symbol")
    for key in ("price", "change_pct", "volume"):
        item[key] = float(item[key])
        if not math.isfinite(item[key]):
            raise ValueError("Non-finite quote value")
    if item["price"] <= 0 or item["volume"] < 0:
        raise ValueError("Invalid price or volume")
    exchange, received = [
        datetime.fromisoformat(item[key]) for key in ("ts_exchange", "ts_received")
    ]
    if exchange.tzinfo is None or received.tzinfo is None:
        raise ValueError("Quote timestamps must include a timezone")
    if exchange > now + pd.Timedelta(seconds=5) or received > now + pd.Timedelta(
        seconds=5
    ):
        raise ValueError("Future quote timestamp")
    return item


def _minute(now: datetime) -> str:
    return now.astimezone(UTC).strftime("date=%Y-%m-%d/%H%M.parquet")


class LocalSink:
    """Atomically replace a latest JSON file and write complete minute snapshots."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.last_minute: str | None = None

    def write(self, updates: list[dict], latest: list[dict], now: datetime) -> None:
        """Use bounded latest state; growing history is partitioned into minute files."""
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / "latest.json.tmp"
        temporary.write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.directory / "latest.json")
        minute = _minute(now)
        if latest and minute != self.last_minute:
            target = self.directory / "snapshots" / minute
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.with_suffix(".parquet.tmp")
            pd.DataFrame(latest, columns=QUOTE_FIELDS).to_parquet(pending, index=False)
            pending.replace(target)
            self.last_minute = minute


class AwsSink:
    """Upsert latest rows, snapshot all retained rows, and emit a minute age metric."""

    def __init__(
        self,
        market: str,
        table,
        s3,
        cloudwatch,
        bucket: str,
        expected_symbols: set[str] | None = None,
    ):
        self.market, self.table, self.s3, self.cloudwatch, self.bucket = (
            market,
            table,
            s3,
            cloudwatch,
            bucket,
        )
        self.last_snapshot: str | None = None
        self.last_metric: str | None = None
        self.expected_symbols = expected_symbols
        self.first_attempt: datetime | None = None

    def write(self, updates: list[dict], latest: list[dict], now: datetime) -> None:
        """Mark each sink operation complete only after its request succeeds."""
        if self.first_attempt is None:
            self.first_attempt = now
        if updates:
            with self.table.batch_writer(overwrite_by_pkeys=["symbol"]) as batch:
                for row in updates:
                    batch.put_item(
                        Item=json.loads(json.dumps(row), parse_float=Decimal)
                    )
        minute = _minute(now)
        if latest and minute != self.last_snapshot:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=f"raw/live/{self.market}/{minute}",
                Body=pd.DataFrame(latest, columns=QUOTE_FIELDS).to_parquet(index=False),
                ContentType="application/vnd.apache.parquet",
            )
            self.last_snapshot = minute
        if minute != self.last_metric:
            # Oldest receipt exposes partial-universe staleness, not merely a healthy ticker.
            age = max(
                (
                    max(
                        0.0,
                        (
                            now - datetime.fromisoformat(row["ts_received"])
                        ).total_seconds(),
                    )
                    for row in latest
                ),
                default=max(0.0, (now - self.first_attempt).total_seconds()),
            )
            if self.expected_symbols and self.expected_symbols - {
                row["symbol"] for row in latest
            }:
                age = max(age, (now - self.first_attempt).total_seconds())
            self.cloudwatch.put_metric_data(
                Namespace="IndicatorLab",
                MetricData=[
                    {
                        "MetricName": "LastUpdateAgeSeconds",
                        "Dimensions": [{"Name": "Market", "Value": self.market}],
                        "Timestamp": now,
                        "Value": age,
                        "Unit": "Seconds",
                    }
                ],
            )
            self.last_metric = minute


class PollLoop:
    """Keep valid partial polls, retry sink failures, and never query a closed market."""

    def __init__(
        self,
        symbols: list[str],
        source: QuoteSource,
        sink: QuoteSink,
        gate: Callable[[datetime], tuple[str, datetime]],
        interval: float = 5,
    ):
        if not symbols or len(symbols) != len(set(symbols)):
            raise ValueError("A nonempty, distinct symbol list is required")
        if interval < 5:
            raise ValueError("Polling interval must be at least five seconds")
        self.symbols, self.expected = symbols, set(symbols)
        self.source, self.sink, self.gate, self.interval = source, sink, gate, interval
        self.latest: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.failures = 0

    def step(self, now: datetime | None = None) -> float:
        """Perform one scheduled poll; return seconds until the next attempt."""
        injected_clock = now is not None
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("An aware clock is required")
        state, next_open = self.gate(now)
        if state != "open":
            self.failures = 0
            return max(1.0, (next_open - now).total_seconds())
        began = time.monotonic()
        try:
            try:
                rows, errors = self.source.fetch(self.symbols)
            # Retain the latest state when the source itself raises.
            except Exception as exc:  # noqa: BLE001
                rows, errors = [], [
                    {"error": "source failed", "kind": type(exc).__name__}
                ]
            for error in errors:
                LOG.warning("quote_error %s", json.dumps(error))
            accepted = []
            received_now = now if injected_clock else datetime.now(UTC)
            for row in rows:
                try:
                    item = validate_quote(row, self.expected, received_now)
                    old = self.latest.get(item["symbol"])
                    if old and datetime.fromisoformat(
                        item["ts_exchange"]
                    ) < datetime.fromisoformat(old["ts_exchange"]):
                        continue
                    self.latest[item["symbol"]] = item
                    self.pending[item["symbol"]] = item
                    accepted.append(item)
                except (KeyError, ValueError, TypeError):
                    LOG.warning("invalid_quote symbol=%s", row.get("symbol", "unknown"))
            # Persist even when the current poll is empty, so retained state is snapshotted.
            self.sink.write(
                list(self.pending.values()), list(self.latest.values()), received_now
            )
            self.pending.clear()
            ages = [
                (
                    datetime.fromisoformat(row["ts_received"])
                    - datetime.fromisoformat(row["ts_exchange"])
                ).total_seconds()
                for row in accepted
            ]
            LOG.info(
                "poll %s",
                json.dumps(
                    {
                        "updated": len(accepted),
                        "requested": len(self.symbols),
                        "elapsed_seconds": time.monotonic() - began,
                        "last_trade_age_seconds": ages,
                    }
                ),
            )
            if not accepted:
                raise RuntimeError("No valid quotes in poll")
            self.failures = 0
            return max(0.0, self.interval - (time.monotonic() - began))
        # A feed/sink outage must not kill the long-running service.
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            delay = min(30, 2 ** min(self.failures - 1, 5))
            LOG.error("poll_failed type=%s retry_seconds=%s", type(exc).__name__, delay)
            return delay

    def run(self, should_stop: Callable[[], bool] = lambda: False) -> None:
        """Run until stopped; long closed-session waits remain interruptible."""
        while not should_stop():
            remaining = self.step()
            while remaining > 0 and not should_stop():
                delay = min(remaining, 1.0)
                time.sleep(delay)
                remaining -= delay
