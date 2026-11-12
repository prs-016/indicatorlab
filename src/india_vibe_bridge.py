"""Subprocess boundary to Vibe's unchanged STREV and rank-IC calculations."""

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from src.india_data import BACKTEST_END, IndiaPanel, validate_close, _validate_dates


# -I isolates Python's import path/environment; only the explicit Vibe agent
# directory is added in the child. No IndicatorLab `src` imports enter it.
_WORKER = r'''
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd

agent = Path(sys.argv[1])
sys.path.insert(0, str(agent))
with contextlib.redirect_stdout(sys.stderr):
    from src.factors.zoo.academic.strev import compute
    from src.factors.factor_analysis_core import compute_ic_series
    request = json.load(sys.stdin)
    close = pd.DataFrame(request['values'],
                         index=pd.to_datetime(request['dates']),
                         columns=request['columns'], dtype=float)
    scores = compute({'close': close})
    # Prediction labels only, not executable portfolio returns. The terminal
    # label stays NaN because the input has already been bounded by the cutoff.
    forward = close.pct_change(fill_method=None).shift(-1)
    ic = compute_ic_series(scores, forward)
    paths = ['src/factors/zoo/academic/strev.py', 'src/factors/base.py',
             'src/factors/factor_analysis_core.py']
    hashes = {p: hashlib.sha256((agent / p).read_bytes()).hexdigest() for p in paths}
print(json.dumps({'scores': json.loads(scores.to_json(orient='split', date_format='iso', double_precision=15)),
                  'ic': json.loads(ic.to_frame('ic').to_json(orient='split', date_format='iso', double_precision=15)),
                  'source_sha256': hashes}, allow_nan=False))
'''


@dataclass(frozen=True)
class StrevDiagnostics:
    """Vibe factor scores, next-session rank IC, and source provenance.

    IC is a prediction diagnostic, not portfolio return or portfolio Sharpe.
    """

    scores: pd.DataFrame
    next_session_ic: pd.Series
    source_sha256: dict[str, str]
    vibe_agent: str
    python_executable: str


def evaluate_strev(
    panel: IndiaPanel, *, vibe_root: str | Path,
    python_executable: str | Path = sys.executable, timeout: float = 60,
) -> StrevDiagnostics:
    """Invoke Vibe STREV and IC offline in an isolated Python interpreter.

    Parameters: panel comes from build_india_panel; vibe_root is the existing
    checkout root; python_executable must already have Vibe's import dependencies;
    timeout bounds worker runtime in seconds. No packages are installed.
    Returns: scores, next-session IC series, and provenance, with no trading
    assumptions or final strategy metrics. Raises RuntimeError on worker failure.
    """
    validate_close(panel.close)
    agent = Path(vibe_root).expanduser().resolve() / "agent"
    if not (agent / "src/factors/zoo/academic/strev.py").is_file():
        raise ValueError(f"Vibe STREV source not found under {agent}")
    request = {
        "dates": panel.close.index.strftime("%Y-%m-%d").tolist(),
        "columns": panel.close.columns.tolist(),
        "values": json.loads(panel.close.to_json(
            orient="values", date_format="iso", double_precision=15)),
    }
    try:
        completed = subprocess.run(
            [str(python_executable), "-I", "-B", "-c", _WORKER, str(agent)],
            input=json.dumps(request, allow_nan=False), capture_output=True,
            text=True, timeout=timeout, check=False, cwd=agent,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Vibe worker could not run: {exc}") from exc
    if completed.returncode:
        raise RuntimeError(
            "Vibe worker failed; use an interpreter with existing Vibe dependencies.\n"
            + completed.stderr
        )
    try:
        result = json.loads(completed.stdout)
        def decode(payload: dict) -> pd.DataFrame:
            return pd.DataFrame(payload["data"], columns=payload["columns"],
                                index=pd.to_datetime(payload["index"]), dtype=float)
        scores = decode(result["scores"])
        ic = decode(result["ic"])["ic"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Invalid Vibe worker response") from exc
    if not scores.index.equals(panel.close.index) or not scores.columns.equals(panel.close.columns):
        raise RuntimeError("Vibe returned misaligned scores")
    return StrevDiagnostics(scores, ic, result["source_sha256"], str(agent),
                            str(python_executable))


_IC_WORKER = r'''
import contextlib
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, sys.argv[1])
request = json.load(sys.stdin)
with contextlib.redirect_stdout(sys.stderr):
    from src.factors.factor_analysis_core import compute_ic_series
    def frame(key):
        return pd.DataFrame(request[key], index=pd.to_datetime(request['dates']),
                            columns=request['columns'], dtype=float)
    ic = compute_ic_series(frame('scores'), frame('returns'))
print(ic.to_frame('ic').to_json(orient='split', date_format='iso', double_precision=15))
'''


def compute_rank_ic(
    scores: pd.DataFrame, forward_returns: pd.DataFrame, *,
    vibe_root: str | Path, python_executable: str | Path = sys.executable,
    timeout: float = 60,
) -> pd.Series:
    """Return Vibe Spearman IC for explicitly aligned evaluation labels.

    Parameters: scores and forward_returns have identical session-date indices
    and stock columns; their horizon is defined by the caller. vibe_root and
    python_executable select the isolated existing Vibe installation. Returns
    its IC series (at least five valid pairs per date), never portfolio Sharpe.
    Missing pairs are preserved; infinite inputs and post-cutoff dates fail.
    """
    _validate_dates(scores.index)
    if (not scores.index.equals(forward_returns.index)
            or not scores.columns.equals(forward_returns.columns)
            or not scores.columns.is_unique):
        raise ValueError("IC scores and return labels must align exactly")
    if len(scores) and scores.index.max() > BACKTEST_END:
        raise ValueError("IC labels exceed the December 31, 2024 cutoff")
    for frame in (scores, forward_returns):
        if np.isinf(frame.to_numpy(dtype=float)).any():
            raise ValueError("IC inputs cannot contain infinity")
    agent = Path(vibe_root).expanduser().resolve() / "agent"
    if not (agent / "src/factors/factor_analysis_core.py").is_file():
        raise ValueError("Vibe IC source not found")
    request = {
        "dates": scores.index.strftime("%Y-%m-%d").tolist(),
        "columns": scores.columns.tolist(),
        "scores": json.loads(scores.to_json(orient="values", date_format="iso",
                                           double_precision=15)),
        "returns": json.loads(forward_returns.to_json(
            orient="values", date_format="iso", double_precision=15)),
    }
    try:
        child = subprocess.run(
            [str(python_executable), "-I", "-B", "-c", _IC_WORKER, str(agent)],
            input=json.dumps(request, allow_nan=False), capture_output=True,
            text=True, timeout=timeout, check=False, cwd=agent,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Vibe IC worker failed: {exc}") from exc
    if child.returncode:
        raise RuntimeError(f"Vibe IC worker failed: {child.stderr}")
    payload = json.loads(child.stdout)
    return pd.Series([row[0] for row in payload["data"]],
                     index=pd.to_datetime(payload["index"]), name="ic", dtype=float)
