"""One separately approved PROVISIONAL India ILLIQ frozen-proxy diagnostic.

No original factor, IC, portfolio logic, old runner or source data is changed.
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

from src.india_phase2_diagnostic import (
    ROOT, DATASET, DATASET_HASH, PACKAGE, PACKAGE_HASH, AUDIT, AUDIT_HASH,
    REVIEW, REVIEW_HASH, CALENDAR_REVIEW, CALENDAR_REVIEW_HASH,
    _verify_inventory, _read_causal_checks, execution_trade_ledger,
)
from src.india_backtest import PortfolioConfig, annualized_sharpe
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_diagnostic import _sha, _json, _git
from src.india_factors import load_factor_dataset
from src.india_phase2_factors import (
    backtest_phase2_factor, load_illiq_basis_evidence, turnover_panel_digest,
    PROXY_INTERPRETATION,
)
from src.india_phase2_readiness import selection_summary, input_and_missing_audit

BASIS_REVIEW = ROOT / 'results/india_phase2_integration_20261029T045327Z/turnover_basis_review.json'
BASIS_REVIEW_HASH = 'ec86d435e80810798df23c1158f2d522424a4e7b1ea5bfd0e7f16f113276b4c7'
APPROVAL_ID = 'one_illiq_frozen_proxy_provisional_20261029'


def validate_illiq_approval(factor, *, approved, dataset_hash, review_hash,
                            audit_hash, calendar_summary, signal_summary,
                            causal_checks, volume_verification, config,
                            prior_sessions, turnover_basis, expected_panel_hash,
                            sensitivity_counts):
    """Bind the single ILLIQ approval to exact evidence, proxy units and settings.

    Parameters carry verified dataset/calendar/signal evidence and bound INR
    proxy interpretation. Returns only a PROVISIONAL, nonrepeat approval record;
    missing or altered units, sensitivity disclosures or structural checks fail.
    """
    if (not approved or factor != 'academic_illiq' or dataset_hash != DATASET_HASH
            or review_hash != REVIEW_HASH or audit_hash != AUDIT_HASH
            or config != PortfolioConfig() or prior_sessions != 25):
        raise ValueError('ILLIQ approval does not cover scope/evidence/settings')
    expected = {'discrepancy_count': 0, 'unverifiable_calendar_dates': 0,
                'lookback_clock_mismatches': 0, 'warmup_complete': True,
                'expected_evaluation_sessions': 990, 'evaluation_start': '2021-01-04'}
    if any(calendar_summary.get(k) != v for k, v in expected.items()):
        raise ValueError('Material calendar validation failed')
    expected = {'finite_scores': 7920, 'nan_scores': 0, 'infinite_scores': 0,
                'weekly_candidates': 209, 'weekly_eight_finite': 209,
                'weekly_unique_top_two': 209, 'weekly_boundary_ties': 0}
    if any(signal_summary.get(k) != v for k, v in expected.items()):
        raise ValueError('ILLIQ readiness evidence changed')
    if (len(causal_checks) != 4 or not all(c['passed'] for c in causal_checks)
            or sorted(c['test'] for c in causal_checks)
            != ['minimum_window_final_row', 'prefix', 'prefix', 'prefix']):
        raise ValueError('No-look-ahead/window evidence incomplete')
    if (volume_verification.get('status') != 'passed'
            or volume_verification.get('verified_changes') != 12
            or volume_verification.get('verified_quantity_anchors') != 24
            or volume_verification.get('dataset_manifest_sha256') != DATASET_HASH
            or not volume_verification.get('all_other_csv_tokens_and_line_endings_preserved')):
        raise ValueError('Quantity/provenance verification failed')
    if (turnover_basis is None or not turnover_basis.supported
            or turnover_basis.currency != 'INR'
            or turnover_basis.interpretation != PROXY_INTERPRETATION
            or turnover_basis.panel_sha256 != expected_panel_hash):
        raise ValueError('Bound adjusted-INR turnover proxy evidence required')
    if sensitivity_counts != {'dividend_sensitive': 51, 'normalization_sensitive': 31}:
        raise ValueError('Predeclared sensitivity evidence changed')
    return {'label': 'PROVISIONAL', 'factor': factor, 'approval_id': APPROVAL_ID,
        'authorization': 'User separately approved one ILLIQ frozen-proxy diagnostic, explicitly accepting documented limitations.',
        'dataset_manifest_sha256': dataset_hash, 'readiness_review_sha256': review_hash,
        'signal_audit_inventory_sha256': audit_hash, 'calendar_review_sha256': CALENDAR_REVIEW_HASH,
        'waived_requirement': 'Exhaustive historical calendar inventory only; all material checks retained',
        'turnover_interpretation': PROXY_INTERPRETATION, 'proxy_is_actual_turnover': False,
        'india_metadata_exception_authority': 'developer-approved research exception, not upstream endorsement',
        'sensitivity_counts': sensitivity_counts, 'configuration': asdict(config),
        'calendar_certified': False, 'repeat_authorized': False,
        'other_factors_authorized': False, 'final_keep_drop_authorized': False}


def _verify_proxy_records(panel, evidence_path):
    records = pd.read_csv(evidence_path)
    errors = []
    for row in records.itertuples():
        if _sha(row.source_file) != row.source_sha256:
            raise ValueError('Official turnover-proxy source changed')
        date = pd.Timestamp(row.date)
        actual = panel.fields['close'].loc[date, row.symbol] * panel.fields['volume'].loc[date, row.symbol]
        expected = row.expected_proxy_inr
        if (not np.isfinite([actual, expected]).all() or expected <= 0
                or not np.isclose(actual, expected, rtol=8*np.finfo(np.float32).eps, atol=0)):
            raise ValueError('Current price-volume proxy differs from verified official evidence')
        errors.append(abs(actual / expected - 1))
    return {'checked_records': len(records), 'sample_dates': records.date.nunique(),
            'source_archives': records.source_file.nunique(), 'failed_records': 0,
            'maximum_absolute_relative_error': max(errors),
            'proxy_is_actual_exchange_turnover': False}


def run_illiq_diagnostic(*, approved):
    """Run the single explicitly approved frozen-proxy ILLIQ diagnostic.

    Parameter approved acknowledges current user permission. Returns a unique
    hashed PROVISIONAL directory after pinned evidence/units/calendar checks.
    Original calculations and prior outputs are unchanged; repeats are rejected.
    """
    factor = 'academic_illiq'
    if not approved:
        raise ValueError('Explicit approval required for this ILLIQ diagnostic')
    if any((ROOT / 'results').glob('india_academic_illiq_PROVISIONAL_*/diagnostic_approval.json')):
        raise ValueError('ILLIQ approval already used; no repeat authorized')
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
    basis = load_illiq_basis_evidence(panel, BASIS_REVIEW)
    proxy_check = _verify_proxy_records(panel, AUDIT / 'official_turnover_proxy_reverification.csv')
    if proxy_check['checked_records'] != 256 or proxy_check['sample_dates'] != 32:
        raise ValueError('Official proxy verification scope changed')
    if _sha(BASIS_REVIEW) != BASIS_REVIEW_HASH:
        raise ValueError('Approved turnover proxy evidence changed')
    sensitivities = json.loads((AUDIT / 'sensitivity_summary.json').read_text())[factor]
    sensitivity_counts = {
        'dividend_sensitive': sensitivities['yahoo_close_basis_not_nominal']['weekly_top_two_changed'],
        'normalization_sensitive': sensitivities['terminal_cash_normalization_removed']['weekly_top_two_changed']}
    approval = validate_illiq_approval(factor, approved=approved,
        turnover_basis=basis, expected_panel_hash=turnover_panel_digest(panel),
        sensitivity_counts=sensitivity_counts,
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
    _json(out / 'turnover_basis_evidence.json', asdict(basis))
    _json(out / 'sensitivity_disclosures.json', sensitivity_counts)
    _json(out / 'preflight.json', {'calendar': audit.summary, 'volume': verification,
        'current_proxy_verification': proxy_check,
        'signal_readiness': summary, 'causality_checks': checks,
        'source_sha256': source_evidence['source_sha256']})
    for source, name in [(manifest, 'dataset_manifest.json'), (REVIEW, 'signal_readiness_review.md'),
                         (CALENDAR_REVIEW, 'calendar_readiness_review.md'),
                         (BASIS_REVIEW, 'turnover_basis_review.json'),
                         (AUDIT / 'official_turnover_proxy_reverification.csv', 'official_proxy_checks.csv')]:
        (out / name).write_bytes(source.read_bytes())
    try:
        run = backtest_phase2_factor(panel, factor, vibe_root='/home/jampip/vibe-Trading',
                                    python_executable=ROOT / '.venv/bin/python', config=config,
                                    turnover_basis=basis)
        evaluation, p, ic = run.evaluation, run.portfolio, run.execution_ic
        f = evaluation.factor
        _json(out / 'india_metadata_exception.json', evaluation.research_exception)
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
        warnings.extend([
            'Adjusted-INR close times vendor volume is a closing-price turnover proxy, not actual exchange turnover or USD traded value.',
            'India use is a developer-approved research exception; upstream metadata lacks equity_in and is unchanged; no upstream endorsement or PM approval is claimed.',
            'Dividend adjustment choice changes 51/209 weekly candidates; fixed terminal normalization removal changes 31/209. No alternative convention is selected from realized returns.',
            'Sampled 256-record proxy verification does not certify every historical daily quantity or resolve Reliance adjusted-return normalization.',
            'Original 21-ratio rolling window propagates zero-volume NaNs; zero volumes do not occur in this study input.',
            'Higher original z-score means less liquid; top-two illiquidity exposure may be concentrated. No score sign or formula change.'])
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
            'turnover_basis': asdict(basis), 'india_metadata_exception': evaluation.research_exception,
            'sensitivity_counts': sensitivity_counts,
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
    parser.add_argument('--approved-illiq-diagnostic', action='store_true')
    print(run_illiq_diagnostic(approved=parser.parse_args().approved_illiq_diagnostic))
