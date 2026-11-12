"""Original Phase 2 factors using the unchanged isolated India infrastructure.

Developer approval covers integration and synthetic tests only. The academic
ILLIQ India exception does not amend upstream metadata or endorse actual turnover.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from src.india_backtest import PortfolioConfig, PortfolioResult, simulate_portfolio
from src.india_data import BACKTEST_END, BENCHMARK, NSE_STOCKS
from src.india_factors import (
    FactorPanel, FactorScores, _WORKER, build_factor_panel, load_factor_dataset,
)
from src.india_factor_readiness import signal_coverage
from src.india_vibe_bridge import compute_rank_ic


@dataclass(frozen=True)
class Phase2Spec:
    """Original module, fields, metadata warm-up and inspected source version."""
    module_path: str
    dependencies: tuple[str, ...]
    warmup_bars: int
    source_sha256: str


PHASE2_SPECS = {
    'alpha101_033': Phase2Spec('src.factors.zoo.alpha101.alpha_033', ('open', 'close'), 1,
        '59a1bf3e7bc6b0abc7dc26f9617e383e373a3a6aa44c0857a44bbcf08a394405'),
    'alpha101_101': Phase2Spec('src.factors.zoo.alpha101.alpha_101', ('open', 'high', 'low', 'close'), 1,
        '7df515c46a4630a46544c4bfd220d1d808f919ebc528d671d7a9b24365da5ecb'),
    'alpha101_054': Phase2Spec('src.factors.zoo.alpha101.alpha_054', ('open', 'high', 'low', 'close'), 1,
        'eb2c86a61dfe0fb8734a62f74fdbc5d15567f8044550e83e499eb567c1b6e26d'),
    'alpha101_014': Phase2Spec('src.factors.zoo.alpha101.alpha_014', ('open', 'close', 'volume'), 10,
        '91f79c6691fb00a6e89f9c1693a27085456ad5dcfaf3ae2d90797059382c9280'),
    'academic_illiq': Phase2Spec('src.factors.zoo.academic.illiq', ('close', 'volume'), 22,
        'a2bab2dce9549f1db7274d8699d41b8fa306c392f3c96fd1e46ac0bba0b6edc6'),
}
BASE_SHA256 = '5b4bd3ae72d8fcd19f0734c7949a40804fdc16b7a8f939c80255d824f0f27291'
PROXY_INTERPRETATION = 'dividend_adjusted_INR_close_times_vendor_volume'


def turnover_panel_digest(panel: FactorPanel) -> str:
    """Return a content binding for the proxy's close/volume dates, stocks and basis.

    Input is the common FactorPanel. The digest includes only denominator-relevant
    fields and explicit adjustment declaration; this function never scores data.
    """
    digest = hashlib.sha256(panel.portfolio_panel.close_basis.encode())
    for name in ('close', 'volume'):
        digest.update(name.encode())
        digest.update(panel.fields[name].to_csv(index_label='date', float_format='%.17g').encode())
    return digest.hexdigest()


@dataclass(frozen=True)
class TurnoverBasisEvidence:
    """Scoped evidence for INR adjusted-close/vendor-volume proxy, not actual turnover.

    Attributes bind data content and source reference, currency/interpretation,
    positive evidence outcome and synthetic/research scope. No implicit basis is
    supplied for academic_illiq; callers must retain and disclose this evidence.
    """
    currency: str
    interpretation: str
    panel_sha256: str
    evidence_reference: str
    evidence_sha256: str
    supported: bool
    data_scope: str


def load_illiq_basis_evidence(panel: FactorPanel, evidence_path: str | Path) -> TurnoverBasisEvidence:
    """Validate an input-only evidence report and bind its actual verified dataset.

    Parameters: intended FactorPanel and saved turnover-basis review JSON.
    Returns scoped research evidence only if sampled checks passed, currency and
    dataset hashes agree and the matrices match. No factors or returns are run.
    """
    path = Path(evidence_path)
    record = json.loads(path.read_text())
    if (not record.get('supported_within_frozen_vendor_proxy_scope')
            or record.get('failed_records') != 0 or record.get('currency') != 'INR'
            or record.get('checked_records', 0) <= 0):
        raise ValueError('ILLIQ turnover basis not reliably supported; stop and review')
    manifest = Path(record['dataset_manifest'])
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != record['dataset_manifest_sha256']:
        raise ValueError('Turnover evidence dataset changed')
    verified_panel = load_factor_dataset(manifest)
    if turnover_panel_digest(verified_panel) != turnover_panel_digest(panel):
        raise ValueError('Turnover evidence does not bind these price/volume observations')
    return TurnoverBasisEvidence('INR', PROXY_INTERPRETATION, turnover_panel_digest(panel),
        str(path.resolve()), hashlib.sha256(path.read_bytes()).hexdigest(), True,
        'frozen_research_vintage_sample_verified_not_point_in_time')


def _checked_panel(panel: FactorPanel, spec: Phase2Spec) -> FactorPanel:
    missing = set(spec.dependencies) - set(panel.fields)
    if missing:
        raise ValueError(f'Missing factor dependencies: {sorted(missing)}')
    if not {'open', 'high', 'low', 'close', 'volume'} <= set(panel.fields):
        raise ValueError('Common India adapter requires the complete OHLCV schema')
    reference = panel.portfolio_panel.close
    for matrix in panel.fields.values():
        if not matrix.index.equals(reference.index) or tuple(matrix.columns) != NSE_STOCKS:
            raise ValueError('Factor inputs must align with the eight-stock panel')
        if len(matrix) and matrix.index.max() > BACKTEST_END:
            raise ValueError('Factor observations exceed 2024-12-31 cutoff')
    histories = {s: pd.DataFrame({k: v[s] for k, v in panel.fields.items()}) for s in NSE_STOCKS}
    histories[BENCHMARK] = panel.portfolio_panel.benchmark.to_frame('close')
    checked = build_factor_panel(histories, close_basis=panel.portfolio_panel.close_basis)
    if (not checked.portfolio_panel.close.equals(reference)
            or not checked.portfolio_panel.volume.equals(panel.portfolio_panel.volume)):
        raise ValueError('Mutable factor and portfolio inputs disagree')
    return checked


def _worker_code() -> str:
    """Reuse the tested protocol, extending only allowlisted module dispatch paths."""
    old_import = "importlib.import_module('src.factors.zoo.alpha101.'+request['module'])"
    old_path = "'src/factors/zoo/alpha101/'+request['module']+'.py'"
    if _WORKER.count(old_import) != 1 or _WORKER.count(old_path) != 1:
        raise RuntimeError('Shared worker protocol changed; inspect before extending dispatch')
    return _WORKER.replace(old_import, "importlib.import_module(request['module_path'])").replace(
        old_path, "request['source_relative']")


def _dependency_flags(panel: FactorPanel, factor: str, spec: Phase2Spec) -> pd.DataFrame:
    rows = []
    for field in spec.dependencies:
        frame = panel.fields[field]
        rows.extend({'date': d, 'symbol': s, 'flag': f'missing_input_{field}'}
            for s in NSE_STOCKS for d in frame.index[frame[s].isna()])
    masks = {}
    if factor == 'alpha101_054':
        masks['flat_range_original_zero_denominator'] = panel.fields['high'].eq(panel.fields['low'])
    elif factor == 'alpha101_101':
        masks['flat_range_zero_body_original_zero_score'] = panel.fields['high'].eq(panel.fields['low'])
    elif factor == 'alpha101_033':
        masks['zero_intraday_body_possible_rank_tie'] = panel.fields['open'].eq(panel.fields['close'])
    elif factor == 'alpha101_014':
        op, vol = panel.fields['open'], panel.fields['volume']
        masks['constant_raw_correlation_window'] = (
            op.rolling(10).max().eq(op.rolling(10).min())
            | vol.rolling(10).max().eq(vol.rolling(10).min()))
    else:
        masks['zero_volume_undefined_turnover_proxy'] = panel.fields['volume'].eq(0)
    for flag, mask in masks.items():
        rows.extend({'date': d, 'symbol': s, 'flag': flag}
            for s in NSE_STOCKS for d in mask.index[mask[s]])
    return pd.DataFrame(rows, columns=['date', 'symbol', 'flag'])


@dataclass(frozen=True)
class Phase2Evaluation:
    """Original output plus dependency flags, ties/coverage and basis/exception evidence."""
    factor: FactorScores
    dependency_flags: pd.DataFrame
    input_coverage: dict
    evaluation_coverage: dict
    turnover_basis: TurnoverBasisEvidence | None
    research_exception: dict | None


def evaluate_phase2_factor(panel: FactorPanel, factor: str, *, vibe_root: str | Path,
                           python_executable: str | Path = sys.executable,
                           turnover_basis: TurnoverBasisEvidence | None = None,
                           timeout: float = 60) -> Phase2Evaluation:
    """Evaluate one original approved factor in isolation; no portfolios or fills.

    Inputs use the existing FactorPanel and Vibe runtime. ILLIQ additionally
    requires bound INR-proxy evidence. Returns untouched original scores, metadata,
    hashes, warnings, per-cell NaNs, dependency flags and separate warm-up/eval tie
    diagnostics. Upstream country metadata is retained exactly as supplied.
    """
    if factor not in PHASE2_SPECS:
        raise ValueError('Only the five approved Phase 2 factors are supported')
    spec = PHASE2_SPECS[factor]
    checked = _checked_panel(panel, spec)
    if factor == 'academic_illiq':
        if (turnover_basis is None or not turnover_basis.supported
                or turnover_basis.currency != 'INR'
                or turnover_basis.interpretation != PROXY_INTERPRETATION
                or turnover_basis.panel_sha256 != turnover_panel_digest(checked)
                or not turnover_basis.evidence_reference or len(turnover_basis.evidence_sha256) != 64
                or not turnover_basis.data_scope):
            raise ValueError('ILLIQ requires reliable bound INR turnover-proxy evidence; stop and review')
    agent = Path(vibe_root).resolve() / 'agent'
    relative = str(Path(*spec.module_path.split('.')).with_suffix('.py'))
    source = agent / relative
    if not source.is_file():
        raise ValueError('Original Vibe factor source not found')
    if (hashlib.sha256(source.read_bytes()).hexdigest() != spec.source_sha256
            or hashlib.sha256((agent / 'src/factors/base.py').read_bytes()).hexdigest() != BASE_SHA256):
        raise ValueError('Original factor/helper version changed; inspect before use')
    request = {'module_path': spec.module_path, 'source_relative': relative,
        'dates': checked.portfolio_panel.close.index.strftime('%Y-%m-%d').tolist(),
        'columns': list(NSE_STOCKS), 'fields': {k: json.loads(checked.fields[k].to_json(
            orient='values', date_format='iso', double_precision=15)) for k in spec.dependencies}}
    try:
        child = subprocess.run([str(python_executable), '-I', '-B', '-c', _worker_code(), str(agent)],
            input=json.dumps(request, allow_nan=False), capture_output=True, text=True,
            timeout=timeout, check=False, cwd=agent)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'Phase 2 Vibe worker failed: {exc}') from exc
    if child.returncode:
        raise RuntimeError(f'Phase 2 Vibe worker failed: {child.stderr}')
    try:
        response = json.loads(child.stdout)
        data = response['scores']
        scores = pd.DataFrame(data['data'], index=pd.to_datetime(data['index']),
                              columns=data['columns'], dtype=float)
        meta = response['metadata']
        if (not scores.index.equals(checked.portfolio_panel.close.index)
                or tuple(scores.columns) != NSE_STOCKS or np.isinf(scores.to_numpy()).any()
                or meta['id'] != factor or tuple(meta['columns_required']) != spec.dependencies
                or meta['min_warmup_bars'] != spec.warmup_bars
                or response['source_sha256'][relative] != spec.source_sha256):
            raise ValueError('Misaligned or changed original factor response')
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f'Invalid Phase 2 Vibe response: {exc}') from exc
    missing = pd.DataFrame([{'date': d, 'symbol': s, 'factor': factor,
        'flag': 'original_factor_score_missing'} for s in NSE_STOCKS
        for d in scores.index[scores[s].isna()]], columns=['date', 'symbol', 'factor', 'flag'])
    result = FactorScores(factor, scores, meta, response['source_sha256'], missing, child.stderr)
    all_coverage = signal_coverage(scores, start=str(scores.index[0].date()),
                                  end=str(scores.index[-1].date()))[0]
    evaluation = scores.loc['2021-01-04':'2024-12-31']
    evaluation_coverage = signal_coverage(scores)[0] if len(evaluation) else {}
    exception = None
    if factor == 'academic_illiq':
        exception = {'authority': 'developer-approved India research exception in current instruction',
            'upstream_equity_in_tag_present': 'equity_in' in meta.get('universe', []),
            'upstream_endorsement_claimed': False, 'upstream_metadata_modified': False,
            'turnover_interpretation': PROXY_INTERPRETATION}
    return Phase2Evaluation(result, _dependency_flags(checked, factor, spec), all_coverage,
        evaluation_coverage, turnover_basis if factor == 'academic_illiq' else None, exception)


@dataclass(frozen=True)
class Phase2PortfolioRun:
    """Synthetic-tested composition of original scores, existing accounting and IC."""
    evaluation: Phase2Evaluation
    portfolio: PortfolioResult
    execution_ic: pd.Series
    input_flags: pd.DataFrame


def backtest_phase2_factor(panel: FactorPanel, factor: str, *, vibe_root: str | Path,
                           python_executable: str | Path = sys.executable,
                           config: PortfolioConfig = PortfolioConfig(),
                           turnover_basis: TurnoverBasisEvidence | None = None) -> Phase2PortfolioRun:
    """Compose original factor/IC with the unchanged fixed portfolio baseline.

    Inputs are the reviewed FactorPanel, ID, Vibe runtime and optional ILLIQ
    evidence. Returns accounting/IC only with exact approved settings and 25 prior
    sessions. Current authorization permits synthetic tests only; this function
    provides no real-data run permission or calendar override.
    """
    if config != PortfolioConfig():
        raise ValueError('All Phase 2 factors require identical approved portfolio settings')
    if int((panel.portfolio_panel.close.index < pd.Timestamp(config.start)).sum()) != 25:
        raise ValueError('Require the common 25 prior-session input window')
    evaluation = evaluate_phase2_factor(panel, factor, vibe_root=vibe_root,
        python_executable=python_executable, turnover_basis=turnover_basis)
    portfolio = simulate_portfolio(panel.portfolio_panel, evaluation.factor.scores, config=config)
    ic = compute_rank_ic(portfolio.ic_scores, portfolio.ic_returns,
        vibe_root=vibe_root, python_executable=python_executable)
    return Phase2PortfolioRun(evaluation, portfolio, ic, panel.input_flags.copy())
