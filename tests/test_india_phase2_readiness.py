"""OFFLINE SYNTHETIC tests for signal-only audit attribution and instrumentation."""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.india_data import NSE_STOCKS
from src.india_phase2_factors import PHASE2_SPECS
from src.india_phase2_readiness import (
    original_diagnostic_scores, input_and_missing_audit, selection_summary,
)


@pytest.fixture
def fields():
    """Invented OHLCV; dates are not a certified NSE calendar."""
    idx = pd.bdate_range('2020-12-01', periods=65)
    rng = np.random.default_rng(2610)
    close = pd.DataFrame(np.exp(rng.normal(0, .015, (65, 8)).cumsum(0))
                         * np.arange(100, 180, 10), index=idx, columns=NSE_STOCKS)
    op = close * (1 + rng.normal(0, .01, close.shape))
    return {'close': close, 'open': op, 'high': np.maximum(close, op) * 1.01,
            'low': np.minimum(close, op) * .99,
            'volume': pd.DataFrame(rng.integers(100, 10000, close.shape),
                                  index=idx, columns=NSE_STOCKS, dtype=float)}


def original(fields, factor):
    if 'VIBE_PYTHON' not in os.environ:
        pytest.skip('Set VIBE_PYTHON for original isolated Vibe tests')
    root = Path(os.environ.get('VIBE_TRADING_ROOT', '/home/jampip/vibe-Trading'))
    if not root.is_dir():
        pytest.skip('Original Vibe checkout unavailable')
    return original_diagnostic_scores(
        fields, factor, basis_label='OFFLINE_SYNTHETIC_not_market_data',
        vibe_root=root, python_executable=os.environ['VIBE_PYTHON'])


@pytest.mark.parametrize('factor', PHASE2_SPECS)
def test_original_raw_numerics_and_missing_causes_cover_every_synthetic_cell(fields, factor):
    scores, meta = original(fields, factor)
    detail = input_and_missing_audit(fields, factor, scores)
    assert len(detail) == scores.size
    assert meta['numerical']['infinite'] == 0
    assert meta['numerical']['nan'] == int(scores.isna().sum().sum())
    assert not detail.cause.eq('unexplained').any()
    assert detail.cause.eq('warmup').sum() == (PHASE2_SPECS[factor].warmup_bars - 1) * 8
    summary, profiles = selection_summary(scores)
    assert summary['nan_scores'] == 0
    assert summary['weekly_eight_finite'] == len(profiles)
    assert not profiles[-1]['has_later_evaluation_session']


def test_zero_volume_propagates_exact_21_session_window_without_filling(fields):
    symbol = NSE_STOCKS[0]
    fields['volume'].iloc[30, 0] = 0
    scores, _ = original(fields, 'academic_illiq')
    detail = input_and_missing_audit(fields, 'academic_illiq', scores)
    affected = detail[(detail.symbol == symbol) & detail.date.isin(scores.index[30:51])]
    assert len(affected) == 21
    assert affected.cause.eq('incomplete_window_including_zero_turnover').all()
    assert scores.iloc[30:51, 0].isna().all()
    assert np.isfinite(scores.iloc[51, 0])


def test_flat_range_denominator_is_attributed_without_score_replacement(fields):
    for key in ['open', 'high', 'low']:
        fields[key].iloc[40, 0] = fields['close'].iloc[40, 0]
    scores, _ = original(fields, 'alpha101_054')
    detail = input_and_missing_audit(fields, 'alpha101_054', scores)
    row = detail[(detail.symbol == NSE_STOCKS[0]) & (detail.date == scores.index[40])].iloc[0]
    assert row.cause == 'zero_denominator'
    assert pd.isna(row.score)


def test_constant_unranked_correlation_window_has_explicit_cause(fields):
    fields['volume'].iloc[25:35, 0] = 100
    scores, _ = original(fields, 'alpha101_014')
    detail = input_and_missing_audit(fields, 'alpha101_014', scores)
    row = detail[(detail.symbol == NSE_STOCKS[0]) & (detail.date == scores.index[34])].iloc[0]
    assert row.cause == 'constant_raw_correlation_window'


def test_boundary_tie_counts_membership_ambiguity_including_terminal():
    idx = pd.to_datetime(['2021-01-08', '2021-01-15'])
    scores = pd.DataFrame([[9, 8, 8, 6, 5, 4, 3, 2], [1] * 8], index=idx, columns=NSE_STOCKS)
    summary, profiles = selection_summary(scores)
    assert summary['weekly_boundary_ties'] == 2
    assert summary['weekly_unique_top_two'] == 0
    assert profiles[0]['admissible_pair_count'] == 2
    assert profiles[1]['admissible_pair_count'] == 28
    assert summary['nonterminal_eligible'] == 1


def test_missing_and_infinite_names_are_ineligible_without_fills():
    scores = pd.DataFrame(1., index=pd.to_datetime(['2021-01-08', '2021-01-15']), columns=NSE_STOCKS)
    scores.iloc[0, 0] = np.nan
    scores.iloc[1, 0] = np.inf
    summary, profiles = selection_summary(scores)
    assert summary['weekly_eight_finite'] == 0
    assert summary['nan_scores'] == 1 and summary['infinite_scores'] == 1
    assert not any(p['eligible'] for p in profiles)


def test_invalid_input_is_rejected_before_worker(fields):
    fields['close'].iloc[0, 0] = np.inf
    with pytest.raises(ValueError, match='Invalid diagnostic input'):
        original_diagnostic_scores(fields, 'alpha101_033', basis_label='synthetic',
                                   vibe_root='/nonexistent', python_executable='/nonexistent')


def test_unlabelled_alternative_basis_is_rejected(fields):
    with pytest.raises(ValueError, match='explicit diagnostic basis'):
        original_diagnostic_scores(fields, 'academic_illiq', basis_label='',
                                   vibe_root='/nonexistent', python_executable='/nonexistent')


def test_zero_illiquidity_dispersion_is_visible_and_never_filled(fields):
    fields['close'].loc[:, :] = 100.
    scores, _ = original(fields, 'academic_illiq')
    detail = input_and_missing_audit(fields, 'academic_illiq', scores)
    assert scores.isna().all().all()
    assert detail[detail.date.ge(scores.index[21])].cause.eq('zero_cross_sectional_dispersion').all()
    assert selection_summary(scores)[0]['weekly_eight_finite'] == 0
