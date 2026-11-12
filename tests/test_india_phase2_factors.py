"""OFFLINE SYNTHETIC Phase 2 original-function, data-basis and accounting tests."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from src.india_backtest import PortfolioConfig
from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_factors import build_factor_panel, FACTOR_SPECS
from src.india_phase2_factors import (PHASE2_SPECS, PROXY_INTERPRETATION,
    TurnoverBasisEvidence, turnover_panel_digest, load_illiq_basis_evidence,
    evaluate_phase2_factor, backtest_phase2_factor)


@pytest.fixture
def histories():
    """Invented dates/prices, not an NSE session calendar or research data."""
    dates=pd.bdate_range('2020-11-30',periods=90);rng=np.random.default_rng(2602)
    result={}
    for i,s in enumerate(NSE_STOCKS):
        c=(80+10*i)*np.exp(np.cumsum(rng.normal(.001,.015,len(dates))))
        o=c*np.exp(rng.normal(0,.01,len(dates)))
        result[s]=pd.DataFrame({'open':o,'high':np.maximum(c,o)*1.015,
            'low':np.minimum(c,o)*.985,'close':c,'volume':rng.integers(1000,20000,len(dates)).astype(float)},index=dates)
    result[BENCHMARK]=pd.DataFrame({'close':200+np.arange(len(dates))*.2},index=dates)
    return result


def runtime():
    if 'VIBE_PYTHON' not in os.environ:pytest.skip('Set VIBE_PYTHON for original isolated Vibe tests')
    root=Path(os.environ.get('VIBE_TRADING_ROOT','/home/jampip/vibe-Trading'))
    if not root.is_dir():pytest.skip('Original Vibe checkout unavailable')
    return {'vibe_root':root,'python_executable':os.environ['VIBE_PYTHON']}


def basis(panel):
    return TurnoverBasisEvidence('INR',PROXY_INTERPRETATION,turnover_panel_digest(panel),
        'OFFLINE_SYNTHETIC_FIXTURE_basis_not_financial_evidence','0'*64,True,'OFFLINE_SYNTHETIC')


def evaluate(histories,factor):
    panel=build_factor_panel(histories,close_basis='adjusted')
    return evaluate_phase2_factor(panel,factor,turnover_basis=basis(panel) if factor=='academic_illiq' else None,**runtime())


def oracle(fields,factor):
    # Independent test-only formula oracles; no production implementation replaces Vibe.
    safe=lambda a,b:a.div(b+1e-12*np.sign(b)).replace([np.inf,-np.inf],np.nan)
    o,h,l,c,v=[fields[k] for k in ['open','high','low','close','volume']]
    if factor=='alpha101_033':return (-(1-safe(o,c))).rank(axis=1,pct=True,method='average')
    if factor=='alpha101_101':return safe(c-o,h-l+.001)
    if factor=='alpha101_054':return -safe((l-c)*o.pow(5),(l-h)*c.pow(5))
    if factor=='alpha101_014':
        r=c.pct_change(fill_method=None)
        return -r.diff(3).rank(axis=1,pct=True,method='average')*o.rolling(10,min_periods=10).corr(v)
    r=safe(c-c.shift(1),c.shift(1));ill=safe(r.abs(),c*v).rolling(21,min_periods=21).mean()
    return ill.sub(ill.mean(axis=1),axis=0).div(ill.std(axis=1,ddof=1).where(lambda x:x>0),axis=0)


@pytest.mark.parametrize('factor',PHASE2_SPECS)
def test_original_formulas_warmup_hashes_metadata_and_independent_bridge(histories,factor):
    panel=build_factor_panel(histories,close_basis='adjusted');kwargs=runtime()
    result=evaluate_phase2_factor(panel,factor,turnover_basis=basis(panel) if factor=='academic_illiq' else None,**kwargs)
    expected=oracle(panel.fields,factor)
    pd.testing.assert_frame_equal(result.factor.scores,expected,check_exact=False,check_freq=False,atol=1e-10,rtol=1e-9)
    leading={'alpha101_033':0,'alpha101_101':0,'alpha101_054':0,'alpha101_014':9,'academic_illiq':21}[factor]
    assert result.factor.scores.iloc[:leading].isna().all().all()
    assert result.factor.scores.iloc[leading].notna().all()
    assert len(result.factor.missing_scores)==result.factor.scores.isna().sum().sum()
    assert result.evaluation_coverage['sessions']==65
    assert 'src.factors' not in sys.modules
    for p,h in result.factor.source_sha256.items():assert hashlib.sha256((kwargs['vibe_root']/'agent'/p).read_bytes()).hexdigest()==h
    if factor=='academic_illiq':
        assert 'equity_in' not in result.factor.metadata['universe']
        assert not result.research_exception['upstream_endorsement_claimed']
        assert not result.research_exception['upstream_metadata_modified']
    else:assert result.research_exception is None


@pytest.mark.parametrize('factor',PHASE2_SPECS)
def test_future_mutation_cannot_change_earlier_original_scores(histories,factor):
    baseline=evaluate(histories,factor).factor.scores;boundary=baseline.index[50]
    for s in NSE_STOCKS:
        mask=histories[s].index>boundary
        histories[s].loc[mask,['open','high','low','close']]*=1.8
        histories[s].loc[mask,'volume']*=3
    changed=evaluate(histories,factor).factor.scores
    pd.testing.assert_frame_equal(baseline.loc[:boundary],changed.loc[:boundary])


@pytest.mark.parametrize('factor',PHASE2_SPECS)
def test_synthetic_portfolio_uses_exact_baseline_benchmark_costs_and_ic_labels(histories,factor):
    panel=build_factor_panel(histories,close_basis='adjusted');kwargs=runtime()
    result=backtest_phase2_factor(panel,factor,turnover_basis=basis(panel) if factor=='academic_illiq' else None,**kwargs)
    p=result.portfolio;assert p.configuration==PortfolioConfig().__dict__
    assert (p.executions.execution_date>p.executions.signal_date).all()
    assert p.net_returns.index[0]==pd.Timestamp('2021-01-04')
    benchmark=panel.portfolio_panel.benchmark.loc[p.net_returns.index].pct_change(fill_method=None);benchmark.iloc[0]=0
    pd.testing.assert_series_equal(p.benchmark_returns,benchmark.rename('benchmark_return'))
    np.testing.assert_allclose(p.costs,p.turnover*.001)
    for a,b in zip(p.executions.itertuples(),p.executions.iloc[1:].itertuples()):
        np.testing.assert_allclose(p.ic_returns.loc[a.signal_date],panel.fields['close'].loc[b.execution_date]/panel.fields['close'].loc[a.execution_date]-1)
    assert len(p.ic_scores)==len(p.executions)-1


@pytest.mark.parametrize('factor,field',[
    ('alpha101_033','open'),('alpha101_101','high'),('alpha101_054','low'),
    ('alpha101_014','volume'),('academic_illiq','volume')])
def test_original_required_missing_observations_are_preserved(histories,factor,field):
    for s in NSE_STOCKS:histories[s].loc[histories[s].index[45],field]=np.nan
    result=evaluate(histories,factor)
    assert result.factor.scores.iloc[45].isna().all()
    assert f'missing_input_{field}' in result.dependency_flags.flag.values


def test_flat_bar_behavior_differs_between_original_054_and_101(histories):
    for s in NSE_STOCKS:histories[s].loc[histories[s].index[40],['open','high','low','close']]=100.
    a=evaluate(histories,'alpha101_054');b=evaluate(histories,'alpha101_101')
    assert a.factor.scores.iloc[40].isna().all()
    assert b.factor.scores.iloc[40].eq(0).all()
    assert 'flat_range_original_zero_denominator' in a.dependency_flags.flag.values


def test_illiq_zero_volume_invalidates_full_original_rolling_window(histories):
    for s in NSE_STOCKS:histories[s].loc[histories[s].index[35],'volume']=0
    result=evaluate(histories,'academic_illiq')
    assert result.factor.scores.iloc[35:56].isna().all().all()
    assert result.factor.scores.iloc[56].notna().all()
    assert 'zero_volume_undefined_turnover_proxy' in result.dependency_flags.flag.values


def test_014_constant_raw_correlation_remains_nan(histories):
    for s in NSE_STOCKS:histories[s].loc[:,'volume']=1000.
    result=evaluate(histories,'alpha101_014')
    assert result.factor.scores.isna().all().all()
    assert 'constant_raw_correlation_window' in result.dependency_flags.flag.values


def test_033_identical_intraday_ratios_produce_tie_diagnostics(histories):
    for s in NSE_STOCKS:histories[s].loc[:,['open','close']]=100.
    # Existing low/high encompass 100 only if explicitly set as consistent synthetic bounds.
    for s in NSE_STOCKS:histories[s].loc[:,'low']=99.;histories[s].loc[:,'high']=101.
    result=evaluate(histories,'alpha101_033')
    assert result.evaluation_coverage['sessions_all_eight_tied']==65
    assert result.evaluation_coverage['weekly_top_two_boundary_exact_ties']>0


@pytest.mark.parametrize('change', ['absent','currency','interpretation','unsupported','stale_data'])
def test_illiq_basis_cannot_be_assumed_or_reused_after_mutation(histories,change):
    panel=build_factor_panel(histories,close_basis='adjusted');evidence=basis(panel)
    if change=='absent':evidence=None
    elif change=='currency':evidence=replace(evidence,currency='USD')
    elif change=='interpretation':evidence=replace(evidence,interpretation='actual_NSE_turnover')
    elif change=='unsupported':evidence=replace(evidence,supported=False)
    else:
        panel.fields['volume'].iloc[0,0]+=1
        panel.portfolio_panel.volume.iloc[0,0]+=1
    with pytest.raises(ValueError):evaluate_phase2_factor(panel,'academic_illiq',turnover_basis=evidence,**runtime())


def test_cutoff_universe_dependency_and_legacy_allowlist_remain_strict(histories,tmp_path):
    panel=build_factor_panel(histories,close_basis='adjusted')
    assert set(FACTOR_SPECS)=={'alpha101_001','alpha101_002','alpha101_003','alpha101_004'}
    with pytest.raises(ValueError,match='five approved'):evaluate_phase2_factor(panel,'academic_strev',vibe_root=tmp_path)
    bad=build_factor_panel(histories,close_basis='adjusted');del bad.fields['low']
    with pytest.raises(ValueError,match='dependencies'):evaluate_phase2_factor(bad,'alpha101_054',vibe_root=tmp_path)
    panel.fields['open'].loc[pd.Timestamp('2025-10-01')]=100.
    with pytest.raises(ValueError):evaluate_phase2_factor(panel,'alpha101_033',vibe_root=tmp_path)


def test_no_portfolio_parameter_or_warmup_exception_is_introduced(histories,tmp_path):
    panel=build_factor_panel(histories,close_basis='adjusted')
    with pytest.raises(ValueError,match='settings'):
        backtest_phase2_factor(panel,'alpha101_033',vibe_root=tmp_path,config=replace(PortfolioConfig(),top_n=1))
    short={s:f.iloc[1:].copy() for s,f in histories.items()};panel=build_factor_panel(short,close_basis='adjusted')
    with pytest.raises(ValueError,match='25 prior'):backtest_phase2_factor(panel,'alpha101_033',vibe_root=tmp_path)


def test_failed_real_basis_review_stops_before_factor_worker(histories,tmp_path):
    path=tmp_path/'basis.json';path.write_text(json.dumps({'supported_within_frozen_vendor_proxy_scope':False,'failed_records':1,'currency':'INR','checked_records':256}))
    with pytest.raises(ValueError,match='stop and review'):
        load_illiq_basis_evidence(build_factor_panel(histories,close_basis='adjusted'),path)


def test_constant_unit_currency_scaling_of_illiq_is_cross_sectionally_neutral(histories):
    original=evaluate(histories,'academic_illiq').factor.scores
    for s in NSE_STOCKS:histories[s].loc[:,['open','high','low','close']]*=10
    changed=evaluate(histories,'academic_illiq').factor.scores
    # Safe-div epsilon is retained; large synthetic turnover makes its difference negligible.
    pd.testing.assert_frame_equal(original,changed,check_exact=False,rtol=1e-8,atol=1e-8)


def test_033_does_not_mask_missing_inputs_it_does_not_use(histories):
    for s in NSE_STOCKS:histories[s].loc[histories[s].index[45],'high']=np.nan
    result=evaluate(histories,'alpha101_033')
    assert result.factor.scores.iloc[45].notna().all()
    assert 'missing_input_high' not in result.dependency_flags.flag.values


def test_reciprocal_share_units_cancel_in_illiq_turnover_proxy(histories):
    original=evaluate(histories,'academic_illiq').factor.scores
    s=NSE_STOCKS[0]
    histories[s].loc[:,['open','high','low','close']]*=.5
    histories[s].loc[:,'volume']*=2
    changed=evaluate(histories,'academic_illiq').factor.scores
    pd.testing.assert_frame_equal(original,changed,check_exact=False,rtol=1e-8,atol=1e-8)


def test_changed_upstream_source_version_is_rejected(histories,monkeypatch):
    import src.india_phase2_factors as integration
    monkeypatch.setitem(integration.PHASE2_SPECS,'alpha101_033',
        replace(integration.PHASE2_SPECS['alpha101_033'],source_sha256='0'*64))
    with pytest.raises(ValueError,match='version changed'):
        evaluate(histories,'alpha101_033')


def test_worker_failure_never_becomes_a_replacement_score(histories,monkeypatch):
    from types import SimpleNamespace
    import src.india_phase2_factors as integration
    monkeypatch.setattr(integration.subprocess,'run',lambda *a,**k:SimpleNamespace(
        returncode=1,stdout='',stderr='SYNTHETIC missing dependency'))
    with pytest.raises(RuntimeError,match='SYNTHETIC missing dependency'):
        evaluate(histories,'alpha101_033')
