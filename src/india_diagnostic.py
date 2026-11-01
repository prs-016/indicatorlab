"""One explicitly approved, dataset-bound PROVISIONAL STREV diagnostic.

No downloads, source-data writes, factor substitutions or certification changes.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

import numpy as np
import pandas as pd

from src.india_backtest import (
    PortfolioConfig, annualized_sharpe, prepare_research_view, simulate_portfolio,
)
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import BENCHMARK, NSE_STOCKS, build_india_panel
from src.india_vibe_bridge import compute_rank_ic, evaluate_strev

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'results/india_session_phase4d_20261029T020413Z_05541bac/research_v3'
REVIEW = ROOT / 'india_research/reports/india_strev_final_readiness_review.md'
DATASET_HASH = 'a99d6671002b8c15dc406d7b532556ee95cb96cb5503dd9e8555253d17e3ca42'
REVIEW_HASH = 'ff5ce2c688f80c71a933799d3f890f0e80866f77084dc61587bce68a989dad9d'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path, obj):
    path.write_text(json.dumps(obj, indent=2, default=str, allow_nan=False)+'\n')


def validate_diagnostic_override(summary: dict, *, dataset_hash: str,
                                 review_hash: str, approved: bool,
                                 strategy: str, config: PortfolioConfig) -> dict:
    """Return a scoped approval record or reject any non-approved deviation.

    Parameters bind the actual manifest/review hashes, explicit authorization,
    original strategy, exact baseline and freshly recomputed calendar summary.
    Returns permission to waive only exhaustive amendment-inventory certainty;
    missing dates, invalid observations, wrong clocks or scope still fail.
    """
    if (not approved or strategy != 'academic_strev' or dataset_hash != DATASET_HASH
            or review_hash != REVIEW_HASH or config != PortfolioConfig()):
        raise ValueError('Diagnostic approval does not cover this dataset/review/strategy/configuration')
    required = {'warmup_complete':True, 'warmup_sessions':21,
                'warmup_start':'2020-12-03','warmup_end':'2021-01-01',
                'evaluation_start':'2021-01-04','expected_evaluation_sessions':990,
                'discrepancy_count':0,'unverifiable_calendar_dates':0,
                'lookback_clock_mismatches':0}
    if any(summary.get(k) != v for k,v in required.items()):
        raise ValueError('Material calendar/data/21-session validation failed; override denied')
    return {'label':'PROVISIONAL', 'strategy':strategy,
            'authorization':'User explicitly approved one provisional diagnostic in this session.',
            'dataset_manifest_sha256':dataset_hash,'readiness_review_sha256':review_hash,
            'waived_requirement':'Exhaustive calendar amendment/daily-publication inventory only',
            'calendar_certified':False,'scope':asdict(config),
            'all_structural_validations_retained':True,'final_evaluation_authorized':False}


def _git(directory, *args):
    return subprocess.check_output(['git','-C',str(directory),*args],text=True).strip()


def run_diagnostic(*, approved: bool, vibe_root: Path, python_executable: Path) -> Path:
    """Validate and execute the approved fixed-scope diagnostic into a new directory.

    Parameters explicitly acknowledge approval and select the existing isolated
    Vibe checkout/interpreter. Returns a unique output directory, retaining a
    failure record if execution fails. Never alters inputs or certification.
    """
    config = PortfolioConfig()
    manifest_path = DATASET/'research_manifest.json'
    if _sha(manifest_path) != DATASET_HASH or _sha(REVIEW) != REVIEW_HASH:
        raise ValueError('Approved frozen dataset or review changed')
    manifest = json.loads(manifest_path.read_text())
    originals = {**manifest['original_files_sha256'], **manifest['evidence_files_sha256'],
                 **manifest['source_code_sha256'],str(manifest_path):DATASET_HASH,
                 str(REVIEW):REVIEW_HASH}
    originals.update({str(DATASET/rel):h for rel,h in manifest['files_sha256'].items()})
    for name,h in originals.items():
        if _sha(name) != h:
            raise ValueError(f'Provenance checksum mismatch: {name}')
    rules_path = ROOT/'results/india_calendar_phase4c_20261029T015149Z_53a60385/audit_v1/calendar_rules.json'
    if _sha(rules_path) != manifest['calendar_rules_sha256']:
        raise ValueError('Calendar evidence changed')
    rules = json.loads(rules_path.read_text())
    calendar = reconstruct_calendar('2020-12-01','2024-12-31',
        annual_rules={int(y):r for y,r in rules['annual_rules'].items()},overrides=rules['overrides'])
    histories = {}
    for symbol in (*NSE_STOCKS,BENCHMARK):
        full = pd.read_csv(DATASET/f'derived/{symbol}.csv',index_col=0,parse_dates=True)
        if full.index.max() > pd.Timestamp('2024-12-31'):
            raise ValueError('Post-cutoff source observation')
        histories[symbol] = full.loc['2020-12-03':'2024-12-31'].copy()
    audit = audit_calendar(calendar,histories,amendment_coverage_confirmed=False)
    override = validate_diagnostic_override(audit.summary,dataset_hash=_sha(manifest_path),
        review_hash=_sha(REVIEW),approved=approved,strategy='academic_strev',config=config)
    expected = calendar.index[(calendar.index >= pd.Timestamp('2020-12-03')) & calendar.status.eq('session')]
    for frame in histories.values():
        if not frame.index.equals(expected):
            raise ValueError('Instrument calendar differs from required sessions')
    panel = build_india_panel(histories,close_basis='adjusted')
    output = ROOT/'results'/('india_strev_PROVISIONAL_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(exist_ok=False)
    _json(output/'diagnostic_override.json',override)
    _json(output/'configuration.json',{'strategy':'academic_strev','label':'PROVISIONAL',
        **asdict(config),'universe':NSE_STOCKS,'benchmark':BENCHMARK,'lookback_sessions':21,
        'input_start':'2020-12-03','execution':'subsequent eligible close',
        'ic_horizon':'signal scores vs all-eight-stock returns from actual execution close to next execution close',
        'sharpe':'sqrt(252) * daily net excess mean / sample std; zero risk-free',
        'no_terminal_liquidation':True,'randomness':'none'})
    _json(output/'calendar_audit.json',audit.summary)
    audit.lookbacks.to_csv(output/'lookback_audit.csv',index=False)
    audit.schedule.to_csv(output/'calendar_execution_candidates.csv',index=False)
    (output/'readiness_review.md').write_bytes(REVIEW.read_bytes())
    (output/'dataset_manifest.json').write_bytes(manifest_path.read_bytes())
    try:
        view = prepare_research_view(panel)
        factor = evaluate_strev(view.panel,vibe_root=vibe_root,python_executable=python_executable)
        portfolio = simulate_portfolio(view.panel,factor.scores,config=config)
        ic = compute_rank_ic(portfolio.ic_scores,portfolio.ic_returns,
                             vibe_root=vibe_root,python_executable=python_executable)
        factor.scores.to_csv(output/'factor_scores.csv',index_label='date')
        # This next-session IC is not the approved headline execution-aligned IC.
        factor.next_session_ic.to_csv(output/'auxiliary_next_session_ic.csv',index_label='date')
        ic.to_csv(output/'execution_aligned_ic.csv',index_label='signal_date')
        portfolio.ic_scores.to_csv(output/'ic_scores.csv',index_label='signal_date')
        portfolio.ic_returns.to_csv(output/'ic_forward_returns.csv',index_label='signal_date')
        portfolio.weights.to_csv(output/'holdings_weights.csv',index_label='date')
        portfolio.executions.to_csv(output/'executions.csv',index=False)
        _json(output/'order_log.json',portfolio.order_log)
        _json(output/'exclusion_ledger.json',view.ledger)
        view.flags.to_csv(output/'quality_flags.csv',index=False)
        panel.close.to_csv(output/'input_adjusted_closes.csv',index_label='date')
        panel.volume.to_csv(output/'input_volumes.csv',index_label='date')
        panel.benchmark.to_csv(output/'input_benchmark.csv',index_label='date')
        daily = pd.concat([portfolio.gross_returns,portfolio.net_returns,portfolio.benchmark_returns,
                           portfolio.turnover,portfolio.costs],axis=1)
        daily['net_nav'] = (1+portfolio.net_returns).cumprod()
        daily['gross_nav'] = (1+portfolio.gross_returns).cumprod()
        daily['benchmark_nav'] = (1+portfolio.benchmark_returns).cumprod()
        daily.to_csv(output/'daily_returns_nav.csv',index_label='date')
        trades=[]
        for event in portfolio.executions.itertuples():
            date=event.execution_date; position=panel.close.index.get_loc(date)
            prior_date=panel.close.index[position-1]
            before = (portfolio.weights.loc[prior_date]*(panel.close.loc[date]/panel.close.loc[prior_date])
                      /(1+portfolio.gross_returns.loc[date])) if prior_date in portfolio.weights.index else pd.Series(0.,index=NSE_STOCKS)
            target=portfolio.weights.loc[date]
            for symbol in NSE_STOCKS:
                change=float(target[symbol]-before[symbol])
                if abs(change)>1e-12:
                    trades.append({'signal_date':event.signal_date,'execution_date':date,'symbol':symbol,
                        'side':'buy' if change>0 else 'sell','pretrade_weight':before[symbol],
                        'target_weight':target[symbol],'signed_nav_weight_change':change,
                        'adjusted_execution_close':panel.close.loc[date,symbol],
                        'cost_fraction':abs(change)*config.cost_bps/10000})
        pd.DataFrame(trades).to_csv(output/'trades.csv',index=False)
        if not np.isclose(sum(abs(t['signed_nav_weight_change']) for t in trades),portfolio.turnover.sum()):
            raise ValueError('Trade ledger does not reconcile to portfolio turnover')
        if not (portfolio.executions.execution_date > portfolio.executions.signal_date).all():
            raise ValueError('Noncausal execution')
        valid_ic=ic.dropna()
        metrics={'label':'PROVISIONAL','strategy':'academic_strev',
            'execution_aligned_mean_rank_ic':float(valid_ic.mean()),'valid_ic_intervals':len(valid_ic),
            'undefined_ic_intervals':len(portfolio.ic_scores)-len(valid_ic),'net_daily_annualized_sharpe':portfolio.sharpe,
            'benchmark_daily_annualized_sharpe':annualized_sharpe(portfolio.benchmark_returns),
            'evaluation_observations':len(daily),'input_sessions_with_warmup':len(panel.close),
            'stock_price_observations_with_warmup':int(panel.close.notna().sum().sum()),
            'rebalance_executions':len(portfolio.executions),'nonzero_turnover_executions':int(portfolio.executions.turnover.gt(1e-12).sum()),
            'stock_trade_legs':len(trades),'total_absolute_nav_turnover':float(portfolio.turnover.sum()),
            'sum_cost_fractions':float(portfolio.costs.sum()),
            'net_cumulative_return':float(daily.net_nav.iloc[-1]-1),
            'gross_cumulative_return':float(daily.gross_nav.iloc[-1]-1),
            'benchmark_cumulative_return':float(daily.benchmark_nav.iloc[-1]-1),
            'net_max_drawdown':float((daily.net_nav/daily.net_nav.cummax()-1).min()),
            'first_execution':str(portfolio.executions.execution_date.min().date()),
            'last_execution':str(portfolio.executions.execution_date.max().date()),
            'quality_flags_by_kind':view.flags.flag.value_counts().to_dict(),
            'no_final_keep_drop_decision':True}
        _json(output/'metrics.json',metrics)
        warnings=['PROVISIONAL diagnostic; no final Keep/Drop decision.',
            'Calendar amendments not exhaustively inventoried; no identified material discrepancy.',
            'Frozen Yahoo adjustment vintage is not historically point-in-time; later corporate actions affect historical scaling.',
            'Nifty 50 is a price index; adjusted equity histories include dividend adjustments.',
            'Fixed eight-stock assignment is not a historical investable broad-market universe.',
            'Positive volume/close is an execution proxy, especially on short special sessions; no spread/impact model.',
            '10 bps per absolute traded NAV; fractional targets, drift, zero cash interest; no forced terminal liquidation.',
            'Unresolved anomaly flags retained; no price repairs or anomaly-based exclusions.',
            'IC is cross-sectional rank correlation over execution intervals, not portfolio Sharpe.',
            'The final uncompleted execution interval is excluded from IC; initial cash days are included in daily Sharpe.']
        _json(output/'warnings.json',warnings)
        # Freeze working source bytes as well as Git revisions (untracked changes exist).
        code=output/'source_snapshot';code.mkdir()
        for relative,h in factor.source_sha256.items():
            source=vibe_root/'agent'/relative
            if _sha(source)!=h:raise ValueError('Vibe source changed during run')
            target=code/'vibe'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source.read_bytes())
        for path in sorted((ROOT/'src').glob('india_*.py')):
            (code/path.name).write_bytes(path.read_bytes())
        _json(output/'provenance.json',{'dataset':str(DATASET),'input_hashes':originals,
            'vibe_root':str(vibe_root),'vibe_head':_git(vibe_root,'rev-parse','HEAD'),
            'vibe_status':_git(vibe_root,'status','--short'),'factor_source_sha256':factor.source_sha256,
            'indicatorlab_head':_git(ROOT,'rev-parse','HEAD'),'indicatorlab_branch':_git(ROOT,'branch','--show-current'),
            'indicatorlab_status':_git(ROOT,'status','--short'),
            'jack_reference':_git(ROOT,'rev-parse','origin/jack'),
            'python':sys.version,'executable':str(python_executable),'platform':platform.platform(),
            'packages':{p:importlib.metadata.version(p) for p in ['pandas','numpy','scipy','pydantic','pytest']},
            'created_utc':datetime.now(timezone.utc).isoformat()})
        for name,h in originals.items():
            if _sha(name)!=h:raise ValueError(f'Input modified during run: {name}')
        _json(output/'status.json',{'status':'completed','label':'PROVISIONAL','originals_unchanged':True})
    except Exception as exc:
        _json(output/'status.json',{'status':'blocked','error':str(exc),'label':'PROVISIONAL'})
        raise
    finally:
        _json(output/'artifact_hashes.json',{str(p.relative_to(output)):_sha(p) for p in output.rglob('*') if p.is_file() and p.name!='artifact_hashes.json'})
    return output


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-diagnostic',action='store_true')
    args=parser.parse_args()
    print(run_diagnostic(approved=args.approved_diagnostic,vibe_root=Path('/home/jampip/vibe-Trading'),
                         python_executable=ROOT/'.venv/bin/python'))
