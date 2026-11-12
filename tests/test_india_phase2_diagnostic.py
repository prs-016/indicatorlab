"""OFFLINE SYNTHETIC approval/serialization regressions; no real-data backtests."""
from dataclasses import replace
import json

import numpy as np
import pandas as pd
import pytest

from src.india_backtest import PortfolioConfig, simulate_portfolio
from src.india_data import NSE_STOCKS, BENCHMARK, build_india_panel
from src.india_phase2_diagnostic import (
    APPROVED_FACTORS, APPROVAL_ID, DATASET_HASH, REVIEW_HASH, AUDIT_HASH,
    validate_phase2_approval, execution_trade_ledger, run_phase2_diagnostic,
)


@pytest.fixture
def evidence():
    return dict(approved=True, dataset_hash=DATASET_HASH, review_hash=REVIEW_HASH,
        audit_hash=AUDIT_HASH, config=PortfolioConfig(), prior_sessions=25,
        calendar_summary={'discrepancy_count': 0, 'unverifiable_calendar_dates': 0,
            'lookback_clock_mismatches': 0, 'warmup_complete': True,
            'expected_evaluation_sessions': 990, 'evaluation_start': '2021-01-04'},
        signal_summary={'finite_scores': 7920, 'nan_scores': 0, 'infinite_scores': 0,
            'weekly_candidates': 209, 'weekly_eight_finite': 209,
            'weekly_unique_top_two': 209, 'weekly_boundary_ties': 0},
        causal_checks=[{'passed': True, 'test': test} for test in
            ['prefix', 'prefix', 'prefix', 'minimum_window_final_row']],
        volume_verification={'status': 'passed', 'verified_changes': 12,
            'verified_quantity_anchors': 24, 'dataset_manifest_sha256': DATASET_HASH,
            'all_other_csv_tokens_and_line_endings_preserved': True})


@pytest.mark.parametrize('factor', APPROVED_FACTORS)
def test_four_factor_exception_is_narrow_and_provisional(evidence, factor):
    result = validate_phase2_approval(factor, **evidence)
    assert result['label'] == 'PROVISIONAL'
    assert not result['academic_illiq_authorized']
    assert not result['calendar_certified'] and not result['repeat_authorized']
    assert not result['final_keep_drop_authorized']


@pytest.mark.parametrize('factor', ['academic_illiq', 'academic_strev', 'alpha101_001'])
def test_other_factors_are_never_authorized(evidence, factor):
    with pytest.raises(ValueError, match='Approval does not cover'):
        validate_phase2_approval(factor, **evidence)


@pytest.mark.parametrize('key,value', [
    ('approved', False), ('dataset_hash', '0' * 64), ('review_hash', '0' * 64),
    ('audit_hash', '0' * 64), ('prior_sessions', 24),
    ('config', replace(PortfolioConfig(), cost_bps=0)),
])
def test_approval_rejects_evidence_or_baseline_drift(evidence, key, value):
    evidence[key] = value
    with pytest.raises(ValueError, match='Approval does not cover'):
        validate_phase2_approval('alpha101_033', **evidence)


@pytest.mark.parametrize('key,value', [
    ('discrepancy_count', 1), ('unverifiable_calendar_dates', 1),
    ('lookback_clock_mismatches', 1), ('warmup_complete', False),
])
def test_material_calendar_failures_cannot_be_waived(evidence, key, value):
    evidence['calendar_summary'][key] = value
    with pytest.raises(ValueError, match='calendar validation'):
        validate_phase2_approval('alpha101_033', **evidence)


@pytest.mark.parametrize('key,value', [('nan_scores', 1), ('weekly_unique_top_two', 208)])
def test_missing_or_tied_signals_require_new_review(evidence, key, value):
    evidence['signal_summary'][key] = value
    with pytest.raises(ValueError, match='Signal readiness'):
        validate_phase2_approval('alpha101_014', **evidence)


def test_failed_or_missing_causal_check_stops_before_scoring(evidence):
    evidence['causal_checks'][0]['passed'] = False
    with pytest.raises(ValueError, match='No-look-ahead'):
        validate_phase2_approval('alpha101_101', **evidence)
    evidence['causal_checks'] = []
    with pytest.raises(ValueError, match='No-look-ahead'):
        validate_phase2_approval('alpha101_101', **evidence)


def test_unverified_volume_anchors_are_rejected(evidence):
    evidence['volume_verification']['verified_quantity_anchors'] = 23
    with pytest.raises(ValueError, match='quantity/provenance'):
        validate_phase2_approval('alpha101_014', **evidence)


@pytest.mark.parametrize('factor,approved', [('academic_illiq', True), ('alpha101_033', False)])
def test_runner_rejects_scope_before_loading_any_real_evidence(factor, approved):
    with pytest.raises(ValueError, match='Only four'):
        run_phase2_diagnostic(factor, approved=approved)


def test_runner_refuses_reuse_of_this_approval(tmp_path, monkeypatch):
    from src import india_phase2_diagnostic as module
    approval = tmp_path / 'results/india_alpha101_033_PROVISIONAL_SYNTHETIC/diagnostic_approval.json'
    approval.parent.mkdir(parents=True)
    approval.write_text(json.dumps({'approval_id': APPROVAL_ID}))
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='already used'):
        run_phase2_diagnostic('alpha101_033', approved=True)


@pytest.fixture
def synthetic_portfolio():
    idx = pd.bdate_range('2021-01-04', periods=20)
    histories = {s: pd.DataFrame({'close': 100 + np.arange(20) * (i + 1),
                 'volume': 10000.}, index=idx) for i, s in enumerate(NSE_STOCKS)}
    histories[BENCHMARK] = pd.DataFrame({'close': 100 + np.arange(20)}, index=idx)
    panel = build_india_panel(histories, close_basis='adjusted')
    scores = pd.DataFrame(np.tile(np.arange(8), (20, 1)), index=idx, columns=NSE_STOCKS)
    config = PortfolioConfig()
    return panel, simulate_portfolio(panel, scores, config=config), config


def test_trade_serialization_reconciles_drift_initial_cash_and_ten_bps(synthetic_portfolio):
    panel, portfolio, config = synthetic_portfolio
    ledger = execution_trade_ledger(panel, portfolio, config)
    assert (ledger.signal_date < ledger.execution_date).all()
    assert np.isclose(ledger.cost_fraction.sum(), portfolio.costs.sum())
    assert np.isclose(ledger.signed_nav_weight_change.abs().sum(), portfolio.turnover.sum())
    assert np.isclose(ledger[ledger.execution_date.eq(ledger.execution_date.min())].signed_nav_weight_change.abs().sum(), 1)


@pytest.mark.parametrize('invalid_date', ['2021-01-08', '2025-01-01'])
def test_same_close_and_post_cutoff_execution_labels_are_rejected(synthetic_portfolio, invalid_date):
    panel, portfolio, config = synthetic_portfolio
    portfolio.executions.loc[0, 'execution_date'] = pd.Timestamp(invalid_date)
    with pytest.raises(ValueError, match='causal/cutoff'):
        execution_trade_ledger(panel, portfolio, config)


def test_optional_causal_csv_fields_are_json_null_not_nan(tmp_path):
    from src.india_phase2_diagnostic import _read_causal_checks
    path = tmp_path / 'SYNTHETIC_causal_checks.csv'
    path.write_text('factor,test,date,passed,sessions,max_abs_difference\n'
                    'alpha101_033,prefix,2022-12-30,True,,\n'
                    'alpha101_033,minimum_window_final_row,,True,1,0\n')
    rows = _read_causal_checks(path, 'alpha101_033')
    json.dumps(rows, allow_nan=False)
    assert rows[0]['sessions'] is None
    assert rows[1]['date'] is None
    assert all(row['passed'] for row in rows)


def test_only_documented_preflight_failure_can_retry_before_any_factor_call(tmp_path, monkeypatch):
    from src import india_phase2_diagnostic as module
    dest = tmp_path / 'results/india_alpha101_033_PROVISIONAL_SYNTHETIC'
    dest.mkdir(parents=True)
    (dest / 'diagnostic_approval.json').write_text(json.dumps({'approval_id': APPROVAL_ID}))
    (dest / 'status.json').write_text(json.dumps({'status': 'preflight_failed_factor_not_invoked',
        'factor_invocations': 0, 'portfolio_evaluations': 0}))
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    def stop_at_evidence(*args):
        raise RuntimeError('SYNTHETIC stop before evidence/scoring')
    monkeypatch.setattr(module, '_verify_inventory', stop_at_evidence)
    with pytest.raises(RuntimeError, match='SYNTHETIC stop'):
        run_phase2_diagnostic('alpha101_033', approved=True)
    (dest / 'factor_scores.csv').write_text('SYNTHETIC marker: invocation already occurred')
    with pytest.raises(ValueError, match='already used'):
        run_phase2_diagnostic('alpha101_033', approved=True)
