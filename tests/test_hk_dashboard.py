"""Offline HK adapter checks; no real-data strategy evaluation or network calls."""

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.hk_dashboard import api
from src.hk_dashboard.data import HKData
from src.hk_dashboard.live import LiveSource, session, valid_quote
from src.hk_dashboard.paths import canonical, names
from src.hk_dashboard.refresh import weekly
from src.reddit import dashboard_server as us


class OfflineLive:
    def snapshot(self):
        return {
            "market": "hk",
            "quotes": [],
            "market_state": "closed",
            "received_count": 0,
        }


@pytest.fixture
def data(tmp_path):
    return HKData(
        root=tmp_path / "source", display=tmp_path / "display", live=OfflineLive()
    )


@pytest.mark.parametrize("raw", ["700", "00700", "hk:700", "HKEX:00700", "0700.hk"])
def test_canonical(raw):
    assert canonical(raw) == "0700.HK"


@pytest.mark.parametrize(
    "raw", ["AAPL", "0700.HK/../../", "700.NS", "0", "-700", "７００", "700<script>"]
)
def test_foreign_and_injected_codes(raw):
    with pytest.raises(ValueError):
        canonical(raw)


def test_roster_and_no_invented_observations(data):
    assert len(names()) == 95
    result = data.now()
    assert len(result["rows"]) == 95
    assert not result["reddit_available"]
    assert result["attention_stocks"] == 0
    assert all(r["metrics"]["views"]["count"] is None for r in result["rows"])
    with pytest.raises(KeyError):
        data.stock("99998")


def test_missing_daily_observations_and_creation():
    rows = weekly(
        {"2026-11-16": 10},
        [],
        date(2026, 11, 16),
        date(2026, 11, 22),
        views_ok=True,
        edits_ok=True,
        created=date(2026, 11, 18),
    )
    assert rows[0]["views"] is None
    assert rows[0]["edits"] == 0
    assert rows[0]["partial"]
    rows = weekly(
        {},
        [],
        date(2026, 11, 16),
        date(2026, 11, 22),
        views_ok=True,
        edits_ok=True,
        created=date(2026, 12, 1),
    )
    assert rows[0]["views"] is None and rows[0]["edits"] is None


def test_attention_gaps_survive_and_baseline_uses_past(data):
    path = data.display / "wikipedia/0700.HK.json"
    path.parent.mkdir(parents=True)
    weeks = pd.date_range("2025-01-06", periods=30, freq="W-MON")
    records = [
        {
            "week": str(w.date()),
            "views": 10,
            "edits": 1,
            "days_covered": 7,
            "partial": False,
        }
        for w in weeks
    ]
    records[12]["views"] = None
    records[-1]["views"] = 1000
    path.write_text(json.dumps({"weeks": records, "lang": "en", "title": "Tencent"}))
    frames, _ = data.attention()
    frame = frames["0700.HK"]
    assert pd.isna(frame.iloc[12]["views"])
    assert frame.iloc[-1]["views_baseline"] == 10
    assert frame.iloc[-1]["views_ratio"] > 50
    assert pd.isna(frame.iloc[13]["views_baseline"])


def test_latest_majority_is_not_pinned_to_old_maximum(data):
    frames = {}
    weeks = pd.to_datetime(["2026-09-21", "2026-11-16", "2026-11-23"])
    for index in range(5):
        frames[str(index)] = pd.DataFrame(
            {
                "views": [1, 1 if index < 4 else np.nan, 1 if index == 0 else np.nan],
                "edits": [1, 1, 1],
            },
            index=weeks,
        )
    result = data.latest_weeks(frames)
    assert result["views"] == weeks[1] and result["edits"] == weeks[2]


def test_price_vintage_is_coherent_and_missing_is_not_filled(data):
    path = data.display / "prices/0700.HK.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {"Close": [100, 200], "Adj Close": [50, 100]},
        index=pd.to_datetime(["2026-10-02", "2026-10-16"]),
    ).to_parquet(path)
    frame, meta = data.price_weeks("0700.HK")
    assert frame.iloc[0]["close"] == 50 and frame.iloc[-1]["close"] == 100
    assert pd.isna(frame.iloc[1]["close"])
    assert pd.isna(frame.iloc[-1]["ret"])
    assert meta["currency"] == "HKD"


def test_sentiment_requires_same_article_and_revision(data):
    path = data.root / "data/hk_week4/wiki_sentiment.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ticker": "0700.HK",
                "week": "2026-10-12",
                "last_revision": 123,
                "sentiment": 0.4,
            }
        ]
    ).to_parquet(path)
    old = path.parent / "wikipedia/0700.HK.json"
    old.parent.mkdir()
    old.write_text(json.dumps({"identity": {"lang": "en", "title": "Tencent"}}))
    doc = {
        "lang": "en",
        "title": "Tencent",
        "revisions": [{"timestamp": "2026-10-13T00:00:00Z", "revid": 123}],
    }
    assert len(data._sentiment("0700.HK", doc)) == 1
    doc["revisions"][0]["revid"] = 124
    assert not data._sentiment("0700.HK", doc)
    doc["title"] = "Another company"
    assert not data._sentiment("0700.HK", doc)


def quote(now):
    return {
        "symbol": "700",
        "price": 100,
        "change_pct": 1,
        "volume": 10,
        "source": "Tencent",
        "ts_exchange": (now - timedelta(seconds=3)).isoformat(),
        "ts_received": now.isoformat(),
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("price", 0),
        ("volume", -1),
        ("price", float("nan")),
        ("price", True),
        ("symbol", "AAPL"),
        ("ts_received", "2026-11-24"),
    ],
)
def test_invalid_quote_rejected(key, value):
    now = datetime(2026, 11, 24, 3, tzinfo=UTC)
    row = quote(now)
    row[key] = value
    with pytest.raises((ValueError, TypeError)):
        valid_quote(row, now, set(names()))


def test_live_snapshot_fallback_and_age(tmp_path, monkeypatch):
    import src.hk_dashboard.live as module

    now = datetime(2026, 11, 24, 3, tzinfo=UTC)
    row = quote(now)
    row["ts_exchange"] = (now - timedelta(minutes=16)).isoformat()
    (tmp_path / "latest.json").write_text(json.dumps([{"bad": True}, row]))
    monkeypatch.setattr(module, "quote_directories", lambda: [tmp_path])
    monkeypatch.setattr(module, "session", lambda now: ("open", None))
    source = LiveSource(base_url="", clock=lambda: now)
    result = source.snapshot()
    assert result["received_count"] == 1 and result["store"] == "local_snapshot"
    assert result["quotes"][0]["label"] == "delayed ~16 min"
    assert result["quotes"][0]["receipt_age_seconds"] == 0
    # A recent read must never make an old trade "live".
    assert result["quotes"][0]["delay_seconds"] == 960


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2026-11-24T02:00:00+00:00", "open"),
        ("2026-11-24T04:30:00+00:00", "lunch"),
        ("2026-11-24T09:00:00+00:00", "closed"),
        ("2026-11-22T02:00:00+00:00", "closed"),
    ],
)
def test_hk_calendar(stamp, expected):
    assert session(datetime.fromisoformat(stamp))[0] == expected


def call_handler(path, method="GET"):
    handler = us.Handler.__new__(us.Handler)
    handler.path = path
    captured = {}
    handler._json = lambda payload, code=200: captured.update(
        payload=payload, code=code
    )
    handler._send = lambda code, body, ctype: captured.update(
        body=body, code=code, ctype=ctype
    )
    getattr(handler, "do_" + method)()
    return captured


def test_us_default_dispatch_and_hk_isolation(monkeypatch):
    monkeypatch.setattr(
        us, "now", lambda: {"market": "US", "rows": [{"ticker": "AAPL", "ret": 0.1}]}
    )
    assert call_handler("/api/now")["payload"]["market"] == "US"
    fake = SimpleNamespace(
        now=lambda: {"market": "hk", "rows": [{"ticker": "0700.HK"}]}
    )
    monkeypatch.setattr(api, "dataset", lambda: fake)
    # dispatch builds its routes eagerly; supply all read-only methods.
    for key in ["status", "spikes", "strategies"]:
        setattr(fake, key, dict)
    fake.live = SimpleNamespace(snapshot=dict)
    assert call_handler("/api/now?market=hk")["payload"]["market"] == "hk"
    assert call_handler("/api/now")["payload"]["market"] == "US"
    for path in ["/api/rebuild?market=hk", "/api/run_strategies?market=hk"]:
        assert call_handler(path, "POST")["code"] == 405
    # The untouched US route still reports its existing running state.
    monkeypatch.setitem(us.strategy_state, "running", True)
    assert call_handler("/api/run_strategies", "POST")["code"] == 409


def test_html_india_control_unchanged_and_assets_allowlisted():
    body = call_handler("/?market=hk")["body"].decode()
    assert (
        '<button type="button" disabled title="No India data in this build yet">India</button>'
        in body
    )
    assert call_handler("/hk-assets/hk-market.js")["code"] == 200
    assert call_handler("/hk-assets/../../config.yaml")["code"] == 404


def test_cost_proxy_keeps_unknown_fees_and_rejects_foreign():
    class Client:
        def get(self, url, params, timeout):
            assert params == {"symbol": "0700.HK", "side": "buy", "shares": "100"}
            return SimpleNamespace(
                raise_for_status=lambda: None,
                content=b"{}",
                json=lambda: {
                    "quote": {"symbol": "0700.HK"},
                    "estimate": {"complete": False},
                },
            )

    source = LiveSource(base_url="http://127.0.0.1:8765", http=Client())
    assert not source.estimate(
        {"ticker": "700", "shares": "100", "commission_hkd": ""}
    )["estimate"]["complete"]
    with pytest.raises(ValueError):
        source.estimate({"ticker": "AAPL", "shares": "100"})


def test_collector_resolves_redirect_and_creation_before_views(tmp_path, monkeypatch):
    from src.hk_dashboard import refresh

    end = datetime.now(UTC).date() - timedelta(days=1)
    created = end - timedelta(days=8)

    class Wikimedia:
        def revisions(self, lang, title, start, end):
            return [], {
                "title": "Current article",
                "created_at": str(created) + "T00:00:00Z",
                "complete": True,
            }

        def views(self, lang, title, start, end):
            assert title == "Current article" and start == created
            return {str(day.date()): 1 for day in pd.date_range(start, end)}, [
                "https://wikimedia.org/source"
            ]

    monkeypatch.setattr(refresh, "Wikimedia", Wikimedia)
    monkeypatch.setattr(
        refresh, "names", lambda: {"0700.HK": {"wiki_en": "Old_redirect"}}
    )
    result = refresh.run(tmp_path)
    document = json.loads((tmp_path / "wikipedia/0700.HK.json").read_text())
    assert not result["stocks"]["0700.HK"]["errors"]
    assert (
        document["title"] == "Current article"
        and document["mapped_title"] == "Old_redirect"
    )
    assert all(
        row["views"] is None
        for row in document["weeks"]
        if row["week"] < str(created - timedelta(days=7))
    )


def test_bundled_research_is_frozen_and_portable(data):
    bundle = data.strategies()
    assert len(bundle["rows"]) == 3
    assert all(row["decision"] == "DROP" for row in bundle["rows"])
    assert all(
        len(s["growth"]) == len(s["dates"]) == 1185 for s in bundle["series"].values()
    )
    assert bundle["cohort_stocks"] == 5
    assert len(bundle["frozen_source_sha256"]) == 3


def test_existing_us_static_export_does_not_request_live_hk_assets():
    from src.reddit.dashboard_export import static_page

    page = static_page((us.DASH / "index.html").read_text(), "2026-11-25")
    assert "/hk-assets/" not in page
    assert 'disabled title="Hong Kong requires the live dashboard server"' in page
    assert "api/now.json" not in page  # Existing generic static resolver is preserved.
    assert 'return fetch(f + ".json"' in page
