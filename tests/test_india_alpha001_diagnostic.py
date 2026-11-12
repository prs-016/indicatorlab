"""OFFLINE SYNTHETIC approval and tie-selection regressions; no real runs."""
from dataclasses import replace

import pandas as pd
import pytest

from src.india_alpha001_diagnostic import (DATASET_HASH, REVIEW_HASH,
    validate_alpha001_approval,selection_tie_audit)
from src.india_backtest import PortfolioConfig
from src.india_data import NSE_STOCKS


def args():
    return {'summary':{'discrepancy_count':0,'unverifiable_calendar_dates':0,
        'lookback_clock_mismatches':0,'warmup_complete':True,
        'expected_evaluation_sessions':990,'evaluation_start':'2021-01-04'},
        'approved':True,'dataset_hash':DATASET_HASH,'review_hash':REVIEW_HASH,
        'prior_sessions':25,'config':PortfolioConfig()}


def test_exact_approval_does_not_certify_calendar():
    original=args();result=validate_alpha001_approval(**original)
    assert result['factor']=='alpha101_001'
    assert not result['calendar_certified']
    assert not result['other_factors_authorized']
    assert not result['final_keep_drop_authorized']


@pytest.mark.parametrize('key,value',[
    ('approved',False),('factor','alpha101_002'),('dataset_hash','0'*64),
    ('review_hash','0'*64),('prior_sessions',21),
    ('config',replace(PortfolioConfig(),cost_bps=5))])
def test_approval_rejects_changed_scope_or_short_warmup(key,value):
    a=args();a[key]=value
    with pytest.raises(ValueError,match='Approval'):validate_alpha001_approval(**a)


@pytest.mark.parametrize('key,value',[
    ('discrepancy_count',1),('unverifiable_calendar_dates',1),
    ('lookback_clock_mismatches',8),('warmup_complete',False),
    ('expected_evaluation_sessions',989)])
def test_calendar_failures_cannot_be_waived(key,value):
    a=args();a['summary'][key]=value
    with pytest.raises(ValueError,match='validation'):validate_alpha001_approval(**a)


def test_all_name_tie_uses_alphabetical_membership_and_records_rejections():
    scores=pd.DataFrame(1.,index=pd.bdate_range('2021-01-04',periods=10),columns=NSE_STOCKS)
    audit=selection_tie_audit(scores)
    first=audit.iloc[0]
    assert first.selected==sorted(NSE_STOCKS)[:2]
    assert first.membership_depends_on_ticker and first.all_eight_tied
    assert len(first.cutoff_tie_pool)==8 and first.slots_at_cutoff==2
    assert len(first.rejected_from_cutoff_pool)==6
    assert first.can_stage_target
    assert not audit.iloc[-1].can_stage_target


def test_tie_among_both_winners_does_not_make_membership_ambiguous():
    scores=pd.DataFrame([[3,3,2,1,0,-1,-2,-3]]*10,index=pd.bdate_range('2021-01-04',periods=10),columns=NSE_STOCKS)
    first=selection_tie_audit(scores).iloc[0]
    assert first.selected==sorted(NSE_STOCKS[:2])
    assert not first.membership_depends_on_ticker
    assert first.slots_at_cutoff==2 and len(first.cutoff_tie_pool)==2


def test_one_strict_winner_cutoff_pool_assigns_one_ticker_slot():
    scores=pd.DataFrame([[3,2,2,2,0,-1,-2,-3]]*10,index=pd.bdate_range('2021-01-04',periods=10),columns=NSE_STOCKS)
    first=selection_tie_audit(scores).iloc[0]
    assert first.strictly_above_cutoff==[NSE_STOCKS[0]]
    assert first.slots_at_cutoff==1
    assert first.selected_from_cutoff_pool==[sorted(NSE_STOCKS[1:4])[0]]
    assert first.membership_depends_on_ticker


def test_missing_score_is_not_treated_as_a_tie_or_filled():
    scores=pd.DataFrame(1.,index=pd.bdate_range('2021-01-04',periods=10),columns=NSE_STOCKS)
    scores.loc[:,NSE_STOCKS[0]]=float('nan')
    audit=selection_tie_audit(scores)
    assert not audit.eligible.any() and not audit.can_stage_target.any()
