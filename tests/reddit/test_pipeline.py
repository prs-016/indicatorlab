"""AWS pipeline modes against a local folder: hourly fetch/score/write, dedupe, the current table, week math."""
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from src import storage
from src.reddit import pipeline as pl
from src.sentiment import finbert_scorer as fs

NOW = datetime(2026, 11, 11, 15, 30, tzinfo=UTC)          # a Wednesday


def _post(pid, sub, title, ts, body=""):
    return {"id": pid, "subreddit": sub, "created_utc": ts, "title": title, "selftext": body, "score": 5,
            "num_comments": 1, "permalink": f"/r/{sub}/comments/{pid}/", "author": "u"}


class FakeArctic:
    """Returns the given posts for their subreddit, filtered to the requested window."""

    def __init__(self, posts):
        self.posts, self.calls = posts, []

    def get(self, path, params):
        self.calls.append(params)
        data = [p for p in self.posts if p["subreddit"].lower() == params["subreddit"].lower()
                and params["after"] < p["created_utc"] < params["before"]]
        return SimpleNamespace(body={"data": data})


@pytest.fixture(autouse=True)
def fake_finbert(monkeypatch):
    def clf(texts, **kw):
        return [[{"label": "positive", "score": 0.7}, {"label": "negative", "score": 0.2},
                 {"label": "neutral", "score": 0.1}] for _ in texts]
    monkeypatch.setattr(fs, "_classifier", lambda *a, **k: clf)


def test_hourly_writes_raw_scored_current_and_state_then_dedupes(tmp_path, capsys):
    ts = int(NOW.timestamp()) - 600
    posts = [_post("a1", "iphone", "Love the new iPhone", ts), _post("s1", "stocks", "TSLA puts printing", ts + 5),
             _post("s2", "stocks", "Market is boring", ts + 9)]
    root = str(tmp_path)
    out = pl.hourly(root, NOW, FakeArctic(posts))
    assert out["new_posts"] == 3 and out["failed_subreddits"] == []
    raw = storage.read_parquet(tmp_path / "raw/reddit/date=2026-11-11/1530.parquet")
    assert set(raw["id"]) == {"a1", "s1", "s2"}
    hourly = storage.read_parquet_dir(tmp_path / "processed/reddit_hourly/date=2026-11-11")
    assert sorted(zip(hourly["post_id"], hourly["ticker"], strict=True)) == [("a1", "AAPL"), ("s1", "TSLA")]
    assert hourly["sentiment_pos"].eq(0.7).all() and set(hourly["market"]) == {"us"}
    cur = storage.read_parquet(tmp_path / "processed/reddit_current.parquet").set_index("ticker")
    assert list(cur.reset_index().columns) == pl.CURRENT_COLS
    assert cur.loc["AAPL", "value"] == 1 and cur.loc["TSLA", "value_trailing_7d"] == 1 and cur.loc["MSFT", "value"] == 0
    assert str(cur.loc["AAPL", "week"]) == "2026-11-09" and cur.loc["AAPL", "source"] == "reddit"
    state = storage.read_json(tmp_path / "raw/reddit/_state.json")
    assert state["hwm"]["stocks"] == ts + 9 and state["hwm"]["iphone"] == ts
    assert '"PostsFetched": 3' in capsys.readouterr().out

    again = pl.hourly(root, NOW.replace(minute=45), FakeArctic(posts))   # overlap window re-sees them
    assert again["new_posts"] == 0


def test_build_current_ratio_uses_trailing_week_against_baseline():
    weeks = pd.date_range("2026-08-03", periods=14, freq="7D")            # full weeks before 2026-11-09
    hist = pd.DataFrame({"ticker": "AAPL", "week": weeks.date, "value": 10.0})
    ts = int(NOW.timestamp())
    rows = pd.DataFrame({"post_id": [f"p{i}" for i in range(31)], "ticker": "AAPL",
                         "created_utc": [ts - 3600 * (i + 1) for i in range(31)], "sentiment_pos": 0.6,
                         "sentiment_neg": 0.3, "sentiment_neu": 0.1})
    cur = pl.build_current(rows, hist, NOW).set_index("ticker")
    assert cur.loc["AAPL", "baseline"] == 10 and cur.loc["AAPL", "value_trailing_7d"] == 31
    assert cur.loc["AAPL", "ratio"] == pytest.approx(32 / 11)
    assert cur.loc["AAPL", "value"] == 31                                # all within this week (Mon-Wed)
    assert cur.loc["TSLA", "value"] == 0 and pd.isna(cur.loc["TSLA", "baseline"])


def test_last_full_week_is_the_monday_to_sunday_before_this_week():
    assert pl.last_full_week(date(2026, 11, 9)) == (date(2026, 11, 2), date(2026, 11, 8))     # a Monday
    assert pl.last_full_week(date(2026, 11, 15)) == (date(2026, 11, 2), date(2026, 11, 8))    # a Sunday


def test_root_uri_from_bucket(monkeypatch):
    monkeypatch.delenv(pl.ROOT_ENV, raising=False)
    monkeypatch.setenv(pl.BUCKET_ENV, "indicatorlab-data")
    assert pl.root_uri() == "s3://indicatorlab-data"
    monkeypatch.setenv(pl.ROOT_ENV, "/tmp/x/")
    assert pl.root_uri() == "/tmp/x"


def test_hourly_with_only_unmatched_posts_still_writes_current(tmp_path):
    ts = int(NOW.timestamp()) - 600
    out = pl.hourly(str(tmp_path), NOW, FakeArctic([_post("s9", "stocks", "Market is boring", ts)]))
    assert out["new_posts"] == 1
    assert storage.exists(tmp_path / "processed/reddit_current.parquet")
    assert not storage.exists(tmp_path / "processed/reddit_hourly")


def test_weekly_pulls_state_runs_steps_pushes_only_changes_and_publishes(tmp_path, monkeypatch):
    import os
    import time as _time

    from src.reddit import build_posts, collect_reddit, match_tickers, reddit_weekly, score_posts, settings

    root, work = tmp_path / "s3", tmp_path / "work"
    storage.write_json({"keep": 1}, root / "raw/reddit/arctic_shift/stocks/2026/2026-11-02.json")
    storage.write_parquet(pd.DataFrame({"x": [1]}), root / "processed/reddit_state/posts/stocks.parquet")
    (root / "raw/reddit").mkdir(parents=True, exist_ok=True)
    (root / "raw/reddit/manifest.csv").write_text("subreddit,date,status\n")
    monkeypatch.setattr(settings, "RAW_ARCTIC", work / "raw/arctic_shift")
    monkeypatch.setattr(settings, "MANIFEST", work / "raw/manifest.csv")
    monkeypatch.setattr(settings, "PROCESSED", work / "processed")
    calls = []
    monkeypatch.setattr(collect_reddit, "run_collect", lambda args: calls.append(("collect", args.start, args.end)))
    monkeypatch.setattr(build_posts, "build", lambda: calls.append("build"))
    monkeypatch.setattr(match_tickers, "run", lambda: calls.append("match"))
    monkeypatch.setattr(score_posts, "run", lambda *a, **k: calls.append(("score", a, k.get("rescore"))))

    def fake_weekly_run():
        calls.append("weekly")
        storage.write_parquet(pd.DataFrame({"week": [date(2026, 11, 2)]}), work / "processed/reddit_weekly.parquet")
        storage.write_parquet(pd.DataFrame({"x": [2]}), work / "processed/posts/stocks.parquet")
    monkeypatch.setattr(reddit_weekly, "run", fake_weekly_run)
    old = _time.time() - 1000            # downloaded files look old, as if unchanged
    real_copy = storage.copy_tree

    def copy_and_age(src, dst, newer_than=None):
        n = real_copy(src, dst, newer_than)
        if str(dst).startswith(str(work)):
            for f in work.rglob("*"):
                os.utime(f, (old, old))
        return n
    monkeypatch.setattr(storage, "copy_tree", copy_and_age)

    out = pl.weekly(str(root), today=date(2026, 11, 9))
    assert calls[0] == ("collect", "2026-11-02", "2026-11-08") and calls[1:3] == ["build", "match"]
    assert calls[3][2] is True and calls[4] == "weekly"
    assert (work / "raw/arctic_shift/stocks/2026/2026-11-02.json").exists()      # state pulled down
    assert storage.read_parquet(root / "processed/reddit_state/posts/stocks.parquet")["x"].tolist() == [2]
    assert out["published"] == ["reddit_weekly.parquet"]
    assert storage.exists(root / "processed/reddit_weekly.parquet")
    assert out["state_files_pushed"] == 1                                        # only the rewritten file
