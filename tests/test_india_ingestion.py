"""OFFLINE SYNTHETIC ingestion tests; no market-data downloads or real prices."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_ingestion import (
    SYMBOLS, SETTINGS, download_yahoo_history, ingest_history, load_snapshot,
    transform_history,
)


@pytest.fixture
def synthetic_csvs():
    """Invented split/dividend-like scaling; not actual corporate actions."""
    frame = pd.DataFrame({
        "Open": [98., 108., 118.], "High": [102., 112., 122.],
        "Low": [96., 106., 116.], "Close": [100., 110., 120.],
        "Adj Close": [50., 55., 120.], "Volume": [100., 200., 300.],
        "Dividends": [0., 1., 0.], "Stock Splits": [0., 0., 2.],
    }, index=pd.to_datetime(["2024-12-27", "2024-12-30", "2024-12-31"]))
    frame.index.name = "Date"
    return {s: frame.to_csv() for s in SYMBOLS}


def save(tmp_path, csvs):
    return ingest_history(tmp_path / "snapshot", start="2024-12-27",
                          vibe_root=tmp_path,
                          fetcher=lambda start: (csvs, {"provider": "SYNTHETIC TEST FIXTURE"}))


def test_snapshot_preserves_raw_and_adjustment_basis(tmp_path, synthetic_csvs):
    manifest_path = save(tmp_path, synthetic_csvs)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "downloaded_with_quality_report"
    assert manifest["validated_for_backtest"] is False
    assert manifest["settings"]["repair"] is False
    assert manifest["end_inclusive"] == "2024-12-31"
    assert manifest["yfinance_end_exclusive"] == "2025-01-01"
    assert len(manifest["files_sha256"]) == 18
    for symbol in SYMBOLS:
        assert (manifest_path.parent / f"raw/{symbol}.csv").read_text() == synthetic_csvs[symbol]
        derived = pd.read_csv(manifest_path.parent / f"derived/{symbol}.csv")
        np.testing.assert_allclose(derived["close"], [50, 55, 120])
        np.testing.assert_allclose(derived["open"], [49, 54, 118])
        np.testing.assert_allclose(derived["high"], [51, 56, 122])
        np.testing.assert_allclose(derived["low"], [48, 53, 116])
        np.testing.assert_allclose(derived["volume"], [100, 200, 300])
        np.testing.assert_allclose(derived["dividends"], [0, 1, 0])
    panel = load_snapshot(manifest_path)
    assert tuple(panel.close.columns) == NSE_STOCKS
    assert BENCHMARK not in panel.close
    np.testing.assert_allclose(panel.benchmark, [50, 55, 120])
    assert panel.close_basis == "adjusted"


def test_never_overwrites_snapshot(tmp_path, synthetic_csvs):
    save(tmp_path, synthetic_csvs)
    with pytest.raises(FileExistsError):
        save(tmp_path, synthetic_csvs)


def test_gaps_and_suspicious_values_retained(tmp_path, synthetic_csvs):
    from io import StringIO

    symbol = NSE_STOCKS[0]
    frame = pd.read_csv(StringIO(synthetic_csvs[symbol]), index_col=0)
    frame.iloc[1, frame.columns.get_loc("Volume")] = np.nan
    frame.iloc[2, frame.columns.get_loc("Volume")] = 0
    frame.iloc[1, frame.columns.get_loc("Open")] = np.nan
    synthetic_csvs[symbol] = frame.to_csv()
    second = pd.read_csv(StringIO(synthetic_csvs[NSE_STOCKS[1]]), index_col=0)
    synthetic_csvs[NSE_STOCKS[1]] = second.iloc[[0, 2]].to_csv()
    path = save(tmp_path, synthetic_csvs)
    report = json.loads(path.read_text())["coverage"]
    assert report[symbol]["rows"] == 3
    assert report[symbol]["flags"]["missing_or_nonnumeric_Volume"] == ["2024-12-30"]
    assert report[symbol]["flags"]["zero_volume"] == ["2024-12-31"]
    assert report[symbol]["flags"]["move_over_20pct_adjusted_close"] == ["2024-12-31"]
    assert report[NSE_STOCKS[1]]["missing_sessions_vs_union"] == ["2024-12-30"]
    panel = load_snapshot(path)
    assert np.isnan(panel.volume.iloc[1, 0])
    assert np.isnan(panel.close.iloc[1, 1])


@pytest.mark.parametrize("date", ["2025-01-01", "2025-10-01", "2024-12-26"])
def test_rejects_provider_out_of_range(tmp_path, synthetic_csvs, date):
    synthetic_csvs[NSE_STOCKS[0]] = synthetic_csvs[NSE_STOCKS[0]].replace("2024-12-31", date)
    with pytest.raises(ValueError, match="dates outside|session dates"):
        save(tmp_path, synthetic_csvs)
    manifest = json.loads((tmp_path / "snapshot/manifest.json").read_text())
    assert manifest["status"] == "incomplete"
    assert "error" in manifest


def test_cutoff_inclusive_and_download_settings(monkeypatch, tmp_path, synthetic_csvs):
    source = tmp_path / "agent/backtest/loaders/yfinance_loader.py"
    source.parent.mkdir(parents=True)
    source.touch()

    def fake_run(command, **kwargs):
        assert command[1:3] == ["-I", "-B"]
        request = json.loads(kwargs["input"])
        assert request["symbols"] == list(SYMBOLS)
        assert request["start"] == "2024-12-27"
        assert request["end_inclusive"] == "2024-12-31"
        assert request["settings"] == SETTINGS
        assert request["settings"]["auto_adjust"] is False
        assert request["settings"]["keepna"] is True
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "csv": synthetic_csvs, "provenance": {"provider": "SYNTHETIC TEST FIXTURE"}}))

    monkeypatch.setattr("src.india_ingestion.subprocess.run", fake_run)
    csvs, _ = download_yahoo_history("2024-12-27", vibe_root=tmp_path)
    assert csvs == synthetic_csvs


@pytest.mark.parametrize("start", ["2025-01-01", "2025-10-01", "2024-12-01T12:00", "NaT"])
def test_invalid_start_fails_before_fetch(tmp_path, start):
    with pytest.raises(ValueError):
        ingest_history(tmp_path / "snapshot", start=start, vibe_root=tmp_path,
                       fetcher=lambda _: pytest.fail("must not fetch"))
    assert not (tmp_path / "snapshot").exists()


def test_invalid_adjustments_flagged_without_inventing_prices():
    raw = pd.DataFrame({"Close": [100., 0., -1., 50.],
                        "Adj Close": [np.nan, 10., 10., np.inf]},
                       index=pd.date_range("2024-12-27", periods=4))
    before = raw.copy(deep=True)
    out = transform_history(raw)
    assert len(out) == 4
    assert out["close"].isna().all()
    assert not out["adjustment_valid"].any()
    assert out["volume"].isna().all()
    pd.testing.assert_frame_equal(raw, before)


def test_failure_manifest_and_checksum_detection(tmp_path, synthetic_csvs):
    def fail(_):
        raise RuntimeError("offline fixture: network unavailable")

    with pytest.raises(RuntimeError):
        ingest_history(tmp_path / "failed", start="2024-12-27", vibe_root=tmp_path, fetcher=fail)
    manifest = json.loads((tmp_path / "failed/manifest.json").read_text())
    assert manifest["status"] == "incomplete"
    assert "network unavailable" in manifest["error"]
    path = save(tmp_path, synthetic_csvs)
    raw_path = path.parent / f"raw/{BENCHMARK}.csv"
    raw_path.write_text(raw_path.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_snapshot(path)


def test_real_vibe_helpers_with_offline_download(monkeypatch, synthetic_csvs):
    """Run actual isolated Vibe helper imports; replace only the network call."""
    import src.india_ingestion as ingestion

    root = Path(os.environ.get("VIBE_TRADING_ROOT", "/home/jampip/vibe-Trading"))
    interpreter = os.environ.get("VIBE_PYTHON")
    if not interpreter or not root.is_dir():
        pytest.skip("Set VIBE_PYTHON and provide Vibe checkout for helper integration")
    prefix = '''
import io
import pandas as pd
import yfinance as yf
def synthetic_download(symbol, **kwargs):
    assert symbol in %r
    assert kwargs['start'] == '2024-12-27'
    assert kwargs['end'] == '2025-01-01'
    assert kwargs['auto_adjust'] is False
    assert kwargs['repair'] is False
    assert kwargs['keepna'] is True
    return pd.read_csv(io.StringIO(%r), index_col=0, parse_dates=True)
yf.download = synthetic_download
''' % (SYMBOLS, synthetic_csvs[BENCHMARK])
    monkeypatch.setattr(ingestion, "_DOWNLOAD_WORKER", prefix + ingestion._DOWNLOAD_WORKER)
    csvs, provenance = download_yahoo_history(
        "2024-12-27", vibe_root=root, python_executable=interpreter)
    assert set(csvs) == set(SYMBOLS)
    assert "2024-12-31" in csvs[BENCHMARK]
    assert len(provenance["vibe_loader_sha256"]) == 64


def test_missing_provider_symbol_fails(tmp_path, synthetic_csvs):
    del synthetic_csvs[BENCHMARK]
    with pytest.raises(ValueError, match="exactly"):
        save(tmp_path, synthetic_csvs)


def test_empty_response_is_incomplete(tmp_path, synthetic_csvs):
    synthetic_csvs[BENCHMARK] = "Date,Open,High,Low,Close,Adj Close,Volume\n"
    path = save(tmp_path, synthetic_csvs)
    assert json.loads(path.read_text())["status"] == "incomplete"
    with pytest.raises(ValueError, match="incomplete"):
        load_snapshot(path)
