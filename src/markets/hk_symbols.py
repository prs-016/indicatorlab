"""HK ticker normalization, validated history and sourced display-name metadata."""

from __future__ import annotations

import copy
import json
import math
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

import requests

from src.markets.errors import SymbolLookupUnavailable, UnknownTicker

ROOT = Path(__file__).resolve().parents[2]
METADATA = ROOT / "config/hk_final_symbol_metadata.json"
SUBREDDIT_EVIDENCE = ROOT / "config/hk_final_subreddit_evidence.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
HISTORY_TIMEOUT_SECONDS = 5
MAX_HISTORY_BYTES = 2_000_000
HISTORY_CACHE_SECONDS = 6 * 60 * 60
UNKNOWN_CACHE_SECONDS = 60
MAX_CACHE_SYMBOLS = 1024
HK_AMBIGUOUS = frozenset({"Link", "Galaxy", "Sands", "AIA", "Bank", "China Life"})
_HISTORY_CACHE: dict[str, tuple[float, bool]] = {}
_CACHE_LOCK = threading.Lock()


def canonical_hk(raw: str) -> str:
    """Return the syntactic Yahoo HK symbol without making a network request.

    Args:
        raw: Numeric HK code, optionally prefixed HK:/HKEX: or suffixed .HK.

    Returns:
        Four digits plus .HK for codes below 10000; five digits for larger codes.

    Raises:
        UnknownTicker: The input is not a positive, at-most-five-digit HK code.
    """
    if not isinstance(raw, str):
        raise UnknownTicker("HK ticker must be a string")
    value = raw.strip().upper()
    match = re.fullmatch(r"(?:(?:HK|HKEX):)?([0-9]{1,5})(?:\.HK)?", value)
    if match is None or int(match[1]) == 0:
        raise UnknownTicker(f"Invalid HK ticker: {raw!r}")
    number = int(match[1])
    return f"{number:04d}.HK"


def tencent_code(symbol: str) -> str:
    """Return Tencent's hk plus five-digit request identifier, without validation."""
    return f"hk{int(canonical_hk(symbol).removesuffix('.HK')):05d}"


def _history_exists(symbol: str) -> bool:
    """Check Yahoo's chart history; outages are distinct from an unknown ticker."""
    try:
        with requests.get(
            YAHOO_CHART_URL + symbol,
            params={"range": "max", "interval": "1mo"},
            timeout=HISTORY_TIMEOUT_SECONDS,
            headers={"User-Agent": "indicator-lab-hk-symbols/1.0 (academic project)"},
            stream=True,
        ) as response:
            if response.status_code == 404:
                return False
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(chunk_size=65_536):
                body.extend(chunk)
                if len(body) > MAX_HISTORY_BYTES:
                    raise SymbolLookupUnavailable("Yahoo history response is too large")
        payload = json.loads(body)
        chart = payload["chart"]
        error = chart.get("error")
        if error:
            if error.get("code") == "Not Found":
                return False
            raise SymbolLookupUnavailable("Yahoo rejected the history lookup")
        results = chart.get("result")
        if results == []:
            return False
        if not isinstance(results, list) or not results:
            raise SymbolLookupUnavailable("Yahoo returned no usable history result")
        row = results[0]
        if canonical_hk(row["meta"]["symbol"]) != symbol:
            raise SymbolLookupUnavailable("Yahoo history identity did not match")
        closes = row["indicators"]["quote"][0]["close"]
        return any(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
            for value in closes
        )
    except SymbolLookupUnavailable:
        raise
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise SymbolLookupUnavailable("Yahoo history lookup is unavailable") from exc


def normalize_hk(
    raw: str,
    *,
    validate: bool = True,
    history_check: Callable[[str], bool] | None = None,
) -> str:
    """Normalize an HK alias and, by default, require actual Yahoo price history.

    Args:
        raw: User-entered HK ticker alias.
        validate: False only when a caller already performed symbol resolution.
        history_check: Injectable history provider; False means confirmed missing.

    Returns:
        The canonical Yahoo symbol.

    Raises:
        UnknownTicker: Bad syntax or a successful lookup found no price history.
        SymbolLookupUnavailable: Yahoo/network failure; never mislabeled as missing.
    """
    symbol = canonical_hk(raw)
    if not validate:
        return symbol
    # Injected providers deliberately bypass the production cache so tests and
    # independent callers do not contaminate each other's lookup semantics.
    if history_check is not None:
        exists = history_check(symbol)
    else:
        now = time.monotonic()
        with _CACHE_LOCK:
            cached = _HISTORY_CACHE.get(symbol)
        if cached is not None and cached[0] > now:
            exists = cached[1]
        else:
            exists = _history_exists(symbol)
            if not isinstance(exists, bool):
                raise SymbolLookupUnavailable(
                    "History provider returned an invalid result"
                )
            ttl = HISTORY_CACHE_SECONDS if exists else UNKNOWN_CACHE_SECONDS
            with _CACHE_LOCK:
                if len(_HISTORY_CACHE) >= MAX_CACHE_SYMBOLS:
                    _HISTORY_CACHE.clear()
                _HISTORY_CACHE[symbol] = (now + ttl, exists)
    if not isinstance(exists, bool):
        raise SymbolLookupUnavailable("History provider returned an invalid result")
    if not exists:
        raise UnknownTicker(f"No Yahoo price history for {symbol}")
    return symbol


def hk_names() -> dict[str, dict]:
    """Return a caller-owned name/alias map for the dated 95-member HSI roster."""
    return copy.deepcopy(json.loads(METADATA.read_text(encoding="utf-8"))["stocks"])


def _selected_subreddits() -> tuple[str, ...]:
    if not SUBREDDIT_EVIDENCE.is_file():
        return ()
    evidence = json.loads(SUBREDDIT_EVIDENCE.read_text(encoding="utf-8"))
    return tuple(evidence["selected"])


HK_SUBREDDITS = _selected_subreddits()
