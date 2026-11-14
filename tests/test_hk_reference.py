"""Reference parsing and migration safety use synthetic data, never live prices."""

import importlib
import io
import json
import sys

import pandas as pd
import pytest

from src.hk import local_service
from src.hk.refresh_reference import board_lots


def workbook(lot="400"):
    frame = pd.DataFrame(
        {
            "Stock Code": ["00005", "00823", "80005"],
            "Category": ["Equity", "Real Estate Investment Trusts", "Equity"],
            "Trading Currency": ["HKD", "HKD", "CNY"],
            "Board Lot": [lot, "100", "400"],
            "Subject to Stamp Duty": ["Y", "", "Y"],
        }
    )
    content = io.BytesIO()
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, startrow=2)
    return content.getvalue()


def test_lots_include_hsi_reit_and_preserve_hash():
    frame = board_lots(workbook(), "2026-11-12T00:00:00+00:00")
    assert dict(zip(frame.symbol, frame.board_lot)) == {"0005.HK": 400, "0823.HK": 100}
    assert frame.source_sha256.str.len().eq(64).all()


@pytest.mark.parametrize("lot", ["0", "1.5", "", "invalid"])
def test_invalid_reference_lots_fail(lot):
    with pytest.raises(ValueError):
        board_lots(workbook(lot), "2026-11-12T00:00:00+00:00")


def test_service_never_signals_a_reused_pid(tmp_path, monkeypatch):
    path = tmp_path / "pid.json"
    path.write_text('{"pid": 123}')
    monkeypatch.setattr(local_service, "PID_FILE", path)
    monkeypatch.setattr(
        local_service.subprocess, "check_output", lambda *a, **kw: "unrelated-program"
    )
    assert local_service.worker_pid() is None


def test_service_recomputes_age_when_reading_old_file(tmp_path, monkeypatch):
    monkeypatch.setattr(local_service, "OUTPUT", tmp_path)
    monkeypatch.setattr(local_service, "worker_pid", lambda: None)
    (tmp_path / "latest.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "0700.HK",
                    "ts_exchange": "2020-01-01T00:00:00+00:00",
                    "delay_seconds": 0,
                }
            ]
        )
    )
    assert local_service.status()["currently_under_60s"] == 0


def test_legacy_modules_import_without_downloads(monkeypatch):
    import requests
    import yfinance

    def forbidden(*args, **kwargs):
        pytest.fail("Import triggered a network call")

    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(yfinance.Ticker, "history", forbidden)
    for name in [
        "week1.check_data",
        "week1.backtest_strategies",
        "history.download_hsi_history",
        "history.validate_hsi_history",
        "history.probe_intraday",
        "week2.backtest_hsi_strategies",
        "week2.backtest_advanced_hsi_strategies",
        "week2.backtest_non_momentum_hsi_strategies",
        "week2.build_week2_evidence",
        "week2.compare_live_sources",
        "week2.live_poller",
        "week2.analyze_latest_intraday_session",
    ]:
        importlib.import_module("src.hk." + name)


def test_refresh_preserves_canonical_history_and_frozen_lots(tmp_path, monkeypatch):
    from src.hk import refresh_reference

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "hsi_constituents_2026-11-04.csv").write_text("symbol\n0005.HK\n")
    titles = config_dir / "hk_wiki_titles.csv"
    lots = config_dir / "hk_board_lots_2026-11-12.csv"
    titles.write_text("historical canonical title intervals\n")
    lots.write_text("immutable research lot snapshot\n")
    cached = tmp_path / "cached"
    cached.mkdir()
    (cached / "lots.xlsx").write_bytes(workbook())
    (cached / "wiki.txt").write_text("cached roster")
    monkeypatch.setattr(refresh_reference, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["refresh_reference", "--cached-sources", str(cached), "--skip-survey"],
    )
    monkeypatch.setattr(
        refresh_reference,
        "wiki_titles",
        lambda *_: (pd.DataFrame({"symbol": ["0005.HK"], "title": ["HSBC"]}), {}),
    )
    refresh_reference.main()
    assert titles.read_text() == "historical canonical title intervals\n"
    assert lots.read_text() == "immutable research lot snapshot\n"
    snapshots = list((tmp_path / "data/hk_reference_refresh").iterdir())
    assert len(snapshots) == 1
    assert (snapshots[0] / "wiki_aliases_observed.csv").is_file()
