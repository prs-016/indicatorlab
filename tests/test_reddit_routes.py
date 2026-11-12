"""/reddit/* routes with FastAPI's TestClient against the parquet fixtures in tests/fixtures/ (no AWS)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api import reddit_data
from src.api.main import app
from src.api.reddit_data import RedditData, get_reddit_data
from src.api.reddit_routes import AttentionRecord

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def data():
    return RedditData.load(str(FIXTURES))


@pytest.fixture
def client(data):
    app.dependency_overrides[get_reddit_data] = lambda: data
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_attention_returns_shared_records_and_stops_before_the_holdout(client):
    r = client.get("/reddit/attention/aapl", params={"market": "us"})
    assert r.status_code == 200
    body = r.json()
    assert [row["week"] for row in body] == ["2025-09-08", "2025-09-15", "2025-09-22"]   # 09-29 week is holdout
    assert set(body[0]) == set(AttentionRecord.model_fields)
    assert body[1]["spike"] is True and body[0]["source"] == "reddit" and body[0]["ticker"] == "AAPL"


def test_attention_date_window_and_empty_range(client):
    r = client.get("/reddit/attention/AAPL", params={"from": "2025-09-15", "to": "2025-09-15"})
    assert [row["week"] for row in r.json()] == ["2025-09-15"]
    r = client.get("/reddit/attention/AAPL", params={"from": "2024-01-01", "to": "2024-02-01"})
    assert r.status_code == 200 and r.json() == []


def test_from_after_to_is_rejected(client):
    r = client.get("/reddit/attention/AAPL", params={"from": "2025-09-22", "to": "2025-09-08"})
    assert r.status_code == 422 and "from" in r.json()["detail"]


def test_unknown_ticker_and_uncovered_market_are_404(client):
    r = client.get("/reddit/attention/ZZZZ")
    assert r.status_code == 404 and "ZZZZ" in r.json()["detail"] and "AAPL" in r.json()["detail"]
    r = client.get("/reddit/attention/AAPL", params={"market": "india"})
    assert r.status_code == 404 and "india" in r.json()["detail"]
    assert client.get("/reddit/attention/AAPL", params={"market": "uk"}).status_code == 422


def test_sentiment_splits_investor_and_product_with_net(client):
    body = client.get("/reddit/sentiment/AAPL").json()
    assert len(body) == 6 and {r["subreddit_type"] for r in body} == {"investor", "product"}
    prod = next(r for r in body if r["subreddit_type"] == "product")
    assert prod["sentiment_net"] == pytest.approx(prod["sentiment_pos"] - prod["sentiment_neg"])
    assert max(r["week"] for r in body) == "2025-09-22"


def test_missing_sentiment_is_null_not_nan(client):
    body = client.get("/reddit/sentiment/TSLA", params={"to": "2025-09-08"}).json()
    assert body and all(r["sentiment_pos"] is None and r["sentiment_net"] is None for r in body)


def test_top_posts_any_day_of_the_week_and_limit(client):
    r = client.get("/reddit/top-posts/AAPL", params={"week": "2025-09-17", "limit": 2})   # a Wednesday
    body = r.json()
    assert r.status_code == 200 and [p["rank"] for p in body] == [1, 2]
    assert body[0]["week"] == "2025-09-15" and body[0]["score"] == 900 and body[1]["subreddit_type"] == "investor"
    assert client.get("/reddit/top-posts/AAPL", params={"week": "2025-09-17", "limit": 11}).status_code == 422


def test_top_posts_refuses_holdout_weeks(client):
    r = client.get("/reddit/top-posts/AAPL", params={"week": "2025-10-01"})
    assert r.status_code == 404 and "holdout" in r.json()["detail"]


def test_loader_drops_holdout_rows_and_cache_reloads_after_ttl(monkeypatch):
    monkeypatch.setenv(reddit_data.DATA_URI_ENV, str(FIXTURES))
    monkeypatch.setattr(reddit_data, "_cache", {})
    first = get_reddit_data()
    assert str(first.weekly["week"].max()) == "2025-09-22"
    assert get_reddit_data() is first                       # within the TTL: same object
    monkeypatch.setattr(reddit_data, "CACHE_TTL_S", -1)
    assert get_reddit_data() is not first                   # expired: re-read


def test_missing_tables_give_503_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setenv(reddit_data.DATA_URI_ENV, str(tmp_path / "empty"))
    monkeypatch.setattr(reddit_data, "_cache", {})
    r = TestClient(app).get("/reddit/attention/AAPL")
    assert r.status_code == 503 and "not published" in r.json()["detail"]
