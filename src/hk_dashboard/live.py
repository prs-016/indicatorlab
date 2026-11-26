"""Read the existing HK quote service or bounded snapshots; never start a collector."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src.hk_dashboard.paths import canonical, names, quote_directories

MAX_BYTES = 2_000_000
API_TIMEOUT = 4


def stamp(value) -> datetime:
    """Parse an aware provider/receipt timestamp without depending on host timezone."""
    result = datetime.fromisoformat(str(value))
    if result.tzinfo is None:
        raise ValueError("Quote timestamps require a timezone")
    return result.astimezone(UTC)


def session(now: datetime) -> tuple[str, str | None]:
    """Use XHKG continuous sessions, lunch, holidays and actual half-day schedules."""
    import exchange_calendars as xcals

    cal = xcals.get_calendar("XHKG", start="2015-01-01", end="2027-12-31")
    day = pd.Timestamp(now.astimezone(ZoneInfo("Asia/Hong_Kong")).date())
    clock = pd.Timestamp(now)
    schedule = cal.schedule.loc[day : day + pd.Timedelta(days=20)]
    if day in schedule.index:
        row = schedule.loc[day]
        if row["open"] <= clock < row["close"]:
            if (
                pd.notna(row["break_start"])
                and row["break_start"] <= clock < row["break_end"]
            ):
                return "lunch", row["break_end"].isoformat()
            return "open", now.isoformat()
    future = [row["open"] for _, row in schedule.iterrows() if row["open"] > clock]
    return "closed", future[0].isoformat() if future else None


def valid_quote(row: dict, now: datetime, allowed: set) -> dict:
    """Keep real finite observations; malformed symbols cannot hide valid rows."""
    code = canonical(row["symbol"])
    if code not in allowed:
        raise ValueError("Outside the configured HSI snapshot")
    result = {"symbol": code, "source": row["source"]}
    for key in ["price", "change_pct", "volume"]:
        if isinstance(row[key], bool):
            raise TypeError("Boolean quote value")
        result[key] = float(row[key])
        if not math.isfinite(result[key]):
            raise ValueError("Non-finite quote value")
    if result["price"] <= 0 or result["volume"] < 0:
        raise ValueError("Invalid quote value")
    for key in ["ts_exchange", "ts_received"]:
        value = stamp(row[key])
        if value > now + timedelta(seconds=5):
            raise ValueError("Future quote timestamp")
        result[key] = value.isoformat()
    if not isinstance(result["source"], str) or not result["source"]:
        raise ValueError("Missing quote source")
    return result


class LiveSource:
    """Share the already-running HK backend, with an explicit local-file fallback.

    Args:
        base_url: Operator-controlled backend origin; never read from browser input.
        http: Injectable requests client.
        clock: Aware current time provider.
        timer: Monotonic cache timer.
    """

    def __init__(
        self,
        *,
        base_url=None,
        http=None,
        clock=lambda: datetime.now(UTC),
        timer=time.monotonic,
    ):
        self.base = (
            base_url
            if base_url is not None
            else os.getenv("INDICATORLAB_HK_API_BASE_URL", "http://127.0.0.1:8765")
        ).rstrip("/")
        if self.base:
            parsed = urlparse(self.base)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "HK API base must be a plain HTTP(S) origin or base path"
                )
        self.http = http or requests.Session()
        self.clock, self.timer = clock, timer
        self.cached = None
        self.lock = threading.Lock()

    def _get(self, params=None):
        if not self.base:
            raise RuntimeError("No HK API is configured")
        response = self.http.get(
            self.base + "/live/hk", params=params, timeout=API_TIMEOUT
        )
        response.raise_for_status()
        if len(response.content) > MAX_BYTES:
            raise ValueError("Oversized quote response")
        result = response.json()
        if not isinstance(result, dict):
            raise TypeError("Quote response must be an object")
        return result

    def snapshot(self) -> dict:
        """Return retained prices with distinct exchange age, receipt age and session."""
        roster = names()
        allowed = set(roster)
        with self.lock:
            if self.cached and self.timer() - self.cached[0] < 5:
                rows, store = self.cached[1:]
            else:
                rows = None
                store = None
                try:
                    data = self._get()
                    if data.get("market") != "hk" or not isinstance(
                        data.get("quotes"), list
                    ):
                        raise ValueError("Unexpected quote API contract")
                    rows, store = data["quotes"], "hk_api"
                except (requests.RequestException, ValueError, TypeError, RuntimeError):
                    available = []
                    for directory in quote_directories():
                        try:
                            with (directory / "latest.json").open("rb") as handle:
                                raw = handle.read(MAX_BYTES + 1)
                            if len(raw) > MAX_BYTES:
                                continue
                            candidate = json.loads(raw)
                            if not isinstance(candidate, list):
                                continue
                            valid = []
                            for row in candidate:
                                try:
                                    valid.append(
                                        valid_quote(row, self.clock(), allowed)
                                    )
                                except (ValueError, KeyError, TypeError):
                                    continue
                            if valid:
                                available.append(
                                    (max(row["ts_received"] for row in valid), valid)
                                )
                        except (OSError, ValueError, TypeError):
                            continue
                    if available:
                        rows, store = (
                            max(available, key=lambda item: item[0])[1],
                            "local_snapshot",
                        )
                if rows is None:
                    rows = []
                self.cached = (self.timer(), rows, store)
        now = self.clock()
        latest = {}
        bad = 0
        for row in rows:
            try:
                item = valid_quote(row, now, allowed)
                previous = latest.get(item["symbol"])
                if not previous or stamp(item["ts_exchange"]) > stamp(
                    previous["ts_exchange"]
                ):
                    latest[item["symbol"]] = item
            except (KeyError, ValueError, TypeError):
                bad += 1
        try:
            state, next_open = session(now)
        except (ValueError, KeyError, IndexError):
            state, next_open = "unknown", None
        for code, row in latest.items():
            row["name"] = roster[code]["short_name"]
            row["currency"] = "HKD"
            row["delay_seconds"] = max(
                0, (now - stamp(row["ts_exchange"])).total_seconds()
            )
            row["receipt_age_seconds"] = max(
                0, (now - stamp(row["ts_received"])).total_seconds()
            )
            row["label"] = (
                "lunch break"
                if state == "lunch"
                else "market closed"
                if state == "closed"
                else "live"
                if row["delay_seconds"] < 60
                else f"delayed ~{max(1, round(row['delay_seconds'] / 60))} min"
            )
        ordered = sorted(latest.values(), key=lambda item: item["symbol"])
        newest = max((row["ts_received"] for row in ordered), default=None)
        oldest = max((row["receipt_age_seconds"] for row in ordered), default=None)
        return {
            "market": "hk",
            "quotes": ordered,
            "received_count": len(ordered),
            "requested_count": len(roster),
            "missing_symbols": sorted(set(roster) - set(latest)),
            "invalid_rows": bad,
            "as_of": newest,
            "market_state": state,
            "market_open": state == "open",
            "next_open": next_open,
            "store": store,
            "is_stale": not ordered
            or (state == "open" and oldest is not None and oldest > 60),
            "roster_as_of": "2026-11-04",
            "poll_seconds": 5,
        }

    def estimate(self, params: dict) -> dict:
        """Proxy the existing cost calculator without copying a restricted lot table."""
        allowed = {
            "shares",
            "hkd_per_usd",
            "commission_hkd",
            "platform_fee_hkd",
            "fx_spread_bps",
            "fx_fee_usd",
            "transfer_fee_usd",
            "settlement_pass_through",
        }
        code = canonical(params.get("ticker") or params.get("symbol", ""))
        if code not in names():
            raise ValueError("Choose a configured HK stock")
        query = {
            key: params[key] for key in allowed if key in params and params[key] != ""
        }
        query.update(symbol=code, side="buy")
        if "shares" not in query:
            raise ValueError("Requested shares are required")
        result = self._get(query)
        if canonical(
            result.get("quote", {}).get("symbol", "")
        ) != code or not isinstance(result.get("estimate"), dict):
            raise ValueError("Unexpected cost estimate response")
        return result
