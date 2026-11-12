"""Dashboard routes (src/api/dashboard.py) on the fixture tables in tests/fixtures/api: no AWS, no network.

The router is tested on its own app: in the merged API, Joshua's Week 2 Reddit router still owns
GET /spikes?ticker= until his routes move under /reddit/ (see src/api/main.py).
"""
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import dashboard
from src.api.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures" / "api"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dashboard.router)
    app.dependency_overrides[dashboard.get_storage] = lambda: Storage(str(FIXTURES))
    return TestClient(app)


def test_main_app_mounts_the_dashboard_routes():
    from src.api.main import app
    paths = set(app.openapi()["paths"])
    assert {"/health", "/attention/{ticker}", "/sentiment/{ticker}", "/hot", "/live/{market}", "/runs"} <= paths


def test_health_lists_each_table_with_its_write_time(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["data_root"] == "local"
    assert {"wiki_weekly", "reddit_weekly", "wiki_current", "prices_weekly"} <= set(body["tables"])


def test_attention_returns_records_and_never_holdout_weeks(client):
    rows = client.get("/attention/aapl").json()
    assert {r["source"] for r in rows} == {"wikipedia", "reddit"}
    assert max(r["week"] for r in rows) == "2025-09-22"          # Sep 29 and Oct 6 weeks end in the holdout
    wiki = client.get("/attention/AAPL", params={"source": "wikipedia", "from": "2025-09-08", "to": "2025-09-15"}).json()
    assert [r["week"] for r in wiki] == ["2025-09-08", "2025-09-15"] and wiki[1]["spike"] is True
    assert set(wiki[0]) >= {"ticker", "market", "source", "week", "value", "baseline", "ratio", "spike",
                            "sentiment_pos", "sentiment_neg", "sentiment_neu", "n_scored"}


def test_a_missing_spike_flag_is_no_spike_not_an_error(client):
    r = client.get("/attention/AAPL", params={"source": "reddit", "to": "2025-09-01"})   # spike is null there
    assert r.status_code == 200 and r.json()[0]["spike"] is False


def test_unknown_ticker_and_bad_source(client):
    r = client.get("/attention/ZZZZ")
    assert r.status_code == 404 and "ZZZZ" in r.json()["detail"]
    assert client.get("/sentiment/ZZZZ").status_code == 404
    assert client.get("/attention/AAPL", params={"source": "twitter"}).status_code == 422


def test_sentiment_splits_reddit_groups_and_wikipedia_edits(client):
    rows = client.get("/sentiment/AAPL").json()
    assert {(r["source"], r["group"]) for r in rows} == {("reddit", "investor"), ("wikipedia", "edits")}
    wiki = [r for r in rows if r["source"] == "wikipedia"]
    assert [r["week"] for r in wiki] == ["2025-09-08", "2025-09-15", "2025-09-22"]   # weeks with sentences only
    assert abs(wiki[0]["sentiment_net"] - (-0.1)) < 1e-9
    assert max(r["week"] for r in rows) < "2025-10-01"


def test_spikes_for_a_week_with_repeat_flag_and_timing(client):
    rows = client.get("/spikes", params={"week": "2025-09-22"}).json()
    assert [(r["ticker"], r["repeat"]) for r in rows] == [("AAPL", True)]           # AAPL also spiked Sep 15
    rows = client.get("/spikes", params={"week": "2025-09-15"}).json()
    by = {(r["ticker"], r["source"]): r for r in rows}
    assert set(by) == {("AAPL", "wikipedia"), ("MSFT", "wikipedia"), ("AAPL", "reddit")}
    assert by[("AAPL", "wikipedia")]["timing"] == "before" and by[("MSFT", "wikipedia")]["timing"] == "after"
    assert not by[("MSFT", "wikipedia")]["repeat"]


def test_spikes_empty_week_and_holdout_week(client):
    assert client.get("/spikes", params={"week": "2024-01-01"}).json() == []
    r = client.get("/spikes", params={"week": "2025-09-29"})
    assert r.status_code == 422 and "holdout" in r.json()["detail"]
    latest = client.get("/spikes").json()                                         # default: latest research week
    assert latest[0]["ticker"] == "AAPL" and latest[0]["week"] == "2025-09-22"


def test_hot_keeps_ratios_above_one_sorted_with_todays_move(client):
    rows = client.get("/hot").json()
    assert [r["ticker"] for r in rows] == ["AAPL", "RELIANCE.NS"]
    assert rows[1]["price_change_today_pct"] == 1.2 and rows[0]["price_change_today_pct"] is None
    assert rows[1]["spike"] is False                                             # null flag in the table
    assert [r["ticker"] for r in client.get("/hot", params={"market": "india"}).json()] == ["RELIANCE.NS"]


def test_live_quotes_with_hot_badge(client):
    body = client.get("/live/india").json()
    assert [q["symbol"] for q in body["quotes"]] == ["RELIANCE.NS", "TCS.NS"]
    assert body["quotes"][0]["hot"] and not body["quotes"][1]["hot"]
    assert client.get("/live/hk").json()["quotes"] == []
    assert client.get("/live/mars").status_code == 422


def test_market_open_respects_sessions_and_the_hk_lunch_break():
    utc = UTC
    assert dashboard.market_open("india", datetime(2026, 11, 10, 5, 0, tzinfo=utc))[0]       # 10:30 IST, Tuesday
    assert not dashboard.market_open("india", datetime(2026, 11, 10, 11, 0, tzinfo=utc))[0]  # 16:30 IST
    assert not dashboard.market_open("hk", datetime(2026, 11, 10, 4, 30, tzinfo=utc))[0]     # 12:30 HKT, lunch
    assert dashboard.market_open("hk", datetime(2026, 11, 10, 5, 30, tzinfo=utc))[0]         # 13:30 HKT
    assert not dashboard.market_open("hk", datetime(2026, 11, 14, 5, 30, tzinfo=utc))[0]     # Saturday


def test_runs_proxy_sends_the_key_server_side_only(client, monkeypatch):
    seen = {}

    class Resp:
        status_code, ok = 200, True

        def json(self):
            return [{"run_id": "r1"}]

    def fake_get(url, headers, timeout):
        seen.update(url=url, headers=headers)
        return Resp()

    monkeypatch.delenv("VIBE_API_URL", raising=False)
    assert client.get("/runs").status_code == 503
    monkeypatch.setenv("VIBE_API_URL", "http://vibe.local:8899/")
    monkeypatch.setenv("VIBE_API_KEY", "secret")
    monkeypatch.setattr(dashboard.requests, "get", fake_get)
    r = client.get("/runs")
    assert r.json() == [{"run_id": "r1"}] and "secret" not in r.text
    assert seen == {"url": "http://vibe.local:8899/runs", "headers": {"Authorization": "Bearer secret"}}
    client.get("/runs/a b")
    assert seen["url"].endswith("/runs/a%20b")


def test_prices_are_research_weeks_only_and_unknown_ticker_is_404(client):
    rows = client.get("/prices/aapl").json()
    assert [r["week"] for r in rows] == ["2025-09-15"]                 # the Sep 29 week ends in the holdout
    assert rows[0]["close"] == 230.0 and rows[0]["abn_ret"] == 0.01
    assert client.get("/prices/ZZZZ").status_code == 404


def test_edits_lists_a_weeks_summaries_with_tags_oldest_first(client):
    rows = client.get("/edits/AAPL", params={"week": "2025-09-15"}).json()
    assert [r["comment"] for r in rows] == ["Added Q4 earnings", "Reverted vandalism"]
    assert rows[0]["tags"] == ["earnings"] and rows[1]["revert"] is True
    assert client.get("/edits/AAPL", params={"week": "2025-09-08"}).json() == []
    assert client.get("/edits/AAPL", params={"week": "2025-09-29"}).status_code == 422
