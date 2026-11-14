"""OFFLINE SYNTHETIC Alpha #4 tie/preference decision regressions."""
import os
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.india_alpha004_audit import membership_profile,weekly_profiles,compare_memberships,low_rank_window_audit
from src.india_data import NSE_STOCKS,BENCHMARK
from src.india_factors import build_factor_panel,evaluate_factor

NAMES=list('ABCDEFGH')


def test_all_equal_scores_allow_28_memberships_and_two_extreme_ticker_choices():
    row=pd.Series(-5/9,index=NAMES)
    p=membership_profile(row)
    assert p['admissible_pair_count']==28
    assert p['selected_pair']==('A','B') and p['reverse_ticker_pair']==('G','H')
    assert p['all_eight_tied'] and p['membership_depends_on_ticker']


def test_tied_two_strict_winners_are_still_unique_membership():
    p=membership_profile(pd.Series([1,1,0,-1,-2,-3,-4,-5],index=NAMES))
    assert p['admissible_pair_count']==1 and not p['membership_depends_on_ticker']


def test_single_strict_winner_and_cutoff_pool_enumerates_only_valid_pairs():
    p=membership_profile(pd.Series([1,0,0,0,-1,-2,-3,-4],index=NAMES))
    assert p['admissible_pairs']==[('A','B'),('A','C'),('A','D')]
    assert p['slots']==1 and p['strict_winners']==['A']


def test_missing_values_are_never_filled_to_form_pairs():
    row=pd.Series([np.nan,1,2,3,4,5,6,7],index=NAMES)
    assert not membership_profile(row)['eligible']
    with pytest.raises(ValueError):membership_profile(row.iloc[:7])


def test_changed_ticker_pair_can_have_common_admissible_membership():
    ix=pd.bdate_range('2024-01-02',periods=10)
    a=pd.DataFrame(-5/9,index=ix,columns=NAMES)
    b=a.copy();b.loc[:,'G']=1.;b.loc[:,'H']=2.
    d=compare_memberships(a,b)
    assert d.selected_pair_changed.all()
    assert not d.admissible_pairs_disjoint.any()
    assert d.overlap_pair_count.eq(1).all()
    assert not d.admissible_pair_sets_equal.any()


def test_disjoint_unique_memberships_are_unavoidable_convention_changes():
    ix=pd.bdate_range('2024-01-02',periods=10)
    a=pd.DataFrame([[8,7,6,5,4,3,2,1]]*10,index=ix,columns=NAMES)
    b=a.iloc[:,::-1].copy();b.columns=NAMES
    d=compare_memberships(a,b)
    assert d.admissible_pairs_disjoint.all()
    assert not d.baseline_tie_ambiguous.any() and not d.alternative_tie_ambiguous.any()


def test_terminal_weekly_candidate_has_no_later_permitted_session():
    scores=pd.DataFrame(1.,index=pd.bdate_range('2024-12-16','2024-12-31'),columns=NAMES)
    p=weekly_profiles(scores)
    assert p[-1]['signal_date']=='2024-12-31'
    assert not p[-1]['has_later_evaluation_session'] and p[0]['has_later_evaluation_session']


def test_low_rank_audit_separates_price_changes_from_constant_ranks():
    ix=pd.bdate_range('2024-01-02',periods=20)
    lows=pd.DataFrame({s:10*(i+1)+np.arange(20)*.01 for i,s in enumerate(NAMES)},index=ix)
    scores=pd.DataFrame(-5/9,index=ix,columns=NAMES)
    d=low_rank_window_audit(lows,scores)
    full=d[d.date.ge(ix[8])]
    assert full.constant_low_rank_window.all() and full.unranked_low_varies.all()
    with pytest.raises(ValueError):low_rank_window_audit(lows,scores.iloc[:10])


def test_original_vibe_constant_relative_low_rank_is_finite_minus_five_ninths():
    if 'VIBE_PYTHON' not in os.environ:pytest.skip('Set VIBE_PYTHON for original Vibe test')
    root=Path(os.environ.get('VIBE_TRADING_ROOT','/home/jampip/vibe-Trading'))
    if not root.is_dir():pytest.skip('Original Vibe checkout unavailable')
    dates=pd.bdate_range('2024-01-02',periods=20);hist={}
    for i,s in enumerate(NSE_STOCKS):
        low=10*(i+1)+np.arange(20)*.01
        hist[s]=pd.DataFrame({'low':low,'high':low+3,'open':low+1,'close':low+1.5,'volume':1000.},index=dates)
    hist[BENCHMARK]=pd.DataFrame({'close':100.},index=dates)
    result=evaluate_factor(build_factor_panel(hist,close_basis='adjusted'),'alpha101_004',vibe_root=root,python_executable=os.environ['VIBE_PYTHON'])
    assert result.scores.iloc[:8].isna().all().all()
    np.testing.assert_allclose(result.scores.iloc[8:],-5/9,atol=1e-14)
