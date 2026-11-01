"""OFFLINE SYNTHETIC regression cases for the narrowly scoped diagnostic gate."""
from dataclasses import replace

import pytest

from src.india_backtest import PortfolioConfig
from src.india_diagnostic import DATASET_HASH, REVIEW_HASH, validate_diagnostic_override


def arguments():
    # Synthetic audit summary; no real data or backtest is executed here.
    return dict(summary={'warmup_complete':True,'warmup_sessions':21,
        'warmup_start':'2020-12-03','warmup_end':'2021-01-01',
        'evaluation_start':'2021-01-04','expected_evaluation_sessions':990,
        'discrepancy_count':0,'unverifiable_calendar_dates':0,
        'lookback_clock_mismatches':0,'calendar_certified':False,
        'amendment_coverage_confirmed':False},dataset_hash=DATASET_HASH,
        review_hash=REVIEW_HASH,approved=True,strategy='academic_strev',config=PortfolioConfig())


def test_waives_only_inventory_certainty_and_does_not_mutate_audit():
    args=arguments(); before=args['summary'].copy()
    result=validate_diagnostic_override(**args)
    assert result['label']=='PROVISIONAL'
    assert not result['calendar_certified']
    assert not result['final_evaluation_authorized']
    assert result['all_structural_validations_retained']
    assert args['summary']==before


@pytest.mark.parametrize('field,value',[
    ('approved',False),('strategy','alpha101_001'),('dataset_hash','0'*64),
    ('review_hash','0'*64),('config',replace(PortfolioConfig(),cost_bps=0)),
    ('config',replace(PortfolioConfig(),start='2022-01-03')),
])
def test_approval_cannot_be_reused_for_other_scope(field,value):
    args=arguments();args[field]=value
    with pytest.raises(ValueError,match='approval'):
        validate_diagnostic_override(**args)


@pytest.mark.parametrize('field,value',[
    ('discrepancy_count',1),('lookback_clock_mismatches',8),
    ('unverifiable_calendar_dates',1),('warmup_complete',False),
    ('warmup_sessions',20),('warmup_start','2020-12-04'),
    ('expected_evaluation_sessions',989),('evaluation_start','2021-01-01'),
])
def test_override_never_waives_material_validation(field,value):
    args=arguments();args['summary'][field]=value
    with pytest.raises(ValueError,match='validation failed'):
        validate_diagnostic_override(**args)


def test_incomplete_summary_is_rejected():
    args=arguments();del args['summary']['discrepancy_count']
    with pytest.raises(ValueError):
        validate_diagnostic_override(**args)
