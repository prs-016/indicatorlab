"""OFFLINE SYNTHETIC tests for the separately approved ILLIQ diagnostic scope."""
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.india_backtest import PortfolioConfig
from src.india_phase2_factors import TurnoverBasisEvidence, PROXY_INTERPRETATION
from src.india_illiq_diagnostic import (
    DATASET_HASH, REVIEW_HASH, AUDIT_HASH, validate_illiq_approval,
    run_illiq_diagnostic, _verify_proxy_records,
)


@pytest.fixture
def evidence():
    basis = TurnoverBasisEvidence('INR', PROXY_INTERPRETATION, 'a'*64,
        'OFFLINE_SYNTHETIC_evidence', 'b'*64, True, 'OFFLINE_SYNTHETIC')
    return dict(approved=True, dataset_hash=DATASET_HASH, review_hash=REVIEW_HASH,
        audit_hash=AUDIT_HASH, config=PortfolioConfig(), prior_sessions=25,
        calendar_summary={'discrepancy_count': 0, 'unverifiable_calendar_dates': 0,
            'lookback_clock_mismatches': 0, 'warmup_complete': True,
            'expected_evaluation_sessions': 990, 'evaluation_start': '2021-01-04'},
        signal_summary={'finite_scores': 7920, 'nan_scores': 0, 'infinite_scores': 0,
            'weekly_candidates': 209, 'weekly_eight_finite': 209,
            'weekly_unique_top_two': 209, 'weekly_boundary_ties': 0},
        causal_checks=[{'passed': True, 'test': t} for t in
            ['prefix', 'prefix', 'prefix', 'minimum_window_final_row']],
        volume_verification={'status': 'passed', 'verified_changes': 12,
            'verified_quantity_anchors': 24, 'dataset_manifest_sha256': DATASET_HASH,
            'all_other_csv_tokens_and_line_endings_preserved': True},
        turnover_basis=basis, expected_panel_hash='a'*64,
        sensitivity_counts={'dividend_sensitive': 51, 'normalization_sensitive': 31})


def test_illiq_permission_records_proxy_exception_and_never_generalizes(evidence):
    result = validate_illiq_approval('academic_illiq', **evidence)
    assert result['label'] == 'PROVISIONAL'
    assert not result['proxy_is_actual_turnover']
    assert 'developer-approved' in result['india_metadata_exception_authority']
    assert not result['calendar_certified'] and not result['repeat_authorized']
    assert not result['other_factors_authorized'] and not result['final_keep_drop_authorized']
    assert result['sensitivity_counts'] == evidence['sensitivity_counts']


@pytest.mark.parametrize('factor', ['academic_strev', 'alpha101_033', 'alpha101_014'])
def test_other_factors_are_rejected(evidence, factor):
    with pytest.raises(ValueError, match='ILLIQ approval'):
        validate_illiq_approval(factor, **evidence)


@pytest.mark.parametrize('key,value', [
    ('approved', False), ('dataset_hash', '0'*64), ('review_hash', '0'*64),
    ('audit_hash', '0'*64), ('prior_sessions', 24),
    ('config', replace(PortfolioConfig(), cost_bps=0)),
])
def test_scope_and_baseline_are_bound(evidence, key, value):
    evidence[key] = value
    with pytest.raises(ValueError, match='ILLIQ approval'):
        validate_illiq_approval('academic_illiq', **evidence)


@pytest.mark.parametrize('change', ['absent', 'currency', 'interpretation', 'panel', 'unsupported'])
def test_turnover_proxy_basis_cannot_be_assumed_or_substituted(evidence, change):
    basis = evidence['turnover_basis']
    if change == 'absent':
        evidence['turnover_basis'] = None
    else:
        delta = {'currency': {'currency': 'USD'}, 'interpretation': {'interpretation': 'actual_exchange_turnover'},
                 'panel': {'panel_sha256': 'c'*64}, 'unsupported': {'supported': False}}[change]
        evidence['turnover_basis'] = replace(basis, **delta)
    with pytest.raises(ValueError, match='turnover proxy'):
        validate_illiq_approval('academic_illiq', **evidence)


@pytest.mark.parametrize('key', ['dividend_sensitive', 'normalization_sensitive'])
def test_original_sensitivity_disclosures_are_required(evidence, key):
    evidence['sensitivity_counts'][key] = 0
    with pytest.raises(ValueError, match='sensitivity evidence'):
        validate_illiq_approval('academic_illiq', **evidence)


@pytest.mark.parametrize('kind', ['calendar', 'causality', 'quantity'])
def test_material_data_or_clock_failures_cannot_be_waived(evidence, kind):
    if kind == 'calendar':
        evidence['calendar_summary']['discrepancy_count'] = 1
    elif kind == 'causality':
        evidence['causal_checks'][0]['passed'] = False
    else:
        evidence['volume_verification']['verified_quantity_anchors'] = 23
    with pytest.raises(ValueError):
        validate_illiq_approval('academic_illiq', **evidence)


def test_runner_requires_explicit_approval_before_any_evidence_load():
    with pytest.raises(ValueError, match='Explicit approval'):
        run_illiq_diagnostic(approved=False)


def test_prior_illiq_invocation_blocks_repeat(tmp_path, monkeypatch):
    from src import india_illiq_diagnostic as module
    path = tmp_path/'results/india_academic_illiq_PROVISIONAL_SYNTHETIC/diagnostic_approval.json'
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='already used'):
        run_illiq_diagnostic(approved=True)


@pytest.mark.parametrize('changed_volume', [False, True])
def test_current_proxy_must_match_hashed_synthetic_record(tmp_path, changed_volume):
    source = tmp_path/'OFFLINE_SYNTHETIC_source.csv'
    source.write_text('clearly invented official-record stand-in\n')
    record = tmp_path/'OFFLINE_SYNTHETIC_proxy.csv'
    pd.DataFrame([{'date': '2021-01-04', 'symbol': 'SYNTHETIC',
        'source_file': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'expected_proxy_inr': 100000}]).to_csv(record, index=False)
    idx = pd.to_datetime(['2021-01-04'])
    panel = SimpleNamespace(fields={
        'close': pd.DataFrame({'SYNTHETIC': [100.]}, index=idx),
        'volume': pd.DataFrame({'SYNTHETIC': [2000. if changed_volume else 1000.]}, index=idx)})
    if changed_volume:
        with pytest.raises(ValueError, match='differs from verified'):
            _verify_proxy_records(panel, record)
    else:
        checked = _verify_proxy_records(panel, record)
        assert checked['checked_records'] == 1 and checked['failed_records'] == 0
        assert not checked['proxy_is_actual_exchange_turnover']
