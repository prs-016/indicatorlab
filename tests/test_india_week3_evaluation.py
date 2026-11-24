"""Synthetic evaluation-contract tests, never historical strategy results."""

import numpy as np
import pandas as pd
import pytest

from src.india_week3_evaluation import (
    guide_decision,
    net_metrics,
    random_timing_schedules,
)


def test_shared_sharpe_compounding_and_fixed_split():
    returns = pd.Series(
        [0.01, -0.005, 0.02], index=pd.date_range("2022-01-03", periods=3, tz="UTC")
    )
    result = net_metrics(returns, "test")
    assert result["net_sharpe"] == pytest.approx(
        returns.mean() / returns.std(ddof=1) * np.sqrt(252)
    )
    assert result["net_cumulative_return"] == pytest.approx((1 + returns).prod() - 1)
    with pytest.raises(ValueError):
        net_metrics(returns, "train")
    with pytest.raises(ValueError):
        net_metrics(
            returns.set_axis(pd.date_range("2025-10-01", periods=3, tz="UTC")), "test"
        )
    with pytest.raises(ValueError):
        net_metrics(returns.where(returns > 0), "test")


def decision(**updates):
    fields = {
        "training_entries": 30,
        "train_sharpe": 1.0,
        "test_sharpe": 1.0,
        "index_test_sharpe": 0.8,
        "random_train": [0.5] * 180 + [1.5] * 20,
        "random_test": [0.5] * 180 + [1.5] * 20,
        "reports_complete": True,
    }
    return guide_decision(**(fields | updates))


def test_exact_guide_thresholds_and_incomplete_evidence():
    assert decision() == "KEEP CANDIDATE"
    assert decision(test_sharpe=0.8) == "DROP"
    assert decision(training_entries=29) == "INSUFFICIENT TRAINING ENTRIES"
    assert decision(random_train=[0.5] * 179 + [1.5] * 21) == "DROP"
    assert decision(random_test=[0.5] * 199) == "NOT EVALUATED"
    assert decision(reports_complete=False) == "NOT EVALUATED"
    assert decision(train_sharpe=np.nan) == "NOT EVALUATED"


def test_200_seeded_schedules_preserve_count_weights_and_durations():
    sessions = pd.date_range("2021-01-01", periods=30, tz="UTC")
    trades = pd.DataFrame(
        {"ticker": ["A", "B"], "duration": [3, 5], "weight": [0.3, 0.4]},
        index=["t1", "t2"],
    )
    candidates = {"t1": [0, 7, 14], "t2": [1, 8, 15]}
    schedules = random_timing_schedules(trades, sessions, candidates, max_attempts=10)
    repeat = random_timing_schedules(trades, sessions, candidates, max_attempts=10)
    assert len(schedules) == 200
    for frame, other in zip(schedules, repeat):
        pd.testing.assert_frame_equal(frame, other)
        assert frame["duration"].tolist() == [3, 5] and frame["weight"].tolist() == [
            0.3,
            0.4,
        ]
        for row in frame.itertuples():
            assert (
                sessions.get_loc(row.exit) - sessions.get_loc(row.entry) + 1
                == row.duration
            )


def test_infeasible_random_schedule_never_returns_partial_or_changes_trades():
    sessions = pd.date_range("2021-01-01", periods=30, tz="UTC")
    trades = pd.DataFrame(
        {"ticker": ["A", "A"], "duration": [3, 5], "weight": [0.3, 0.4]},
        index=["t1", "t2"],
    )
    with pytest.raises(ValueError, match="Infeasible"):
        random_timing_schedules(
            trades, sessions, {"t1": [0], "t2": [0]}, max_attempts=2
        )


def test_market_cost_adapter_delegates_without_double_charging():
    from src.india_week3_evaluation import fill_cost

    class SpyEngine:
        def apply_slippage(self, price, direction):
            assert direction == -1
            return price - 1

        def calc_commission(self, quantity, price, direction, is_open):
            assert (quantity, price, direction, is_open) == (10, 99, 1, False)
            return 3.5

    assert fill_cost("US", quantity=10, close=100, buy=True) == {
        "price": 100,
        "commission": 1,
    }
    assert fill_cost(
        "IN", quantity=10, close=100, buy=False, india_engine=SpyEngine()
    ) == {"price": 99, "commission": 3.5}
    with pytest.raises(ValueError):
        fill_cost("IN", quantity=10, close=100, buy=True)
