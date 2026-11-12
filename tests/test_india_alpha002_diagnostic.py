"""OFFLINE SYNTHETIC #2 approval/provenance boundary regressions."""
from dataclasses import replace
import pytest

from src.india_alpha002_diagnostic import (DATASET_HASH,REVIEW_HASH,PACKAGE_HASH,
    validate_alpha002_approval)
from src.india_backtest import PortfolioConfig


def args():
    return {'summary':{'discrepancy_count':0,'unverifiable_calendar_dates':0,
        'lookback_clock_mismatches':0,'warmup_complete':True,
        'expected_evaluation_sessions':990,'evaluation_start':'2021-01-04'},
        'verification':{'status':'passed','verified_changes':12,'verified_quantity_anchors':24,
            'all_other_csv_tokens_and_line_endings_preserved':True,'dataset_manifest_sha256':DATASET_HASH},
        'approved':True,'dataset_hash':DATASET_HASH,'review_hash':REVIEW_HASH,
        'package_hash':PACKAGE_HASH,'config':PortfolioConfig(),'prior_sessions':25}


def test_exact_approval_is_diagnostic_only():
    result=validate_alpha002_approval(**args())
    assert result['factor']=='alpha101_002'
    assert not result['calendar_certified']
    assert not result['other_real_factors_authorized']
    assert not result['repeat_run_authorized']
    assert not result['final_keep_drop_authorized']


@pytest.mark.parametrize('key,value',[
    ('approved',False),('factor','alpha101_003'),('dataset_hash','0'*64),
    ('review_hash','0'*64),('package_hash','0'*64),('prior_sessions',21),
    ('config',replace(PortfolioConfig(),cost_bps=0)),
    ('config',replace(PortfolioConfig(),start='2022-01-03'))])
def test_approval_cannot_cover_changed_scope(key,value):
    a=args();a[key]=value
    with pytest.raises(ValueError,match='Approval'):validate_alpha002_approval(**a)


@pytest.mark.parametrize('key,value',[
    ('discrepancy_count',1),('unverifiable_calendar_dates',1),
    ('lookback_clock_mismatches',8),('expected_evaluation_sessions',989)])
def test_material_calendar_failures_are_not_waived(key,value):
    a=args();a['summary'][key]=value
    with pytest.raises(ValueError,match='calendar'):validate_alpha002_approval(**a)


@pytest.mark.parametrize('key,value',[
    ('status','failed'),('verified_changes',11),('verified_quantity_anchors',23),
    ('all_other_csv_tokens_and_line_endings_preserved',False)])
def test_volume_evidence_failures_are_not_waived(key,value):
    a=args();a['verification'][key]=value
    with pytest.raises(ValueError,match='provenance'):validate_alpha002_approval(**a)
