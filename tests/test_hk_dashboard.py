"""Network-free contract, corruption, calendar and static-build tests for HK display."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.api.live_data import LiveDataUnavailable, LiveSettings, LiveStore
from src.api.live_routes import get_live_store
from src.api.main import app
from src.hk.dashboard import build, public_config

NOW = datetime(2026, 11, 18, 2, 0, tzinfo=UTC)


def quote(code="0700.HK", **changes):
    return {
        "symbol": code,
        "price": 398.8,
        "change_pct": -2.64,
        "volume": 25844607,
        "ts_exchange": (NOW - timedelta(seconds=12)).isoformat(),
        "ts_received": NOW.isoformat(),
        "source": "tencent",
        **changes,
    }


@pytest.fixture
def store(tmp_path):
    roster = tmp_path / "roster.csv"
    roster.write_text(
        "as_of,yahoo_ticker,company_name\n2026-11-04,0700.HK,Tencent\n2026-11-04,0005.HK,HSBC\n"
    )
    (tmp_path / "latest.json").write_text(json.dumps([quote()]))
    return LiveStore(LiveSettings(directory=tmp_path, roster=roster))


def save(store, rows):
    (store.settings.directory / "latest.json").write_text(json.dumps(rows))


def test_snapshot_alias_deduplication_and_missing_instruments(store):
    save(
        store,
        [
            quote("700"),
            quote("0700.HK", price=400, ts_exchange=NOW.isoformat()),
            quote("9988.HK"),
        ],
    )
    result = store.snapshot(NOW)
    assert len(result["quotes"]) == 1
    assert result["quotes"][0]["symbol"] == "0700.HK"
    assert result["quotes"][0]["name"] == "Tencent"
    assert result["quotes"][0]["price"] == 400
    assert result["missing_symbols"] == ["0005.HK"]
    assert result["received_count"] == 1 and result["requested_count"] == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"price": -1},
        {"price": True},
        {"price": float("nan")},
        {"volume": -1},
        {"change_pct": float("inf")},
        {"source": None},
        {"ts_exchange": "bad"},
        {"ts_received": "2026-11-18T02:00:00"},
        {"ts_exchange": (NOW + timedelta(seconds=30)).isoformat()},
    ],
)
def test_one_bad_quote_does_not_hide_other_stock(store, changes):
    save(store, [quote(**changes), quote("0005.HK")])
    result = store.snapshot(NOW)
    assert [row["symbol"] for row in result["quotes"]] == ["0005.HK"]
    assert result["invalid_rows"] == 1


def test_slow_trade_is_separate_from_stale_receipt(store):
    save(store, [quote(ts_exchange=(NOW - timedelta(minutes=20)).isoformat())])
    result = store.snapshot(NOW)
    assert result["quotes"][0]["last_trade_age_seconds"] == 1200
    assert result["is_stale"] is False
    result = store.snapshot(NOW + timedelta(minutes=2))
    assert result["is_stale"] is True


@pytest.mark.parametrize(
    "stamp,state,next_open",
    [
        ("2026-11-18T04:30:00+00:00", "lunch", "2026-11-18T05:00:00+00:00"),
        ("2026-11-18T10:00:00+00:00", "closed", "2026-11-19T01:30:00+00:00"),
        ("2026-10-01T02:00:00+00:00", "closed", "2026-10-02T01:30:00+00:00"),
    ],
)
def test_closed_lunch_and_holiday_keep_last_quotes(store, stamp, state, next_open):
    now = datetime.fromisoformat(stamp)
    save(
        store,
        [
            quote(
                ts_exchange=(now - timedelta(hours=1)).isoformat(),
                ts_received=(now - timedelta(hours=1)).isoformat(),
            )
        ],
    )
    result = store.snapshot(now)
    assert result["market_state"] == state and result["next_open"] == next_open
    assert result["quotes"] and result["is_stale"] is False


def test_empty_file_is_valid_empty_data_but_corruption_is_not(store):
    save(store, [])
    assert store.snapshot(NOW)["quotes"] == []
    assert store.snapshot(NOW)["is_stale"] is True
    (store.settings.directory / "latest.json").write_text("{half-written")
    with pytest.raises(LiveDataUnavailable):
        store.snapshot(NOW)


def test_dynamodb_pagination_decimal_and_read_only_contract(store):
    table = Mock()
    table.scan.side_effect = [
        {
            "Items": [quote(price=Decimal("398.8"))],
            "LastEvaluatedKey": {"symbol": "0700.HK"},
        },
        {"Items": [quote("0005.HK")]},
    ]
    cloud = LiveStore(
        LiveSettings(mode="dynamodb", roster=store.settings.roster), table=table
    )
    result = cloud.snapshot(NOW)
    assert result["received_count"] == 2 and result["quotes"][1]["price"] == 398.8
    table.scan.assert_any_call(ExclusiveStartKey={"symbol": "0700.HK"})
    assert all(call[0] == "scan" for call in table.method_calls)


def test_aws_error_does_not_leak_exception_contents(store):
    table = Mock()
    table.scan.side_effect = RuntimeError("credential=do-not-expose")
    cloud = LiveStore(
        LiveSettings(mode="dynamodb", roster=store.settings.roster), table=table
    )
    with pytest.raises(LiveDataUnavailable, match="table is unavailable") as error:
        cloud.snapshot(NOW)
    assert "credential" not in str(error.value)


@pytest.fixture
def client(store, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("src.api.live_data.datetime", Clock)
    app.dependency_overrides[get_live_store] = lambda: store
    with TestClient(app) as result:
        yield result
    app.dependency_overrides.clear()


def test_live_health_and_missing_feed_api(client):
    response = client.get("/live/hk")
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert response.json()["currency"] == "HKD"
    assert (
        client.get("/health").json()["sources"]["live_hk"]["as_of"] == NOW.isoformat()
    )
    assert (
        client.get("/health").json()["status"] == "degraded"
    )  # One configured stock missing.
    assert client.get("/live/india").status_code == 404
    assert client.post("/live/hk").status_code == 405


def test_missing_data_returns_unavailable_and_health_degraded(client, store):
    (store.settings.directory / "latest.json").unlink()
    response = client.get("/live/hk")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert str(store.settings.directory) not in response.text
    assert client.get("/health").json()["status"] == "degraded"


def test_complete_valid_snapshot_is_healthy(client, store):
    save(store, [quote(), quote("0005.HK")])
    assert client.get("/health").json()["status"] == "ok"


def test_frontend_serving_public_config_and_existing_router(client):
    assert client.get("/").status_code == 200
    assert "Live markets" in client.get("/live-markets/").text
    config = client.get("/live-markets/config.js")
    assert config.headers["cache-control"] == "no-store"
    assert "apiBaseUrl" in config.text and "5000" in config.text
    paths = client.get("/openapi.json").json()["paths"]
    assert "/sentiment" in paths and "/spikes" in paths


def test_build_copies_only_static_allowlist_and_public_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("INDICATORLAB_API_BASE_URL", "https://api.example.org")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "never-in-browser")
    build(tmp_path / "dist")
    paths = sorted(path.name for path in (tmp_path / "dist").iterdir())
    assert paths == ["app.mjs", "config.js", "index.html", "model.mjs", "styles.css"]
    config = (tmp_path / "dist/config.js").read_text()
    assert "https://api.example.org" in config and "never-in-browser" not in config


@pytest.mark.parametrize(
    "base",
    [
        "javascript:alert(1)",
        "https://user:secret@example.org",
        "https://example.org?key=secret",
    ],
)
def test_public_api_url_rejects_unsafe_or_secret_bearing_values(base):
    with pytest.raises(ValueError):
        public_config(base)
