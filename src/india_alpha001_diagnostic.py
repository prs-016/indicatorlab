"""Dataset-bound, single-factor PROVISIONAL Alpha101 #1 diagnostic runner.

Uses original Vibe factor/IC and the unchanged India portfolio simulator.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import uuid

import numpy as np
import pandas as pd

from src.india_backtest import PortfolioConfig, annualized_sharpe
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_diagnostic import ROOT, DATASET, DATASET_HASH, _sha, _json, _git
from src.india_factor_readiness import signal_coverage
from src.india_factors import load_factor_dataset, backtest_factor

REVIEW = ROOT/'india_research/reports/india_four_factor_real_readiness_review.md'
REVIEW_HASH = '2aff4b77b10e150f05f56510df31951e192fb998e1ac924d1a803e09174bedb3'
STREV_OUTPUT = ROOT/'results/india_strev_PROVISIONAL_20261029T021955Z_21d1a038'


def validate_alpha001_approval(summary: dict, *, approved: bool, dataset_hash: str,
                               review_hash: str, prior_sessions: int,
                               config: PortfolioConfig, factor='alpha101_001') -> dict:
    """Bind approval to #1, frozen evidence, unchanged settings and valid calendar.

    Inputs identify explicit approval, manifest/review hashes, common warm-up,
    actual calendar audit and configuration. Returns a diagnostic exception for
    exhaustive calendar inventory only; any scope/material validation change fails.
    """
    if (not approved or factor!='alpha101_001' or dataset_hash!=DATASET_HASH
            or review_hash!=REVIEW_HASH or config!=PortfolioConfig() or prior_sessions!=25):
        raise ValueError('Approval does not cover this factor, evidence, settings or 25-session warm-up')
    for key,expected in {'discrepancy_count':0,'unverifiable_calendar_dates':0,
                         'lookback_clock_mismatches':0,'warmup_complete':True,
                         'expected_evaluation_sessions':990,'evaluation_start':'2021-01-04'}.items():
        if summary.get(key)!=expected:
            raise ValueError('Material calendar/data validation failed; diagnostic denied')
    return {'label':'PROVISIONAL','factor':factor,'approved_by':'User/developer in current conversation',
        'authorization':'One provisional real-data diagnostic for alpha101_001 only.',
        'dataset_manifest_sha256':dataset_hash,'readiness_review_sha256':review_hash,
        'configuration':asdict(config),'prior_sessions':prior_sessions,
        'waived_requirement':'Exhaustive historical calendar inventory only',
        'calendar_certified':False,'other_factors_authorized':False,'final_keep_drop_authorized':False}


def selection_tie_audit(scores: pd.DataFrame) -> pd.DataFrame:
    """Describe weekly tie-driven membership under the unchanged ticker rule.

    Input is original eight-stock scores. Returns every weekly candidate's
    strict winners, cutoff tie pool, available slots, selected/rejected tied
    names, and whether the terminal signal can stage a later target. No alternate
    rule, holdings, returns or portfolio simulation is calculated.
    """
    evaluation=scores.loc['2021-01-04':'2024-12-31']
    weekly=evaluation.groupby(evaluation.index.to_period('W-FRI')).tail(1)
    rows=[]
    for date,row in weekly.iterrows():
        valid=row.dropna()
        if len(valid)!=8:
            rows.append({'signal_date':date,'eligible':False,'can_stage_target':False})
            continue
        selected=sorted(valid.index,key=lambda s:(-valid[s],s))[:2]
        cutoff=valid[selected[-1]]
        higher=sorted(valid.index[valid.gt(cutoff)])
        pool=sorted(valid.index[valid.eq(cutoff)])
        slots=2-len(higher)
        winners=[s for s in selected if s in pool]
        rows.append({'signal_date':date,'eligible':True,
            'can_stage_target':bool(date!=evaluation.index[-1]),
            'selected':selected,'strictly_above_cutoff':higher,'cutoff_score':float(cutoff),
            'cutoff_tie_pool':pool,'slots_at_cutoff':slots,
            'selected_from_cutoff_pool':winners,'rejected_from_cutoff_pool':[s for s in pool if s not in winners],
            'membership_depends_on_ticker':len(pool)>slots,'all_eight_tied':valid.nunique()==1})
    return pd.DataFrame(rows)


def run_alpha001(*, approved: bool) -> Path:
    """Run the one approved #1 diagnostic, preserving evidence and older results.

    Explicit approval is required; output is a new uniquely named directory.
    All inputs, source files and STREV artifacts are checksum-verified before and
    after. Errors retain a blocked status. No other factor or source data is run
    or changed, and strict calendar certification is never globally disabled.
    """
    config=PortfolioConfig();manifest_path=DATASET/'research_manifest.json'
    if _sha(manifest_path)!=DATASET_HASH or _sha(REVIEW)!=REVIEW_HASH:
        raise ValueError('Approved manifest or readiness review changed')
    manifest=json.loads(manifest_path.read_text())
    originals={**manifest['original_files_sha256'],**manifest['evidence_files_sha256'],
        **manifest['source_code_sha256'],str(manifest_path):DATASET_HASH,str(REVIEW):REVIEW_HASH}
    originals.update({str(DATASET/p):h for p,h in manifest['files_sha256'].items()})
    originals.update({str(STREV_OUTPUT/p):h for p,h in json.loads((STREV_OUTPUT/'artifact_hashes.json').read_text()).items()})
    for path,h in originals.items():
        if _sha(path)!=h:raise ValueError(f'Original checksum mismatch: {path}')
    # Assert the baseline is byte-for-value the same configuration as STREV.
    strev_config=json.loads((STREV_OUTPUT/'configuration.json').read_text())
    if any(strev_config[k]!=v for k,v in asdict(config).items()):
        raise ValueError('Portfolio baseline differs from archived STREV run')
    factor_evidence=ROOT/'results/india_four_factor_readiness_20261029T030714Z/factor_sources.json'
    source_versions=json.loads(factor_evidence.read_text())['alpha101_001']['source_sha256']
    originals[str(factor_evidence)]=_sha(factor_evidence)
    for relative,h in source_versions.items():
        source=Path('/home/jampip/vibe-Trading/agent')/relative
        if _sha(source)!=h:raise ValueError('Original Vibe source differs from audited implementation')
        originals[str(source)]=h
    panel=load_factor_dataset(manifest_path)
    rules_path=ROOT/'results/india_calendar_phase4c_20261029T015149Z_53a60385/audit_v1/calendar_rules.json'
    if _sha(rules_path)!=manifest['calendar_rules_sha256']:raise ValueError('Calendar rule checksum mismatch')
    rules=json.loads(rules_path.read_text())
    calendar=reconstruct_calendar('2020-11-26','2024-12-31',
        annual_rules={int(y):r for y,r in rules['annual_rules'].items()},overrides=rules['overrides'])
    expected=calendar.index[calendar.status.eq('session')]
    if not panel.portfolio_panel.close.index.equals(expected) or len(expected)!=1015:
        raise ValueError('Required 25-session/evaluation calendar mismatch')
    ppanel=panel.portfolio_panel
    histories={s:pd.DataFrame({'close':ppanel.close[s],'volume':ppanel.volume[s]}) for s in NSE_STOCKS}
    histories[BENCHMARK]=ppanel.benchmark.to_frame('close')
    audit=audit_calendar(calendar,histories,amendment_coverage_confirmed=False)
    prior=int((ppanel.close.index<pd.Timestamp(config.start)).sum())
    approval=validate_alpha001_approval(audit.summary,approved=approved,dataset_hash=_sha(manifest_path),
        review_hash=_sha(REVIEW),prior_sessions=prior,config=config)
    output=ROOT/'results'/('india_alpha101_001_PROVISIONAL_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
    output.mkdir(exist_ok=False)
    _json(output/'diagnostic_approval.json',approval)
    _json(output/'configuration.json',{'label':'PROVISIONAL','factor':'alpha101_001',**asdict(config),
        'universe':NSE_STOCKS,'benchmark':BENCHMARK,'warmup_prior_sessions':25,
        'input_start':'2020-11-26','execution':'subsequent eligible close',
        'ties':'descending original score, then ascending ticker; no randomization',
        'ic':'all-eight cross-sectional rank IC, actual execution to next execution interval',
        'sharpe':'sqrt(252) * daily net mean / sample standard deviation; zero risk-free',
        'terminal_liquidation':False})
    (output/'dataset_manifest.json').write_bytes(manifest_path.read_bytes())
    (output/'readiness_review.md').write_bytes(REVIEW.read_bytes())
    _json(output/'calendar_audit.json',audit.summary)
    _json(output/'warmup_audit.json',{'prior_sessions':prior,'first_prior_session':str(expected[0].date()),
        'last_prior_session':'2021-01-01','evaluation_sessions':990,
        'comparison':'exact date equality for 25 prior sessions and 990 evaluation sessions',
        'calendar_certified':False})
    try:
        run=backtest_factor(panel,'alpha101_001',vibe_root='/home/jampip/vibe-Trading',
                           python_executable=ROOT/'.venv/bin/python',config=config)
        p=run.portfolio;factor=run.factor;ic=run.execution_ic
        ties=selection_tie_audit(factor.scores)
        _json(output/'weekly_selection_ties.json',ties.to_dict('records'))
        ties.to_csv(output/'weekly_selection_ties.csv',index=False)
        executed=ties.set_index('signal_date').loc[p.executions.signal_date]
        totals={s:0 for s in NSE_STOCKS};tie_picks={s:0 for s in NSE_STOCKS}
        for row in executed.itertuples():
            for s in row.selected:totals[s]+=1
            if row.membership_depends_on_ticker:
                for s in row.selected_from_cutoff_pool:tie_picks[s]+=1
        _json(output/'tie_selection_counts_by_stock.json',{'all_executed_selection_counts':totals,
            'membership_ambiguous_cutoff_picks_by_ticker':tie_picks})
        coverage,daily_ties=signal_coverage(factor.scores)
        _json(output/'signal_coverage.json',coverage)
        daily_ties.to_csv(output/'daily_signal_ties.csv')
        factor.scores.to_csv(output/'factor_scores.csv',index_label='date')
        factor.missing_scores.to_csv(output/'missing_scores.csv',index=False)
        (output/'factor_worker_stderr.txt').write_text(factor.worker_stderr)
        ic.to_csv(output/'execution_aligned_ic.csv',index_label='signal_date')
        p.ic_scores.to_csv(output/'ic_scores.csv',index_label='signal_date')
        p.ic_returns.to_csv(output/'ic_forward_returns.csv',index_label='signal_date')
        undefined=p.ic_scores.index.difference(ic.index)
        _json(output/'undefined_ic_intervals.json',[{'signal_date':d,
            'cause':'constant_signal_scores' if p.ic_scores.loc[d].nunique()==1 else 'other_original_IC_degeneracy'} for d in undefined])
        p.weights.to_csv(output/'holdings_weights.csv',index_label='date')
        p.executions.to_csv(output/'executions.csv',index=False)
        _json(output/'order_log.json',p.order_log)
        run.input_flags.to_csv(output/'quality_flags.csv',index=False)
        ppanel.close.to_csv(output/'input_adjusted_closes.csv',index_label='date')
        ppanel.volume.to_csv(output/'input_volumes.csv',index_label='date')
        ppanel.benchmark.to_csv(output/'input_benchmark.csv',index_label='date')
        daily=pd.concat([p.net_returns,p.gross_returns,p.benchmark_returns,p.turnover,p.costs],axis=1)
        daily['net_nav']=(1+p.net_returns).cumprod();daily['gross_nav']=(1+p.gross_returns).cumprod()
        daily['benchmark_nav']=(1+p.benchmark_returns).cumprod()
        daily.to_csv(output/'daily_returns_nav.csv',index_label='date')
        trades=[]
        for event in p.executions.itertuples():
            date=event.execution_date;prior_date=ppanel.close.index[ppanel.close.index.get_loc(date)-1]
            before=(p.weights.loc[prior_date]*(ppanel.close.loc[date]/ppanel.close.loc[prior_date])/(1+p.gross_returns.loc[date])) if prior_date in p.weights.index else pd.Series(0.,index=NSE_STOCKS)
            for s in NSE_STOCKS:
                change=float(p.weights.loc[date,s]-before[s])
                if abs(change)>1e-12:
                    trades.append({'signal_date':event.signal_date,'execution_date':date,'symbol':s,
                        'side':'buy' if change>0 else 'sell','pretrade_weight':float(before[s]),
                        'target_weight':float(p.weights.loc[date,s]),'signed_nav_weight_change':change,
                        'adjusted_execution_close':float(ppanel.close.loc[date,s]),'cost_fraction':abs(change)*.001})
        pd.DataFrame(trades).to_csv(output/'trades.csv',index=False)
        if not np.isclose(sum(abs(t['signed_nav_weight_change']) for t in trades),p.turnover.sum()):
            raise ValueError('Trade ledger turnover mismatch')
        if not (p.executions.execution_date>p.executions.signal_date).all():raise ValueError('Noncausal execution')
        metrics={'label':'PROVISIONAL','factor':'alpha101_001',
            'execution_aligned_mean_rank_ic':float(ic.mean()),'valid_ic_intervals':len(ic),
            'undefined_ic_intervals':len(undefined),'net_daily_annualized_sharpe':p.sharpe,
            'benchmark_daily_annualized_sharpe':annualized_sharpe(p.benchmark_returns),
            'net_cumulative_return':float(daily.net_nav.iloc[-1]-1),
            'gross_cumulative_return':float(daily.gross_nav.iloc[-1]-1),
            'benchmark_cumulative_return':float(daily.benchmark_nav.iloc[-1]-1),
            'net_max_drawdown':float((daily.net_nav/daily.net_nav.cummax()-1).min()),
            'evaluation_observations':len(daily),'input_sessions':len(expected),'prior_sessions':prior,
            'rebalance_executions':len(p.executions),'stock_trade_legs':len(trades),
            'total_absolute_nav_turnover':float(p.turnover.sum()),'sum_cost_fractions':float(p.costs.sum()),
            'executed_targets_membership_depends_on_ticker':int(executed.membership_depends_on_ticker.sum()),
            'executed_targets_all_eight_tied':int(executed.all_eight_tied.sum()),
            'quality_flags_by_kind':run.input_flags.flag.value_counts().to_dict(),
            'first_execution':str(p.executions.execution_date.min().date()),
            'last_execution':str(p.executions.execution_date.max().date()),'no_final_keep_drop':True}
        _json(output/'metrics.json',metrics)
        _json(output/'warnings.json',[
            'PROVISIONAL one-factor diagnostic; no Keep/Drop decision.',
            'Original discrete factor scores are heavily tied; alphabetical ticker order can determine portfolio membership.',
            'Constant cross-sectional signal scores yield undefined IC, omitted by original Vibe IC rather than filled with zero.',
            'Frozen Yahoo adjustment vintage is not historically point-in-time; exact pre-demerger Reliance normalization remains unresolved.',
            'Recovered nominal volume differs from vendor share-scaled volume for three stocks; #1 is close-only and simulator uses positive-volume eligibility, not volume sizing.',
            'Original dataset and all STREV artifacts unchanged. No volume/price repair, input convention change or other factor run.',
            'Calendar inventory is not exhaustive; structural calendar and 25-session warm-up checks passed.',
            'Nifty 50 is a price index, while adjusted stock histories include dividend adjustments.',
            'Fixed eight-stock universe, fractional weights, flat 10 bps turnover costs and close/positive-volume execution proxies; no spread/impact model.',
            'Initial cash days included; zero risk-free/cash interest; no terminal liquidation or post-cutoff labels.'])
        snapshot=output/'source_snapshot';snapshot.mkdir()
        for path in (ROOT/'src').glob('india_*.py'):(snapshot/path.name).write_bytes(path.read_bytes())
        for relative,h in factor.source_sha256.items():
            source=Path('/home/jampip/vibe-Trading/agent')/relative
            if _sha(source)!=h:raise ValueError('Vibe source changed during run')
            target=snapshot/'vibe'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        _json(output/'provenance.json',{'input_hashes':originals,'factor_source_sha256':factor.source_sha256,
            'factor_metadata':factor.metadata,'indicatorlab_head':_git(ROOT,'rev-parse','HEAD'),
            'branch':_git(ROOT,'branch','--show-current'),'working_tree':_git(ROOT,'status','--short'),
            'vibe_head':_git('/home/jampip/vibe-Trading','rev-parse','HEAD'),
            'jack_reference':_git(ROOT,'rev-parse','origin/jack'),'python':sys.version,
            'executable':str(ROOT/'.venv/bin/python'),
            'packages':{k:importlib.metadata.version(k) for k in ['pandas','numpy','scipy','pydantic','pytest']},
            'created_utc':datetime.now(timezone.utc).isoformat()})
        for path,h in originals.items():
            if _sha(path)!=h:raise ValueError(f'Original changed during run: {path}')
        _json(output/'status.json',{'status':'completed','label':'PROVISIONAL','all_originals_and_strev_unchanged':True})
    except Exception as exc:
        _json(output/'status.json',{'status':'blocked','error':str(exc),'label':'PROVISIONAL'})
        raise
    finally:
        _json(output/'artifact_hashes.json',{str(p.relative_to(output)):_sha(p) for p in output.rglob('*') if p.is_file() and p.name!='artifact_hashes.json'})
    return output


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-alpha001-diagnostic',action='store_true')
    print(run_alpha001(approved=parser.parse_args().approved_alpha001_diagnostic))
