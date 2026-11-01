"""Four explicitly approved PROVISIONAL India expansion-factor diagnostics.

Original factor/IC and portfolio implementations are reused without changes.
Only exhaustive historical calendar-inventory certainty is waived, within the
pinned scope; no source-data certification flag is changed.
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

from src.india_alpha002_diagnostic import (
    DATASET, DATASET_HASH, PACKAGE, PACKAGE_HASH,
)
from src.india_backtest import PortfolioConfig, annualized_sharpe
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_diagnostic import ROOT, REVIEW as CALENDAR_REVIEW
from src.india_diagnostic import REVIEW_HASH as CALENDAR_REVIEW_HASH
from src.india_diagnostic import _sha, _json, _git
from src.india_factors import load_factor_dataset
from src.india_phase2_factors import PHASE2_SPECS, backtest_phase2_factor
from src.india_phase2_readiness import selection_summary, input_and_missing_audit

APPROVED_FACTORS = ('alpha101_033', 'alpha101_101', 'alpha101_054', 'alpha101_014')
APPROVAL_ID = 'four_phase2_provisional_diagnostics_20261029'
AUDIT = ROOT / 'results/india_phase2_signal_readiness_20261029T050613Z'
AUDIT_HASH = '353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b'
REVIEW = ROOT / 'india_research/reports/india_phase2_signal_readiness_review.md'
REVIEW_HASH = '055cebcac8f176f2ad31bcf80bb29a3d019fd516ad9deb085e41391f8b82f1f3'


def validate_phase2_approval(factor, *, approved, dataset_hash, review_hash,
                             audit_hash, calendar_summary, signal_summary,
                             causal_checks, volume_verification, config,
                             prior_sessions):
    """Return a narrow diagnostic permission record or reject scope/evidence drift.

    Inputs bind explicit approval, four-ID allowlist, evidence hashes, exact
    baseline, complete signals, causal checks and material calendar/quantity gates.
    No permission for ILLIQ, repeats, final claims or source changes is returned.
    """
    if (not approved or factor not in APPROVED_FACTORS
            or dataset_hash != DATASET_HASH or review_hash != REVIEW_HASH
            or audit_hash != AUDIT_HASH or config != PortfolioConfig()
            or prior_sessions != 25):
        raise ValueError('Approval does not cover factor/evidence/settings/warm-up')
    expected = {'discrepancy_count': 0, 'unverifiable_calendar_dates': 0,
                'lookback_clock_mismatches': 0, 'warmup_complete': True,
                'expected_evaluation_sessions': 990, 'evaluation_start': '2021-01-04'}
    if any(calendar_summary.get(k) != v for k, v in expected.items()):
        raise ValueError('Material calendar validation failed')
    signal_expected = {'finite_scores': 7920, 'nan_scores': 0, 'infinite_scores': 0,
                       'weekly_candidates': 209, 'weekly_eight_finite': 209,
                       'weekly_unique_top_two': 209, 'weekly_boundary_ties': 0}
    if any(signal_summary.get(k) != v for k, v in signal_expected.items()):
        raise ValueError('Signal readiness evidence changed')
    if (len(causal_checks) != 4 or not all(c['passed'] for c in causal_checks)
            or sorted(c['test'] for c in causal_checks)
            != ['minimum_window_final_row', 'prefix', 'prefix', 'prefix']):
        raise ValueError('No-look-ahead/window evidence incomplete')
    if (volume_verification.get('status') != 'passed'
            or volume_verification.get('verified_changes') != 12
            or volume_verification.get('verified_quantity_anchors') != 24
            or volume_verification.get('dataset_manifest_sha256') != DATASET_HASH
            or not volume_verification.get('all_other_csv_tokens_and_line_endings_preserved')):
        raise ValueError('research_v4 quantity/provenance verification failed')
    return {'label': 'PROVISIONAL', 'factor': factor, 'approval_id': APPROVAL_ID,
            'authorization': 'User approved one run each of exactly four Phase 2 factors.',
            'dataset_manifest_sha256': dataset_hash, 'readiness_review_sha256': review_hash,
            'signal_audit_inventory_sha256': audit_hash,
            'calendar_review_sha256': CALENDAR_REVIEW_HASH,
            'waived_requirement': 'Exhaustive historical calendar inventory only; all material checks retained',
            'calendar_certified': False, 'academic_illiq_authorized': False,
            'repeat_authorized': False, 'final_keep_drop_authorized': False,
            'configuration': asdict(config)}


def execution_trade_ledger(panel, portfolio, config):
    """Derive auditable signed NAV trade legs from existing accounting results.

    Inputs are the unchanged panel/result/config. Returns legs whose absolute
    weights and costs reconcile to recorded turnover; no execution is simulated.
    """
    trades = []
    for event in portfolio.executions.itertuples():
        date = event.execution_date
        if not event.signal_date < date <= pd.Timestamp(config.end):
            raise ValueError('Execution outside approved causal/cutoff bounds')
        previous = panel.close.index[panel.close.index.get_loc(date) - 1]
        before = pd.Series(0., index=NSE_STOCKS)
        if previous in portfolio.weights.index:
            before = (portfolio.weights.loc[previous]
                      * (panel.close.loc[date] / panel.close.loc[previous])
                      / (1 + portfolio.gross_returns.loc[date]))
        for symbol in NSE_STOCKS:
            change = float(portfolio.weights.loc[date, symbol] - before[symbol])
            if abs(change) > 1e-12:
                trades.append({'signal_date': event.signal_date, 'execution_date': date,
                    'symbol': symbol, 'side': 'buy' if change > 0 else 'sell',
                    'pretrade_weight': float(before[symbol]),
                    'target_weight': float(portfolio.weights.loc[date, symbol]),
                    'signed_nav_weight_change': change,
                    'adjusted_execution_close': float(panel.close.loc[date, symbol]),
                    'cost_fraction': abs(change) * config.cost_bps / 10000})
    frame = pd.DataFrame(trades)
    if (not np.isclose(frame.signed_nav_weight_change.abs().sum(), portfolio.turnover.sum())
            or not np.isclose(frame.cost_fraction.sum(), portfolio.costs.sum())):
        raise ValueError('Trade ledger does not reconcile to turnover/costs')
    return frame


def _verify_inventory(directory, inventory_hash):
    inventory = directory / 'artifact_hashes.json'
    if _sha(inventory) != inventory_hash:
        raise ValueError('Frozen inventory changed')
    for rel, expected in json.loads(inventory.read_text()).items():
        if _sha(directory / rel) != expected:
            raise ValueError(f'Frozen artifact changed: {directory / rel}')


def _read_causal_checks(path, factor):
    checks = pd.read_csv(path)
    checks = checks[checks.factor.eq(factor)]
    # Absent optional dates/windows are evidence nulls, not numeric NaNs.
    return checks.astype(object).where(checks.notna(), None).to_dict('records')


def run_phase2_diagnostic(factor, *, approved):
    """Preflight and execute exactly one approved original factor into a fresh output.

    Explicit approval and pinned signal/dataset/calendar evidence are required.
    Returns unique output path; failures retain a blocked record, never overwrite
    prior outputs. This approval cannot authorize ILLIQ or repeat completed runs.
    """
    if not approved or factor not in APPROVED_FACTORS:
        raise ValueError('Only four explicitly approved factors may run')
    for old in (ROOT / 'results').glob(f'india_{factor}_PROVISIONAL_*/diagnostic_approval.json'):
        record = json.loads(old.read_text())
        if record.get('approval_id') == APPROVAL_ID:
            status_path = old.parent / 'status.json'
            status = json.loads(status_path.read_text()) if status_path.exists() else {}
            failed_before_run = (
                status.get('status') == 'preflight_failed_factor_not_invoked'
                and status.get('factor_invocations') == 0
                and status.get('portfolio_evaluations') == 0
                and not (old.parent / 'factor_scores.csv').exists()
                and not (old.parent / 'executions.csv').exists())
            if not failed_before_run:
                raise ValueError('This factor approval was already used; do not repeat')
    _verify_inventory(AUDIT, AUDIT_HASH)
    _verify_inventory(PACKAGE, PACKAGE_HASH)
    manifest = DATASET / 'research_manifest.json'
    if (_sha(manifest) != DATASET_HASH or _sha(REVIEW) != REVIEW_HASH
            or _sha(CALENDAR_REVIEW) != CALENDAR_REVIEW_HASH):
        raise ValueError('Dataset/readiness/calendar review changed')
    for path, expected in json.loads((PACKAGE / 'protected_inputs.json').read_text()).items():
        if _sha(path) != expected:
            raise ValueError(f'Protected input changed: {path}')
    spec = importlib.util.spec_from_file_location('phase2_readonly_v4', PACKAGE / 'verify_existing_v4.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verification = verifier.verify()
    panel = load_factor_dataset(manifest)
    pp = panel.portfolio_panel
    config = PortfolioConfig()
    oldconfig = json.loads((ROOT / 'results/india_strev_PROVISIONAL_20261029T021955Z_21d1a038/configuration.json').read_text())
    if any(oldconfig[k] != v for k, v in asdict(config).items()):
        raise ValueError('Established portfolio configuration changed')
    rules_path = ROOT / 'results/india_calendar_phase4c_20261029T015149Z_53a60385/audit_v1/calendar_rules.json'
    if _sha(rules_path) != json.loads(manifest.read_text())['calendar_rules_sha256']:
        raise ValueError('Calendar rules changed')
    rules = json.loads(rules_path.read_text())
    calendar = reconstruct_calendar('2020-11-26', '2024-12-31',
        annual_rules={int(y): v for y, v in rules['annual_rules'].items()}, overrides=rules['overrides'])
    if not calendar.index[calendar.status.eq('session')].equals(pp.close.index):
        raise ValueError('Calendar/input mismatch')
    histories = {s: pd.DataFrame({'close': pp.close[s], 'volume': pp.volume[s]}) for s in NSE_STOCKS}
    histories[BENCHMARK] = pp.benchmark.to_frame('close')
    audit = audit_calendar(calendar, histories, amendment_coverage_confirmed=False)
    summary = json.loads((AUDIT / 'baseline_summary.json').read_text())[factor]
    checks = _read_causal_checks(AUDIT / 'causality_and_window_checks.csv', factor)
    approval = validate_phase2_approval(factor, approved=approved,
        dataset_hash=_sha(manifest), review_hash=_sha(REVIEW), audit_hash=_sha(AUDIT / 'artifact_hashes.json'),
        calendar_summary=audit.summary, signal_summary=summary, causal_checks=checks,
        volume_verification=verification, config=config,
        prior_sessions=int((pp.close.index < pd.Timestamp(config.start)).sum()))
    # Source versions are checked independently before each factor evaluation.
    source_evidence = json.loads((AUDIT / factor / 'original_metadata_and_numerics.json').read_text())
    for rel, expected in source_evidence['source_sha256'].items():
        if _sha(Path('/home/jampip/vibe-Trading/agent') / rel) != expected:
            raise ValueError('Audited original Vibe implementation changed')
    out = ROOT / 'results' / (f'india_{factor}_PROVISIONAL_'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    _json(out / 'diagnostic_approval.json', approval)
    _json(out / 'configuration.json', {'label': 'PROVISIONAL', 'factor': factor, **asdict(config),
        'universe': NSE_STOCKS, 'benchmark': BENCHMARK, 'prior_sessions': 25,
        'input_start': '2020-11-26', 'execution': 'strictly subsequent eligible close',
        'tie_rule': 'descending score then ascending ticker',
        'ic_horizon': 'actual execution close to next execution close across all eight stocks',
        'sharpe': 'daily net mean / sample std * sqrt(252), zero risk-free',
        'cash_interest': 0, 'terminal_liquidation': False})
    _json(out / 'preflight.json', {'calendar': audit.summary, 'volume': verification,
        'signal_readiness': summary, 'causality_checks': checks,
        'source_sha256': source_evidence['source_sha256']})
    for source, name in [(manifest, 'dataset_manifest.json'), (REVIEW, 'signal_readiness_review.md'),
                         (CALENDAR_REVIEW, 'calendar_readiness_review.md')]:
        (out / name).write_bytes(source.read_bytes())
    try:
        run = backtest_phase2_factor(panel, factor, vibe_root='/home/jampip/vibe-Trading',
                                    python_executable=ROOT / '.venv/bin/python', config=config)
        evaluation, p, ic = run.evaluation, run.portfolio, run.execution_ic
        f = evaluation.factor
        saved = pd.read_csv(AUDIT / factor / 'baseline_scores.csv', index_col=0, parse_dates=True)
        pd.testing.assert_frame_equal(saved, f.scores, check_names=False, rtol=1e-14, atol=1e-15)
        current_summary, profiles = selection_summary(f.scores)
        if any(current_summary[k] != summary[k] for k in ['finite_scores', 'nan_scores', 'weekly_unique_top_two']):
            raise ValueError('Signals differ from approved readiness evidence')
        f.scores.to_csv(out / 'factor_scores.csv', index_label='date')
        f.missing_scores.to_csv(out / 'missing_scores.csv', index=False)
        input_and_missing_audit(panel.fields, factor, f.scores).to_csv(out / 'input_and_nan_causes.csv', index=False)
        _json(out / 'signal_coverage.json', current_summary)
        _json(out / 'weekly_candidates.json', profiles)
        (out / 'factor_worker_stderr.txt').write_text(f.worker_stderr)
        ic.to_csv(out / 'execution_aligned_ic.csv', index_label='signal_date')
        p.ic_scores.to_csv(out / 'ic_scores.csv', index_label='signal_date')
        p.ic_returns.to_csv(out / 'ic_forward_returns.csv', index_label='signal_date')
        intervals = []
        for a, b in zip(p.executions.itertuples(), p.executions.iloc[1:].itertuples()):
            if not a.signal_date < a.execution_date < b.execution_date <= pd.Timestamp(config.end):
                raise ValueError('Invalid execution-aligned label boundary')
            intervals.append({'signal_date': a.signal_date, 'entry_close': a.execution_date,
                'exit_close': b.execution_date, 'session_intervals': pp.close.index.get_loc(b.execution_date) - pp.close.index.get_loc(a.execution_date)})
        pd.DataFrame(intervals).to_csv(out / 'ic_intervals.csv', index=False)
        p.weights.to_csv(out / 'holdings_weights.csv', index_label='date')
        p.executions.to_csv(out / 'executions.csv', index=False)
        _json(out / 'order_log.json', p.order_log)
        run.input_flags.to_csv(out / 'quality_flags.csv', index=False)
        for field, frame in panel.fields.items():
            frame.to_csv(out / f'input_{field}.csv', index_label='date')
        pp.benchmark.to_csv(out / 'input_benchmark.csv', index_label='date')
        daily = pd.concat([p.net_returns, p.gross_returns, p.benchmark_returns, p.turnover, p.costs], axis=1)
        daily['net_nav'] = (1 + p.net_returns).cumprod()
        daily['gross_nav'] = (1 + p.gross_returns).cumprod()
        daily['benchmark_nav'] = (1 + p.benchmark_returns).cumprod()
        if len(daily) != 990 or daily.index.max() > pd.Timestamp(config.end) or not np.isfinite(daily.to_numpy()).all():
            raise ValueError('Invalid evaluation returns')
        daily.to_csv(out / 'daily_returns_nav.csv', index_label='date')
        trades = execution_trade_ledger(pp, p, config)
        trades.to_csv(out / 'trades.csv', index=False)
        metrics = {'label': 'PROVISIONAL', 'factor': factor,
            'execution_aligned_mean_rank_ic': float(ic.mean()), 'valid_ic_intervals': len(ic),
            'undefined_ic_intervals': len(p.ic_scores) - len(ic),
            'net_daily_annualized_sharpe': p.sharpe,
            'benchmark_daily_annualized_sharpe': annualized_sharpe(p.benchmark_returns),
            'net_cumulative_return': float(daily.net_nav.iloc[-1] - 1),
            'gross_cumulative_return': float(daily.gross_nav.iloc[-1] - 1),
            'benchmark_cumulative_return': float(daily.benchmark_nav.iloc[-1] - 1),
            'net_max_drawdown': float((daily.net_nav / daily.net_nav.cummax() - 1).min()),
            'evaluation_observations': len(daily), 'input_sessions': len(pp.close),
            'prior_sessions': 25, 'rebalance_executions': len(p.executions),
            'stock_trade_legs': len(trades), 'total_absolute_nav_turnover': float(p.turnover.sum()),
            'sum_cost_fractions': float(p.costs.sum()),
            'first_execution': str(p.executions.execution_date.min().date()),
            'last_execution': str(p.executions.execution_date.max().date()),
            'executed_targets_membership_depends_on_ticker': sum(
                r['membership_depends_on_ticker'] for r in profiles if r['has_later_evaluation_session']),
            'no_final_keep_drop': True}
        _json(out / 'metrics.json', metrics)
        warnings = ['PROVISIONAL diagnostic; no final Keep/Drop or repeat authorization.',
            'Frozen Yahoo adjustment vintage is not historically point-in-time.',
            'Reliance pre-July-2023 normalization and small Kotak quantity discrepancy remain unresolved.',
            'Calendar structural checks pass; exhaustive amendment inventory certainty alone is waived.',
            'Strict dataset certification flags are unchanged; no source prices or quantities were repaired.',
            'Nifty 50 is a price index; stock adjusted prices contain dividend adjustments.',
            'Fixed eight-name basket; fractional targets and flat turnover costs omit spreads, impact and taxes.',
            'Initial cash included; zero cash interest/risk-free; no terminal liquidation or post-cutoff labels.']
        if factor == 'alpha101_101':
            warnings.append('Original high-low + 0.001 denominator constant is unchanged and price-unit dependent.')
        if factor == 'alpha101_014':
            warnings.append('Dividend adjustment convention changed 5/209 weekly pairs in the signal audit; no alternate convention adopted.')
        _json(out / 'warnings.json', warnings)
        snapshot = out / 'source_snapshot'
        for source in (ROOT / 'src').glob('india_*.py'):
            dest = snapshot / 'indicatorlab' / source.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
        for rel, expected in f.source_sha256.items():
            source = Path('/home/jampip/vibe-Trading/agent') / rel
            if _sha(source) != expected:
                raise ValueError('Vibe changed during evaluation')
            dest = snapshot / 'vibe' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
        _json(out / 'provenance.json', {'dataset_manifest_sha256': DATASET_HASH,
            'dataset_files_sha256': json.loads(manifest.read_text())['files_sha256'],
            'readiness_audit_inventory_sha256': AUDIT_HASH, 'readiness_review_sha256': REVIEW_HASH,
            'factor_source_sha256': f.source_sha256, 'factor_metadata': f.metadata,
            'indicatorlab_head': _git(ROOT, 'rev-parse', 'HEAD'), 'branch': _git(ROOT, 'branch', '--show-current'),
            'working_tree': _git(ROOT, 'status', '--short'),
            'vibe_head': _git('/home/jampip/vibe-Trading', 'rev-parse', 'HEAD'),
            'jack_reference': _git(ROOT, 'rev-parse', 'origin/jack'),
            'python': sys.version, 'executable': str(ROOT / '.venv/bin/python'),
            'packages': {k: importlib.metadata.version(k) for k in ['pandas', 'numpy', 'scipy', 'pydantic', 'pytest']}})
        _verify_inventory(AUDIT, AUDIT_HASH)
        _verify_inventory(PACKAGE, PACKAGE_HASH)
        _json(out / 'status.json', {'label': 'PROVISIONAL', 'status': 'completed',
            'signal_scores_match_readiness': True, 'labels_and_executions_within_cutoff': True,
            'strict_dataset_flags_unchanged': True})
    except Exception as exc:
        _json(out / 'status.json', {'label': 'PROVISIONAL', 'status': 'blocked', 'error': str(exc)})
        raise
    finally:
        _json(out / 'artifact_hashes.json', {str(p.relative_to(out)): _sha(p)
            for p in out.rglob('*') if p.is_file() and p.name != 'artifact_hashes.json'})
    return out


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('factor', choices=APPROVED_FACTORS)
    parser.add_argument('--approved-phase2-diagnostic', action='store_true')
    args = parser.parse_args()
    print(run_phase2_diagnostic(args.factor, approved=args.approved_phase2_diagnostic))
