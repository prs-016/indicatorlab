"""Weekly attention table: completeness, source split, sentiment columns and the holdout split."""
import numpy as np
import pandas as pd

from src.reddit import reddit_weekly as rw

SUBS = {("AAPL", "reddit_product"): ["iphone", "hardware"], ("AAPL", "reddit_stock"): ["stocks"]}


def _day_status(days, failed=()):
    return pd.DataFrame([{"subreddit": s, "date": d.strftime("%Y-%m-%d"),
                          "day_status": "failed" if (s, d.strftime("%Y-%m-%d")) in failed else "complete"}
                         for s in ("iphone", "hardware", "stocks") for d in days])


def _matches():
    rows = [("p1", "iphone", "product", "2024-01-01"), ("p2", "iphone", "product", "2024-01-02"),
            ("p3", "hardware", "sector", "2024-01-03"), ("p4", "stocks", "general", "2024-01-04"),
            ("p5", "iphone", "product", "2024-01-09")]
    return pd.DataFrame([{"post_id": p, "ticker": "AAPL", "subreddit": s, "subreddit_type": t, "date": d,
                          "score": 10, "num_comments": 2} for p, s, t, d in rows])


def _build(monkeypatch, failed=(), sentiment=None):
    monkeypatch.setattr(rw, "source_subreddits", lambda market="US": SUBS)
    days = pd.date_range("2024-01-01", "2024-01-14", freq="D")
    return rw.build(_matches(), _day_status(days, failed), sentiment)


def test_sector_posts_count_as_product_and_general_as_stock(monkeypatch):
    df = _build(monkeypatch)
    w1 = df[df["week"] == pd.Timestamp("2024-01-01", tz="UTC")].set_index("source")
    assert w1.loc["reddit_product", "posts"] == 3 and w1.loc["reddit_stock", "posts"] == 1
    assert (df["week"].dt.day_of_week == 0).all() and set(df["market"]) == {"US"}


def test_one_failed_day_blanks_only_that_source_week(monkeypatch):
    df = _build(monkeypatch, failed={("hardware", "2024-01-10")})
    w2 = df[df["week"] == pd.Timestamp("2024-01-08", tz="UTC")].set_index("source")
    assert np.isnan(w2.loc["reddit_product", "posts"]) and not w2.loc["reddit_product", "coverage_complete"]
    assert w2.loc["reddit_stock", "posts"] == 0 and w2.loc["reddit_stock", "coverage_complete"]   # 0 is real


def test_sentiment_columns(monkeypatch):
    sent = pd.DataFrame({"post_id": ["p1", "p2", "p3"], "ticker": "AAPL",
                         "sentiment_label": ["positive", "negative", "positive"], "sentiment_score": [1.0, -1.0, 0.5]})
    w1 = _build(monkeypatch, sentiment=sent).set_index(["week", "source"]).loc[
        (pd.Timestamp("2024-01-01", tz="UTC"), "reddit_product")]
    assert w1["n_scored"] == 3 and np.isclose(w1["sentiment_mean"], 0.5 / 3)
    assert np.isclose(w1["pct_positive"], 2 / 3) and np.isclose(w1["pct_negative"], 1 / 3)


def test_holdout_split_keeps_whole_weeks_before_oct_1_2025():
    weeks = pd.date_range("2025-09-15", periods=4, freq="7D", tz="UTC")   # Sep 15, 22, 29, Oct 6
    research, recent = rw.split_holdout(pd.DataFrame({"week": weeks}))
    assert research["week"].dt.strftime("%m-%d").tolist() == ["09-15", "09-22"]
    assert recent["week"].dt.strftime("%m-%d").tolist() == ["09-29", "10-06"]   # Sep 29 week holds Oct 1-5
