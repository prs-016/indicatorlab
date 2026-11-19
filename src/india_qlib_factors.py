"""Five approved Qlib158 integrations; original Vibe code runs only in a child.

No Microsoft Qlib dependency, formula replacement, data retrieval or portfolio
execution occurs here. Metadata warm-up and effective input length are separate.
"""
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from src.india_data import NSE_STOCKS
from src.india_phase2_factors import BASE_SHA256, Phase2Spec, _checked_panel, _worker_code
from src.india_phase2_readiness import selection_summary


@dataclass(frozen=True)
class QlibSpec:
    """Original dispatch specification and effective number of input rows."""
    original: Phase2Spec
    effective_rows: int


def _spec(name, dependencies, declared, effective, digest):
    return QlibSpec(Phase2Spec('src.factors.zoo.qlib158.' + name,
                             dependencies, declared, digest), effective)


IC_SHA256 = '7d39b4220b477f3a5de9051b8c19e56dd1ae55fd11c1d276fc5ea4c099a2a940'

QLIB_SPECS = {
    'qlib158_std20': _spec('std20', ('close',), 20, 20,
        '8abed102785febbc178930c99a954f207fe1fa066147d6328b41e842f9862724'),
    'qlib158_rsv20': _spec('rsv20', ('high', 'low', 'close'), 20, 20,
        '904103606d9251c095a2af3474b83ef638411816e5f4f6d381927708c8d96c8b'),
    'qlib158_sump20': _spec('sump20', ('close',), 20, 21,
        '346cfbcd3cfef020cd577326af042e158656e65e0498babd93dee88157af5dcc'),
    'qlib158_wvma20': _spec('wvma20', ('close', 'volume'), 20, 21,
        '6a593c8d752eefe97d86cf1e66ac8cfe7e7838e0903decd1079bcc60e716ed94'),
    'qlib158_cord10': _spec('cord10', ('close', 'volume'), 10, 11,
        'e8b0efc6705f8c4c35ec58d520a9798360c1bee7a99509e88b8cba486d8d3803'),
}


def _observed_worker():
    worker = _worker_code()
    token = ' scores=module.compute(panel)'
    if worker.count(token) != 1:
        raise RuntimeError('Shared worker changed; review before dispatch')
    worker = worker.replace('import pandas as pd',
                            'import pandas as pd\nimport numpy as np,warnings')
    worker = worker.replace(token,
        " with warnings.catch_warnings(record=True) as captured:\n"
        "  warnings.simplefilter('always')\n"
        "  scores=module.compute(panel)\n"
        " numerical={'infinite':int(np.isinf(scores.to_numpy()).sum()),"
        "'nan':int(scores.isna().sum().sum()),"
        "'warnings':[{'category':w.category.__name__,'message':str(w.message)} for w in captured]}")
    return worker.replace("'metadata':module.__alpha_meta__",
                          "'numerical':numerical,'metadata':module.__alpha_meta__")


def evaluate_qlib_factor(panel, factor, *, vibe_root, python_executable=sys.executable):
    """Compute one original factor once and return scores plus exact source evidence.

    Parameters: validated India FactorPanel, approved registry ID, Vibe checkout
    and child interpreter. Returns (DataFrame, evidence dict). Missing values are
    retained; raw infinities are rejected before pandas JSON can hide them.
    """
    if factor not in QLIB_SPECS:
        raise ValueError('Require an approved Qlib158 factor')
    spec = QLIB_SPECS[factor].original
    checked = _checked_panel(panel, spec)
    agent = Path(vibe_root).resolve() / 'agent'
    relative = str(Path(*spec.module_path.split('.')).with_suffix('.py'))
    expected = {relative: spec.source_sha256, 'src/factors/base.py': BASE_SHA256,
                'src/factors/factor_analysis_core.py': IC_SHA256}
    for path, digest in expected.items():
        if hashlib.sha256((agent / path).read_bytes()).hexdigest() != digest:
            raise ValueError('Pinned original factor/helper source changed')
    tree = ast.parse((agent / relative).read_text())
    original_metadata = next(ast.literal_eval(n.value) for n in tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name)
            and t.id == '__alpha_meta__' for t in n.targets))
    request = {'module_path': spec.module_path, 'source_relative': relative,
        'dates': checked.portfolio_panel.close.index.strftime('%Y-%m-%d').tolist(),
        'columns': list(NSE_STOCKS), 'fields': {k: json.loads(checked.fields[k].to_json(
            orient='values', date_format='iso', double_precision=15)) for k in spec.dependencies}}
    child = subprocess.run([str(python_executable), '-I', '-B', '-c', _observed_worker(), str(agent)],
        input=json.dumps(request, allow_nan=False), capture_output=True, text=True,
        cwd=agent, timeout=60, check=False)
    if child.returncode:
        raise RuntimeError('Isolated Qlib158 worker failed: ' + child.stderr)
    response = json.loads(child.stdout)
    data = response.pop('scores')
    scores = pd.DataFrame(data['data'], index=pd.to_datetime(data['index']),
                          columns=data['columns'], dtype=float)
    if (not scores.index.equals(checked.portfolio_panel.close.index)
            or tuple(scores.columns) != NSE_STOCKS
            or response['metadata'] != original_metadata
            or response['metadata']['id'] != factor
            or tuple(response['metadata']['columns_required']) != spec.dependencies
            or response['metadata']['min_warmup_bars'] != spec.warmup_bars
            or 'equity_in' not in response['metadata']['universe']
            or response['numerical']['infinite'] != 0
            or response['numerical']['nan'] != int(scores.isna().sum().sum())
            or any(response['source_sha256'].get(k) != v for k, v in expected.items())):
        raise ValueError('Changed metadata, numerical failure or misaligned original output')
    response.update(worker_stderr=child.stderr, effective_input_rows=QLIB_SPECS[factor].effective_rows,
                    original_compute_invocations=1)
    return scores, response


def missing_score_causes(fields, factor, scores):
    """Explain original missing cells using input/window masks, without score fills.

    Parameters are aligned fields, ID and already computed scores. Returns a
    per-missing-cell table, including unexplained failures for readiness rejection.
    Mask calculations are diagnostics only; production scores always come from Vibe.
    """
    spec = QLIB_SPECS[factor]
    c = fields['close']
    valid = c.notna()
    for k in spec.original.dependencies:
        valid &= fields[k].notna()
    n = 10 if factor == 'qlib158_cord10' else 20
    lagged = spec.effective_rows > n
    if lagged:
        valid &= c.shift().notna()
        if factor in ('qlib158_wvma20', 'qlib158_cord10'):
            valid &= fields['volume'].shift().notna() if factor == 'qlib158_cord10' else True
    incomplete = valid.rolling(n, min_periods=1).sum().lt(n)
    zero = c.eq(-1)  # all-false mask on validated positive prices
    constant = zero.copy()
    if factor == 'qlib158_rsv20':
        zero = fields['high'].rolling(n).max().eq(fields['low'].rolling(n).min())
    elif factor == 'qlib158_sump20':
        zero = c.diff().abs().rolling(n).sum().eq(0)
    elif factor == 'qlib158_wvma20':
        zero = ((c / (c.shift() + 1e-12) - 1).abs() * fields['volume']).rolling(n).mean().eq(0)
    elif factor == 'qlib158_cord10':
        price_ratio = c / (c.shift() + 1e-12)
        volume_ratio = np.log((fields['volume'] + 1) / (fields['volume'].shift() + 1 + 1e-12))
        constant = (price_ratio.rolling(n).max().eq(price_ratio.rolling(n).min())
                    | volume_ratio.rolling(n).max().eq(volume_ratio.rolling(n).min()))
    rows = []
    for s in scores:
        for d in scores.index[scores[s].isna()]:
            i = scores.index.get_loc(d)
            cause = ('warmup' if i < spec.effective_rows - 1 else
                     'incomplete_input_window' if incomplete.loc[d, s] else
                     'zero_denominator' if zero.loc[d, s] else
                     'constant_correlation_window' if constant.loc[d, s] else 'unexplained')
            rows.append({'date': d, 'symbol': s, 'cause': cause})
    return pd.DataFrame(rows, columns=['date', 'symbol', 'cause'])


def readiness_gate(scores, evidence, causes):
    """Return conservative complete/unique-signal readiness and explicit blockers.

    Inputs are cached scores, worker evidence and missing-cell diagnostics. The
    five-factor approval uses the established expansion baseline: complete finite
    evaluation signals and uniquely identified top-two weekly targets. Returns
    (summary, profiles, blockers); no alternative scores or relaxed gate is used.
    """
    summary, profiles = selection_summary(scores)
    selected = scores.loc['2021-01-04':'2024-12-31']
    summary['daily_any_exact_tie'] = int(selected.nunique(axis=1, dropna=True).lt(8).sum())
    weekly = selected.groupby(selected.index.to_period('W-FRI')).tail(1)
    gaps = weekly.apply(lambda r: r.dropna().sort_values(ascending=False).iloc[1:3].diff().abs().iloc[-1]
                        if r.notna().sum() == 8 else np.nan, axis=1)
    summary['weekly_near_boundary_ties_1e_10'] = int(gaps.le(1e-10).sum())
    blockers = []
    expected = {'sessions': 990, 'total_scores': 7920, 'finite_scores': 7920,
                'nan_scores': 0, 'infinite_scores': 0, 'weekly_candidates': 209,
                'weekly_eight_finite': 209, 'weekly_unique_top_two': 209,
                'weekly_boundary_ties': 0, 'nonterminal_eligible': 208}
    for key, value in expected.items():
        if summary[key] != value:
            blockers.append(f'{key}: expected {value}, observed {summary[key]}')
    if evidence['numerical']['infinite'] or evidence['numerical']['warnings']:
        blockers.append('Original numerical failure/warning requires review')
    factor = evidence['metadata']['id']
    values = selected.to_numpy()
    if factor in ('qlib158_rsv20', 'qlib158_sump20'):
        if ((values < -1e-10) | (values > 1 + 1e-10)).any():
            blockers.append('Score outside original mathematical [0, 1] range')
    elif factor == 'qlib158_cord10':
        if (np.abs(values) > 1 + 1e-8).any():
            blockers.append('Numerically invalid correlation outside [-1, 1]')
    elif (values < -1e-10).any():
        blockers.append('Negative standard-deviation ratio')
    if causes.cause.eq('unexplained').any():
        blockers.append('Unexplained missing scores')
    return summary, profiles, blockers
