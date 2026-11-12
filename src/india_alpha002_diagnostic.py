"""One scoped PROVISIONAL Alpha101 #2 diagnostic on verified research_v4."""
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import numpy as np
import pandas as pd

from src.india_backtest import PortfolioConfig, annualized_sharpe
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_diagnostic import ROOT, _sha, _json, _git
from src.india_factor_readiness import signal_coverage, missing_causes
from src.india_factors import load_factor_dataset, backtest_factor

PACKAGE=ROOT/'results/india_alpha002_volume_reconciliation_20261029T034510Z'
DATASET=PACKAGE/'research_v4'
DATASET_HASH='9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1'
PACKAGE_HASH='270dac129c81271587f3fbd8d44b55ea65b25fe136677b90c27171cfabb50e36'
REVIEW=ROOT/'india_research/reports/india_alpha101_002_volume_readiness_review.md'
REVIEW_HASH='f2ed66105d57c98b4816a85b7505b274241696f468bcf5d4262db7aeecfaf6bc'


def validate_alpha002_approval(summary: dict, verification: dict, *, approved: bool,
                               dataset_hash: str, review_hash: str, package_hash: str,
                               config: PortfolioConfig, prior_sessions: int,
                               factor: str = 'alpha101_002') -> dict:
    """Authorize only this frozen #2 diagnostic with all material checks intact.

    Inputs bind actual evidence hashes, independent 12/24 source verification,
    calendar summary, fixed baseline and 25 prior sessions. Returns a recorded
    exception for exhaustive calendar-inventory certainty only; other scopes fail.
    """
    if (not approved or factor!='alpha101_002' or dataset_hash!=DATASET_HASH
            or review_hash!=REVIEW_HASH or package_hash!=PACKAGE_HASH
            or config!=PortfolioConfig() or prior_sessions!=25):
        raise ValueError('Approval does not cover this factor/dataset/review/settings/warm-up')
    required={'discrepancy_count':0,'unverifiable_calendar_dates':0,'lookback_clock_mismatches':0,
              'warmup_complete':True,'expected_evaluation_sessions':990,'evaluation_start':'2021-01-04'}
    if any(summary.get(k)!=v for k,v in required.items()):
        raise ValueError('Material calendar/data validation failed')
    verified={'status':'passed','verified_changes':12,'verified_quantity_anchors':24,
              'all_other_csv_tokens_and_line_endings_preserved':True,
              'dataset_manifest_sha256':DATASET_HASH}
    if any(verification.get(k)!=v for k,v in verified.items()):
        raise ValueError('research_v4 volume/provenance verification failed')
    return {'label':'PROVISIONAL','factor':factor,'authorization':'User explicitly approved one #2 diagnostic in this conversation.',
        'dataset_manifest_sha256':dataset_hash,'readiness_review_sha256':review_hash,
        'finalized_package_inventory_sha256':package_hash,'configuration':asdict(config),
        'waived_requirement':'Exhaustive historical calendar inventory only; no material data check waived',
        'calendar_certified':False,'other_real_factors_authorized':False,'repeat_run_authorized':False,
        'final_keep_drop_authorized':False}


def run_alpha002(*, approved: bool) -> Path:
    """Verify research_v4 and run only the approved original #2 into a fresh output.

    Explicit approval is required. Returns unique results directory with frozen
    inputs, code, NaNs, execution-aligned labels, trades/costs and warnings.
    No dataset, archived output, factor or portfolio definition is changed.
    """
    manifest_path=DATASET/'research_manifest.json';inventory=PACKAGE/'artifact_hashes.json'
    if (_sha(manifest_path)!=DATASET_HASH or _sha(inventory)!=PACKAGE_HASH or _sha(REVIEW)!=REVIEW_HASH):
        raise ValueError('Approved frozen evidence changed')
    originals={str(manifest_path):DATASET_HASH,str(inventory):PACKAGE_HASH,str(REVIEW):REVIEW_HASH}
    originals.update({str(PACKAGE/p):h for p,h in json.loads(inventory.read_text()).items()})
    originals.update(json.loads((PACKAGE/'protected_inputs.json').read_text()))
    for p,h in originals.items():
        if _sha(p)!=h:raise ValueError(f'Input/source/prior-output checksum mismatch: {p}')
    # The saved read-only verifier reparses quantities; it never calls a writer,
    # factor worker or portfolio simulator and does not change its old output.
    spec=importlib.util.spec_from_file_location('verified_volume_v4',PACKAGE/'verify_existing_v4.py')
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    verification=verifier.verify()
    baseline_test_log=(PACKAGE/'finalization_test_results.txt').read_text()
    if '218 passed' not in baseline_test_log:raise ValueError('Recorded 218-test baseline unavailable')
    evidence=ROOT/'results/india_four_factor_readiness_20261029T030714Z/factor_sources.json'
    source_versions=json.loads(evidence.read_text())['alpha101_002']['source_sha256']
    for rel,h in source_versions.items():
        p=Path('/home/jampip/vibe-Trading/agent')/rel
        if _sha(p)!=h:raise ValueError('Original Vibe source differs from audited implementation')
        originals[str(p)]=h
    config=PortfolioConfig()
    oldconfig=json.loads((ROOT/'results/india_strev_PROVISIONAL_20261029T021955Z_21d1a038/configuration.json').read_text())
    if any(oldconfig[k]!=v for k,v in asdict(config).items()):raise ValueError('Portfolio baseline changed')
    panel=load_factor_dataset(manifest_path);pp=panel.portfolio_panel
    m=json.loads(manifest_path.read_text())
    rules_path=ROOT/'results/india_calendar_phase4c_20261029T015149Z_53a60385/audit_v1/calendar_rules.json'
    if _sha(rules_path)!=m['calendar_rules_sha256']:raise ValueError('Calendar rules changed')
    rules=json.loads(rules_path.read_text())
    calendar=reconstruct_calendar('2020-11-26','2024-12-31',annual_rules={int(y):v for y,v in rules['annual_rules'].items()},overrides=rules['overrides'])
    expected=calendar.index[calendar.status.eq('session')]
    if len(expected)!=1015 or not expected.equals(pp.close.index):raise ValueError('Input calendar differs')
    histories={s:pd.DataFrame({'close':pp.close[s],'volume':pp.volume[s]}) for s in NSE_STOCKS}
    histories[BENCHMARK]=pp.benchmark.to_frame('close')
    audit=audit_calendar(calendar,histories,amendment_coverage_confirmed=False)
    approval=validate_alpha002_approval(audit.summary,verification,approved=approved,
        dataset_hash=_sha(manifest_path),review_hash=_sha(REVIEW),package_hash=_sha(inventory),
        config=config,prior_sessions=int((pp.close.index<pd.Timestamp(config.start)).sum()))
    out=ROOT/'results'/('india_alpha101_002_PROVISIONAL_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    _json(out/'diagnostic_approval.json',approval);_json(out/'preflight_volume_verification.json',verification)
    _json(out/'configuration.json',{'label':'PROVISIONAL','factor':'alpha101_002',**asdict(config),
        'universe':NSE_STOCKS,'benchmark':BENCHMARK,'prior_sessions':25,'input_start':'2020-11-26',
        'execution':'strictly subsequent eligible close','tie_rule':'descending score then ascending ticker',
        'ic_horizon':'actual execution close to next actual execution close, ranked across all eight names',
        'sharpe':'daily net excess mean / sample std * sqrt(252); zero risk-free',
        'cash_interest':0,'terminal_liquidation':False})
    _json(out/'calendar_audit.json',audit.summary)
    _json(out/'warmup_audit.json',{'prior_sessions':25,'first':'2020-11-26','last':'2021-01-01',
        'input_sessions':1015,'evaluation_sessions':990,
        'note':'Shared calendar auditor also checks its auxiliary 21-session offsets; original #2 metadata warm-up is 10 bars, with 25 prior sessions supplied.'})
    for src,name in [(manifest_path,'dataset_manifest.json'),(REVIEW,'readiness_review.md'),
        (DATASET/'volume_adjustment_ledger.json','volume_adjustment_ledger.json')]:
        (out/name).write_bytes(src.read_bytes())
    try:
        run=backtest_factor(panel,'alpha101_002',vibe_root='/home/jampip/vibe-Trading',python_executable=ROOT/'.venv/bin/python',config=config)
        p,factor,ic=run.portfolio,run.factor,run.execution_ic
        factor.scores.to_csv(out/'factor_scores.csv',index_label='date')
        factor.missing_scores.to_csv(out/'missing_scores.csv',index=False)
        missing_causes(panel.fields,'alpha101_002',factor.scores).to_csv(out/'nan_causes.csv',index=False)
        coverage,details=signal_coverage(factor.scores);_json(out/'signal_coverage.json',coverage)
        details.to_csv(out/'daily_signal_diagnostics.csv')
        (out/'factor_worker_stderr.txt').write_text(factor.worker_stderr)
        ic.to_csv(out/'execution_aligned_ic.csv',index_label='signal_date')
        p.ic_scores.to_csv(out/'ic_scores.csv',index_label='signal_date')
        p.ic_returns.to_csv(out/'ic_forward_returns.csv',index_label='signal_date')
        intervals=[]
        for a,b in zip(p.executions.itertuples(),p.executions.iloc[1:].itertuples()):
            if not a.signal_date<a.execution_date<b.execution_date<=pd.Timestamp(config.end):
                raise ValueError('Invalid execution-aligned return-label bounds')
            intervals.append({'signal_date':a.signal_date,'entry_close':a.execution_date,
                'exit_close':b.execution_date,'session_intervals':pp.close.index.get_loc(b.execution_date)-pp.close.index.get_loc(a.execution_date),
                'valid_pairs':int((p.ic_scores.loc[a.signal_date].notna()&p.ic_returns.loc[a.signal_date].notna()).sum()),
                'ic_defined':a.signal_date in ic.index})
        pd.DataFrame(intervals).to_csv(out/'ic_intervals.csv',index=False)
        _json(out/'undefined_ic_dates.json',[str(d.date()) for d in p.ic_scores.index.difference(ic.index)])
        p.weights.to_csv(out/'holdings_weights.csv',index_label='date')
        p.executions.to_csv(out/'executions.csv',index=False);_json(out/'order_log.json',p.order_log)
        run.input_flags.to_csv(out/'quality_flags.csv',index=False)
        for field,frame in panel.fields.items():frame.to_csv(out/f'input_{field}.csv',index_label='date')
        pp.benchmark.to_csv(out/'input_benchmark.csv',index_label='date')
        daily=pd.concat([p.net_returns,p.gross_returns,p.benchmark_returns,p.turnover,p.costs],axis=1)
        daily['net_nav']=(1+p.net_returns).cumprod();daily['gross_nav']=(1+p.gross_returns).cumprod()
        daily['benchmark_nav']=(1+p.benchmark_returns).cumprod();daily.to_csv(out/'daily_returns_nav.csv',index_label='date')
        trades=[]
        for event in p.executions.itertuples():
            date=event.execution_date
            if not event.signal_date<date<=pd.Timestamp(config.end):raise ValueError('Execution outside cutoff')
            prior=pp.close.index[pp.close.index.get_loc(date)-1]
            before=(p.weights.loc[prior]*(pp.close.loc[date]/pp.close.loc[prior])/(1+p.gross_returns.loc[date])) if prior in p.weights.index else pd.Series(0.,index=NSE_STOCKS)
            for s in NSE_STOCKS:
                change=float(p.weights.loc[date,s]-before[s])
                if abs(change)>1e-12:trades.append({'signal_date':event.signal_date,'execution_date':date,'symbol':s,
                    'side':'buy' if change>0 else 'sell','pretrade_weight':float(before[s]),'target_weight':float(p.weights.loc[date,s]),
                    'signed_nav_weight_change':change,'adjusted_execution_close':float(pp.close.loc[date,s]),'cost_fraction':abs(change)*.001})
        pd.DataFrame(trades).to_csv(out/'trades.csv',index=False)
        if not np.isclose(sum(abs(t['signed_nav_weight_change']) for t in trades),p.turnover.sum()):raise ValueError('Trade ledger turnover mismatch')
        metrics={'label':'PROVISIONAL','factor':'alpha101_002','execution_aligned_mean_rank_ic':float(ic.mean()),
            'valid_ic_intervals':len(ic),'undefined_ic_intervals':len(p.ic_scores)-len(ic),
            'net_daily_annualized_sharpe':p.sharpe,'benchmark_daily_annualized_sharpe':annualized_sharpe(p.benchmark_returns),
            'net_cumulative_return':float(daily.net_nav.iloc[-1]-1),'gross_cumulative_return':float(daily.gross_nav.iloc[-1]-1),
            'benchmark_cumulative_return':float(daily.benchmark_nav.iloc[-1]-1),
            'net_max_drawdown':float((daily.net_nav/daily.net_nav.cummax()-1).min()),
            'evaluation_observations':len(daily),'input_sessions':len(pp.close),'rebalance_executions':len(p.executions),
            'stock_trade_legs':len(trades),'total_absolute_nav_turnover':float(p.turnover.sum()),
            'sum_cost_fractions':float(p.costs.sum()),'order_log_status_counts':pd.Series([r['status'] for r in p.order_log]).value_counts().to_dict(),
            'first_execution':str(p.executions.execution_date.min().date()),'last_execution':str(p.executions.execution_date.max().date()),
            'quality_flags':run.input_flags.flag.value_counts().to_dict(),'no_final_keep_drop':True}
        _json(out/'metrics.json',metrics)
        _json(out/'warnings.json',[
            'PROVISIONAL; one approved #2 diagnostic only; no final Keep/Drop.',
            'Pre-July-2023 Reliance vendor non-split price/volume normalization remains independently unexplained.',
            'Kotak March 1, 2024 five-vendor-share quantity discrepancy retained, not repaired or explained.',
            'Exactly twelve recovered quantities use verified surrounding frozen vendor units; no full historical nominal-volume certification.',
            'Frozen vendor adjustment vintage is not historically point-in-time. Later share metadata is not holdout price use.',
            'Original correlation NaNs remain NaN; fewer than eight scores skips a target and preserves existing holdings.',
            'Execution-aligned IC intervals can span more than one week when a signal is skipped; no fabricated weekly label.',
            'Calendar structural checks pass but exhaustive amendment inventory certainty is not claimed; strict manifest flags remain false.',
            'Nifty 50 is a price index; adjusted stock histories include cash-dividend adjustments.',
            'Fixed eight-stock universe, fractional targets, flat turnover costs and close/positive-volume fill proxies; no spread/impact/tax model.',
            'Initial cash days included; cash interest/risk-free zero; no final liquidation or post-cutoff observations.'])
        snapshot=out/'source_snapshot';snapshot.mkdir()
        for path in (ROOT/'src').glob('india_*.py'):(snapshot/path.name).write_bytes(path.read_bytes())
        for rel,h in factor.source_sha256.items():
            source=Path('/home/jampip/vibe-Trading/agent')/rel
            if _sha(source)!=h:raise ValueError('Vibe source changed')
            target=snapshot/'vibe'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        _json(out/'provenance.json',{'input_hashes':originals,'factor_source_sha256':factor.source_sha256,
            'factor_metadata':factor.metadata,'indicatorlab_head':_git(ROOT,'rev-parse','HEAD'),'branch':_git(ROOT,'branch','--show-current'),
            'working_tree':_git(ROOT,'status','--short'),'vibe_head':_git('/home/jampip/vibe-Trading','rev-parse','HEAD'),
            'jack_reference':_git(ROOT,'rev-parse','origin/jack'),'python':sys.version,'executable':str(ROOT/'.venv/bin/python'),
            'packages':{k:importlib.metadata.version(k) for k in ['pandas','numpy','scipy','pydantic','pytest']},
            'created_utc':datetime.now(timezone.utc).isoformat()})
        for path,h in originals.items():
            if _sha(path)!=h:raise ValueError(f'Protected input changed: {path}')
        _json(out/'status.json',{'status':'completed','label':'PROVISIONAL','all_inputs_and_prior_results_unchanged':True})
    except Exception as exc:
        _json(out/'status.json',{'status':'blocked','label':'PROVISIONAL','error':str(exc)});raise
    finally:
        _json(out/'artifact_hashes.json',{str(p.relative_to(out)):_sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_hashes.json'})
    return out


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-alpha002-diagnostic',action='store_true')
    print(run_alpha002(approved=parser.parse_args().approved_alpha002_diagnostic))
