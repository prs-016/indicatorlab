"""OFFLINE SYNTHETIC OHLCV/original-factor and portfolio integration regressions."""
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
from src.india_factors import (FACTOR_SPECS,build_factor_panel,evaluate_factor,
                               backtest_factor,load_factor_dataset)


@pytest.fixture
def histories():
    """Seeded invented OHLCV, unsuitable for financial conclusions."""
    rng=np.random.default_rng(814);dates=pd.bdate_range('2020-11-01',periods=100)
    result={}
    for i,s in enumerate(NSE_STOCKS):
        close=100*np.exp(np.cumsum(rng.normal(.0003,.02,len(dates))))
        op=close*np.exp(rng.normal(0,.01,len(dates)))
        result[s]=pd.DataFrame({'open':op,'close':close,'low':np.minimum(op,close)*.98,
            'high':np.maximum(op,close)*1.02,'volume':rng.integers(500,10000,len(dates)).astype(float)},index=dates)
    result[BENCHMARK]=pd.DataFrame({'close':200+np.arange(len(dates))},index=dates)
    return result


def runtime():
    if 'VIBE_PYTHON' not in os.environ:
        pytest.skip('Set VIBE_PYTHON for actual isolated Vibe regression tests')
    root=Path(os.environ.get('VIBE_TRADING_ROOT','/home/jampip/vibe-Trading'))
    if not root.is_dir():pytest.skip('Vibe checkout unavailable')
    return {'vibe_root':root,'python_executable':os.environ['VIBE_PYTHON']}


def test_adapter_preserves_prices_volume_benchmark_and_missing(histories):
    histories[NSE_STOCKS[0]].iloc[30,0]=np.nan
    histories[NSE_STOCKS[1]].iloc[31,4]=0.
    panel=build_factor_panel(histories,close_basis='adjusted')
    assert np.isnan(panel.fields['open'].iloc[30,0])
    assert panel.fields['volume'].iloc[31,1]==0
    assert BENCHMARK not in panel.fields['close'].columns
    assert set(panel.input_flags.flag)>={'missing_open','zero_volume'}
    pd.testing.assert_series_equal(panel.portfolio_panel.benchmark,histories[BENCHMARK].close.astype(float).rename(BENCHMARK))
    panel.fields['open'].iloc[0,0]=1.
    assert histories[NSE_STOCKS[0]].open.iloc[0]!=1.


@pytest.mark.parametrize('field,value',[('open',0),('high',-1),('low',np.inf),('volume',-1),('close',np.inf)])
def test_invalid_data_is_rejected(histories,field,value):
    histories[NSE_STOCKS[0]].loc[histories[NSE_STOCKS[0]].index[0],field]=value
    with pytest.raises(ValueError):build_factor_panel(histories,close_basis='adjusted')


def test_ohlc_basis_bounds_and_missing_columns(histories):
    with pytest.raises(ValueError,match='adjusted'):build_factor_panel(histories,close_basis='unadjusted')
    histories[NSE_STOCKS[0]]['open']=histories[NSE_STOCKS[0]].high*2
    with pytest.raises(ValueError,match='OHLC'):build_factor_panel(histories,close_basis='adjusted')
    histories[NSE_STOCKS[0]]=histories[NSE_STOCKS[0]].drop(columns='open')
    with pytest.raises(ValueError,match='column'):build_factor_panel(histories,close_basis='adjusted')


def oracle(fields,factor):
    # Independent test-only paper/helper formula checks, never production factors.
    rank=lambda x:x.rank(axis=1,pct=True,method='average')
    close=fields['close']
    if factor=='alpha101_001':
        returns=close.pct_change(fill_method=None);cond=(returns<0).astype(float)
        x=returns.rolling(20,min_periods=20).std(ddof=1)*cond+close*(1-cond)
        arg=(x*x).rolling(5,min_periods=5).apply(np.argmax,raw=True)
        return rank(arg)-.5
    if factor=='alpha101_002':
        x=rank(np.log(fields['volume']).diff(2));y=rank((close-fields['open'])/fields['open'])
        return -x.rolling(6,min_periods=6).corr(y)
    if factor=='alpha101_003':
        return -rank(fields['open']).rolling(10,min_periods=10).corr(rank(fields['volume']))
    return -rank(fields['low']).rolling(9,min_periods=9).apply(lambda a:pd.Series(a).rank(pct=True).iloc[-1],raw=True)


@pytest.mark.parametrize('factor',FACTOR_SPECS)
def test_original_formula_metadata_warmup_provenance_and_future_invariance(histories,factor):
    panel=build_factor_panel(histories,close_basis='adjusted');kwargs=runtime()
    result=evaluate_factor(panel,factor,**kwargs)
    pd.testing.assert_frame_equal(result.scores,oracle(panel.fields,factor),check_exact=False,check_freq=False,atol=1e-10,rtol=1e-9)
    expected_first={'alpha101_001':24,'alpha101_002':7,'alpha101_003':9,'alpha101_004':8}[factor]
    assert result.scores.iloc[:expected_first].isna().all().all()
    assert result.scores.iloc[expected_first].notna().any()
    assert len(result.missing_scores)==int(result.scores.isna().sum().sum())
    for path,h in result.source_sha256.items():
        assert hashlib.sha256((kwargs['vibe_root']/'agent'/path).read_bytes()).hexdigest()==h
    boundary=panel.portfolio_panel.close.index[55]
    changed={s:f.copy() for s,f in histories.items()}
    for s in NSE_STOCKS:
        mask=changed[s].index>boundary
        changed[s].loc[mask,['open','high','low','close']]*=1.7
        changed[s].loc[mask,'volume']*=2
    future=evaluate_factor(build_factor_panel(changed,close_basis='adjusted'),factor,**kwargs)
    pd.testing.assert_frame_equal(result.scores.loc[:boundary],future.scores.loc[:boundary])
    assert 'src.factors' not in sys.modules


@pytest.mark.parametrize('factor',FACTOR_SPECS)
def test_synthetic_portfolio_same_baseline_and_ic_horizon(histories,factor):
    panel=build_factor_panel(histories,close_basis='adjusted')
    result=backtest_factor(panel,factor,**runtime());p=result.portfolio
    assert p.configuration==PortfolioConfig().__dict__
    assert p.net_returns.index[0]==pd.Timestamp('2021-01-04')
    assert p.net_returns.index.max()<=pd.Timestamp('2024-12-31')
    assert (p.executions.execution_date>p.executions.signal_date).all()
    expected_benchmark=panel.portfolio_panel.benchmark.loc[p.net_returns.index].pct_change(fill_method=None)
    expected_benchmark.iloc[0]=0.
    pd.testing.assert_series_equal(p.benchmark_returns,expected_benchmark.rename('benchmark_return'))
    assert len(p.ic_scores)==max(len(p.executions)-1,0)
    for a,b in zip(p.executions.itertuples(),p.executions.iloc[1:].itertuples()):
        np.testing.assert_allclose(p.ic_returns.loc[a.signal_date],panel.fields['close'].loc[b.execution_date]/panel.fields['close'].loc[a.execution_date]-1)
    with pytest.raises(ValueError,match='identical'):
        backtest_factor(panel,factor,config=replace(PortfolioConfig(),cost_bps=0),**runtime())


@pytest.mark.parametrize('factor',FACTOR_SPECS)
def test_missing_required_input_scores_preserved(histories,factor):
    field={'alpha101_001':'close','alpha101_002':'open','alpha101_003':'open','alpha101_004':'low'}[factor]
    for s in NSE_STOCKS:histories[s].loc[histories[s].index[40],field]=np.nan
    panel=build_factor_panel(histories,close_basis='adjusted')
    result=evaluate_factor(panel,factor,**runtime())
    assert result.scores.iloc[40].isna().all()
    assert not result.missing_scores.empty


@pytest.mark.parametrize('factor',['alpha101_002','alpha101_003'])
def test_constant_rank_correlations_remain_missing(histories,factor):
    for s in NSE_STOCKS:
        histories[s].loc[:,['open','high','low','close']]=100.
        histories[s].loc[:,'volume']=1000.
    result=evaluate_factor(build_factor_panel(histories,close_basis='adjusted'),factor,**runtime())
    assert result.scores.isna().all().all()


def test_mutated_alignment_cutoff_and_factor_allowlist(histories,tmp_path):
    panel=build_factor_panel(histories,close_basis='adjusted')
    with pytest.raises(ValueError,match='four assigned'):evaluate_factor(panel,'alpha101_005',vibe_root=tmp_path)
    with pytest.raises(ValueError,match='not found'):evaluate_factor(panel,'alpha101_001',vibe_root=tmp_path)
    panel.fields['open'].loc[pd.Timestamp('2025-10-01')]=100.
    with pytest.raises(ValueError):evaluate_factor(panel,'alpha101_001',vibe_root=tmp_path)


def test_loader_checksums_common_warmup_and_cutoff(histories,tmp_path):
    (tmp_path/'derived').mkdir()
    hashes={}
    for s,f in histories.items():
        path=tmp_path/f'derived/{s}.csv';f.to_csv(path)
        hashes[str(path.relative_to(tmp_path))]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=tmp_path/'research_manifest.json';manifest.write_text(json.dumps({'files_sha256':hashes}))
    panel=load_factor_dataset(manifest)
    assert len(panel.portfolio_panel.close.loc[:'2021-01-01'])==25
    with pytest.raises(ValueError,match='boundaries'):load_factor_dataset(manifest,start='2022-01-03')
    path=tmp_path/f'derived/{NSE_STOCKS[0]}.csv';path.write_text('tampered')
    with pytest.raises(ValueError,match='checksum'):load_factor_dataset(manifest)


def test_mutated_fields_cannot_misalign_eight_stock_universe(histories,tmp_path):
    panel=build_factor_panel(histories,close_basis='adjusted')
    panel.fields['open']=panel.fields['open'].iloc[:,::-1]
    with pytest.raises(ValueError,match='align'):
        evaluate_factor(panel,'alpha101_002',vibe_root=tmp_path)


def test_adapter_excludes_future_without_changing_historical_fields(histories):
    original=build_factor_panel(histories,close_basis='adjusted')
    for s,f in histories.items():f.loc[pd.Timestamp('2025-10-01')]=1e9
    bounded=build_factor_panel(histories,close_basis='adjusted')
    for field in original.fields:pd.testing.assert_frame_equal(original.fields[field],bounded.fields[field],check_freq=False)
    pd.testing.assert_series_equal(original.portfolio_panel.benchmark,bounded.portfolio_panel.benchmark,check_freq=False)


def test_zero_volume_is_preserved_for_original_log_volume_factor(histories):
    histories[NSE_STOCKS[0]].loc[histories[NSE_STOCKS[0]].index[35],'volume']=0.
    panel=build_factor_panel(histories,close_basis='adjusted')
    result=evaluate_factor(panel,'alpha101_002',**runtime())
    assert panel.fields['volume'].iloc[35,0]==0.
    assert 'zero_volume' in panel.input_flags.flag.values
    assert 'divide by zero' in result.worker_stderr
    assert not np.isinf(result.scores.to_numpy()).any()


def test_worker_errors_are_not_replaced_with_scores(histories,tmp_path,monkeypatch):
    import src.india_factors as integration
    from types import SimpleNamespace
    p=tmp_path/'agent/src/factors/zoo/alpha101/alpha_001.py';p.parent.mkdir(parents=True);p.touch()
    monkeypatch.setattr(integration.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stderr='synthetic import error',stdout=''))
    with pytest.raises(RuntimeError,match='synthetic import error'):
        evaluate_factor(build_factor_panel(histories,close_basis='adjusted'),'alpha101_001',vibe_root=tmp_path)


def test_loader_refuses_unhashed_history(tmp_path):
    manifest=tmp_path/'research_manifest.json'
    manifest.write_text(json.dumps({'files_sha256':{}}))
    with pytest.raises(ValueError,match='all nine'):
        load_factor_dataset(manifest)
