"""One test per Wikipedia/price endpoint, on a small in-memory store (no data files needed)."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import wikipedia
from src.api.main import app


@pytest.fixture
def client():
    att = pd.DataFrame({
        "week": ["2024-01-01", "2024-01-08", "2024-01-01", "2024-01-08", "2024-01-08"],
        "ticker": ["AAPL"] * 5,
        "market": ["US"] * 5,
        "source": ["wikipedia_views", "wikipedia_views", "wikipedia_edits", "wikipedia_edits", "reddit_product"],
        "views": [100.0, 300.0, None, None, None],
        "edits": [None, None, 2.0, 9.0, None],
        "posts": [None, None, None, None, 40.0],
        "spike": [False, True, False, True, False],
    })
    prices = pd.DataFrame({"week": ["2024-01-01", "2024-01-08"], "ticker": ["AAPL", "AAPL"],
                           "close": [185.0, 186.0], "ret": [None, 0.0054], "ret_next1": [0.0054, -0.01]})
    app.dependency_overrides[wikipedia.get_store] = lambda: wikipedia.Store(att, prices)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_tickers_lists_sources_with_coverage(client):
    body = client.get("/tickers").json()
    aapl = body["tickers"][0]
    assert body["n_tickers"] == 1 and aapl["ticker"] == "AAPL" and aapl["name"] == "Apple"
    views = next(s for s in aapl["sources"] if s["source"] == "wikipedia_views")
    assert views == {"source": "wikipedia_views", "first_week": "2024-01-01", "last_week": "2024-01-08", "weeks": 2}


def test_attention_filters_by_source_prefix_and_dates(client):
    r = client.get("/attention", params={"ticker": "aapl", "start": "2024-01-02", "end": "2024-12-31",
                                         "source": "wikipedia,reddit_product"})
    body = r.json()
    assert r.status_code == 200 and body["n_rows"] == 3
    assert body["sources"] == ["reddit_product", "wikipedia_edits", "wikipedia_views"]
    assert all(row["week"] == "2024-01-08" for row in body["rows"])
    assert client.get("/attention", params={"ticker": "ZZZ", "start": "2024-01-01", "end": "2024-02-01"}).status_code == 404


def test_price_returns_weekly_rows_with_forward_returns(client):
    body = client.get("/price", params={"ticker": "AAPL", "start": "2024-01-01", "end": "2024-01-31"}).json()
    assert body["n_weeks"] == 2
    assert body["weeks"][0] == {"week": "2024-01-01", "close": 185.0, "ret": None, "ret_next1": 0.0054}
    bad = client.get("/price", params={"ticker": "AAPL", "start": "2024-02-01", "end": "2024-01-01"})
    assert bad.status_code == 422
