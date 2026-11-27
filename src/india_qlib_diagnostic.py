"""Single approved, cached-score PROVISIONAL diagnostics for India factors 11–15.

Reuse the frozen research_v4 panel, material calendar checks, original isolated
factor/IC functions and unchanged Jack-inspired portfolio. Never download data.
"""
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

from src.india_alpha002_diagnostic import DATASET, DATASET_HASH, PACKAGE, PACKAGE_HASH
from src.india_backtest import PortfolioConfig, annualized_sharpe, simulate_portfolio
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_diagnostic import ROOT, REVIEW, REVIEW_HASH, _sha, _json, _git
from src.india_factors import load_factor_dataset
from src.india_phase2_diagnostic import _verify_inventory, execution_trade_ledger
from src.india_qlib_factors import (
    QLIB_SPECS, evaluate_qlib_factor, missing_score_causes, readiness_gate,
)
from src.india_vibe_bridge import compute_rank_ic

APPROVAL_ID = 'user_approved_single_qlib158_11_15_conditional_diagnostics_20261101'
CACHED_BENCHMARK = ROOT / 'results/india_alpha101_033_PROVISIONAL_20261029T052028Z_88f535b9/daily_returns_nav.csv'
WARNINGS = [
    'PROVISIONAL single diagnostic; no final Keep/Drop, repeat or publication approval.',
    'Frozen Yahoo adjusted history is not historically point-in-time; later actions affect the vintage.',
    'Reliance pre-July-2023 normalization and the small Kotak quantity discrepancy remain unresolved.',
    'Twelve recovered volume units are verified; full-history daily quantities are not independently certified.',
    'Material calendar/session checks pass; only exhaustive amendment-inventory certainty is waived.',
    'Nifty 50 price index excludes dividends; adjusted stock histories carry dividend adjustments.',
    'Fixed eight-name basket and concentrated long-only portfolio; no spread, impact, taxes or capacity model.',
    'Price adjustments varying within a rolling window can change scores; no alternative convention chosen from returns.',
]


def validate_scope(*, approved, dataset_hash, review_hash, calendar_summary,
                   config, prior_sessions):
    """Bind approval to v4, review, fixed settings and complete material calendar.

    Inputs are explicit approval, hashes and current audit/configuration. Returns
    the narrowly scoped record; strict source certification flags remain false.
    """
    if (not approved or dataset_hash != DATASET_HASH or review_hash != REVIEW_HASH
            or config != PortfolioConfig() or prior_sessions != 25):
        raise ValueError('Qlib158 approval does not cover changed scope/settings')
    expected = {'discrepancy_count': 0, 'unverifiable_calendar_dates': 0,
                'lookback_clock_mismatches': 0, 'warmup_complete': True,
                'expected_evaluation_sessions': 990, 'evaluation_start': '2021-01-04'}
    if any(calendar_summary.get(k) != v for k, v in expected.items()):
        raise ValueError('Material calendar validation failed')
    return {'approval_id': APPROVAL_ID, 'label': 'PROVISIONAL',
        'factors': list(QLIB_SPECS), 'dataset_manifest_sha256': dataset_hash,
        'calendar_review_sha256': review_hash, 'configuration': asdict(config),
        'prior_sessions': prior_sessions, 'calendar_certified': False,
        'waived_requirement': 'Exhaustive historical amendment inventory only',
        'signal_readiness_required_before_each_portfolio': True,
        'repeat_authorized': False, 'final_keep_drop_authorized': False}


def _inventory(directory):
    _json(directory / 'artifact_hashes.json', {str(p.relative_to(directory)): _sha(p)
        for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'artifact_hashes.json'})


def _calendar(panel, manifest):
    path = ROOT / 'results/india_calendar_phase4c_20261029T015149Z_53a60385/audit_v1/calendar_rules.json'
    if _sha(path) != manifest['calendar_rules_sha256']:
        raise ValueError('Frozen calendar rules changed')
    rules = json.loads(path.read_text())
    calendar = reconstruct_calendar('2020-11-26', '2024-12-31',
        annual_rules={int(y): v for y, v in rules['annual_rules'].items()}, overrides=rules['overrides'])
    pp = panel.portfolio_panel
    if not calendar.index[calendar.status.eq('session')].equals(pp.close.index):
        raise ValueError('Calendar/input mismatch')
    histories = {s: pd.DataFrame({'close': pp.close[s], 'volume': pp.volume[s]}) for s in NSE_STOCKS}
    histories[BENCHMARK] = pp.benchmark.to_frame('close')
    return audit_calendar(calendar, histories, amendment_coverage_confirmed=False)


def _save_portfolio(out, panel, scores, factor, runtime, cached_benchmark):
    pp, config = panel.portfolio_panel, PortfolioConfig()
    p = simulate_portfolio(pp, scores, config=config)
    ic = compute_rank_ic(p.ic_scores, p.ic_returns, **runtime)
    pd.testing.assert_series_equal(p.benchmark_returns, cached_benchmark,
        check_names=False, check_freq=False, rtol=1e-13, atol=1e-15)
    daily = pd.concat([p.net_returns, p.gross_returns, p.benchmark_returns, p.turnover, p.costs], axis=1)
    for key, series in [('net_nav', p.net_returns), ('gross_nav', p.gross_returns),
                        ('benchmark_nav', p.benchmark_returns)]:
        daily[key] = (1 + series).cumprod()
    if (len(daily) != 990 or daily.index.max() > pd.Timestamp(config.end)
            or not np.isfinite(daily.to_numpy()).all()):
        raise ValueError('Invalid daily observations or cutoff')
    np.testing.assert_allclose(p.costs, p.turnover * .001, atol=1e-15)
    np.testing.assert_allclose(p.net_returns, (1+p.gross_returns)*(1-p.costs)-1, atol=1e-15)
    intervals = []
    for a, b in zip(p.executions.itertuples(), p.executions.iloc[1:].itertuples()):
        if not a.signal_date < a.execution_date < b.execution_date <= pd.Timestamp(config.end):
            raise ValueError('Execution/label timing outside approved bounds')
        np.testing.assert_allclose(p.ic_returns.loc[a.signal_date],
            pp.close.loc[b.execution_date] / pp.close.loc[a.execution_date] - 1)
        intervals.append({'signal_date': a.signal_date, 'entry_close': a.execution_date,
            'exit_close': b.execution_date, 'sessions': pp.close.index.get_loc(b.execution_date)
                                                       - pp.close.index.get_loc(a.execution_date)})
    trades = execution_trade_ledger(pp, p, config)
    for name, frame in [('daily_returns_nav', daily), ('holdings_weights', p.weights),
                        ('ic_scores', p.ic_scores), ('ic_forward_returns', p.ic_returns)]:
        frame.to_csv(out / (name + '.csv'), index_label='date')
    p.executions.to_csv(out / 'executions.csv', index=False)
    trades.to_csv(out / 'trades.csv', index=False)
    pd.DataFrame(intervals).to_csv(out / 'ic_intervals.csv', index=False)
    ic.to_csv(out / 'execution_aligned_ic.csv', index_label='signal_date')
    _json(out / 'order_log.json', p.order_log)
    return {'label': 'PROVISIONAL', 'factor': factor,
        'execution_aligned_mean_rank_ic': float(ic.mean()), 'valid_ic_intervals': len(ic),
        'undefined_ic_intervals': len(p.ic_scores)-len(ic),
        'net_daily_annualized_sharpe': p.sharpe,
        'net_cumulative_return': float(daily.net_nav.iloc[-1]-1),
        'gross_cumulative_return': float(daily.gross_nav.iloc[-1]-1),
        'benchmark_cumulative_return': float(daily.benchmark_nav.iloc[-1]-1),
        'benchmark_daily_annualized_sharpe': annualized_sharpe(p.benchmark_returns),
        'return_minus_benchmark_pp': float((daily.net_nav.iloc[-1]-daily.benchmark_nav.iloc[-1])*100),
        'rebalance_executions': len(p.executions), 'stock_trade_legs': len(trades),
        'total_absolute_nav_turnover': float(p.turnover.sum()), 'sum_cost_fractions': float(p.costs.sum()),
        'evaluation_observations': len(daily), 'input_sessions': len(pp.close), 'prior_sessions': 25,
        'first_execution': str(p.executions.execution_date.min().date()),
        'last_execution': str(p.executions.execution_date.max().date()),
        'labels_and_executions_within_cutoff': True}


def run_qlib_diagnostics(*, approved, vibe_root, python_executable, test_log):
    """Run the five conditional single diagnostics, calculating each score once.

    Parameters specify current approval, existing Vibe runtime and a completed
    test log. Returns a unique hashed batch directory. Shared v4/calendar/volume
    checks run once; cached original scores feed readiness then accounting/IC.
    A failed signal gate saves N/A metrics and never invokes the simulator.
    """
    if not approved:
        raise ValueError('Explicit approval required')
    for old in (ROOT / 'results').glob('india_qlib158_PROVISIONAL_*/**/factor_scores.csv'):
        raise ValueError(f'Single-run score approval already consumed: {old}')
    _verify_inventory(PACKAGE, PACKAGE_HASH)
    manifest_path = DATASET / 'research_manifest.json'
    if _sha(manifest_path) != DATASET_HASH or _sha(REVIEW) != REVIEW_HASH:
        raise ValueError('Frozen dataset/calendar review changed')
    verifier_spec = importlib.util.spec_from_file_location('readonly_existing_v4', PACKAGE / 'verify_existing_v4.py')
    verifier = importlib.util.module_from_spec(verifier_spec)
    verifier_spec.loader.exec_module(verifier)
    verification = verifier.verify()
    if verification['verified_changes'] != 12 or verification['verified_quantity_anchors'] != 24:
        raise ValueError('Volume verification scope changed')
    _verify_inventory(CACHED_BENCHMARK.parent,
        'f5c58de1daafe0c244d3922873673d46e46e94c26c2bbbcb8ee16ab9c92657e9')
    panel = load_factor_dataset(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    audit = _calendar(panel, manifest)
    config = PortfolioConfig()
    approval = validate_scope(approved=approved, dataset_hash=_sha(manifest_path),
        review_hash=_sha(REVIEW), calendar_summary=audit.summary, config=config,
        prior_sessions=int((panel.portfolio_panel.close.index < pd.Timestamp(config.start)).sum()))
    test_bytes = Path(test_log).read_bytes()
    summary_line = test_bytes.decode().strip().splitlines()[-1].lower()
    if (' passed ' not in summary_line
            or any(token in summary_line for token in (' failed', ' error', ' skipped'))):
        raise ValueError('A passing complete test log is required')
    out = ROOT / 'results' / ('india_qlib158_PROVISIONAL_' +
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    _json(out / 'diagnostic_approval.json', approval)
    (out / 'complete_test_suite.log').write_bytes(test_bytes)
    (out / 'dataset_manifest.json').write_bytes(manifest_path.read_bytes())
    (out / 'calendar_readiness_review.md').write_bytes(REVIEW.read_bytes())
    _json(out / 'shared_preflight.json', {'calendar': audit.summary, 'volume': verification})
    panel.input_flags.to_csv(out / 'quality_flags.csv', index=False)
    cached = pd.read_csv(CACHED_BENCHMARK, index_col=0, parse_dates=True)['benchmark_return']
    cached.to_csv(out / 'cached_benchmark_returns.csv', index_label='date')
    provenance = {'dataset_manifest': str(manifest_path.relative_to(ROOT)),
        'dataset_manifest_sha256': DATASET_HASH, 'dataset_files_sha256': manifest['files_sha256'],
        'volume_package_inventory_sha256': PACKAGE_HASH, 'calendar_review_sha256': REVIEW_HASH,
        'cached_benchmark_source': str(CACHED_BENCHMARK.relative_to(ROOT)),
        'cached_benchmark_source_sha256': _sha(CACHED_BENCHMARK),
        'indicatorlab_head': _git(ROOT, 'rev-parse', 'HEAD'),
        'vibe_head': _git(vibe_root, 'rev-parse', 'HEAD'), 'python': sys.version,
        'packages': {k: importlib.metadata.version(k) for k in ['numpy', 'pandas', 'scipy', 'pydantic', 'pytest']}}
    _json(out / 'provenance.json', provenance)
    for source in (ROOT / 'src').glob('india_*.py'):
        dest = out / 'source_snapshot' / 'indicatorlab' / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
    runtime = {'vibe_root': vibe_root, 'python_executable': python_executable}
    comparison = []
    for factor, spec in QLIB_SPECS.items():
        dest = out / factor
        dest.mkdir(exist_ok=False)
        try:
            _json(dest / 'configuration.json', {'label': 'PROVISIONAL', 'factor': factor,
                **asdict(config), 'universe': NSE_STOCKS, 'benchmark': BENCHMARK,
                'prior_sessions': 25, 'metadata_warmup_bars': spec.original.warmup_bars,
                'effective_input_rows': spec.effective_rows, 'score_direction': 'unchanged; descending',
                'execution': 'subsequent eligible close', 'tie_rule': 'ascending ticker',
                'ic': 'original Vibe rank IC; actual execution close to next successful execution close',
                'sharpe': 'daily net mean / sample std * sqrt(252); zero risk-free',
                'costs': '10 bps * absolute traded NAV, including initial entry and drift rebalance',
                'net_return': '(1 + gross_return) * (1 - cost_fraction) - 1',
                'initial_cash_included': True, 'terminal_liquidation': False})
            _json(dest / 'status.json', {'status': 'factor_invocation_started', 'original_compute_invocations': 1})
            scores, evidence = evaluate_qlib_factor(panel, factor, **runtime)
            scores.to_csv(dest / 'factor_scores.csv', index_label='date', float_format='%.17g')
            _json(dest / 'original_metadata_and_numerics.json', evidence)
            # Round-trip the saved cache; portfolios use these exact saved scores.
            saved = pd.read_csv(dest / 'factor_scores.csv', index_col=0, parse_dates=True, float_precision='round_trip')
            pd.testing.assert_frame_equal(saved, scores, check_freq=False, check_names=False, check_exact=True)
            causes = missing_score_causes(panel.fields, factor, saved)
            causes.to_csv(dest / 'missing_score_causes.csv', index=False)
            summary, profiles, blockers = readiness_gate(saved, evidence, causes)
            input_issues = {k: {'missing': int(panel.fields[k].isna().sum().sum()),
                               'zero': int(panel.fields[k].eq(0).sum().sum())}
                            for k in spec.original.dependencies}
            if any(v['missing'] or v['zero'] for v in input_issues.values()):
                blockers.append('Missing/zero dependency observations require input review')
            _json(dest / 'signal_readiness.json', {'summary': summary, 'blockers': blockers,
                'missing_causes': causes.cause.value_counts().to_dict(), 'input_observations': input_issues,
                'basis': 'Frozen adjusted INR OHLC; research_v4 vendor share-volume convention',
                'known_limitations': WARNINGS, 'alternative_conventions_scored': False})
            _json(dest / 'weekly_candidates.json', profiles)
            _json(dest / 'provenance.json', {**provenance, 'source_sha256': evidence['source_sha256'],
                'factor_scores_sha256': _sha(dest / 'factor_scores.csv'), 'original_compute_invocations': 1})
            for rel, expected in evidence['source_sha256'].items():
                source = Path(vibe_root) / 'agent' / rel
                if _sha(source) != expected:
                    raise ValueError('Original Vibe source changed during run')
                target = dest / 'source_snapshot' / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            warnings = list(WARNINGS)
            if factor == 'qlib158_wvma20':
                warnings.append('Constant per-stock volume scaling mostly cancels; time-varying share units/return adjustments do not. Zero volume contributes zero; all-zero weighted mean is undefined.')
            if factor == 'qlib158_cord10':
                warnings.append('Original volume +1 constant makes volume-unit invariance inexact. Constant ratio windows are undefined; full-history vendor-volume certification is incomplete.')
            _json(dest / 'warnings.json', warnings)
            if blockers:
                metrics = {'label': 'PROVISIONAL', 'factor': factor, 'status': 'unrun_readiness_blocked',
                           'execution_aligned_mean_rank_ic': None, 'net_daily_annualized_sharpe': None,
                           'net_cumulative_return': None, 'blockers': blockers}
            else:
                metrics = _save_portfolio(dest, panel, saved, factor, runtime, cached)
                metrics['status'] = 'completed'
            _json(dest / 'metrics.json', metrics)
            _json(dest / 'status.json', {'label': 'PROVISIONAL', 'status': metrics['status'],
                'original_compute_invocations': 1, 'portfolio_evaluations': int(not blockers),
                'score_cache_sha256': _sha(dest / 'factor_scores.csv')})
            _inventory(dest)
            comparison.append(metrics)
        except Exception as exc:
            _json(dest / 'status.json', {'label': 'PROVISIONAL', 'status': 'blocked_error',
                'error': str(exc), 'repeat_authorized': False})
            _inventory(dest)
            _inventory(out)
            raise
    _json(out / 'comparison.json', comparison)
    pd.DataFrame(comparison).to_csv(out / 'comparison.csv', index=False, na_rep='N/A')
    _verify_inventory(PACKAGE, PACKAGE_HASH)
    if _sha(manifest_path) != DATASET_HASH:
        raise ValueError('Dataset changed during run')
    _json(out / 'status.json', {'label': 'PROVISIONAL', 'factor_compute_invocations': 5,
        'completed_portfolios': sum(r['status'] == 'completed' for r in comparison),
        'blocked_portfolios': sum(r['status'] != 'completed' for r in comparison)})
    _inventory(out)
    return out


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-diagnostics', action='store_true')
    parser.add_argument('--test-log', type=Path, required=True)
    args = parser.parse_args()
    print(run_qlib_diagnostics(approved=args.approved_diagnostics,
        vibe_root='/home/jampip/vibe-Trading', python_executable=ROOT / '.venv/bin/python',
        test_log=args.test_log))
