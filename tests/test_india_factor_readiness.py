"""OFFLINE SYNTHETIC signal-only audit regressions; no portfolios or market data."""
import numpy as np
import pandas as pd
import pytest

from src.india_factor_readiness import (signal_coverage,missing_causes,compare_scores,
                                       classify_volume_ratio)


def frame(values):
    return pd.DataFrame(values,index=pd.bdate_range('2021-01-04',periods=len(values)),columns=list('ABCDEFGH'))


def test_coverage_distinguishes_nan_ties_and_eight_name_eligibility():
    scores=frame([[1]*8,[8,7,7,5,4,3,2,1],[np.nan]*8,[8,7,6,5,4,3,2,np.nan]])
    summary,daily=signal_coverage(scores)
    assert summary['finite_cells']==23 and summary['missing_cells']==9
    assert summary['all_eight_finite_sessions']==2
    assert summary['all_missing_sessions']==1
    assert summary['sessions_all_eight_tied']==1
    assert daily.iloc[1].top_two_boundary_exact_tie
    assert not daily.iloc[3].top_two_boundary_exact_tie


def test_near_ties_are_diagnostic_not_score_replacement():
    scores=frame([[8,7,7-1e-12,5,4,3,2,1]])
    original=scores.copy();_,daily=signal_coverage(scores)
    assert not daily.iloc[0].top_two_boundary_exact_tie
    assert daily.iloc[0].top_two_boundary_near_tie
    pd.testing.assert_frame_equal(scores,original)


def test_comparison_counts_availability_separately_from_top_two():
    b=frame([[8,7,6,5,4,3,2,1],[8,7,6,5,4,3,2,1]])
    a=b.copy();a.iloc[0]=[1,2,3,4,5,6,7,8];a.iloc[1,0]=np.nan
    summary,daily=compare_scores(b,a)
    assert summary['availability_changed']==1
    assert summary['top_two_changed']==1
    assert not daily.iloc[1].both_all_eight_finite
    assert not daily.iloc[1].top_two_changed


def test_comparison_rejects_different_calendar():
    b=frame([[1]*8,[2]*8])
    with pytest.raises(ValueError):compare_scores(b,b.iloc[:1])


def test_constant_rank_cause_is_not_missing_raw_data():
    dates=pd.bdate_range('2020-12-01',periods=30)
    fields={'open':pd.DataFrame({s:np.repeat(10+i,30) for i,s in enumerate('ABCDEFGH')},index=dates),
            'volume':pd.DataFrame({s:np.arange(30)+10+i for i,s in enumerate('ABCDEFGH')},index=dates)}
    scores=pd.DataFrame(np.nan,index=dates,columns=list('ABCDEFGH'))
    causes=missing_causes(fields,'alpha101_003',scores)
    assert causes.cause.value_counts()['warmup']==9*8
    assert causes.cause.value_counts()['constant_rank_window']==21*8


@pytest.mark.parametrize('vendor,official,multiplier,label',[
    (100,100,2,'nominal'),(200,100,2,'later_share_scaled'),
    (500,100,5,'later_share_scaled'),(100,100,1,'nominal_and_scaled_identical'),
    (150,100,2,'unexplained_volume_difference')])
def test_actual_quantity_evidence_distinguishes_bases(vendor,official,multiplier,label):
    result=classify_volume_ratio(vendor,official,multiplier)
    assert result['classification']==label
    assert result['vendor_to_official_ratio']==pytest.approx(vendor/official)


@pytest.mark.parametrize('vendor,official,multiplier',[(0,10,2),(10,-1,2),(10,10,np.inf)])
def test_bad_volume_evidence_not_classified(vendor,official,multiplier):
    with pytest.raises(ValueError):classify_volume_ratio(vendor,official,multiplier)
