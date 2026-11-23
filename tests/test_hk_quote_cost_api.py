"""The existing live endpoint supports HK quote/cost queries without breaking lists."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api import live_routes
from src.api.live_data import LiveSettings, LiveStore
from src.api.main import app
from src.hk.trade_costs import FxObservation, FxUnavailable


@pytest.fixture
def client(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    roster = tmp_path / "roster.csv"
    roster.write_text("as_of,yahoo_ticker,company_name\n2026-11-04,0700.HK,Tencent\n")
    quote = {
        "symbol": "0700.HK",
        "price": 400,
        "change_pct": 1,
        "volume": 12345,
        "ts_exchange": now.isoformat(),
        "ts_received": now.isoformat(),
        "source": "tencent",
    }
    (tmp_path / "latest.json").write_text(json.dumps([quote]))
    store = LiveStore(LiveSettings(directory=tmp_path, roster=roster))
    app.dependency_overrides[live_routes.get_live_store] = lambda: store
    fx = FxObservation(Decimal("7.8"), now.date(), "manual", now)
    monkeypatch.setattr(
        live_routes, "get_fx_provider", lambda: SimpleNamespace(get=lambda: fx)
    )
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.pop(live_routes.get_live_store, None)


def test_existing_list_shape_preserved(client):
    response = client.get("/live/hk")
    assert response.status_code == 200
    assert response.json()["received_count"] == 1
    assert "estimate" not in response.json()


def test_symbol_query_reads_local_without_frontend_or_aws(client):
    response = client.get("/live/hk", params={"symbol": "HK:700"})
    assert response.status_code == 200
    assert response.json()["symbol"] == "0700.HK"
    assert response.json()["store"] == "local"
    assert response.headers["cache-control"] == "no-store"


def test_cost_query_has_unknown_defaults_and_duty(client):
    response = client.get("/live/hk", params={"symbol": "700", "shares": 250})
    assert response.status_code == 200, response.text
    value = response.json()["estimate"]
    assert value["executed_shares"] == 200
    assert value["complete"] is False
    assert value["fees_hkd"]["stamp_duty"] == 80
    assert "platform_fee_hkd" in value["unknown_charges"]


def test_manual_rate_bypasses_unavailable_fx_service(client, monkeypatch):
    def fail():
        raise AssertionError("Manual FX must not fetch reference data")

    monkeypatch.setattr(live_routes, "get_fx_provider", fail)
    params = {
        "symbol": "700",
        "shares": 100,
        "hkd_per_usd": 7.8,
        "commission_hkd": 50,
        "platform_fee_hkd": 0,
        "fx_spread_bps": 10,
        "fx_fee_usd": 2,
        "transfer_fee_usd": 5,
        "settlement_pass_through": "true",
    }
    response = client.get("/live/hk", params=params)
    assert response.status_code == 200, response.text
    value = response.json()["estimate"]
    assert value["complete"] is True and value["cash_usd"] == 5152.54
    assert value["fx"]["kind"] == "manual"


@pytest.mark.parametrize(
    "params",
    [
        {"shares": 100},
        {"symbol": "700", "shares": 99},
        {"symbol": "700", "shares": 0},
        {"symbol": "700", "shares": 100, "hkd_per_usd": 0},
        {"symbol": "700", "shares": 100, "fx_spread_bps": -1},
    ],
)
def test_invalid_cost_inputs_are_422(client, params):
    assert client.get("/live/hk", params=params).status_code == 422


def test_unknown_code_is_404(client):
    response = client.get("/live/hk", params={"symbol": "bad-code"})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "unknown_ticker"


def test_unavailable_fx_does_not_break_quote_list(client, monkeypatch):
    def fail():
        raise FxUnavailable("Recent FX is unavailable")

    monkeypatch.setattr(
        live_routes, "get_fx_provider", lambda: SimpleNamespace(get=fail)
    )
    assert (
        client.get("/live/hk", params={"symbol": "700", "shares": 100}).status_code
        == 503
    )
    assert client.get("/live/hk").status_code == 200


def test_local_alias_and_duplicate_selection_matches_list(client):
    store = app.dependency_overrides[live_routes.get_live_store]()
    path = store.settings.directory / "latest.json"
    original = json.loads(path.read_text())[0]
    older = original | {
        "symbol": "0700.HK",
        "price": 399,
        "ts_exchange": (
            datetime.fromisoformat(original["ts_exchange"]) - timedelta(seconds=10)
        ).isoformat(),
    }
    newer = original | {"symbol": "700.HK", "price": 401}
    path.write_text(json.dumps([older, newer]))
    assert client.get("/live/hk").json()["quotes"][0]["price"] == 401
    assert client.get("/live/hk", params={"symbol": "0700"}).json()["price"] == 401


def test_india_remains_owned_by_other_provider(client):
    assert client.get("/live/in", params={"symbol": "INFY"}).status_code == 404
