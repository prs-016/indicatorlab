"""Signal-only diagnostics for the five approved India expansion factors.

No portfolio accounting, forward return labels or convention selection occurs.
"""
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from src.india_alpha004_audit import weekly_profiles
from src.india_data import NSE_STOCKS, BACKTEST_END
from src.india_phase2_factors import PHASE2_SPECS, BASE_SHA256, _worker_code


def original_diagnostic_scores(fields, factor, *, basis_label, vibe_root,
                               python_executable):
    """Invoke a pinned original module on explicitly labelled diagnostic inputs.

    Parameters are aligned eight-stock fields, approved ID, diagnostic basis and
    isolated runtime. Returns original scores and raw-output numerical/warning
    evidence. Alternative inputs confer no approval to change the study basis.
    """
    if factor not in PHASE2_SPECS or not basis_label:
        raise ValueError('Require an approved ID and explicit diagnostic basis')
    spec = PHASE2_SPECS[factor]
    ref = fields['close']
    if (ref.empty or not ref.index.is_unique or not ref.index.is_monotonic_increasing
            or ref.index.max() > BACKTEST_END or tuple(ref.columns) != NSE_STOCKS):
        raise ValueError('Require sorted pre-cutoff eight-stock observations')
    for key in spec.dependencies:
        frame = fields[key]
        if not frame.index.equals(ref.index) or not frame.columns.equals(ref.columns):
            raise ValueError('Diagnostic inputs must align')
        if (np.isinf(frame.to_numpy()).any() or frame.lt(0).any().any()
                or (key != 'volume' and frame.eq(0).any().any())):
            raise ValueError('Invalid diagnostic input')
    agent = Path(vibe_root).resolve() / 'agent'
    relative = str(Path(*spec.module_path.split('.')).with_suffix('.py'))
    for path, expected in [(relative, spec.source_sha256),
                           ('src/factors/base.py', BASE_SHA256)]:
        if hashlib.sha256((agent / path).read_bytes()).hexdigest() != expected:
            raise ValueError('Original Vibe source changed')
    # Observe final values BEFORE pandas JSON turns infinities into nulls.
    # Warning capture surrounds original compute only; its arithmetic is unchanged.
    worker = _worker_code().replace(
        'import pandas as pd', 'import pandas as pd\nimport numpy as np,warnings')
    worker = worker.replace(' scores=module.compute(panel)',
        " with warnings.catch_warnings(record=True) as captured:\n"
        "  warnings.simplefilter('always')\n"
        "  scores=module.compute(panel)\n"
        " numerical={'infinite':int(np.isinf(scores.to_numpy()).sum()),"
        "'nan':int(scores.isna().sum().sum()),"
        "'warnings':[{'category':w.category.__name__,'message':str(w.message)} for w in captured]}")
    worker = worker.replace("'metadata':module.__alpha_meta__",
                            "'numerical':numerical,'metadata':module.__alpha_meta__")
    request = {'module_path': spec.module_path, 'source_relative': relative,
               'dates': ref.index.strftime('%Y-%m-%d').tolist(),
               'columns': list(NSE_STOCKS),
               'fields': {k: json.loads(fields[k].to_json(orient='values', date_format='iso',
                           double_precision=15)) for k in spec.dependencies}}
    child = subprocess.run(
        [str(python_executable), '-I', '-B', '-c', worker, str(agent)],
        input=json.dumps(request, allow_nan=False), capture_output=True, text=True,
        cwd=agent, timeout=60, check=False)
    if child.returncode:
        raise RuntimeError(child.stderr)
    result = json.loads(child.stdout)
    data = result.pop('scores')
    scores = pd.DataFrame(data['data'], index=pd.to_datetime(data['index']),
                          columns=data['columns'], dtype=float)
    if not scores.index.equals(ref.index) or not scores.columns.equals(ref.columns):
        raise RuntimeError('Misaligned original response')
    result.update(basis_label=basis_label, worker_stderr=child.stderr)
    return scores, result


def input_and_missing_audit(fields, factor, scores):
    """Attribute NaNs and expose original rolling/denominator risks per cell.

    Inputs are original matrices/scores. Returns diagnostic rows, never filled or
    substitute scores. Any unexplained NaN remains a visible validation failure.
    """
    spec = PHASE2_SPECS[factor]
    close, vol = fields['close'], fields['volume']
    zero = close * 0
    required_missing = zero.astype(bool)
    for key in spec.dependencies:
        required_missing |= fields[key].isna()
    constant = zero.astype(bool)
    incomplete = required_missing.copy()
    degenerate = zero.astype(bool)
    denominator = close.copy()
    if factor == 'alpha101_054':
        denominator = (fields['low'] - fields['high']) * close.pow(5)
    elif factor == 'alpha101_101':
        denominator = fields['high'] - fields['low'] + .001
    elif factor == 'alpha101_014':
        op = fields['open']
        constant = (op.rolling(10).max().eq(op.rolling(10).min())
                    | vol.rolling(10).max().eq(vol.rolling(10).min()))
        ret = close.pct_change(fill_method=None)
        incomplete = ((op.notna() & vol.notna()).rolling(10).sum().lt(10)
                      | ret.diff(3).isna())
        denominator = op.rolling(10).std() * vol.rolling(10).std()
    elif factor == 'academic_illiq':
        denominator = close * vol
        ret = (close - close.shift()) / (close.shift() + 1e-12)
        valid = ret.notna() & denominator.gt(0)
        incomplete = valid.rolling(21, min_periods=1).sum().lt(21)
        proxy = ret.abs().div(denominator + 1e-12).where(denominator.ne(0))
        mean = proxy.rolling(21).mean()
        std = mean.std(axis=1, ddof=1)
        degenerate.loc[:, :] = np.broadcast_to(
            std.le(0).to_numpy()[:, None], degenerate.shape)
    rows = []
    for s in scores:
        for i, date in enumerate(scores.index):
            missing = pd.isna(scores.loc[date, s])
            cause = 'finite'
            if missing:
                if i < spec.warmup_bars - 1:
                    cause = 'warmup'
                elif required_missing.loc[date, s]:
                    cause = 'required_input_missing'
                elif incomplete.loc[date, s]:
                    cause = 'incomplete_window_including_zero_turnover' if factor == 'academic_illiq' else 'incomplete_window'
                elif constant.loc[date, s]:
                    cause = 'constant_raw_correlation_window'
                elif denominator.loc[date, s] == 0:
                    cause = 'zero_denominator'
                elif degenerate.loc[date, s]:
                    cause = 'zero_cross_sectional_dispersion'
                else:
                    cause = 'unexplained'
            rows.append({'date': date, 'symbol': s, 'score': scores.loc[date, s],
                         'cause': cause, 'zero_volume': bool(vol.loc[date, s] == 0),
                         'denominator': denominator.loc[date, s],
                         'constant_correlation_window': bool(constant.loc[date, s]),
                         'incomplete_window': bool(incomplete.loc[date, s])})
    return pd.DataFrame(rows)


def selection_summary(scores):
    """Return W-FRI candidate profiles and finite/unique/tie counts, without trades.

    Scores use the fixed eight-name study. Terminal candidates are counted but
    separately marked as lacking a subsequent evaluation session.
    """
    profiles = weekly_profiles(scores)
    eligible = [p for p in profiles if p['eligible']]
    selected = scores.loc['2021-01-04':'2024-12-31']
    summary = {'sessions': len(selected), 'total_scores': selected.size,
               'finite_scores': int(np.isfinite(selected.to_numpy()).sum()),
               'nan_scores': int(selected.isna().sum().sum()),
               'infinite_scores': int(np.isinf(selected.to_numpy()).sum()),
               'nan_by_symbol': selected.isna().sum().to_dict(),
               'weekly_candidates': len(profiles), 'weekly_eight_finite': len(eligible),
               'weekly_unique_top_two': sum(p['admissible_pair_count'] == 1 for p in eligible),
               'weekly_boundary_ties': sum(p['membership_depends_on_ticker'] for p in eligible),
               'weekly_all_eight_tied': sum(p['all_eight_tied'] for p in eligible),
               'nonterminal_eligible': sum(p['has_later_evaluation_session'] for p in eligible),
               'selected_pair_counts': {s: sum(s in p['selected_pair'] for p in eligible) for s in NSE_STOCKS}}
    return summary, profiles
