"""2016-2022 label pool and the Week 3 sentiment sample drawn from pool + corpus."""
import pandas as pd

from src.reddit import label_pool as lp
from src.reddit import label_samples as ls
from src.reddit.utils import write_json_gz


def _raw_day(sub, day, posts):
    return {"date": day, "status": "complete", "pages": [{"retrieved_at_utc": f"{day}T23:00:00Z",
                                                          "response": {"data": posts}}]}


def _p(pid, sub, ts, title, body=""):
    return {"id": pid, "subreddit": sub, "created_utc": ts, "title": title, "selftext": body, "score": 3,
            "num_comments": 1, "permalink": f"/r/{sub}/comments/{pid}/"}


def test_pool_build_matches_tickers_and_keeps_text(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "RAW_POOL", tmp_path / "raw")
    monkeypatch.setattr(lp, "POOL", tmp_path / "pool")
    monkeypatch.setattr(lp, "POOL_POSTS", tmp_path / "pool/posts.parquet")
    monkeypatch.setattr(lp, "POOL_MATCHES", tmp_path / "pool/matches.parquet")
    ts = 1497000000                                                     # 2017-06-09
    write_json_gz(tmp_path / "raw/iphone/2017-06-09.json.gz",
                  _raw_day("iphone", "2017-06-09", [_p("a", "iphone", ts, "Battery life is great")]))
    write_json_gz(tmp_path / "raw/stocks/2017-06-09.json.gz",
                  _raw_day("stocks", "2017-06-09", [_p("b", "stocks", ts + 5, "TSLA to the moon"),
                                                    _p("c", "stocks", ts + 9, "Index funds?")]))
    m = lp.build()
    assert sorted(zip(m["post_id"], m["ticker"], strict=True)) == [("a", "AAPL"), ("b", "TSLA")]
    assert m.set_index("post_id").loc["b", "title"] == "TSLA to the moon"
    assert set(m["day_status"]) == {"complete"} and set(m["period"]) == {"research"}


def test_pool_days_are_seeded_and_per_year():
    from datetime import date
    d1 = lp.pool_days(date(2016, 6, 1), date(2017, 12, 31), 3, 7)
    assert d1 == lp.pool_days(date(2016, 6, 1), date(2017, 12, 31), 3, 7) and len(d1) == 6
    assert {d.year for d in d1} == {2016, 2017} and min(d1) >= date(2016, 6, 1)


def _setup_draw(tmp_path, monkeypatch, corpus_title):
    from src.reddit import settings
    processed, posts_dir, val = tmp_path / "processed", tmp_path / "processed/posts", tmp_path / "validation"
    posts_dir.mkdir(parents=True)
    val.mkdir()
    cols = {"market": "US", "day_status": "complete", "removed_flag": False, "multi_ticker_list": False, "period": "research"}
    corpus = pd.DataFrame([dict(post_id=f"c{i}", ticker="AAPL", subreddit="iphone", subreddit_type="product",
                                date="2024-03-0" + str(i + 1), created_utc_iso="2024-03-01T00:00:00Z",
                                permalink=f"/c{i}", **cols) for i in range(4)])
    corpus.to_parquet(processed / "post_ticker_matches.parquet")
    pd.DataFrame({"id": corpus["post_id"], "title": corpus_title, "selftext": "", "permalink": "/x"}).to_parquet(
        posts_dir / "iphone.parquet")
    pool = pd.DataFrame([dict(post_id=f"p{i}", ticker="AAPL", subreddit="iphone", subreddit_type="product",
                              date="2017-05-0" + str(i + 1), created_utc_iso="2017-05-01T00:00:00Z",
                              title="pool title text here", selftext="", permalink=f"/p{i}", **cols) for i in range(4)])
    pool.to_parquet(tmp_path / "pool_matches.parquet")
    monkeypatch.setattr(settings, "PROCESSED", processed)
    monkeypatch.setattr(settings, "POSTS", posts_dir)
    monkeypatch.setattr(settings, "VALIDATION", val)
    monkeypatch.setattr(ls, "POOL_MATCHES", tmp_path / "pool_matches.parquet")
    monkeypatch.setattr(ls, "SENTIMENT_OUT", val / "sentiment_sample.csv")
    monkeypatch.setattr(ls, "SECOND_RATER_OUT", val / "sentiment_second_rater.csv")


def test_draw_uses_pool_text_and_two_year_buckets(tmp_path, monkeypatch):
    _setup_draw(tmp_path, monkeypatch, "corpus title text, long enough")
    out = ls.draw_sentiment(seed=1).set_index("post_id")
    assert out["core"].dtype == bool
    assert set(out["cell"]) == {"AAPL|reddit_product|2016-17", "AAPL|reddit_product|2024-25"}
    assert (out.loc[out.index.str.startswith("p"), "title"] == "pool title text here").all()
    assert (out.loc[out.index.str.startswith("c"), "title"] == "corpus title text, long enough").all()
    assert out["core"].sum() == 2 * ls.PER_CELL_CORE and len(out) == 2 * (ls.PER_CELL_CORE + ls.PER_CELL_RESERVE)



def test_a_cell_with_no_usable_posts_is_skipped_not_fatal(tmp_path, monkeypatch):
    _setup_draw(tmp_path, monkeypatch, "short")                  # every 2024 corpus post is too short
    out = ls.draw_sentiment(seed=1)
    assert set(out["cell"]) == {"AAPL|reddit_product|2016-17"} and out["core"].dtype == bool
