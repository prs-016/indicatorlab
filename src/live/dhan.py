"""Explicitly activated Dhan v2 bulk quotes; no credential discovery on import."""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock

import requests

from src.live.india import IST, MAX_SYMBOLS, _symbols, normalize_quote

QUOTE_URL = "https://api.dhan.co/v2/marketfeed/quote"
MIN_REQUEST_INTERVAL = 1.0  # Dhan market-quote limit: one request per second.
AUTH_CODES = frozenset(
    {"806", "807", "808", "809", "810", "DH-901", "DH-902", "DH-903"}
)
THROTTLE_CODES = frozenset({"805", "DH-904"})


class DhanRateLimitError(OSError):
    """Retryable cooldown; callers must retry through the service session gate."""


class DhanQuoteProvider:
    """Bulk NSE equity provider implementing India's QuoteProvider contract.

    Parameters: instruments maps normalized .NS names to dictionaries containing
    security_id and exchange_segment (only NSE_EQ). Credentials come exclusively
    from DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN via from_env. session, monotonic and
    clock are injectable for offline tests. One instance/account worker is required
    so its one-second request/cooldown gate covers all calls, including retries.
    fetch returns normalized seven-field quotes or sanitized per-symbol errors;
    IndiaLiveService stamps its own authoritative batch receipt time again.
    """

    name = "dhan"
    max_batch_size = MAX_SYMBOLS

    def __init__(
        self,
        instruments: Mapping,
        *,
        environ: Mapping[str, str] | None = None,
        session=None,
        timeout_seconds=5.0,
        monotonic=time.monotonic,
        clock=lambda: datetime.now(UTC),
    ):
        env = os.environ if environ is None else environ
        self._credentials = tuple(
            env.get(key, "") for key in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN")
        )
        if any(
            not isinstance(value, str)
            or not value.strip()
            or any(c.isspace() or ord(c) < 32 for c in value)
            for value in self._credentials
        ):
            raise PermissionError("Dhan environment credentials missing or invalid")
        _symbols(instruments)
        self._instruments = {}
        for symbol, spec in instruments.items():
            if (
                not isinstance(spec, Mapping)
                or spec.get("exchange_segment") != "NSE_EQ"
            ):
                raise ValueError("Dhan requires explicit NSE_EQ instrument mappings")
            security_id = spec.get("security_id")
            if isinstance(security_id, bool) or not re.fullmatch(
                r"[1-9][0-9]*", str(security_id)
            ):
                raise ValueError(
                    "Dhan requires positive canonical numeric security IDs"
                )
            self._instruments[symbol] = str(security_id)
        if len(set(self._instruments.values())) != len(self._instruments):
            raise ValueError("Dhan security IDs must be unique")
        if (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Dhan requires a finite positive timeout")
        self._session = session if session is not None else requests.Session()
        # No implicit .netrc credentials or environment proxies. Redirects are
        # separately disabled at request time; credentials go only to QUOTE_URL.
        self._session.trust_env = False
        self._timeout = timeout_seconds
        self._monotonic, self._clock = monotonic, clock
        self._next_request = float("-inf")
        self._denied = False
        self._lock = Lock()

    @classmethod
    def from_env(cls, instruments: Mapping, **kwargs) -> DhanQuoteProvider:
        """Create an inactive provider from environment credentials and local IDs.

        No request occurs until fetch (normally called by IndiaLiveService).
        kwargs allow explicit timeout/session/clock configuration.
        """
        return cls(instruments, **kwargs)

    def fetch(self, symbols: Sequence[str]) -> dict:
        """Request 1–100 configured names; return valid quotes or symbol errors.

        Authorization raises PermissionError permanently for this instance;
        throttling raises DhanRateLimitError without sleeping past a session gate.
        Missing/malformed quotes never become zero prices or invented timestamps.
        """
        symbols = _symbols(symbols)
        if any(symbol not in self._instruments for symbol in symbols):
            raise ValueError("Dhan symbol has no approved instrument mapping")
        with self._lock:
            if self._denied:
                raise PermissionError("Dhan authorization denied; restart after review")
            if self._monotonic() < self._next_request:
                raise DhanRateLimitError("Dhan request cooldown active")
            self._next_request = self._monotonic() + MIN_REQUEST_INTERVAL
            try:
                response = self._session.post(
                    QUOTE_URL,
                    headers={
                        "client-id": self._credentials[0],
                        "access-token": self._credentials[1],
                        "Accept": "application/json",
                    },
                    json={"NSE_EQ": [int(self._instruments[s]) for s in symbols]},
                    timeout=self._timeout,
                    allow_redirects=False,
                )
            except Exception:  # noqa: BLE001 -- sanitize injected transport failures
                raise OSError("Dhan quote transport failed") from None
            if response.status_code in (401, 403):
                self._deny()
            if response.status_code == 429:
                self._throttle(response)
            if response.status_code >= 500:
                raise OSError("Dhan quote service unavailable")
            if 300 <= response.status_code < 400:
                raise ValueError("Dhan quote redirect refused")
            try:
                payload = response.json()
            except (ValueError, TypeError):
                raise ValueError("Dhan quote response is not valid JSON") from None
            if not isinstance(payload, Mapping):
                raise ValueError("Dhan quote envelope invalid")  # noqa: TRY004
            # Dhan data errors may use numeric errorCode; SDK/trading errors use
            # errorCode or error_code with DH- prefixes. Never expose messages.
            codes = {
                str(payload.get(k, "")) for k in ("errorCode", "error_code", "code")
            }
            if codes & AUTH_CODES:
                self._deny()
            if codes & THROTTLE_CODES:
                self._throttle(response)
            if response.status_code != 200 or payload.get("status") != "success":
                raise ValueError("Dhan quote request rejected")
            data = payload.get("data")
            if not isinstance(data, Mapping) or set(data) - {"NSE_EQ"}:
                raise ValueError("Dhan quote response exchange invalid")
            quotes = data.get("NSE_EQ", {})
            requested = {self._instruments[s] for s in symbols}
            if not isinstance(quotes, Mapping) or set(quotes) - requested:
                raise ValueError("Dhan quote response instrument invalid")
            received = self._clock()
            return {
                s: self._normalize(quotes.get(self._instruments[s]), s, received)
                for s in symbols
            }

    def _deny(self):
        self._denied = True
        raise PermissionError("Dhan authentication or data entitlement denied")

    def _throttle(self, response):
        delay = MIN_REQUEST_INTERVAL
        try:
            raw = response.headers.get("Retry-After", "")
            try:
                seconds = float(raw)
            except ValueError:
                seconds = (parsedate_to_datetime(raw) - self._clock()).total_seconds()
            if math.isfinite(seconds):
                delay = max(delay, seconds)
        except (TypeError, ValueError, OverflowError):
            pass
        self._next_request = max(self._next_request, self._monotonic() + delay)
        raise DhanRateLimitError("Dhan throttled quote requests")

    def _normalize(self, raw, symbol, received):
        try:
            if not isinstance(raw, Mapping):
                raise TypeError
            price, change = raw["last_price"], raw["net_change"]
            if isinstance(price, bool) or isinstance(change, bool):
                raise TypeError
            price, change = float(price), float(change)
            previous = price - change
            if (
                not math.isfinite(change)
                or not math.isfinite(previous)
                or previous <= 0
            ):
                raise ValueError
            # API text is exchange-local DD/MM/YYYY HH:MM:SS, NOT receipt time.
            stamp = datetime.strptime(raw["last_trade_time"], "%d/%m/%Y %H:%M:%S")
            if stamp.year < 2000:  # Reject documented 1980 missing-trade sentinel.
                raise ValueError
            return normalize_quote(
                {
                    "symbol": symbol,
                    "price": price,
                    "change_pct": 100 * change / previous,
                    "volume": raw["volume"],
                    "ts_exchange": stamp.replace(tzinfo=IST),
                    "source": self.name,
                },
                symbol,
                received,
                self.name,
            )
        except (KeyError, ValueError, TypeError, OverflowError):
            return ValueError("Dhan required quote data missing or invalid")
