"""Offline shared-table export checks with no Mac path, quote API or AWS access."""

import json

import pandas as pd
import pytest

from src.hk_dashboard.paths import names
from src.hk_dashboard.snapshot import SnapshotData
from src.reddit import dashboard_export as export


def tables():
    current = pd.DataFrame(
        [
            {
                "ticker": code,
                "market": "hk",
                "source": "wikipedia",
                "week": "2026-11-23",
                "value": 100,
                "baseline": 50,
                "ratio": 2.0,
                "spike": True,
                "as_of": "2026-11-25",
            }
            for code in names()
        ]
    )
    weekly = current.drop(columns="as_of").assign(
        edits=3, edits_baseline=2, edits_ratio=1.5, edits_spike=False, n_scored=0
    )
    prices = current[["market", "ticker", "week"]].assign(close=100.0, ret=0.01)
    return {
        "wiki_current.parquet": current,
        "wiki_weekly.parquet": weekly,
        "prices_weekly.parquet": prices,
    }


def source(data=None):
    data = tables() if data is None else data

    def reader(uri):
        assert uri.startswith("s3://shared-test/processed/")
        name = uri.rsplit("/", 1)[-1]
        if name not in data:
            raise FileNotFoundError(name)
        return data[name]

    def json_reader(uri):
        raise FileNotFoundError(uri)

    return SnapshotData("s3://shared-test", reader=reader, json_reader=json_reader)


def test_95_stock_snapshot_without_local_service(tmp_path, monkeypatch):
    monkeypatch.setenv("INDICATORLAB_HK_SOURCE_ROOT", "/not/a/mac/folder")
    data = source()
    result = data.now()
    assert len(result["rows"]) == 95 and result["attention_stocks"] == 95
    assert result["rows"][0]["metrics"]["views"]["count"] == 100
    assert result["rows"][0]["metrics"]["edits"]["count"] is None
    assert "Trailing seven published days" in result["attention_window"]
    assert data.live["received_count"] == 0
    assert data.stock("700")["weeks"][0]["tone"] is None
    metadata = data.write(tmp_path)
    assert metadata["stocks"] == 95
    assert len(list((tmp_path / "api/hk/stock").glob("*.json"))) == 95
    assert (
        len(json.loads((tmp_path / "api/hk/strategy_log.json").read_text())["rows"])
        == 3
    )
    assert json.loads((tmp_path / "api/hk/status.json").read_text())["snapshot"] is True


def test_missing_current_and_duplicate_rows_fail():
    with pytest.raises(RuntimeError):
        source({})
    data = tables()
    data["wiki_current.parquet"] = pd.concat([data["wiki_current.parquet"]] * 2)
    with pytest.raises(ValueError, match="Duplicate"):
        source(data)


def test_cross_market_rows_never_become_hk():
    data = tables()
    data["wiki_current.parquet"] = pd.concat(
        [
            data["wiki_current.parquet"],
            pd.DataFrame([{"ticker": "AAPL", "market": "us", "value": 999999}]),
        ]
    )
    assert len(source(data).current) == 95
    data["wiki_current.parquet"] = data["wiki_current.parquet"].drop(columns="market")
    with pytest.raises(ValueError, match="market"):
        source(data)


def test_existing_us_only_history_is_reported_as_a_hk_data_gap():
    data = tables()
    for key in ["wiki_weekly.parquet", "prices_weekly.parquet"]:
        data[key] = data[key].assign(market="us", ticker="AAPL")
    snapshot = source(data)
    assert snapshot.errors["wiki_weekly.parquet"] == "no_hk_rows"
    assert snapshot.errors["prices_weekly.parquet"] == "no_hk_rows"
    assert snapshot.stock("0700.HK")["weeks"] == []
    assert (
        snapshot.stock("0700.HK")["current_attention"]["metrics"]["views"]["count"]
        == 100
    )
    assert snapshot.status()["historical_price_stocks"] == 0


def test_permission_failures_do_not_become_missing_data():
    def reader(uri):
        if uri.endswith("wiki_current.parquet"):
            return tables()["wiki_current.parquet"]
        raise PermissionError("test access denied")

    with pytest.raises(PermissionError):
        SnapshotData("s3://example", reader=reader)


def test_static_page_keeps_hk_and_uses_relative_assets():
    html = (export.settings.DASHBOARD / "index.html").read_text()
    page = export.static_page(html, "2026-11-26", hk_snapshot=True)
    assert 'data-hk-snapshot="true"' in page
    assert 'src="hk-assets/hk-market.js"' in page
    assert 'disabled title="Hong Kong requires' not in page
    assert 'return fetch(f + ".json"' in page


def test_quote_object_and_edit_evidence_are_not_invented():
    data = tables()
    data["wiki_edit_summaries.parquet"] = pd.DataFrame(
        [
            {
                "market": "hk",
                "ticker": "0700.HK",
                "week": "2026-11-23",
                "timestamp": "2026-11-24T02:00:00Z",
                "comment": "Published summary",
            }
        ]
    )

    def reader(uri):
        key = uri.rsplit("/", 1)[-1]
        if key not in data:
            raise FileNotFoundError(key)
        return data[key]

    quote = {
        "symbol": "0700.HK",
        "price": 100.0,
        "volume": 123.0,
        "change_pct": 1.0,
        "ts_exchange": "2026-11-24T02:00:00+00:00",
        "ts_received": "2026-11-24T02:00:01+00:00",
        "source": "tencent",
    }
    snapshot = SnapshotData("s3://test", reader=reader, json_reader=lambda uri: [quote])
    assert snapshot.live["received_count"] == 1
    assert snapshot.live["quotes"][0]["label"] == "snapshot"
    row = snapshot.stock("0700.HK")["revisions"][0]
    assert (
        row["comment"] == "Published summary"
        and row["revid"] is None
        and row["url"] is None
    )


def test_export_includes_snapshot_endpoints(tmp_path, monkeypatch):
    import src.hk_dashboard.snapshot as module

    data = source()
    monkeypatch.setattr(module, "SnapshotData", lambda uri: data)
    monkeypatch.setattr(export.ds, "status", dict)
    monkeypatch.setattr(export.ds, "_csv", lambda path: {"rows": []})
    for name in ["now", "spike_weeks"]:
        monkeypatch.setattr(export.ds, name, lambda: {"rows": []})
    for name in ["weekly", "stock"]:
        monkeypatch.setattr(export.ds, name, lambda code: {"ticker": code, "rows": []})
    monkeypatch.setattr(export.ds, "strategy_run", lambda run: {"runs": []})
    monkeypatch.setattr(export.settings, "CHARTS", tmp_path / "no-charts")
    out = tmp_path / "site"
    export.export(out, hk_root_uri="s3://shared-test")
    assert (out / "hk-assets/hk-market.js").is_file()
    assert (out / "api/hk/manifest.json").is_file()
    assert (out / "api/hk/stock/0700.HK.json").is_file()
    assert (out / "api/now.json").is_file()
