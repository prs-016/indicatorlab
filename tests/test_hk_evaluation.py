"""Synthetic timing-null invariants and holdout/multiple-testing boundaries."""

import numpy as np
import pandas as pd
import pytest

from src.hk.evaluation import (
    Trade,
    deflated_sharpe,
    random_baseline,
    random_timing,
    validate_dates,
)


def test_timing_null_preserves_all_trades_and_holding_times():
    trades = [Trade("700", 10, 15), Trade("700", 20, 23), Trade("5", 30, 40, -1, 0.2)]
    result = random_timing(trades, 300, np.random.default_rng(7))
    key = lambda t: (t.symbol, t.exit - t.entry, t.side, t.weight)
    assert sorted(map(key, result)) == sorted(map(key, trades))
    assert result != sorted(trades, key=lambda t: (t.entry, t.symbol))
    a, b = [trade for trade in result if trade.symbol == "700"]
    assert a.exit <= b.entry or b.exit <= a.entry


def test_random_baseline_calls_the_engine_200_times_reproducibly():
    dates = pd.bdate_range("2023-01-01", periods=100)
    calls = []

    def engine(schedule):
        calls.append(schedule)
        return float(schedule[0].entry)

    args = ([Trade("700", 1, 6)], dates, "test", engine)
    a = random_baseline(*args)
    assert len(calls) == 200
    b = random_baseline(*args)
    np.testing.assert_array_equal(a, b)
    assert len(set(a)) > 20


@pytest.mark.parametrize(
    "dates,split",
    [
        (pd.date_range("2025-09-30", periods=2), "test"),
        (pd.date_range("2022-01-01", periods=2), "train"),
        (pd.date_range("2016-05-31", periods=2), "train"),
    ],
)
def test_cutoff_and_split_are_enforced(dates, split):
    with pytest.raises(ValueError):
        validate_dates(dates, split)


def test_dsr_penalty_increases_with_more_trials():
    rng = np.random.default_rng(1)
    returns = rng.normal(0.001, 0.01, 1000)
    few = np.array([-0.1, 0.1])
    many = np.tile(few, 100)
    assert deflated_sharpe(returns, many) < deflated_sharpe(returns, few)


def test_dsr_rejects_missing_trial_history():
    with pytest.raises(ValueError):
        deflated_sharpe([0.01] * 100, [])
