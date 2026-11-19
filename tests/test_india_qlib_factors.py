"""OFFLINE SYNTHETIC Qlib158 regressions; fixtures are not financial evidence."""
from dataclasses import replace
import sys

import numpy as np
import pandas as pd
import pytest

from test_india_phase2_factors import histories, runtime  # reuse synthetic fixture
from src.india_backtest import PortfolioConfig, simulate_portfolio
from src.india_data import NSE_STOCKS
from src.india_factors import build_factor_panel
from src.india_qlib_factors import (
    QLIB_SPECS, evaluate_qlib_factor, missing_score_causes, readiness_gate,
)


def oracle(fields, factor):
    """Independent test-only expressions; production invokes original Vibe code."""
    c, h, l, v = [fields[k] for k in ('close', 'high', 'low', 'volume')]
    safe = lambda a, b: a.div(b + 1e-12 * np.sign(b)).replace([np.inf, -np.inf], np.nan)
    if factor == 'qlib158_std20':
        return safe(c.rolling(20).std(ddof=1), c)
    if factor == 'qlib158_rsv20':
        return safe(c - l.rolling(20).min(), h.rolling(20).max() - l.rolling(20).min())
    if factor == 'qlib158_sump20':
        delta = c.diff()
        return safe(delta.clip(lower=0).fillna(0).rolling(20).sum(), delta.abs().rolling(20).sum())
    if factor == 'qlib158_wvma20':
        x = (safe(c, c.shift()) - 1).abs() * v
        return safe(x.rolling(20).std(ddof=1), x.rolling(20).mean())
    return safe(c, c.shift()).rolling(10).corr(np.log(safe(v + 1, v.shift() + 1)))


@pytest.mark.parametrize('factor', QLIB_SPECS)
def test_original_formula_metadata_effective_window_and_isolation(histories, factor):
    panel = build_factor_panel(histories, close_basis='adjusted')
    scores, evidence = evaluate_qlib_factor(panel, factor, **runtime())
    expected = oracle(panel.fields, factor)
    pd.testing.assert_frame_equal(scores, expected, check_freq=False, atol=1e-10, rtol=1e-9)
    leading = QLIB_SPECS[factor].effective_rows - 1
    assert scores.iloc[:leading].isna().all().all()
    assert scores.iloc[leading].notna().all()
    assert evidence['metadata']['min_warmup_bars'] == QLIB_SPECS[factor].original.warmup_bars
    assert evidence['numerical']['infinite'] == 0
    causes = missing_score_causes(panel.fields, factor, scores)
    assert len(causes) == leading * 8
    assert causes.cause.eq('warmup').all()
    assert 'src.factors' not in sys.modules


@pytest.mark.parametrize('factor', QLIB_SPECS)
def test_future_changes_and_rolling_prefix_do_not_change_past(histories, factor):
    kwargs = runtime()
    panel = build_factor_panel(histories, close_basis='adjusted')
    scores, _ = evaluate_qlib_factor(panel, factor, **kwargs)
    boundary = scores.index[50]
    for symbol in NSE_STOCKS:
        future = histories[symbol].index > boundary
        histories[symbol].loc[future, ['open', 'high', 'low', 'close']] *= 2
        histories[symbol].loc[future, 'volume'] *= 7
    changed, _ = evaluate_qlib_factor(build_factor_panel(histories, close_basis='adjusted'), factor, **kwargs)
    pd.testing.assert_frame_equal(scores.loc[:boundary], changed.loc[:boundary])
    # A truncated input prefix must produce the same trailing window at the boundary.
    prefix = {s: frame.loc[:boundary].copy() for s, frame in histories.items()}
    short, _ = evaluate_qlib_factor(build_factor_panel(prefix, close_basis='adjusted'), factor, **kwargs)
    pd.testing.assert_frame_equal(scores.loc[:boundary], short)


@pytest.mark.parametrize('factor', QLIB_SPECS)
def test_cached_scores_execution_costs_labels_and_benchmark(histories, factor):
    panel = build_factor_panel(histories, close_basis='adjusted')
    scores, _ = evaluate_qlib_factor(panel, factor, **runtime())
    config = PortfolioConfig()
    p = simulate_portfolio(panel.portfolio_panel, scores, config=config)
    assert (p.executions.execution_date > p.executions.signal_date).all()
    assert p.configuration == config.__dict__
    np.testing.assert_allclose(p.costs, .001 * p.turnover)
    np.testing.assert_allclose(p.net_returns, (1 + p.gross_returns) * (1 - p.costs) - 1)
    for a, b in zip(p.executions.itertuples(), p.executions.iloc[1:].itertuples()):
        np.testing.assert_allclose(p.ic_returns.loc[a.signal_date],
            panel.fields['close'].loc[b.execution_date] / panel.fields['close'].loc[a.execution_date] - 1)
    benchmark = panel.portfolio_panel.benchmark.loc[p.net_returns.index].pct_change(fill_method=None)
    benchmark.iloc[0] = 0
    np.testing.assert_allclose(p.benchmark_returns, benchmark)
    # Alter scores after a boundary: earlier orders/returns must remain identical.
    future = scores.copy()
    future.loc[future.index > scores.index[50]] *= -1
    alternate = simulate_portfolio(panel.portfolio_panel, future, config=config)
    pd.testing.assert_series_equal(p.net_returns.loc[:scores.index[50]],
                                   alternate.net_returns.loc[:scores.index[50]])


@pytest.mark.parametrize('factor', QLIB_SPECS)
def test_missing_dependency_observation_propagates_full_window(histories, factor):
    for symbol in NSE_STOCKS:
        histories[symbol].loc[histories[symbol].index[40],
                              'high' if factor == 'qlib158_rsv20' else 'close'] = np.nan
    panel = build_factor_panel(histories, close_basis='adjusted')
    scores, _ = evaluate_qlib_factor(panel, factor, **runtime())
    end = 40 + QLIB_SPECS[factor].effective_rows
    assert scores.iloc[40:end].isna().all().all()
    assert scores.iloc[end].notna().all()
    causes = missing_score_causes(panel.fields, factor, scores)
    assert not causes.cause.eq('unexplained').any()


@pytest.mark.parametrize('factor', ['qlib158_rsv20', 'qlib158_sump20', 'qlib158_cord10'])
def test_constant_windows_preserve_original_undefined_values(histories, factor):
    for symbol in NSE_STOCKS:
        histories[symbol].loc[:, ['open', 'high', 'low', 'close']] = 100.
        histories[symbol].loc[:, 'volume'] = 1000.
    panel = build_factor_panel(histories, close_basis='adjusted')
    scores, evidence = evaluate_qlib_factor(panel, factor, **runtime())
    assert scores.isna().all().all()
    causes = missing_score_causes(panel.fields, factor, scores)
    assert not causes.cause.eq('unexplained').any()
    _, _, blockers = readiness_gate(scores, evidence, causes)
    assert blockers


def test_zero_volume_is_not_illiq_zero_denominator(histories):
    for symbol in NSE_STOCKS:
        histories[symbol].loc[histories[symbol].index[40], 'volume'] = 0
    panel = build_factor_panel(histories, close_basis='adjusted')
    for factor in ('qlib158_wvma20', 'qlib158_cord10'):
        scores, _ = evaluate_qlib_factor(panel, factor, **runtime())
        assert scores.iloc[40:62].notna().all().all()


def test_allowlist_alignment_dependency_and_source_gates(histories, tmp_path):
    panel = build_factor_panel(histories, close_basis='adjusted')
    with pytest.raises(ValueError, match='approved'):
        evaluate_qlib_factor(panel, 'alpha101_001', vibe_root=tmp_path)
    bad = build_factor_panel(histories, close_basis='adjusted')
    del bad.fields['volume']
    with pytest.raises(ValueError, match='dependencies'):
        evaluate_qlib_factor(bad, 'qlib158_cord10', vibe_root=tmp_path)
    panel.fields['close'].loc[pd.Timestamp('2025-10-01')] = 100.
    with pytest.raises(ValueError):
        evaluate_qlib_factor(panel, 'qlib158_std20', vibe_root=tmp_path)


def test_rsv_missing_current_close_does_not_invent_rolling_close_dependency(histories):
    for symbol in NSE_STOCKS:
        histories[symbol].loc[histories[symbol].index[40], 'close'] = np.nan
    panel = build_factor_panel(histories, close_basis='adjusted')
    scores, _ = evaluate_qlib_factor(panel, 'qlib158_rsv20', **runtime())
    assert scores.iloc[40].isna().all()
    assert scores.iloc[41].notna().all()


@pytest.mark.parametrize('change', ['approval', 'dataset', 'review', 'costs', 'warmup',
                                     'gap', 'unknown_calendar_date', 'clock'])
def test_scope_never_globally_disables_calendar_or_approved_settings(change):
    from src.india_qlib_diagnostic import validate_scope, DATASET_HASH, REVIEW_HASH
    kwargs = dict(approved=True, dataset_hash=DATASET_HASH, review_hash=REVIEW_HASH,
        config=PortfolioConfig(), prior_sessions=25,
        calendar_summary={'discrepancy_count': 0, 'unverifiable_calendar_dates': 0,
            'lookback_clock_mismatches': 0, 'warmup_complete': True,
            'expected_evaluation_sessions': 990, 'evaluation_start': '2021-01-04'})
    assert validate_scope(**kwargs)['calendar_certified'] is False
    if change == 'approval': kwargs['approved'] = False
    elif change == 'dataset': kwargs['dataset_hash'] = '0' * 64
    elif change == 'review': kwargs['review_hash'] = '0' * 64
    elif change == 'costs': kwargs['config'] = replace(PortfolioConfig(), cost_bps=0)
    elif change == 'warmup': kwargs['prior_sessions'] = 24
    else:
        key = {'gap': 'discrepancy_count', 'unknown_calendar_date': 'unverifiable_calendar_dates',
               'clock': 'lookback_clock_mismatches'}[change]
        kwargs['calendar_summary'][key] = 1
    with pytest.raises(ValueError): validate_scope(**kwargs)


def test_wvma_constant_volume_unit_scaling_cancels_but_cord_plus_one_is_retained(histories):
    panel = build_factor_panel(histories, close_basis='adjusted')
    kwargs = runtime()
    wvma, _ = evaluate_qlib_factor(panel, 'qlib158_wvma20', **kwargs)
    cord, _ = evaluate_qlib_factor(panel, 'qlib158_cord10', **kwargs)
    for symbol in NSE_STOCKS:
        histories[symbol]['volume'] *= .001  # deliberately tiny SYNTHETIC volume units
    altered = build_factor_panel(histories, close_basis='adjusted')
    new_wvma, _ = evaluate_qlib_factor(altered, 'qlib158_wvma20', **kwargs)
    new_cord, _ = evaluate_qlib_factor(altered, 'qlib158_cord10', **kwargs)
    np.testing.assert_allclose(wvma, new_wvma, equal_nan=True, atol=1e-10)
    assert (cord - new_cord).abs().max().max() > 1e-4
