"""On-demand HK quotes for the dashboard contract, independent of its frontend.

The default HSI reader uses DynamoDB GetItem, not a table scan. A local reader
can be injected explicitly for laptops; it never silently replaces AWS data.
"""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests

from src.hk.live import (
    FIELD_CHANGE,
    FIELD_PRICE,
    FIELD_TIME,
    FIELD_VOLUME,
    HKT,
    QUOTE_URL,
    parse_quotes,
)
from src.hk.live_paths import FUTURE_TOLERANCE_SECONDS, local_quote_directory
from src.live.hk import session_gate
from src.markets.errors import UnknownTicker
from src.markets.hk_symbols import canonical_hk, tencent_code

ROOT = Path(__file__).resolve().parents[2]
CACHE_SECONDS = 5
MAX_RESPONSE_BYTES = 200_000
MAX_LOCAL_BYTES = 2_000_000


class QuoteUnavailable(RuntimeError):
    """A configured store or quote provider cannot supply a valid observation."""


def _time(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value))
    if stamp.tzinfo is None:
        raise ValueError("Quote timestamps must include a timezone")
    return stamp.astimezone(UTC)


def _validate(row: dict, symbol: str, now: datetime) -> dict:
    value = {
        key: row[key]
        for key in (
            "symbol",
            "price",
            "change_pct",
            "volume",
            "ts_exchange",
            "ts_received",
            "source",
        )
    }
    if canonical_hk(value["symbol"]) != symbol:
        raise ValueError("Provider returned another stock")
    value["symbol"] = symbol
    for key in ("price", "change_pct", "volume"):
        if isinstance(value[key], bool):
            raise TypeError("Boolean quote value")
        value[key] = float(value[key])
        if not math.isfinite(value[key]):
            raise ValueError("Non-finite quote value")
    if value["price"] <= 0 or value["volume"] < 0:
        raise ValueError("Invalid price or volume")
    exchange, received = _time(value["ts_exchange"]), _time(value["ts_received"])
    if (
        max((exchange - now).total_seconds(), (received - now).total_seconds())
        > FUTURE_TOLERANCE_SECONDS
    ):
        raise ValueError("Future quote timestamp")
    value["ts_exchange"], value["ts_received"] = (
        exchange.isoformat(),
        received.isoformat(),
    )
    if not isinstance(value["source"], str) or not value["source"].strip():
        raise ValueError("Missing quote source")
    return value


def parse_tencent_quote(text: str, symbol: str, received: datetime) -> dict:
    """Reuse the collector parser, extending its field map for five-digit counters.

    The frozen research collector accepts four-digit HKD codes only. Five-digit
    counters use its same field positions and validation without changing it.
    """
    symbol = canonical_hk(symbol)
    if len(symbol.removesuffix(".HK")) == 4:
        rows, _ = parse_quotes(text, received)
        row = next((row for row in rows if row["symbol"] == symbol), None)
        if row is None:
            raise QuoteUnavailable("Tencent returned no valid quote for this stock")
        return _validate(row, symbol, received)
    expected = "v_r_" + tencent_code(symbol)
    for line in text.splitlines():
        if not line.startswith(expected + "="):
            continue
        try:
            fields = line.split('"', 2)[1].split("~")
            stamp = datetime.strptime(fields[FIELD_TIME], "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=HKT
            )
            return _validate(
                {
                    "symbol": canonical_hk(fields[2]),
                    "price": fields[FIELD_PRICE],
                    "change_pct": fields[FIELD_CHANGE],
                    "volume": fields[FIELD_VOLUME],
                    "ts_exchange": stamp.isoformat(),
                    "ts_received": received.isoformat(),
                    "source": "tencent",
                },
                symbol,
                received,
            )
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise QuoteUnavailable("Tencent returned an invalid quote") from exc
    raise QuoteUnavailable("Tencent returned no valid quote for this stock")


def local_hsi_reader(symbol: str) -> dict | None:
    """Read the existing bounded local snapshot; opt-in replacement for DynamoDB."""
    try:
        with (local_quote_directory() / "latest.json").open("rb") as handle:
            raw = handle.read(MAX_LOCAL_BYTES + 1)
        if len(raw) > MAX_LOCAL_BYTES:
            raise ValueError("Latest snapshot exceeds size bound")
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise TypeError("Latest snapshot must be a list")
        for row in rows:
            try:
                if canonical_hk(row["symbol"]) == symbol:
                    return row
            except (UnknownTicker, KeyError, TypeError):
                continue
        return None
    except (OSError, ValueError, TypeError) as exc:
        raise QuoteUnavailable("The local HK quote snapshot is unavailable") from exc


class QuoteService:
    """Read HSI GetItem rows or Tencent quotes, caching observations for five seconds.

    Args:
        hsi_reader: Explicit reader override for tests or local operation.
        symbols: Override the dated operational roster, primarily for tests.
        session: HTTP client for Tencent; no request is made during construction.
        clock: Aware observation clock.
        timer: Monotonic clock for cache expiry.
    """

    def __init__(
        self,
        *,
        hsi_reader=None,
        hsi_store=None,
        symbols=None,
        session=None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        timer: Callable[[], float] = time.monotonic,
    ):
        if symbols is None:
            path = Path(
                os.getenv(
                    "INDICATORLAB_HSI_ROSTER",
                    str(ROOT / "config/hsi_constituents_2026-11-04.csv"),
                )
            )
            with path.open(encoding="utf-8-sig", newline="") as handle:
                symbols = [row["yahoo_ticker"] for row in csv.DictReader(handle)]
        self.symbols = {canonical_hk(value) for value in symbols}
        self.reader = hsi_reader or self._dynamodb
        self.hsi_store = hsi_store or (
            "local" if hsi_reader is local_hsi_reader else "dynamodb"
        )
        self.session, self.clock, self.timer = (
            session or requests.Session(),
            clock,
            timer,
        )
        self.cache: dict[str, tuple[float, dict, str]] = {}
        self.table = None
        self.lock = threading.Lock()

    def _dynamodb(self, symbol: str) -> dict | None:
        try:
            if self.table is None:
                import boto3
                from botocore.config import Config

                resource = boto3.resource(
                    "dynamodb",
                    region_name=os.getenv("AWS_REGION", "us-west-2"),
                    config=Config(
                        connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}
                    ),
                )
                self.table = resource.Table(
                    os.getenv("INDICATORLAB_LIVE_HK_TABLE", "indicatorlab-live-hk")
                )
            return self.table.get_item(Key={"symbol": symbol}, ConsistentRead=True).get(
                "Item"
            )
        except Exception as exc:
            raise QuoteUnavailable("The HK quote table is unavailable") from exc

    def _tencent(self, symbol: str) -> dict:
        try:
            response = self.session.get(
                QUOTE_URL + "r_" + tencent_code(symbol), timeout=4
            )
            response.raise_for_status()
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise QuoteUnavailable("Tencent response exceeds size bound")
            response.encoding = "gbk"
            # Explicit provider not-found responses are unknown symbols; a timeout
            # or malformed response remains an outage, never an unknown ticker.
            if response.text.strip().startswith("v_pv_none_match="):
                raise UnknownTicker(f"No Tencent quote for {symbol}")
            return parse_tencent_quote(response.text, symbol, self.clock())
        except requests.RequestException as exc:
            raise QuoteUnavailable("Tencent quotes are unavailable") from exc

    def get(self, raw: str) -> dict:
        """Return a quote with exchange-age and current session labels.

        Session and delay are recomputed even for cached observations, so a quote
        cached before noon cannot remain labelled live through the lunch break.
        """
        symbol = canonical_hk(raw)
        with self.lock:
            cached = self.cache.get(symbol)
            if cached and self.timer() - cached[0] < CACHE_SECONDS:
                _, row, store = cached
            else:
                if symbol in self.symbols:
                    row = self.reader(symbol)
                    store = self.hsi_store
                    if row is None:
                        raise QuoteUnavailable(
                            "No stored quote is available for this HSI stock"
                        )
                else:
                    row, store = self._tencent(symbol), "tencent"
                try:
                    row = _validate(row, symbol, self.clock())
                except (ValueError, KeyError, TypeError) as exc:
                    raise QuoteUnavailable("The quote observation is invalid") from exc
                self.cache[symbol] = (self.timer(), row, store)
                if len(self.cache) > 1024:
                    oldest = min(self.cache, key=lambda key: self.cache[key][0])
                    del self.cache[oldest]
        result = copy.deepcopy(row)
        now = self.clock()
        state, next_open = session_gate(now)
        delay = max(0.0, (now - _time(row["ts_exchange"])).total_seconds())
        label = "live" if delay < 60 else f"delayed ~{max(1, round(delay / 60))} min"
        if state == "lunch":
            label = "lunch break"
        elif state != "open":
            label = "market closed"
        # HKEX's five-digit 8xxxx counters are RMB, not HKD. Do not send them
        # through the HKD cost estimator. Other counter currencies stay unknown
        # unless provider metadata identifies them.
        currency = (
            "CNY"
            if symbol.startswith("8") and len(symbol) == 8
            else "HKD"
            if symbol in self.symbols
            else None
        )
        result.update(
            {
                "market": "hk",
                "currency": currency,
                "market_open": state == "open",
                "market_state": state,
                "next_open": next_open.isoformat(),
                "label": label,
                "delay_seconds": delay,
                "store": store,
                "cache_seconds": CACHE_SECONDS,
            }
        )
        return result


_services: dict[str, QuoteService] = {}
_service_lock = threading.Lock()


def get_quote(symbol: str, market: str) -> dict:
    """Shared dispatch entry point; this contribution implements the HK branch.

    The India/US providers belong to the other owners. Unsupported branches fail
    explicitly until those implementations are composed at this entry point.
    """
    if market.lower() != "hk":
        raise NotImplementedError(
            "This contribution supplies HK quotes; compose the other market providers here"
        )
    with _service_lock:
        if "hk" not in _services:
            _services["hk"] = QuoteService()
    return _services["hk"].get(symbol)
