"""OFFLINE SYNTHETIC correlation-cause and universe-mechanism tests."""
from pathlib import Path
import os
import numpy as np
import pandas as pd
import pytest

from src.india_alpha003_audit import (correlation_window_audit,rank_run_lengths,
                                      evaluate_original_alpha003)


def test_mutually_exclusive_zero_variance_causes_and_real_price_movement():
    dates=pd.bdate_range('2024-01-02',periods=20)
    prices=pd.DataFrame({'A':10+np.arange(20)*.01,'B':20+np.arange(20)*.02,
                         'C':30+np.arange(20)*.03},index=dates)
    volume=pd.DataFrame({'A':100+np.arange(20),'B':1000+np.arange(20),
                         'C':np.where(np.arange(20)%2,50,500)},index=dates)
    scores=pd.DataFrame(np.nan,index=dates,columns=prices.columns)
    audit=correlation_window_audit(prices,volume,scores)
    assert audit.cause.eq('warmup').sum()==9*3
    assert set(audit.loc[audit.date.ge(dates[9]),'cause'])=={'both_ranks_constant','open_rank_constant_only'}
    assert audit.loc[audit.date.ge(dates[9]),'raw_open_varies_despite_constant_rank'].all()
    runs=rank_run_lengths(prices)
    assert len(runs)==3 and runs.sessions.eq(20).all()


def test_missing_pairs_are_not_called_constant_ranks():
    dates=pd.bdate_range('2024-01-02',periods=20)
    p=pd.DataFrame({'A':10.,'B':20.},index=dates);v=p.copy()
    p.loc[dates[12],'A']=np.nan
    scores=p.copy()*np.nan
    detail=correlation_window_audit(p,v,scores)
    assert detail.loc[detail.date.eq(dates[12])&detail.symbol.eq('A'),'cause'].iloc[0]=='incomplete_pairs'


def test_audit_rejects_misalignment():
    dates=pd.bdate_range('2024-01-02',periods=12);p=pd.DataFrame({'A':10.},index=dates)
    with pytest.raises(ValueError,match='align'):correlation_window_audit(p,p.iloc[:10],p)


def runtime():
    if 'VIBE_PYTHON' not in os.environ:pytest.skip('Set VIBE_PYTHON for original isolated Vibe test')
    root=Path(os.environ.get('VIBE_TRADING_ROOT','/home/jampip/vibe-Trading'))
    if not root.is_dir():pytest.skip('Original Vibe checkout unavailable')
    return {'vibe_root':root,'python_executable':os.environ['VIBE_PYTHON']}


def test_synthetic_extra_neighbors_change_original_ranks_without_changing_prices_or_formula():
    dates=pd.bdate_range('2024-01-02',periods=40);step=np.arange(40)
    core=pd.DataFrame({f'C{i}':10*(i+1)+step*.01 for i in range(8)},index=dates)
    extra=pd.DataFrame({f'E{i}':core[f'C{i}']+np.where(step%2,.5,-.5) for i in range(8)},index=dates)
    wide=pd.concat([core,extra],axis=1)
    rng=np.random.default_rng(1403)
    volume=pd.DataFrame(rng.integers(100,10000,size=(40,16)),index=dates,columns=wide.columns)
    fields=lambda p:{'open':p,'close':p*1.001,'volume':volume[p.columns]}
    a,_=evaluate_original_alpha003(fields(core),basis_label='SYNTHETIC original eight',**runtime())
    b,_=evaluate_original_alpha003(fields(wide),basis_label='SYNTHETIC original eight plus fixed synthetic neighbors',**runtime())
    assert a.isna().all().all()
    assert b.loc[:,core.columns].iloc[9:].notna().all().all()
    # More stocks that never cross the existing price levels need not help.
    separated=wide.copy();separated[extra.columns]=extra*1000
    c,_=evaluate_original_alpha003(fields(separated),basis_label='SYNTHETIC distant neighbors',**runtime())
    assert c.loc[:,core.columns].isna().all().all()


def test_same_day_common_price_scaling_cannot_fix_cross_sectional_rank():
    dates=pd.bdate_range('2024-01-02',periods=20)
    rng=np.random.default_rng(233)
    p=pd.DataFrame(rng.uniform(10,100,(20,8)),index=dates)
    scales=pd.Series(np.linspace(.5,2,20),index=dates)
    pd.testing.assert_frame_equal(p.rank(axis=1),p.mul(scales,axis=0).rank(axis=1))


def test_original_diagnostic_boundary_still_rejects_holdout_and_undeclared_basis(tmp_path):
    p=pd.DataFrame({'A':[100.]},index=pd.DatetimeIndex(['2025-10-01']))
    with pytest.raises(ValueError,match='pre-cutoff'):
        evaluate_original_alpha003({'open':p,'close':p,'volume':p},basis_label='nominal proxy',vibe_root=tmp_path,python_executable='unused')
    with pytest.raises(ValueError,match='basis'):
        evaluate_original_alpha003({'open':p,'close':p,'volume':p},basis_label='',vibe_root=tmp_path,python_executable='unused')
