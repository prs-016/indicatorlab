"""Offline adapters for the assigned eight-stock India research basket."""

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


NSE_STOCKS = (
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
    "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS",
)
BENCHMARK = "^NSEI"
BACKTEST_END = pd.Timestamp("2024-12-31")
HOLDOUT_START = pd.Timestamp("2025-10-01")


@dataclass(frozen=True)
class IndiaPanel:
    """Adapted close/volume matrices, separate benchmark, and declared basis.

    Frames are indexed by timezone-naive exchange session dates. ``close_basis``
    records the caller's declaration; it does not independently verify prices.
    """

    close: pd.DataFrame
    volume: pd.DataFrame
    benchmark: pd.Series
    close_basis: str


def validate_close(close: pd.DataFrame) -> None:
    """Validate a stock close matrix; return None or raise ValueError.

    Parameters: close is a session-indexed wide frame of the assigned stocks.
    Missing prices are retained, but finite observed prices must be positive.
    """
    _validate_dates(close.index)
    if tuple(close.columns) != NSE_STOCKS:
        raise ValueError("Close columns must be the eight assigned NSE stocks in order")
    if close.empty or close.index.max() > BACKTEST_END:
        raise ValueError("Close data must be nonempty and end by 2024-12-31")
    values = close.to_numpy(dtype=float)
    if np.isinf(values).any() or (values <= 0).any():
        raise ValueError("Observed close prices must be positive and finite")


def _validate_dates(index: pd.Index) -> None:
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError("Expected a DatetimeIndex of exchange session dates")
    if (index.tz is not None or index.hasnans or index.has_duplicates
            or not index.is_monotonic_increasing
            or not index.equals(index.normalize())):
        raise ValueError("Session dates must be naive, normalized, sorted and unique")


def build_india_panel(
    histories: Mapping[str, pd.DataFrame], *, close_basis: str,
) -> IndiaPanel:
    """Adapt in-memory histories without downloading, repairing, or filling data.

    Parameters: histories must contain exactly the eight NSE stocks and ^NSEI.
    Stock frames require lowercase close/volume; the benchmark requires close.
    close_basis must explicitly declare 'adjusted' or 'unadjusted'.
    Returns: an IndiaPanel on the union of stock dates through 2024-12-31,
    with benchmark observations reindexed to that calendar. Missing values stay
    missing. No start date, trading calendar, or anomaly policy is selected.
    """
    if set(histories) != {*NSE_STOCKS, BENCHMARK}:
        raise ValueError("Expected exactly eight assigned NSE equities and ^NSEI")
    if close_basis not in {"adjusted", "unadjusted"}:
        raise ValueError("Declare close_basis as adjusted or unadjusted")
    frames = {}
    for symbol, original in histories.items():
        _validate_dates(original.index)
        required = ["close"] if symbol == BENCHMARK else ["close", "volume"]
        if not original.columns.is_unique or not set(required) <= set(original.columns):
            raise ValueError(f"{symbol}: missing or duplicate required columns")
        frame = original.loc[:BACKTEST_END, required].astype(float).copy()
        if frame.empty:
            raise ValueError(f"{symbol}: no observations before cutoff")
        prices = frame["close"].to_numpy()
        if np.isinf(prices).any() or (prices <= 0).any():
            raise ValueError(f"{symbol}: observed prices must be positive and finite")
        if symbol != BENCHMARK:
            volumes = frame["volume"].to_numpy()
            if np.isinf(volumes).any() or (volumes < 0).any():
                raise ValueError(f"{symbol}: volume must be nonnegative and finite")
        frames[symbol] = frame
    close = pd.concat({s: frames[s]["close"] for s in NSE_STOCKS}, axis=1, sort=True)
    volume = pd.concat({s: frames[s]["volume"] for s in NSE_STOCKS}, axis=1, sort=True)
    volume = volume.reindex(index=close.index, columns=close.columns)
    benchmark = frames[BENCHMARK]["close"].reindex(close.index).rename(BENCHMARK)
    validate_close(close)
    return IndiaPanel(close, volume, benchmark, close_basis)
