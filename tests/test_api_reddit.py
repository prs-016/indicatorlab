"""Reddit API endpoints, run with FastAPI's TestClient on a small fixture store."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import reddit
from src.api.main import app


def _store() -> reddit.RedditStore:
    weeks = ["2024-01-01", "2024-01-08", "2024-01-15"]
    att = pd.DataFrame({
        "week": weeks * 2, "ticker": "AAPL", "market": "US",
        "source": ["reddit_product"] * 3 + ["reddit_stock"] * 3,
        "posts": [100, 400, 120, 10, 12, 30], "comments": 5, "upvotes": 50,
        "sentiment_mean": [0.1, -0.4, np.nan, 0.0, 0.2, 0.3], "pct_positive": 0.3, "pct_negative": 0.2,
        "n_scored": [90, 380, 0, 9, 11, 28], "baseline": 100.0, "ratio": [1.0, 4.0, 1.2, 1.0, 1.1, 2.9],
        "rz": [0.1, 5.0, 0.3, 0.0, 0.2, 3.1], "spike": [False, True, False, False, False, True]})
    samples = pd.DataFrame({
        "week": "2024-01-08", "ticker": "AAPL", "source": "reddit_product", "rank": [1, 2, 3, 4],
        "post_id": ["a", "b", "c", "d"], "subreddit": "iphone", "title": ["t1", "t2", "t3", "t4"],
        "score": [900, 500, 300, 100], "num_comments": 10, "url": "https://www.reddit.com/x",
        "sentiment_label": "negative"})
    prices = pd.DataFrame({"week": weeks, "ticker": "AAPL", "ret": [0.01, -0.03, 0.02],
                           "ret_next1": [-0.03, 0.02, 0.01], "ret_next2": [-0.01, 0.03, np.nan],
                           "ret_next3": 0.0, "ret_next4": 0.0, "abn_ret": 0.0, "abn_ret_next1": 0.0,
                           "abn_ret_next2": 0.0, "abn_ret_next3": 0.0, "abn_ret_next4": 0.0})
    return reddit.RedditStore(att, samples, prices)


@pytest.fixture
def client():
    app.dependency_overrides[reddit.get_store] = _store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_sentiment_returns_weekly_rows_and_samples_for_spike_weeks(client):
    r = client.get("/sentiment", params={"ticker": "aapl", "start": "2024-01-01", "end": "2024-01-31"})
    assert r.status_code == 200
    body = r.json()
    prod = body["sources"]["reddit_product"]
    assert [w["week"] for w in prod] == ["2024-01-01", "2024-01-08", "2024-01-15"]
    spike_week = prod[1]
    assert spike_week["spike"] is True and [p["post_id"] for p in spike_week["sample_posts"]] == ["a", "b", "c"]
    assert "sample_posts" not in prod[0] and prod[2]["sentiment_mean"] is None   # NaN -> null
    assert len(body["sources"]["reddit_stock"]) == 3


def test_spikes_returns_only_flagged_weeks_with_forward_returns(client):
    r = client.get("/spikes", params={"ticker": "AAPL", "start": "2024-01-01", "end": "2024-01-31"})
    assert r.status_code == 200
    body = r.json()
    assert body["n_spikes"] == 2
    first = body["spikes"][0]
    assert first["week"] == "2024-01-08" and first["source"] == "reddit_product"
    assert first["ret_next1"] == 0.02 and first["ratio"] == 4.0


def test_source_filter_and_date_window(client):
    r = client.get("/spikes", params={"ticker": "AAPL", "start": "2024-01-10", "end": "2024-01-31",
                                      "source": "reddit_stock"})
    assert [s["week"] for s in r.json()["spikes"]] == ["2024-01-15"]


def test_unknown_ticker_is_404_and_bad_dates_are_422(client):
    assert client.get("/sentiment", params={"ticker": "ZZZZ", "start": "2024-01-01", "end": "2024-02-01"}).status_code == 404
    assert client.get("/spikes", params={"ticker": "AAPL", "start": "2024-13-01", "end": "2024-02-01"}).status_code == 422
    assert client.get("/spikes", params={"ticker": "AAPL", "start": "2024-03-01", "end": "2024-02-01"}).status_code == 422
