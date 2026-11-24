"""Local India quote service with injected providers, clocks and storage clients.

No provider, credentials, AWS session or resources are discovered on import.
Only explicitly supplied adapters can perform I/O. Operational quotes must not
be fed into historical research without a separately approved research workflow.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd

LOGGER = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
REGION = "us-east-2"
TABLE = "indicatorlab-live-india"
BUCKET = "indicatorlab-data"
COLUMNS = (
    "symbol",
    "price",
    "change_pct",
    "volume",
    "ts_exchange",
    "ts_received",
    "source",
)
DYNAMO_BATCH_SIZE = 25
MAX_SYMBOLS = 100
MAX_VOLUME = 2**63 - 1  # Quantity must fit the Parquet int64 representation.


class QuoteProvider(Protocol):
    """Batch provider contract; implement only for a separately authorized source.

    fetch receives normalized .NS symbols and returns a mapping of symbol to
    normalized quote fields (COLUMNS without ts_received), or an Exception for
    that symbol. Missing symbols are explicit failures. max_batch_size must
    reflect the provider's permitted batch limit. Adapters own bounded request
    timeouts and broker-specific timezone, quantity and percentage conversion.
    """

    name: str
    max_batch_size: int

    def fetch(self, symbols: Sequence[str]) -> Mapping[str, Mapping | Exception]:
        """Return independent quotes/errors; PermissionError denies further access."""
        ...


class CalendarCoverageError(ValueError):
    """Raised when no reviewed session/closure entry covers the local date."""


class SessionClosed(ValueError):
    """A retry would occur outside the permitted exchange session."""


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry settings; delays are exponential, capped in seconds."""

    attempts: int = 3
    base_seconds: float = 0.5
    cap_seconds: float = 4.0

    def __post_init__(self):
        if (
            isinstance(self.attempts, bool)
            or not isinstance(self.attempts, int)
            or self.attempts < 1
            or not math.isfinite(self.base_seconds)
            or not math.isfinite(self.cap_seconds)
            or self.base_seconds < 0
            or self.cap_seconds < self.base_seconds
        ):
            raise ValueError("Invalid retry policy")


DEFAULT_RETRY_POLICY = RetryPolicy()


def _retry(operation, policy, sleep):
    for attempt in range(policy.attempts):
        try:
            return operation()
        except (PermissionError, ValueError, TypeError):
            raise
        except Exception:
            if attempt + 1 == policy.attempts:
                raise
            sleep(min(policy.cap_seconds, policy.base_seconds * 2**attempt))


def _aware(value):
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if (
        not isinstance(stamp, datetime)
        or stamp.tzinfo is None
        or stamp.utcoffset() is None
    ):
        raise ValueError("Timezone-aware timestamp required")
    return stamp.astimezone(UTC)


def _symbols(values):
    symbols = tuple(values)
    if (
        not 1 <= len(symbols) <= MAX_SYMBOLS
        or len(set(symbols)) != len(symbols)
        or not all(
            isinstance(s, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9&-]*\.NS", s)
            for s in symbols
        )
    ):
        raise ValueError("Require 1–100 unique normalized NSE equity symbols")
    return symbols


def load_nifty100_symbols(path: str | Path) -> tuple[str, ...]:
    """Read a local official-style constituent CSV; return exactly 100 .NS names.

    Parameters: path is a separately reviewed local CSV with Symbol and Series.
    No retrieval, current-membership discovery, fallback or config activation occurs.
    Duplicate symbols, non-EQ entries and incorrect constituent counts are errors.
    """
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != MAX_SYMBOLS or any(r.get("Series") != "EQ" for r in rows):
        raise ValueError("Require exactly 100 official-style EQ constituent rows")
    return _symbols([r.get("Symbol", "") + ".NS" for r in rows])


class SessionCalendar:
    """Explicit India date/session map; holidays/weekends use empty interval lists.

    Parameters: sessions maps YYYY-MM-DD to local HH:MM opening/closing pairs;
    source identifies the reviewed calendar evidence. Every operational date must
    have an explicit entry. No weekday, holiday or special-session dates are inferred.
    """

    def __init__(self, sessions: Mapping, *, source: str):
        if not source or not sessions:
            raise ValueError("Calendar evidence and dated entries required")
        self.source = source
        self.sessions = {}
        for day, intervals in sessions.items():
            date = datetime.strptime(day, "%Y-%m-%d").date()
            if date.isoformat() != day:
                raise ValueError("Canonical calendar dates required")
            parsed = []
            for opening, closing in intervals:
                start = datetime.strptime(opening, "%H:%M").time()
                end = datetime.strptime(closing, "%H:%M").time()
                if start >= end or (parsed and start < parsed[-1][1]):
                    raise ValueError("Invalid/overlapping session intervals")
                parsed.append((start, end))
            self.sessions[date] = tuple(parsed)

    @classmethod
    def from_file(cls, path: str | Path) -> SessionCalendar:
        """Load a local calendar JSON containing source, timezone and sessions."""
        data = json.loads(Path(path).read_text())
        if data.get("timezone") != "Asia/Kolkata":
            raise ValueError("India calendar must declare Asia/Kolkata")
        return cls(data["sessions"], source=data["source"])

    def is_open(self, now: datetime) -> bool:
        """Return whether aware now lies in an explicit half-open local session.

        Unknown dates raise CalendarCoverageError, preventing provider polling.
        """
        local = _aware(now).astimezone(IST)
        if local.date() not in self.sessions:
            raise CalendarCoverageError("No reviewed calendar coverage for date")
        return any(
            start <= local.time() < end for start, end in self.sessions[local.date()]
        )


class MockQuoteProvider:
    """Offline fixture provider; never opens sockets or fabricates missing quotes.

    Parameters: quotes maps symbols to six normalized synthetic fields; errors is
    an optional symbol-to-error map. Fixtures must identify source as mock_fixture.
    """

    name = "mock_fixture"
    max_batch_size = MAX_SYMBOLS

    def __init__(self, quotes: Mapping, errors: Mapping | None = None):
        self.quotes = dict(quotes)
        self.errors = dict(errors or {})
        self.calls = []

    @classmethod
    def from_file(cls, path: str | Path) -> MockQuoteProvider:
        """Read a local synthetic JSON with quotes and optional errors mappings."""
        data = json.loads(Path(path).read_text())
        return cls(data["quotes"], data.get("errors"))

    def fetch(self, symbols: Sequence[str]) -> dict:
        """Return copied fixture rows or per-symbol synthetic errors, without I/O."""
        self.calls.append(tuple(symbols))
        return {
            s: (
                ValueError("Synthetic unavailable quote")
                if s in self.errors
                else dict(self.quotes[s])
            )
            for s in symbols
            if s in self.quotes or s in self.errors
        }


def normalize_quote(row: Mapping, symbol: str, received: datetime, source: str) -> dict:
    """Validate normalized provider fields and stamp receipt time in UTC.

    Parameters identify the requested symbol, actual receipt time and provider.
    Returns exactly the seven official fields. Missing/invalid values are errors;
    exchange time is never replaced with receipt time or inferred from local time.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Provider source must be a nonempty string")
    if (
        not isinstance(row, Mapping)
        or row.get("symbol") != symbol
        or row.get("source") != source
    ):
        raise ValueError("Wrong quote identity/source")
    numbers = {}
    for field in ("price", "change_pct"):
        value = row[field]
        if isinstance(value, bool):
            raise TypeError("Boolean is not a quote number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite quote number")
        numbers[field] = number
    try:
        volume = Decimal(str(row["volume"]))
        valid_volume = (
            volume.is_finite()
            and 0 <= volume <= MAX_VOLUME
            and volume == volume.to_integral_value()
        )
    except InvalidOperation as exc:
        raise ValueError("Invalid quantity") from exc
    if numbers["price"] <= 0 or isinstance(row["volume"], bool) or not valid_volume:
        raise ValueError("Invalid price/quantity")
    receipt = _aware(received)
    exchange = _aware(row["ts_exchange"])
    if exchange > receipt:
        raise ValueError("Exchange timestamp is after receipt")
    return {
        "symbol": symbol,
        "price": numbers["price"],
        "change_pct": numbers["change_pct"],
        "volume": int(volume),
        "ts_exchange": exchange.isoformat(),
        "ts_received": receipt.isoformat(),
        "source": source,
    }


def _region(client, region):
    if getattr(getattr(client, "meta", None), "region_name", None) != region:
        raise ValueError(f"Explicit {region} storage client required")


class DynamoLatestStore:
    """Latest-record sink using an injected low-level DynamoDB client.

    Parameters: client must target the selected Region; table defaults to the official name.
    Bounded retries resend only unprocessed items. No boto3 session is created.
    """

    def __init__(
        self,
        client,
        *,
        table=TABLE,
        region=REGION,
        retry=DEFAULT_RETRY_POLICY,
        sleep=time.sleep,
    ):
        _region(client, region)
        self.client, self.table, self.retry, self.sleep = client, table, retry, sleep

    def write(self, quotes: Sequence[Mapping]) -> None:
        """Overwrite latest quotes in groups of at most 25; raise on exhaustion."""
        for offset in range(0, len(quotes), DYNAMO_BATCH_SIZE):
            pending = [
                {
                    "PutRequest": {
                        "Item": {
                            k: {
                                (
                                    "N"
                                    if k in ("price", "change_pct", "volume")
                                    else "S"
                                ): str(q[k])
                            }
                            for k in COLUMNS
                        }
                    }
                }
                for q in quotes[offset : offset + DYNAMO_BATCH_SIZE]
            ]

            def send():
                nonlocal pending
                response = self.client.batch_write_item(
                    RequestItems={self.table: pending}
                )
                unprocessed = response.get("UnprocessedItems", {})
                remaining = unprocessed.get(self.table, [])
                if set(unprocessed) - {self.table} or any(
                    item not in pending for item in remaining
                ):
                    raise ValueError("Unexpected unprocessed write items")
                pending = remaining
                if pending:
                    raise RuntimeError("Unprocessed writes remain")

            _retry(send, self.retry, self.sleep)


class S3MinuteStore:
    """Parquet snapshot sink with an injected regional S3 client.

    Parameters: bucket defaults to indicatorlab-data; retry/sleep bound write
    retries. Minute partitions use UTC receipt time. No client/resources are created.
    """

    def __init__(
        self,
        client,
        *,
        bucket=BUCKET,
        region=REGION,
        retry=DEFAULT_RETRY_POLICY,
        sleep=time.sleep,
    ):
        _region(client, region)
        self.client, self.bucket, self.retry, self.sleep = client, bucket, retry, sleep

    def write(self, minute: datetime, quotes: Sequence[Mapping]) -> None:
        """Write last successful quote per symbol observed in this UTC minute."""
        minute = _aware(minute).replace(second=0, microsecond=0)
        if not quotes:
            return
        buffer = BytesIO()
        pd.DataFrame(quotes, columns=COLUMNS).to_parquet(
            buffer, engine="pyarrow", index=False
        )
        key = f"raw/live/india/date={minute:%Y-%m-%d}/{minute:%H%M}.parquet"
        body = buffer.getvalue()
        _retry(
            lambda: self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="application/vnd.apache.parquet",
            ),
            self.retry,
            self.sleep,
        )


class IndiaLiveService:
    """Sequential local polling loop; provider and both stores are explicit inputs.

    Parameters: symbols is a reviewed roster, calendar supplies explicit sessions,
    and stores implement write. A 60-second interval requires fallback_authorized.
    clock/monotonic/sleep are injectable for offline tests. No background thread,
    scheduler, broker or AWS connection starts until run/step is explicitly called.
    """

    def __init__(
        self,
        symbols,
        provider: QuoteProvider,
        calendar: SessionCalendar,
        latest_store,
        snapshot_store,
        *,
        poll_interval_seconds=5,
        fallback_authorized=False,
        retry=DEFAULT_RETRY_POLICY,
        clock=lambda: datetime.now(UTC),
        monotonic=time.monotonic,
        sleep=time.sleep,
        logger=LOGGER,
    ):
        self.symbols = _symbols(symbols)
        if poll_interval_seconds not in (5, 60) or (
            poll_interval_seconds == 60
            and not (fallback_authorized or provider.name == "yahoo")
        ):
            raise ValueError(
                "Use five seconds or an explicitly authorized 60-second fallback"
            )
        if (
            not isinstance(provider.max_batch_size, int)
            or isinstance(provider.max_batch_size, bool)
            or not 1 <= provider.max_batch_size <= MAX_SYMBOLS
            or not isinstance(provider.name, str)
            or not provider.name.strip()
        ):
            raise ValueError("Provider identity/permitted batch size required")
        self.provider, self.calendar = provider, calendar
        self.latest_store, self.snapshot_store = latest_store, snapshot_store
        self.interval, self.retry = poll_interval_seconds, retry
        self.clock, self.monotonic, self.sleep, self.log = (
            clock,
            monotonic,
            sleep,
            logger,
        )
        self._minutes = {}
        self._access_blocked = False

    def flush(self, *, force=False) -> bool:
        """Flush completed minutes, or partial minutes on graceful stop.

        Failed snapshots remain in memory; polling pauses until they are saved.
        No empty/stale-filled snapshots are generated. Returns False on write error.
        """
        now = _aware(self.clock()).replace(second=0, microsecond=0)
        for minute in sorted(self._minutes):
            if not force and minute >= now:
                continue
            try:
                self.snapshot_store.write(minute, list(self._minutes[minute].values()))
            except Exception as exc:  # noqa: BLE001
                self.log.error(
                    "india_live_snapshot_error",
                    extra={"error_type": type(exc).__name__},
                )
                return False
            del self._minutes[minute]
        return True

    def _write_latest(self, quotes) -> bool:
        try:
            self.latest_store.write(quotes)
        except Exception as exc:  # noqa: BLE001
            self.log.error(
                "india_live_latest_error",
                extra={"error_type": type(exc).__name__},
            )
            return False
        return True

    def step(self) -> list[dict]:
        """Run one gated poll, isolate bad symbols, write latests and log latency.

        Returns valid quotes only. Unknown calendar dates, denied provider access
        or snapshot backpressure skip acquisition; storage errors are logged.
        """
        started = self.monotonic()
        accepted = []
        pending = []
        latest_ok = True
        outcome = "ok"
        try:
            if not self.flush():
                outcome = "snapshot_backpressure"
                return accepted
            if not self.calendar.is_open(self.clock()):
                outcome = "closed"
                return accepted
            if self._access_blocked:
                outcome = "provider_access_blocked"
                return accepted
            batch_size = self.provider.max_batch_size
            for offset in range(0, len(self.symbols), batch_size):
                if not self.flush():
                    outcome = "snapshot_backpressure"
                    break
                batch = self.symbols[offset : offset + batch_size]

                def fetch(batch=batch):
                    if not self.calendar.is_open(self.clock()):
                        raise SessionClosed("Session closed before request/retry")
                    return self.provider.fetch(batch)

                try:
                    response = _retry(fetch, self.retry, self.sleep)
                    if not isinstance(response, Mapping) or set(response) - set(batch):
                        raise ValueError("Unexpected provider response symbols")
                except PermissionError:
                    self._access_blocked = True
                    outcome = "provider_access_blocked"
                    break
                except SessionClosed:
                    outcome = "closed"
                    break
                except Exception as exc:  # noqa: BLE001
                    self.log.warning(
                        "india_live_batch_error",
                        extra={"error_type": type(exc).__name__},
                    )
                    outcome = "partial"
                    continue
                received = _aware(self.clock())
                for symbol in batch:
                    try:
                        quote = normalize_quote(
                            response[symbol], symbol, received, self.provider.name
                        )
                    except (ValueError, TypeError, KeyError, OverflowError) as exc:
                        self.log.warning(
                            "india_live_symbol_error",
                            extra={"symbol": symbol, "error_type": type(exc).__name__},
                        )
                        outcome = "partial"
                        continue
                    accepted.append(quote)
                    pending.append(quote)
                    minute = received.replace(second=0, microsecond=0)
                    self._minutes.setdefault(minute, {})[symbol] = quote
                    # Persist completed Yahoo batches during long single-symbol sweeps.
                    if (
                        self.provider.name == "yahoo"
                        and len(pending) == DYNAMO_BATCH_SIZE
                    ):
                        latest_ok = self._write_latest(pending) and latest_ok
                        pending = []
            if pending:
                latest_ok = self._write_latest(pending) and latest_ok
            if not latest_ok:
                outcome = "latest_write_failed"
            if not self.flush():
                outcome = "snapshot_backpressure"
            return accepted
        except CalendarCoverageError:
            outcome = "calendar_uncovered"
            return accepted
        finally:
            latency = max(0.0, self.monotonic() - started)
            self.log.info(
                "india_live_poll source=%s outcome=%s latency_seconds=%.6f quotes=%d",
                self.provider.name,
                outcome,
                latency,
                len(accepted),
                extra={
                    "outcome": outcome,
                    "quotes_received": len(accepted),
                    "poll_latency_seconds": latency,
                    "source": self.provider.name,
                    "calendar_source": self.calendar.source,
                    "max_exchange_age_seconds": max(
                        (
                            (
                                _aware(q["ts_received"]) - _aware(q["ts_exchange"])
                            ).total_seconds()
                            for q in accepted
                        ),
                        default=None,
                    ),
                },
            )

    def run(self, *, stop_event=None, max_cycles=None) -> None:
        """Run sequentially until stopped; flush the final partial minute on exit.

        Parameters: optional stop_event supports interruptible waits; max_cycles
        bounds offline demonstrations. Slow polls never overlap or create a backlog.
        """
        cycles = 0
        try:
            while (max_cycles is None or cycles < max_cycles) and not (
                stop_event is not None and stop_event.is_set()
            ):
                start = self.monotonic()
                self.step()
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                delay = max(0.0, self.interval - (self.monotonic() - start))
                if stop_event is not None:
                    stop_event.wait(delay)
                else:
                    self.sleep(delay)
        finally:
            if not self.flush(force=True):
                self.log.error("india_live_shutdown_unsaved_snapshot")
