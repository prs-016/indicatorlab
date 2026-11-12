"""OFFLINE SYNTHETIC portfolio fixtures; these are not strategy evaluations."""

from dataclasses import replace
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.india_data import IndiaPanel, NSE_STOCKS
from src.india_backtest import (
    PortfolioConfig, annualized_sharpe, backtest_strev,
    prepare_research_view, simulate_portfolio,
)
from src.india_vibe_bridge import compute_rank_ic


@pytest.fixture
def synthetic():
    """Invented flat eight-stock prices, volumes, scores, and benchmark."""
    dates = pd.bdate_range("2021-01-04", "2021-01-29")
    close = pd.DataFrame(100.0, index=dates, columns=NSE_STOCKS)
    volume = pd.DataFrame(1000.0, index=dates, columns=NSE_STOCKS)
    panel = IndiaPanel(close, volume, pd.Series(100.0, index=dates), "adjusted")
    scores = pd.DataFrame(np.tile(np.arange(8)[::-1], (len(dates), 1)),
                          index=dates, columns=NSE_STOCKS, dtype=float)
    return panel, scores, PortfolioConfig(end="2021-01-29")


def test_signal_lag_entry_cost_and_holdings(synthetic):
    panel, scores, config = synthetic
    # A jump before the execution close must not be earned by the new position.
    panel.close.loc["2021-01-11":, NSE_STOCKS[0]] = 200
    panel.close.loc["2021-01-12":, NSE_STOCKS[0]] = 220
    result = simulate_portfolio(panel, scores, config=config)
    first = result.executions.iloc[0]
    assert first.signal_date == pd.Timestamp("2021-01-08")
    assert first.execution_date == pd.Timestamp("2021-01-11")
    assert first.selected == NSE_STOCKS[:2]
    assert result.weights.loc[:"2021-01-08"].eq(0).all().all()
    np.testing.assert_allclose(result.weights.loc["2021-01-11", list(NSE_STOCKS[:2])], .5)
    assert result.gross_returns.loc["2021-01-11"] == 0
    assert result.net_returns.loc["2021-01-11"] == pytest.approx(-.001)
    assert result.turnover.loc["2021-01-11"] == 1
    assert result.gross_returns.loc["2021-01-12"] == pytest.approx(.05)
    assert result.weights.loc["2021-01-12", NSE_STOCKS[0]] == pytest.approx(.55 / 1.05)
    np.testing.assert_allclose(result.weights.loc["2021-01-11":].sum(axis=1), 1)


def test_turnover_replacement_and_multiplicative_costs(synthetic):
    panel, scores, config = synthetic
    scores.loc["2021-01-15":, :] = np.arange(8)
    panel.close.loc["2021-01-18":, NSE_STOCKS[0]] = 110
    result = simulate_portfolio(panel, scores, config=config)
    assert result.turnover.loc["2021-01-18"] == pytest.approx(2)
    assert result.costs.loc["2021-01-18"] == pytest.approx(.002)
    assert result.net_returns.loc["2021-01-18"] == pytest.approx(1.05 * .998 - 1)
    assert result.executions.iloc[1].selected == (NSE_STOCKS[7], NSE_STOCKS[6])
    assert result.turnover.loc["2021-01-25"] == 0


def test_sell_volume_gates_execution(synthetic):
    panel, scores, config = synthetic
    scores.loc["2021-01-15":, :] = np.arange(8)
    panel.volume.loc["2021-01-18", NSE_STOCKS[0]] = 0
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.iloc[1].execution_date == pd.Timestamp("2021-01-19")
    assert result.weights.loc["2021-01-18", NSE_STOCKS[0]] == .5
    assert any(log["status"] == "deferred" for log in result.order_log)


def test_deferred_orders_cancel_and_targets_do_not_overlap(synthetic):
    panel, scores, config = synthetic
    panel.volume.loc[:"2021-01-15", NSE_STOCKS[0]] = 0
    scores.loc["2021-01-15":, :] = np.arange(8)
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.iloc[0].signal_date == pd.Timestamp("2021-01-15")
    assert result.executions.iloc[0].execution_date == pd.Timestamp("2021-01-18")
    assert result.executions.execution_date.is_unique
    assert any(log["status"] == "cancelled_replaced" for log in result.order_log)


def test_ties_are_lexicographic(synthetic):
    panel, scores, config = synthetic
    scores[:] = 1
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.iloc[0].selected == tuple(sorted(NSE_STOCKS)[:2])


def test_unfilled_final_order_expires_without_invented_execution(synthetic):
    panel, scores, config = synthetic
    panel.volume[:] = 0
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.empty
    assert result.net_returns.eq(0).all()
    assert np.isnan(result.sharpe)
    assert result.ic_returns.empty
    assert any(log["status"] == "expired_at_cutoff" for log in result.order_log)


def test_missing_held_price_fails_instead_of_zero_return(synthetic):
    panel, scores, config = synthetic
    panel.close.loc["2021-01-12", NSE_STOCKS[0]] = np.nan
    with pytest.raises(ValueError, match="Missing held price on 2021-01-12"):
        simulate_portfolio(panel, scores, config=config)


def test_unheld_missing_price_and_insufficient_signal(synthetic):
    panel, scores, config = synthetic
    panel.close.loc["2021-01-12", NSE_STOCKS[7]] = np.nan
    scores.loc["2021-01-08", NSE_STOCKS[0]] = np.nan
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.iloc[0].signal_date == pd.Timestamp("2021-01-15")
    assert any(log["status"] == "signal_skipped" for log in result.order_log)


def test_missing_buy_price_defers_and_missing_volume_is_not_zero_filled(synthetic):
    panel, scores, config = synthetic
    panel.close.loc["2021-01-11", NSE_STOCKS[0]] = np.nan
    panel.volume.loc["2021-01-12", NSE_STOCKS[0]] = np.nan
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.iloc[0].execution_date == pd.Timestamp("2021-01-13")


def test_no_future_prices_or_scores_change_prior_trades(synthetic):
    panel, scores, config = synthetic
    first = simulate_portfolio(panel, scores, config=config)
    panel.close.loc["2021-01-20":] *= 1.3
    scores.loc["2021-01-20":] *= -1
    changed = simulate_portfolio(panel, scores, config=config)
    pd.testing.assert_series_equal(first.net_returns.loc[:"2021-01-19"],
                                   changed.net_returns.loc[:"2021-01-19"])
    pd.testing.assert_frame_equal(first.weights.loc[:"2021-01-19"],
                                  changed.weights.loc[:"2021-01-19"])


def test_execution_ic_labels_use_holding_intervals(synthetic):
    panel, scores, config = synthetic
    panel.close.loc["2021-01-18":, NSE_STOCKS[0]] = 110
    result = simulate_portfolio(panel, scores, config=config)
    assert result.ic_scores.index[0] == pd.Timestamp("2021-01-08")
    assert result.ic_returns.iloc[0, 0] == pytest.approx(.1)
    assert len(result.ic_returns) == len(result.executions) - 1
    assert result.ic_returns.index.equals(result.ic_scores.index)
    assert len(result.ic_returns.columns) == 8


def test_sharpe_independent_oracle_and_missing_values():
    returns = pd.Series([-.01, .02, .005, .03])
    expected = returns.mean() / returns.std(ddof=1) * np.sqrt(252)
    assert annualized_sharpe(returns) == pytest.approx(expected)
    daily_rf = 1.05 ** (1 / 252) - 1
    assert annualized_sharpe(returns, annual_risk_free=.05) == pytest.approx(
        (returns.mean() - daily_rf) / returns.std(ddof=1) * np.sqrt(252))
    assert np.isnan(annualized_sharpe(pd.Series([0., 0.])))
    assert np.isnan(annualized_sharpe(pd.Series([.03, .03, .03])))
    with pytest.raises(ValueError, match="missing/nonfinite"):
        annualized_sharpe(pd.Series([.01, np.nan]))


@pytest.mark.parametrize("changes", [
    {"end": "2025-01-01"}, {"end": "2025-10-01"}, {"top_n": 9},
    {"cost_bps": -1}, {"min_signal_names": 1}, {"rebalance_frequency": "D"},
    {"annual_risk_free": -1}, {"annualization": 0},
])
def test_invalid_configuration(changes):
    with pytest.raises(ValueError):
        PortfolioConfig(**changes)


def test_configuration_and_end_boundary(synthetic):
    panel, scores, config = synthetic
    config = replace(config, top_n=1, cost_bps=25, end="2021-01-18")
    result = simulate_portfolio(panel, scores, config=config)
    assert result.net_returns.index.max() == pd.Timestamp("2021-01-18")
    assert result.executions.iloc[0].cost_fraction == pytest.approx(.0025)
    assert result.weights.loc["2021-01-11", NSE_STOCKS[0]] == 1
    assert result.configuration["top_n"] == 1
    assert (result.executions.execution_date > result.executions.signal_date).all()


def test_missing_benchmark_blocks_complete_comparison(synthetic):
    panel, scores, config = synthetic
    panel.benchmark.iloc[2] = np.nan
    with pytest.raises(ValueError, match="benchmark close"):
        simulate_portfolio(panel, scores, config=config)


def test_verified_exclusions_preserve_special_sessions_and_flags():
    dates = pd.to_datetime(["2004-08-24", "2004-08-25", "2005-07-27",
                            "2005-07-28", "2005-07-29", "2015-02-28"])
    close = pd.DataFrame(100., index=dates, columns=NSE_STOCKS)
    close.loc["2005-07-29", NSE_STOCKS[0]] = 150
    panel = IndiaPanel(close, close * 10, pd.Series(100., index=dates), "adjusted")
    before = panel.close.copy(deep=True)
    view = prepare_research_view(panel)
    assert pd.Timestamp("2005-07-28") not in view.panel.close.index
    assert pd.Timestamp("2015-02-28") in view.panel.close.index
    assert np.isnan(view.panel.close.loc["2004-08-24", "TCS.NS"])
    assert view.panel.close.loc["2004-08-25", "TCS.NS"] == 100
    assert view.panel.close.loc["2005-07-29", NSE_STOCKS[0]] == 150
    assert "move_over_20pct" in view.flags.flag.tolist()
    assert len(view.ledger) == 2
    assert all(entry["evidence"].startswith("https://") for entry in view.ledger)
    pd.testing.assert_frame_equal(before, panel.close)


def test_special_saturday_remains_in_execution_calendar(synthetic):
    panel, scores, config = synthetic
    saturday = pd.Timestamp("2021-01-09")  # Synthetic declared special session.
    dates = panel.close.index.union(pd.DatetimeIndex([saturday]))
    panel = IndiaPanel(panel.close.reindex(dates).fillna(100),
                       panel.volume.reindex(dates).fillna(1000),
                       panel.benchmark.reindex(dates).fillna(100), "adjusted")
    scores = scores.reindex(dates).fillna(0)
    result = simulate_portfolio(panel, scores, config=config)
    assert result.executions.iloc[0].execution_date == saturday
    assert saturday in result.net_returns.index


def vibe_environment():
    interpreter = os.environ.get("VIBE_PYTHON")
    root = Path(os.environ.get("VIBE_TRADING_ROOT", "/home/jampip/vibe-Trading"))
    if not interpreter or not root.is_dir():
        pytest.skip("Set VIBE_PYTHON and provide Vibe checkout for integration")
    return root, interpreter


def test_actual_vibe_ic_on_execution_labels(synthetic):
    root, interpreter = vibe_environment()
    panel, scores, config = synthetic
    # Independently specified monotonic cross-sectional holding returns.
    panel.close.loc["2021-01-18":] *= np.linspace(1.08, 1.01, 8)
    result = simulate_portfolio(panel, scores, config=config)
    ic = compute_rank_ic(result.ic_scores, result.ic_returns,
                         vibe_root=root, python_executable=interpreter)
    assert ic.iloc[0] == pytest.approx(1)
    assert ic.index[0] == pd.Timestamp("2021-01-08")
    negative = compute_rank_ic(-result.ic_scores, result.ic_returns,
                               vibe_root=root, python_executable=interpreter)
    assert negative.iloc[0] == pytest.approx(-1)
    few = result.ic_returns.copy()
    few.iloc[:, :4] = np.nan
    assert compute_rank_ic(result.ic_scores, few, vibe_root=root,
                           python_executable=interpreter).empty


def test_original_strev_to_portfolio_composition_offline():
    root, interpreter = vibe_environment()
    dates = pd.bdate_range("2020-11-02", "2021-02-01")
    values = 100 + np.arange(len(dates))[:, None] * np.arange(1, 9)[None, :]
    close = pd.DataFrame(values, index=dates, columns=NSE_STOCKS, dtype=float)
    panel = IndiaPanel(close, close * 0 + 1000,
                       pd.Series(100., index=dates), "adjusted")
    result = backtest_strev(panel, vibe_root=root, python_executable=interpreter,
                            config=PortfolioConfig(end="2021-02-01"))
    assert not result.portfolio.executions.empty
    # Original STREV buys recent losers, not the strongest growth paths.
    assert result.portfolio.executions.iloc[0].selected == NSE_STOCKS[:2]
    assert not result.execution_ic.empty
    assert len(result.factor_source_sha256) == 3
