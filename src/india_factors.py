"""Offline OHLCV integration for the four unchanged Vibe Alpha101 factors.

This module grants no real-data evaluation permission and never downloads.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from src.india_backtest import PortfolioConfig, PortfolioResult, prepare_research_view, simulate_portfolio
from src.india_data import BACKTEST_END, BENCHMARK, NSE_STOCKS, IndiaPanel, build_india_panel
from src.india_vibe_bridge import compute_rank_ic

# Values are inspected original Vibe metadata, not new factor definitions.
FACTOR_SPECS = {
    'alpha101_001': ('alpha_001', ('close',), 25),
    'alpha101_002': ('alpha_002', ('open', 'close', 'volume'), 10),
    'alpha101_003': ('alpha_003', ('open', 'volume', 'close'), 10),
    'alpha101_004': ('alpha_004', ('low', 'close'), 9),
}
COMMON_WARMUP = 25


@dataclass(frozen=True)
class FactorPanel:
    """Aligned stock-only OHLCV, separate portfolio/benchmark data and input flags."""
    fields: dict[str, pd.DataFrame]
    portfolio_panel: IndiaPanel
    input_flags: pd.DataFrame


def build_factor_panel(histories: dict[str, pd.DataFrame], *, close_basis: str) -> FactorPanel:
    """Validate adjusted OHLCV histories without repairing or dropping observations.

    Parameters: exactly eight equities plus ^NSEI with lowercase OHLCV; benchmark
    needs close only. close_basis must be adjusted. Returns independent aligned
    matrices, existing IndiaPanel and missing/zero/repetition/move flags. NaNs
    remain NaNs, zero volume remains zero, infinities/negative volume/bad OHLC
    raise. Union alignment exposes missing instrument rows rather than filling.
    """
    if close_basis != 'adjusted':
        raise ValueError('Require consistently adjusted OHLC prices')
    panel = build_india_panel(histories, close_basis=close_basis)
    fields = {}
    flags = prepare_research_view(panel).flags.to_dict('records')
    for field in ('open','high','low','close','volume'):
        values = {}
        for symbol in NSE_STOCKS:
            frame = histories[symbol]
            if field not in frame:
                raise ValueError(f'{symbol}: missing required OHLCV column {field}')
            values[symbol] = frame.loc[:BACKTEST_END,field].astype(float)
        matrix = pd.DataFrame(values).reindex(panel.close.index)
        observed = matrix.to_numpy()
        if np.isinf(observed).any() or (observed < 0).any() or (field != 'volume' and (observed == 0).any()):
            raise ValueError(f'Invalid observed {field}')
        fields[field] = matrix
        if field in ('open','high','low'):
            flags.extend({'date':day,'symbol':s,'flag':f'missing_{field}'}
                         for s in NSE_STOCKS for day in matrix.index[matrix[s].isna()])
    # Only compare observed fields; missing values are explicitly left missing.
    for a,b in [('low','open'),('low','close'),('low','high'),('open','high'),('close','high')]:
        if fields[a].gt(fields[b]).any().any():
            raise ValueError(f'Inconsistent OHLC bounds: {a} > {b}')
    return FactorPanel(fields,panel,pd.DataFrame(flags,columns=['date','symbol','flag']))


_WORKER = r'''
import contextlib,hashlib,importlib,json,sys
from pathlib import Path
import pandas as pd
agent=Path(sys.argv[1]);sys.path.insert(0,str(agent))
request=json.load(sys.stdin)
with contextlib.redirect_stdout(sys.stderr):
 module=importlib.import_module('src.factors.zoo.alpha101.'+request['module'])
 panel={k:pd.DataFrame(v,index=pd.to_datetime(request['dates']),columns=request['columns'],dtype=float) for k,v in request['fields'].items()}
 scores=module.compute(panel)
 paths=['src/factors/zoo/alpha101/'+request['module']+'.py','src/factors/base.py','src/factors/factor_analysis_core.py']
 hashes={p:hashlib.sha256((agent/p).read_bytes()).hexdigest() for p in paths}
print(json.dumps({'scores':json.loads(scores.to_json(orient='split',date_format='iso',double_precision=15)),
 'metadata':module.__alpha_meta__,'source_sha256':hashes},allow_nan=False))
'''


@dataclass(frozen=True)
class FactorScores:
    """Original Vibe outputs, source metadata/hashes and per-cell missing-score flags."""
    factor: str
    scores: pd.DataFrame
    metadata: dict
    source_sha256: dict
    missing_scores: pd.DataFrame
    worker_stderr: str


def evaluate_factor(panel: FactorPanel, factor: str, *, vibe_root: str | Path,
                    python_executable: str | Path = sys.executable, timeout: float = 60) -> FactorScores:
    """Invoke one allowlisted original factor in an isolated existing interpreter.

    Parameters: validated FactorPanel, assigned factor ID, checkout/interpreter
    and timeout. Returns aligned scores with NaNs preserved and provenance.
    No portfolio simulation, downloads, zero filling or factor replacement occurs.
    """
    if factor not in FACTOR_SPECS:
        raise ValueError('Only the four assigned Alpha101 factors are supported')
    # Frozen dataclasses still contain mutable pandas objects: revalidate all
    # fields at the public boundary rather than trusting initial construction.
    histories = {s:pd.DataFrame({k:v[s] for k,v in panel.fields.items()}) for s in NSE_STOCKS}
    histories[BENCHMARK] = panel.portfolio_panel.benchmark.to_frame('close')
    for frame in histories.values():
        if len(frame) and frame.index.max()>BACKTEST_END:
            raise ValueError('Factor input exceeds 2024-12-31 cutoff')
    for matrix in panel.fields.values():
        if not matrix.index.equals(panel.portfolio_panel.close.index) or tuple(matrix.columns)!=NSE_STOCKS:
            raise ValueError('Factor fields must align with eight-stock portfolio panel')
    checked = build_factor_panel(histories,close_basis=panel.portfolio_panel.close_basis)
    pd.testing.assert_frame_equal(checked.portfolio_panel.close,panel.portfolio_panel.close)
    pd.testing.assert_frame_equal(checked.portfolio_panel.volume,panel.portfolio_panel.volume)
    module, required, _ = FACTOR_SPECS[factor]
    agent = Path(vibe_root).resolve()/'agent'
    if not (agent/f'src/factors/zoo/alpha101/{module}.py').is_file():
        raise ValueError('Original Vibe factor source not found')
    request = {'module':module,'dates':checked.portfolio_panel.close.index.strftime('%Y-%m-%d').tolist(),
               'columns':list(NSE_STOCKS),'fields':{k:json.loads(checked.fields[k].to_json(orient='values',date_format='iso',double_precision=15)) for k in required}}
    try:
        child = subprocess.run([str(python_executable),'-I','-B','-c',_WORKER,str(agent)],
            input=json.dumps(request,allow_nan=False),capture_output=True,text=True,
            timeout=timeout,check=False,cwd=agent)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'Vibe factor worker failed: {exc}') from exc
    if child.returncode:
        raise RuntimeError(f'Vibe factor worker failed: {child.stderr}')
    try:
        payload=json.loads(child.stdout);data=payload['scores']
        scores=pd.DataFrame(data['data'],index=pd.to_datetime(data['index']),columns=data['columns'],dtype=float)
        if not scores.index.equals(checked.portfolio_panel.close.index) or tuple(scores.columns)!=NSE_STOCKS:
            raise ValueError('Misaligned output')
        if np.isinf(scores.to_numpy()).any():
            raise ValueError('Nonfinite factor output')
        meta=payload['metadata']
        if meta['id']!=factor or tuple(meta['columns_required'])!=required or meta['min_warmup_bars']!=FACTOR_SPECS[factor][2]:
            raise ValueError('Original metadata changed; inspect before integration')
    except (ValueError,KeyError,TypeError) as exc:
        raise RuntimeError(f'Invalid original Vibe response: {exc}') from exc
    missing=pd.DataFrame([{'date':d,'symbol':s,'factor':factor,'flag':'original_factor_score_missing'}
        for s in NSE_STOCKS for d in scores.index[scores[s].isna()]],columns=['date','symbol','factor','flag'])
    return FactorScores(factor,scores,meta,payload['source_sha256'],missing,child.stderr)


def load_factor_dataset(manifest_path: str | Path, *, start: str = '2021-01-04',
                        end: str = '2024-12-31') -> FactorPanel:
    """Read checksum-verified research OHLCV with common 25-session prior history.

    Parameters: versioned research manifest and exact approved evaluation bounds.
    Returns a validated panel; this loader performs no factors or backtests and
    confers no calendar certification or diagnostic override. Missing calendar
    dates still need the exchange audit before real evaluation.
    """
    if (start,end)!=('2021-01-04','2024-12-31'):
        raise ValueError('Use identical approved evaluation boundaries')
    path=Path(manifest_path);manifest=json.loads(path.read_text())
    required_files={f'derived/{s}.csv' for s in (*NSE_STOCKS,BENCHMARK)}
    if not required_files <= set(manifest.get('files_sha256',{})):
        raise ValueError('Research manifest must checksum all nine derived histories')
    for relative,h in manifest['files_sha256'].items():
        if hashlib.sha256((path.parent/relative).read_bytes()).hexdigest()!=h:
            raise ValueError('Research dataset checksum mismatch')
    histories={s:pd.read_csv(path.parent/f'derived/{s}.csv',index_col=0,parse_dates=True) for s in (*NSE_STOCKS,BENCHMARK)}
    # Never let a malformed version be silently clipped by the generic adapter.
    for frame in histories.values():
        if frame.index.max()>BACKTEST_END:
            raise ValueError('Dataset includes post-cutoff observations')
    reference=histories[NSE_STOCKS[0]].index
    prior=reference[reference<pd.Timestamp(start)]
    if len(prior)<COMMON_WARMUP:
        raise ValueError('Need 25 prior sessions for common factor warm-up')
    first=prior[-COMMON_WARMUP]
    for s,frame in histories.items():
        selected=frame.loc[first:end].copy()
        if not selected.index.equals(reference[(reference>=first)&(reference<=pd.Timestamp(end))]):
            raise ValueError('Research instrument session calendars differ')
        histories[s]=selected
    return build_factor_panel(histories,close_basis='adjusted')


@dataclass(frozen=True)
class FactorPortfolioRun:
    """Integration output; simulation is pure and grants no real-evaluation approval."""
    factor: FactorScores
    portfolio: PortfolioResult
    execution_ic: pd.Series
    input_flags: pd.DataFrame


def backtest_factor(panel: FactorPanel, factor: str, *, vibe_root: str | Path,
                    config: PortfolioConfig = PortfolioConfig(),
                    python_executable: str | Path = sys.executable) -> FactorPortfolioRun:
    """Compose original factor/IC and existing portfolio simulator unchanged.

    Parameters: reviewed FactorPanel, assigned ID, existing Vibe runtime, and
    shared approved baseline. Returns scores, missingness, portfolio and IC.
    Intended for synthetic integration tests now; real runs require separate
    authorization/calendar review. STREV's diagnostic override is not reused.
    """
    if config!=PortfolioConfig():
        raise ValueError('All four factors require identical approved portfolio settings')
    result=evaluate_factor(panel,factor,vibe_root=vibe_root,python_executable=python_executable)
    portfolio=simulate_portfolio(panel.portfolio_panel,result.scores,config=config)
    ic=compute_rank_ic(portfolio.ic_scores,portfolio.ic_returns,vibe_root=vibe_root,python_executable=python_executable)
    return FactorPortfolioRun(result,portfolio,ic,panel.input_flags.copy())
