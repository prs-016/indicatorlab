"""OFFLINE SYNTHETIC fixtures only: no prices or results represent markets."""

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from src.india_data import (
    BACKTEST_END, BENCHMARK, NSE_STOCKS, build_india_panel,
)
from src.india_vibe_bridge import evaluate_strev


@pytest.fixture
def synthetic_histories():
    """Invented linear price paths, explicitly unsuitable as research data."""
    dates = pd.bdate_range("2024-10-01", "2025-10-06")
    step = np.arange(len(dates), dtype=float)
    histories = {
        symbol: pd.DataFrame({"close": 100 + (i + 1) * step,
                              "volume": 1000.0}, index=dates)
        for i, symbol in enumerate(NSE_STOCKS)
    }
    histories[BENCHMARK] = pd.DataFrame({"close": 200 + step}, index=dates)
    return histories


def adapt(histories):
    return build_india_panel(histories, close_basis="adjusted")


def run_vibe(panel):
    if "VIBE_PYTHON" not in os.environ:
        pytest.skip("Set VIBE_PYTHON to an existing Vibe-capable interpreter for integration tests")
    root = Path(os.environ.get("VIBE_TRADING_ROOT", "/home/jampip/vibe-Trading"))
    if not root.is_dir():
        pytest.skip("External Vibe checkout unavailable; integration not verified")
    return evaluate_strev(
        panel, vibe_root=root,
        python_executable=os.environ.get("VIBE_PYTHON", sys.executable),
    )


def test_alignment_and_benchmark_separation(synthetic_histories):
    source = synthetic_histories
    removed = source[NSE_STOCKS[0]].index[5]
    source[NSE_STOCKS[0]] = source[NSE_STOCKS[0]].drop(removed)
    source[BENCHMARK] = source[BENCHMARK].drop(source[BENCHMARK].index[6])
    panel = adapt(source)
    assert tuple(panel.close.columns) == NSE_STOCKS
    assert BENCHMARK not in panel.close
    assert panel.volume.index.equals(panel.close.index)
    assert panel.volume.columns.equals(panel.close.columns)
    assert panel.benchmark.index.equals(panel.close.index)
    assert np.isnan(panel.close.loc[removed, NSE_STOCKS[0]])
    assert np.isnan(panel.volume.loc[removed, NSE_STOCKS[0]])
    assert np.isnan(panel.benchmark.iloc[6])
    assert panel.close.index.max() == BACKTEST_END
    assert panel.close_basis == "adjusted"
    panel.close.iloc[0, 0] = 999
    assert source[NSE_STOCKS[0]].iloc[0]["close"] == 100


@pytest.mark.parametrize("mutation", ["missing", "extra", "benchmark_missing"])
def test_exact_universe(synthetic_histories, mutation):
    if mutation == "missing":
        del synthetic_histories[NSE_STOCKS[0]]
    elif mutation == "extra":
        synthetic_histories["OTHER.NS"] = synthetic_histories[NSE_STOCKS[0]]
    else:
        del synthetic_histories[BENCHMARK]
    with pytest.raises(ValueError, match="exactly eight"):
        adapt(synthetic_histories)


@pytest.mark.parametrize("mutation", ["duplicate", "unsorted", "timezone", "intraday"])
def test_invalid_session_dates(synthetic_histories, mutation):
    frame = synthetic_histories[NSE_STOCKS[0]]
    if mutation == "duplicate":
        frame = pd.concat([frame.iloc[:1], frame])
    elif mutation == "unsorted":
        frame = frame.iloc[::-1]
    elif mutation == "timezone":
        frame = frame.tz_localize("Asia/Kolkata")
    else:
        frame.index = frame.index + pd.Timedelta(hours=1)
    synthetic_histories[NSE_STOCKS[0]] = frame
    with pytest.raises(ValueError, match="Session dates"):
        adapt(synthetic_histories)


@pytest.mark.parametrize("field,value", [("close", 0), ("close", -1),
                                          ("close", np.inf), ("volume", -1)])
def test_invalid_observations(synthetic_histories, field, value):
    synthetic_histories[NSE_STOCKS[0]].iloc[0,
        synthetic_histories[NSE_STOCKS[0]].columns.get_loc(field)] = value
    with pytest.raises(ValueError):
        adapt(synthetic_histories)


def test_required_fields_and_basis(synthetic_histories):
    with pytest.raises(ValueError, match="close_basis"):
        build_india_panel(synthetic_histories, close_basis="unknown")
    synthetic_histories[NSE_STOCKS[0]] = synthetic_histories[NSE_STOCKS[0]].drop(columns="volume")
    with pytest.raises(ValueError, match="required columns"):
        adapt(synthetic_histories)


def test_vibe_strev_and_ic(synthetic_histories):
    panel = adapt(synthetic_histories)
    result = run_vibe(panel)
    # Independent formula oracle, not a replacement implementation.
    negative_return = -(panel.close.iloc[21] / panel.close.iloc[0] - 1)
    expected = (negative_return - negative_return.mean()) / negative_return.std(ddof=1)
    np.testing.assert_allclose(result.scores.iloc[21], expected, atol=1e-9)
    assert result.scores.iloc[:21].isna().all().all()
    # Synthetic stocks have persistently ordered growth rates: losers rank
    # opposite next-session returns, giving IC=-1 for every valid date.
    np.testing.assert_allclose(result.next_session_ic, -1, atol=1e-9)
    assert len(result.next_session_ic) == len(panel.close) - 22
    assert panel.close.index[-1] not in result.next_session_ic.index
    assert len(result.source_sha256) == 3
    assert all(len(h) == 64 for h in result.source_sha256.values())
    assert not hasattr(result, "sharpe")
    assert "src.factors" not in sys.modules


def test_no_lookahead_or_holdout_leakage(synthetic_histories):
    original = run_vibe(adapt(synthetic_histories))
    boundary = pd.Timestamp("2024-11-15")
    for i, symbol in enumerate(NSE_STOCKS):
        frame = synthetic_histories[symbol]
        frame.loc[frame.index > boundary, "close"] *= i + 2
    changed = run_vibe(adapt(synthetic_histories))
    pd.testing.assert_frame_equal(original.scores.loc[:boundary], changed.scores.loc[:boundary])
    # Labels at the boundary legitimately depend on the next date. Earlier
    # labels and scores must remain unaffected by the future mutation.
    pd.testing.assert_series_equal(original.next_session_ic.loc[lambda s: s.index < boundary],
                                   changed.next_session_ic.loc[lambda s: s.index < boundary])
    before = adapt(synthetic_histories)
    for frame in synthetic_histories.values():
        frame.loc[frame.index > BACKTEST_END, "close"] = 1e12
    after = adapt(synthetic_histories)
    pd.testing.assert_frame_equal(before.close, after.close)
    pd.testing.assert_series_equal(before.benchmark, after.benchmark)


def test_constant_and_missing_scores(synthetic_histories):
    for symbol in NSE_STOCKS:
        synthetic_histories[symbol]["close"] = 100.0
    constant = run_vibe(adapt(synthetic_histories))
    assert constant.scores.isna().all().all()
    assert constant.next_session_ic.empty
    # Restore varying paths; only four valid factor/return pairs remain.
    for i, symbol in enumerate(NSE_STOCKS):
        synthetic_histories[symbol]["close"] = 100 + (i + 1) * np.arange(len(synthetic_histories[symbol]))
    for symbol in NSE_STOCKS[:4]:
        synthetic_histories[symbol]["close"] = np.nan
    missing = run_vibe(adapt(synthetic_histories))
    assert missing.scores.loc[:, list(NSE_STOCKS[:4])].isna().all().all()
    assert missing.next_session_ic.empty


def test_missing_repository(synthetic_histories, tmp_path):
    with pytest.raises(ValueError, match="not found"):
        evaluate_strev(adapt(synthetic_histories), vibe_root=tmp_path)


def test_worker_failure(synthetic_histories, monkeypatch, tmp_path):
    from types import SimpleNamespace
    import src.india_vibe_bridge as bridge

    source = tmp_path / "agent/src/factors/zoo/academic/strev.py"
    source.parent.mkdir(parents=True)
    source.touch()
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stderr="missing dependency", stdout=""))
    with pytest.raises(RuntimeError, match="missing dependency"):
        evaluate_strev(adapt(synthetic_histories), vibe_root=tmp_path)


def test_bridge_rejects_post_cutoff_mutation(synthetic_histories, tmp_path):
    panel = adapt(synthetic_histories)
    panel.close.loc[pd.Timestamp("2025-10-01")] = 123.0
    with pytest.raises(ValueError, match="2024-12-31"):
        evaluate_strev(panel, vibe_root=tmp_path)
