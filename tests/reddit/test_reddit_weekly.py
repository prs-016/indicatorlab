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
    monkeypatch.setattr(rw, "source_subreddits", lambda market="US", source_of_type=None: SUBS)
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


COMBINED_SUBS = {("AAPL", "reddit"): ["iphone", "hardware", "stocks"]}


def _sent():
    return pd.DataFrame({"post_id": ["p1", "p2", "p3", "p4"], "ticker": "AAPL",
                         "sentiment_label": ["positive", "negative", "neutral", "positive"],
                         "sentiment_score": [0.6, -0.7, 0.0, 0.5],
                         "sentiment_pos": [0.7, 0.1, 0.2, 0.6], "sentiment_neg": [0.1, 0.8, 0.2, 0.1],
                         "sentiment_neu": [0.2, 0.1, 0.6, 0.3]})


def test_attention_record_by_type_has_exact_shared_columns(monkeypatch):
    df = _build(monkeypatch, sentiment=_sent())
    rec = rw.attention_record(df, by_type=True)
    assert list(rec.columns) == rw.ATTENTION_COLS + ["subreddit_type"]
    assert set(rec["source"]) == {"reddit"} and set(rec["market"]) == {"us"}
    assert set(rec["subreddit_type"]) == {"investor", "product"}
    w1 = rec[rec["week"] == pd.Timestamp("2024-01-01").date()].set_index("subreddit_type")
    assert w1.loc["product", "value"] == 3 and w1.loc["investor", "value"] == 1
    assert w1.loc["product", "sentiment_pos"] == np.mean([0.7, 0.1, 0.2])
    assert w1.loc["product", "n_scored"] == 3


def test_combined_build_counts_every_subreddit_kind_once(monkeypatch):
    monkeypatch.setattr(rw, "source_subreddits", lambda market="US", source_of_type=None: COMBINED_SUBS)
    days = pd.date_range("2024-01-01", "2024-01-14", freq="D")
    df = rw.build(_matches(), _day_status(days), _sent(), source_of_type=rw.COMBINED_OF_TYPE)
    rec = rw.attention_record(df)
    assert list(rec.columns) == rw.ATTENTION_COLS
    w1 = rec[rec["week"] == pd.Timestamp("2024-01-01").date()].iloc[0]
    assert w1["value"] == 4 and w1["source"] == "reddit" and w1["n_scored"] == 4
    assert rec["spike"].dtype == bool


def test_top_posts_ranks_by_score_with_sentiment(monkeypatch):
    mt = _matches().assign(removed_flag=False, permalink="/r/x/1", score=[5, 50, 1, 20, 9])
    mt.loc[mt["post_id"] == "p3", "removed_flag"] = True
    monkeypatch.setattr(rw, "attach_text", lambda df, cols: df.assign(title="t:" + df["post_id"]))
    top = rw.top_posts(mt, _sent(), n=2)
    assert list(top.columns) == rw.TOP_POST_COLS
    w1 = top[top["week"] == pd.Timestamp("2024-01-01").date()]
    assert w1["post_id"].tolist() == ["p2", "p4"] and w1["rank"].tolist() == [1, 2]
    assert w1.iloc[0]["sentiment_label"] == "negative" and w1.iloc[0]["subreddit_type"] == "product"
    assert w1.iloc[1]["subreddit_type"] == "investor"
    assert "p3" not in set(top["post_id"])          # removed posts never show
