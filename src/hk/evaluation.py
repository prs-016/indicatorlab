"""Week 3 timing-null and multiple-testing statistics, independent of an engine.

The caller must rerun schedules through the same Vibe engine and costs. This
module never substitutes a synthetic portfolio simulator for that engine.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

TRAIN = ("2016-06-01", "2021-12-31")
TEST = ("2022-01-01", "2025-09-30")
CUTOFF = pd.Timestamp("2025-10-01")
EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True)
class Trade:
    """An executed trade with entry/exit session positions; exit is exclusive."""

    symbol: str
    entry: int
    exit: int
    side: int = 1
    weight: float = 1.0


def validate_dates(index: pd.DatetimeIndex, split: str) -> None:
    """Reject post-cutoff, duplicate, unsorted or cross-split observations."""
    if split not in {"train", "test"}:
        raise ValueError("split must be train or test")
    start, end = TRAIN if split == "train" else TEST
    if not len(index) or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("Expected a nonempty, ordered unique session index")
    if index.tz is not None:
        raise ValueError("Use exchange-local session dates without timezone")
    if (
        index.min() < pd.Timestamp(start)
        or index.max() > pd.Timestamp(end)
        or (index >= CUTOFF).any()
    ):
        raise ValueError("Data falls outside the approved Week 3 split")


def random_timing(
    trades: Sequence[Trade],
    sessions: int,
    rng: np.random.Generator,
    *,
    max_attempts=1000,
) -> list[Trade]:
    """Randomize entries while preserving symbols, count, durations, sides, sizes.

    No overlap within a symbol, matching a one-position-per-name strategy.
    Reject impossible/dense schedules instead of silently dropping trades.
    """
    if not trades or sessions < 2:
        raise ValueError("Trades and at least two sessions are required")
    for trade in trades:
        if not 0 <= trade.entry < trade.exit < sessions or trade.side not in {-1, 1}:
            raise ValueError("Trade boundaries or side are invalid")
        if not math.isfinite(trade.weight) or trade.weight <= 0:
            raise ValueError("Trade weight must be positive and finite")
    for _ in range(max_attempts):
        schedule, occupied = [], {}
        for item in rng.permutation(len(trades)):
            trade = trades[int(item)]
            duration = trade.exit - trade.entry
            entry = int(rng.integers(0, sessions - duration))
            candidate = replace(trade, entry=entry, exit=entry + duration)
            intervals = occupied.setdefault(trade.symbol, [])
            if any(
                candidate.entry < end and candidate.exit > start
                for start, end in intervals
            ):
                break
            intervals.append((candidate.entry, candidate.exit))
            schedule.append(candidate)
        else:
            return sorted(schedule, key=lambda trade: (trade.entry, trade.symbol))
    raise ValueError("Cannot sample a complete non-overlapping timing schedule")


def random_baseline(
    trades: Sequence[Trade],
    index: pd.DatetimeIndex,
    split: str,
    evaluate: Callable[[list[Trade]], float],
    *,
    runs=200,
    seed=42,
) -> np.ndarray:
    """Evaluate 200 timing schedules with the caller's unchanged engine and costs."""
    validate_dates(index, split)
    if runs < 200:
        raise ValueError("Week 3 requires at least 200 random timing runs")
    rng = np.random.default_rng(seed)
    results = np.array(
        [evaluate(random_timing(trades, len(index), rng)) for _ in range(runs)],
        dtype=float,
    )
    if not np.isfinite(results).all():
        raise ValueError("Every random run must produce a finite engine Sharpe")
    return results


def deflated_sharpe(
    returns: Sequence[float],
    trial_sharpes: Sequence[float],
    *,
    total_trials: int | None = None,
) -> float:
    """Bailey & Lopez de Prado (2014) DSR with per-observation trial Sharpes.

    Supply EVERY attempted variant's Sharpe on the same frequency and split.
    Counting all trials as independent is conservative when trials correlate.
    IID approximation; serial dependence requires further analysis.
    Source: https://davidhbailey.com/dhbpapers/deflated-sharpe.pdf
    """
    values, trials = np.asarray(returns, dtype=float), np.asarray(
        trial_sharpes, dtype=float
    )
    if values.ndim != 1 or trials.ndim != 1 or len(values) < 30 or len(trials) < 2:
        raise ValueError("Need >=30 returns and >=2 documented trial Sharpes")
    if (
        not np.isfinite(values).all()
        or not np.isfinite(trials).all()
        or values.std(ddof=1) <= 0
    ):
        raise ValueError("Returns and all trial Sharpes must be usable and finite")
    count = len(trials) if total_trials is None else total_trials
    if not isinstance(count, int) or count < len(trials):
        raise ValueError(
            "Total trial count cannot be smaller than observed trial Sharpes"
        )
    sr = float(values.mean() / values.std(ddof=1))
    expected_max = float(trials.std(ddof=1)) * (
        (1 - EULER_GAMMA) * norm.ppf(1 - 1 / count)
        + EULER_GAMMA * norm.ppf(1 - 1 / (count * math.e))
    )
    variance = (
        1
        - float(skew(values, bias=False)) * sr
        + (float(kurtosis(values, fisher=False, bias=False)) - 1) * sr**2 / 4
    )
    if not variance > 0:
        raise ValueError("Invalid Sharpe sampling variance")
    return float(
        norm.cdf((sr - expected_max) * math.sqrt(len(values) - 1) / math.sqrt(variance))
    )
