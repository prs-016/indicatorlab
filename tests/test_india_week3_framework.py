"""Synthetic end-to-end accounting/research infrastructure, no market data."""

import socket
import sys

import numpy as np
import pandas as pd
import pytest
from india_week3_test_support import vibe_checkout
from scipy.stats import norm

from src.india_week3_portfolio import AccountingPolicy, account_orders
from src.india_week3_research import (
    deflated_sharpe,
    evaluate_splits,
    execute_ablations,
    five_session_labels,
    original_rank_ic,
    price_random_comparisons,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Synthetic framework attempted network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def example():
    dates = pd.date_range("2022-01-03", periods=15, freq="D", tz="UTC")
    close = pd.DataFrame(
        {"A": np.linspace(100, 114, 15), "B": np.linspace(100, 93, 15)}, index=dates
    )
    volume = close * 0 + 100
    orders = pd.DataFrame(
        [
            {
                "ticker": "A",
                "target_weight": 0.5,
                "execution_at": dates[1],
                "decision_at": dates[0],
                "reason": "entry",
            },
            {
                "ticker": "A",
                "target_weight": 0.0,
                "execution_at": dates[6],
                "decision_at": dates[5],
                "reason": "exit",
            },
        ]
    )
    policy = AccountingPolicy(1000, "fractional", "pretrade_nav_fee_inclusive_budget")
    return close, volume, orders, {"market": "US", "split": "test", "policy": policy}


def test_cash_fees_nav_trades_and_terminal_liquidation(example):
    close, volume, orders, kwargs = example
    result = account_orders(close, volume, orders, **kwargs)
    q = 500 / (101 * 1.001)
    assert result.quantities.iloc[1]["A"] == pytest.approx(q)
    assert result.daily.iloc[1]["cash"] == pytest.approx(500)
    assert result.daily.iloc[1]["nav"] == pytest.approx(500 + 101 * q)
    assert result.daily.iloc[6]["cash"] == pytest.approx(500 + 106 * q * (1 - 0.001))
    assert result.daily.iloc[0].net_return == 0
    assert (result.daily.cash >= -1e-8).all()
    assert result.daily.iloc[-1].positions_value == 0
    assert result.metrics["filled_entries"] == 1
    assert result.trades.duration.tolist() == [6]
    assert len(result.fills) == 2
    assert np.prod(1 + result.daily.net_return) == pytest.approx(
        result.daily.iloc[-1]["nav"] / 1000
    )


def test_whole_share_policy_and_no_silent_rounding_default(example):
    close, volume, orders, kwargs = example
    kwargs["policy"] = AccountingPolicy(
        1000, "whole", "pretrade_nav_fee_inclusive_budget"
    )
    result = account_orders(close, volume, orders, **kwargs)
    assert result.quantities.iloc[1]["A"] == 4
    with pytest.raises(ValueError):
        AccountingPolicy(1000, "unknown", "pretrade_nav_fee_inclusive_budget")
    with pytest.raises(ValueError):
        AccountingPolicy(1000, "whole", "post_cost_nav")


@pytest.mark.parametrize(
    "failure",
    ["missing_held", "zero_volume", "signal_close", "terminal", "out_of_split"],
)
def test_accounting_rejects_invalid_evidence(example, failure):
    close, volume, orders, kwargs = example
    if failure == "missing_held":
        close.iloc[3, 0] = np.nan
    if failure == "zero_volume":
        volume.iloc[1, 0] = 0
    if failure == "signal_close":
        orders.loc[0, "decision_at"] = orders.loc[0, "execution_at"]
    if failure == "terminal":
        orders = orders.iloc[:1]
    if failure == "out_of_split":
        kwargs["split"] = "train"
    with pytest.raises(ValueError):
        account_orders(close, volume, orders, **kwargs)


def test_resizing_keeps_one_opening_and_flags_path_for_null(example):
    close, volume, orders, kwargs = example
    resize = orders.iloc[:1].copy()
    resize["execution_at"] = close.index[3]
    resize["decision_at"] = close.index[2]
    resize["target_weight"] = 0.3
    result = account_orders(close, volume, pd.concat([orders, resize]), **kwargs)
    assert len(result.fills) == 3 and result.trades.resized.all()
    assert len(result.trades.iloc[0].resize_path) == 1
    assert result.trades.iloc[0].net_cash == pytest.approx(
        result.daily.iloc[-1].nav - 1000
    )


def test_same_close_sell_funds_new_entry_without_lookahead(example):
    close, volume, orders, kwargs = example
    add = pd.DataFrame(
        [
            {
                "ticker": "B",
                "target_weight": 0.5,
                "execution_at": close.index[6],
                "decision_at": close.index[5],
                "reason": "entry",
            },
            {
                "ticker": "B",
                "target_weight": 0.0,
                "execution_at": close.index[10],
                "decision_at": close.index[9],
                "reason": "exit",
            },
        ]
    )
    result = account_orders(close, volume, pd.concat([orders, add]), **kwargs)
    at = result.fills[result.fills.execution_at == close.index[6]]
    assert at.buy.tolist() == [False, True]
    assert result.metrics["filled_entries"] == 2


def test_200_null_returns_use_identical_accounting_and_preserve_durations(example):
    close, volume, orders, kwargs = example
    actual = account_orders(close, volume, orders, **kwargs)
    trades = actual.trades.set_index("trade_id")
    candidates = {trades.index[0]: [1, 2, 4, 6]}
    result = price_random_comparisons(
        trades, close, volume, candidates, max_attempts=2, accounting=kwargs
    )
    assert len(result["results"]) == len(result["sharpes"]) == 200
    assert result["seeds"] == list(range(42, 242))
    for schedule, ledger in zip(result["schedules"], result["results"]):
        assert len(ledger.trades) == len(trades)
        assert ledger.trades.duration.tolist() == [6]
        assert ledger.trades.iloc[0]["entry"] == schedule.iloc[0]["entry"]
        assert ledger.daily.commission.sum() > 0


def test_ablations_run_declared_builder_without_changing_protection(example):
    close, volume, orders, kwargs = example
    calls = []

    def builder(disabled):
        calls.append(disabled)
        out = orders.copy()
        if "attention" in disabled:
            out.loc[0, "target_weight"] = 0.25
        return out

    output = execute_ablations(
        builder,
        {"no_attention": frozenset({"attention"})},
        predictive_components=frozenset({"attention"}),
        close=close,
        volume=volume,
        accounting=kwargs,
    )
    assert len(calls) == 2
    assert output["no_attention"]["returns_changed"]
    with pytest.raises(ValueError):
        execute_ablations(
            builder,
            {"no_stop": frozenset({"stop"})},
            predictive_components=frozenset({"stop"}),
            close=close,
            volume=volume,
            accounting=kwargs,
        )


def test_five_session_labels_and_original_vibe_ic_after_2024():
    dates = pd.date_range("2025-01-01", periods=12, tz="UTC")
    tickers = list("ABCDEF")
    close = pd.DataFrame(
        {t: 100 + np.arange(12) * i for i, t in enumerate(tickers, 1)}, index=dates
    )
    signals = dates[[0, 8]]
    scores = pd.DataFrame(
        [range(6), range(6)], index=signals, columns=tickers, dtype=float
    )
    executions = pd.DataFrame(
        [[dates[1]] * 6, [dates[9]] * 6], index=signals, columns=tickers
    )
    labels = five_session_labels(scores, executions, close, split="test")
    assert labels.iloc[0, 0] == pytest.approx(106 / 101 - 1)
    assert labels.iloc[1].isna().all()
    root = vibe_checkout()
    assert (
        root.exists()
    ), "Original local Vibe IC checkout required for integration verification"
    result = original_rank_ic(
        scores, labels, vibe_root=root, python_executable=sys.executable
    )
    assert result["defined_intervals"] == 1
    assert result["ic"].iloc[0] == pytest.approx(1)
    assert len(result["source_sha256"]) == 64
    executions.iloc[0, 0] = signals[0]
    with pytest.raises(ValueError):
        five_session_labels(scores, executions, close, split="test")


def test_ic_no_holdout_or_split_crossing(example):
    close, _, _, _ = example
    dates = pd.date_range("2025-10-01", periods=1, tz="UTC")
    scores = pd.DataFrame([[1, 2]], index=dates, columns=close.columns)
    with pytest.raises(ValueError):
        five_session_labels(scores, scores, close, split="test")


def trials():
    return pd.DataFrame(
        {
            "trial_id": ["v1", "v2", "ablation"],
            "status": ["complete"] * 3,
            "daily_sharpe": [-0.1, 0.05, 0.2],
        }
    )


def test_dsr_single_effective_trial_reduces_to_psr_and_deflation_is_monotone():
    returns = pd.Series([0.01, -0.005, 0.002, 0.015, -0.003, 0.007, -0.002, 0.004])
    one = deflated_sharpe(
        returns,
        trials(),
        effective_trials=1,
        dependence_assumption="explicit perfectly dependent sensitivity",
        ledger_complete=True,
    )
    many = deflated_sharpe(
        returns,
        trials(),
        effective_trials=3,
        dependence_assumption="all recorded trials independent sensitivity",
        ledger_complete=True,
    )
    sr = one["daily_sharpe"]
    denom = np.sqrt(
        1 - one["skewness"] * sr + (one["pearson_kurtosis"] - 1) * sr * sr / 4
    )
    assert one["probability"] == pytest.approx(
        norm.cdf(sr * np.sqrt(len(returns) - 1) / denom)
    )
    assert 0 <= many["probability"] < one["probability"] <= 1
    assert many["attempted_trials"] == 3


@pytest.mark.parametrize(
    "failure", ["incomplete", "missing_trial_sr", "duplicate", "effective_count"]
)
def test_dsr_rejects_invented_trial_evidence(failure):
    ledger = trials()
    n = 3
    complete = True
    if failure == "incomplete":
        complete = False
    if failure == "missing_trial_sr":
        ledger.loc[0, "daily_sharpe"] = np.nan
        ledger.loc[0, "status"] = "failed"
    if failure == "duplicate":
        ledger.loc[1, "trial_id"] = "v1"
    if failure == "effective_count":
        n = 4
    with pytest.raises(ValueError):
        deflated_sharpe(
            pd.Series([0.01, -0.01, 0.02, 0.005]),
            ledger,
            effective_trials=n,
            dependence_assumption="explicit",
            ledger_complete=complete,
        )


def test_train_and_test_restart_cash_and_compare_benchmarks(example):
    close, volume, orders, kwargs = example
    train_dates = close.index - pd.DateOffset(years=1)
    train = close.set_axis(train_dates)
    train_volume = volume.set_axis(train_dates)
    train_orders = orders.copy()
    for col in ["execution_at", "decision_at"]:
        train_orders[col] = train_orders[col] - pd.DateOffset(years=1)
    panels = {
        "test": {"close": close, "volume": volume, "benchmark": close.A},
        "train": {"close": train, "volume": train_volume, "benchmark": train.A},
    }
    kwargs.pop("split")
    results = evaluate_splits(
        panels, {"test": orders, "train": train_orders}, accounting=kwargs
    )
    assert results["test"]["result"].daily.iloc[0]["cash"] == 1000
    assert results["train"]["result"].daily.iloc[0]["cash"] == 1000
    assert np.isfinite(results["test"]["benchmark"]["net_sharpe"])
    assert results["test"]["result"].metrics == results["train"]["result"].metrics


def test_resized_exposure_paths_are_replayed_in_all_200_nulls(example):
    close, volume, orders, kwargs = example
    resize = orders.iloc[:1].copy()
    resize["execution_at"] = close.index[3]
    resize["decision_at"] = close.index[2]
    resize["target_weight"] = 0.3
    result = account_orders(close, volume, pd.concat([orders, resize]), **kwargs)
    trades = result.trades.set_index("trade_id")
    null = price_random_comparisons(
        trades,
        close,
        volume,
        {trades.index[0]: [1, 3]},
        max_attempts=2,
        accounting=kwargs,
    )
    assert all(
        len(r.fills) == 3 and r.trades.iloc[0].resize_path == [(2, 0.3)]
        for r in null["results"]
    )


def test_labels_reject_mixed_train_test_panel():
    dates = pd.date_range("2021-12-28", periods=10, tz="UTC")
    close = pd.DataFrame({"A": range(100, 110)}, index=dates)
    scores = pd.DataFrame([[1]], index=dates[:1], columns=["A"])
    executions = pd.DataFrame([[dates[1]]], index=scores.index, columns=scores.columns)
    with pytest.raises(ValueError, match="split"):
        five_session_labels(scores, executions, close, split="train")


def test_india_delegates_actual_sides_and_slippage_in_accounting(example):
    close, volume, orders, kwargs = example
    sides = []

    class Engine:
        def apply_slippage(self, price, direction):
            return price * (1 + 0.001 * direction)

        def calc_commission(self, size, price, direction, is_open):
            sides.append(is_open)
            return size * price * 0.002 + (0 if is_open else 1)

    kwargs.update(market="IN", india_engine=Engine())
    result = account_orders(close, volume, orders, **kwargs)
    assert result.fills.buy.tolist() == [True, False]
    assert result.fills.iloc[0].price > result.fills.iloc[0].close
    assert result.fills.iloc[1].price < result.fills.iloc[1].close
    assert not sides[-1] and result.daily.commission.sum() > 0


def test_failed_ablations_remain_in_trial_history(example):
    from src.india_week3_research import ablation_trial_ledger

    close, volume, orders, kwargs = example

    def builder(disabled):
        if disabled:
            raise ValueError("synthetic unavailable input")
        return orders

    outputs = execute_ablations(
        builder,
        {"no_attention": frozenset({"attention"})},
        predictive_components=frozenset({"attention"}),
        close=close,
        volume=volume,
        accounting=kwargs,
    )
    ledger = ablation_trial_ledger(outputs, study_id="synthetic_v2_US_test")
    assert len(ledger) == 2 and ledger.status.tolist() == ["complete", "failed"]
    assert pd.isna(ledger.iloc[1].daily_sharpe)
    assert outputs["no_attention"]["returns_changed"] is None


def test_final_five_session_entry_gate_is_enforced_by_ledger(example):
    close, volume, orders, kwargs = example
    orders.loc[0, "execution_at"] = close.index[-3]
    orders.loc[0, "decision_at"] = close.index[-4]
    orders.loc[1, "execution_at"] = close.index[-1]
    orders.loc[1, "decision_at"] = close.index[-2]
    with pytest.raises(ValueError, match="five sessions"):
        account_orders(close, volume, orders, **kwargs)


def test_future_price_changes_do_not_change_past_accounting(example):
    close, volume, orders, kwargs = example
    base = account_orders(close, volume, orders, **kwargs)
    changed = close.copy()
    changed.iloc[5:] = changed.iloc[5:] * 1.1
    altered = account_orders(changed, volume, orders, **kwargs)
    pd.testing.assert_frame_equal(base.daily.iloc[:5], altered.daily.iloc[:5])
