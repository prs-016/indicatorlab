"""Explain original Alpha #3 degeneracy without replacing its scores or formula."""
import numpy as np
import pandas as pd


def correlation_window_audit(open_prices: pd.DataFrame, volumes: pd.DataFrame,
                              scores: pd.DataFrame) -> pd.DataFrame:
    """Attribute each original score using its exact ten-session ranked inputs.

    Parameters are aligned original stock open/volume matrices and original Vibe
    scores. Returns stock/date diagnostics with mutually exclusive price-only,
    volume-only, both-constant, incomplete or unexplained causes. No score is
    calculated or filled by this function. Nonfinite source values are rejected.
    """
    for frame in [volumes,scores]:
        if not frame.index.equals(open_prices.index) or not frame.columns.equals(open_prices.columns):
            raise ValueError('Inputs and original scores must align')
    if np.isinf(open_prices.to_numpy()).any() or np.isinf(volumes.to_numpy()).any():
        raise ValueError('Infinite source inputs cannot be diagnosed as missing scores')
    x=open_prices.rank(axis=1,method='average',pct=True)
    y=volumes.rank(axis=1,method='average',pct=True)
    pairs=(x.notna()&y.notna()).astype(int).rolling(10,min_periods=1).sum()
    xr=x.rolling(10).max()-x.rolling(10).min()
    yr=y.rolling(10).max()-y.rolling(10).min()
    raw_range=open_prices.rolling(10).max()-open_prices.rolling(10).min()
    rows=[]
    for s in scores:
        for i,d in enumerate(scores.index):
            valid=int(pairs.loc[d,s]);cx=bool(xr.loc[d,s]==0);cy=bool(yr.loc[d,s]==0)
            missing=bool(pd.isna(scores.loc[d,s]))
            if not missing:cause='finite'
            elif i<9:cause='warmup'
            elif valid<10:cause='incomplete_pairs'
            elif cx and cy:cause='both_ranks_constant'
            elif cx:cause='open_rank_constant_only'
            elif cy:cause='volume_rank_constant_only'
            else:cause='unexplained'
            rows.append({'date':d,'symbol':s,'score_missing':missing,'cause':cause,
                'valid_pairs':valid,'open_percentile_rank':x.loc[d,s],'volume_percentile_rank':y.loc[d,s],
                'open_rank_range_10':xr.loc[d,s],'volume_rank_range_10':yr.loc[d,s],
                'raw_open_range_10':raw_range.loc[d,s],
                'raw_open_varies_despite_constant_rank':bool(cx and raw_range.loc[d,s]>0)})
    return pd.DataFrame(rows)


def rank_run_lengths(prices: pd.DataFrame) -> pd.DataFrame:
    """Return consecutive constant cross-sectional open-rank runs per stock.

    Input is positive session-indexed stock opens. Output records run dates,
    length and rank; it does not infer closed days or carry missing values.
    """
    ranks=prices.rank(axis=1,method='average',pct=True)
    rows=[]
    for s in prices:
        series=ranks[s];groups=series.ne(series.shift()).cumsum()
        for _,block in series.groupby(groups):
            rows.append({'symbol':s,'start':block.index[0],'end':block.index[-1],
                         'sessions':len(block),'percentile_rank':float(block.iloc[0])})
    return pd.DataFrame(rows)


def evaluate_original_alpha003(fields: dict, *, basis_label: str,
                                vibe_root, python_executable):
    """Invoke original #3 for labelled diagnostic inputs, including nominal units.

    Parameters: aligned open/volume/close frames, explicit research basis label,
    existing Vibe checkout and interpreter. Returns original scores plus source
    hashes/metadata/stderr. Unlike the production India adapter this diagnostic
    boundary permits nominal prices and synthetic broad universes; it grants no
    trading/universe approval and performs no portfolio calculations or filling.
    """
    import json
    from pathlib import Path
    import subprocess
    from src.india_data import BACKTEST_END, _validate_dates
    from src.india_factors import _WORKER
    if not basis_label or not {'open','close','volume'}<=set(fields):
        raise ValueError('Explicit basis and original declared inputs required')
    reference=fields['open'];_validate_dates(reference.index)
    if reference.empty or reference.index.max()>BACKTEST_END or not reference.columns.is_unique:
        raise ValueError('Nonempty unique stock columns and pre-cutoff dates required')
    for k in ['open','close','volume']:
        f=fields[k]
        if not f.index.equals(reference.index) or not f.columns.equals(reference.columns):
            raise ValueError('Diagnostic inputs must align')
        if np.isinf(f.to_numpy()).any() or f.lt(0).any().any() or (k!='volume' and f.eq(0).any().any()):
            raise ValueError('Invalid diagnostic inputs')
    agent=Path(vibe_root).resolve()/'agent'
    if not (agent/'src/factors/zoo/alpha101/alpha_003.py').is_file():
        raise ValueError('Original Alpha #3 not found')
    request={'module':'alpha_003','dates':reference.index.strftime('%Y-%m-%d').tolist(),
        'columns':reference.columns.tolist(),'fields':{k:json.loads(fields[k].to_json(
            orient='values',date_format='iso',double_precision=15)) for k in ['open','volume','close']}}
    child=subprocess.run([str(python_executable),'-I','-B','-c',_WORKER,str(agent)],
        input=json.dumps(request,allow_nan=False),capture_output=True,text=True,cwd=agent,timeout=60,check=False)
    if child.returncode:raise RuntimeError(f'Original Alpha #3 worker failed: {child.stderr}')
    result=json.loads(child.stdout);data=result['scores']
    scores=pd.DataFrame(data['data'],index=pd.to_datetime(data['index']),columns=data['columns'],dtype=float)
    if not scores.index.equals(reference.index) or not scores.columns.equals(reference.columns):
        raise RuntimeError('Original factor returned misaligned scores')
    if result['metadata']['id']!='alpha101_003':raise RuntimeError('Wrong original factor')
    return scores,{'basis_label':basis_label,'metadata':result['metadata'],
        'source_sha256':result['source_sha256'],'worker_stderr':child.stderr}
