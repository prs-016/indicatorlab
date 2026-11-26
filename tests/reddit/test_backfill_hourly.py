"""Backfilling the hourly files from Arctic Shift listings (src/reddit/backfill_hourly.py), no network."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd

from src import storage
from src.reddit import backfill_hourly as bf
from src.reddit import on_demand
from src.reddit.pipeline import HOURLY_COLS, RAW_COLS

START, END = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 13, 5, tzinfo=UTC)


def _post(pid, sub, title, when):
    return {"id": pid, "subreddit": sub, "created_utc": int(datetime.fromisoformat(when).replace(tzinfo=UTC).timestamp()),
            "title": title, "selftext": "", "score": 5, "num_comments": 1, "permalink": f"/r/{sub}/comments/{pid}/",
            "author": "u", "all_awardings": [{"nested": "fields are dropped"}]}


class FakeArctic:
    """Plain listing: subreddit filter, exclusive after/before, oldest first, 100 a page."""

    def __init__(self, posts):
        self.posts, self.calls = sorted(posts, key=lambda p: p["created_utc"]), []

    def get(self, path, params):
        assert "query" not in params, "the backfill never uses keyword search"
        self.calls.append(params)
        data = [p for p in self.posts if p["subreddit"].lower() == params["subreddit"].lower()
                and params["after"] < p["created_utc"] < params["before"]]
        return SimpleNamespace(body={"data": data[:100]})


POSTS = [_post("a1", "iphone", "New iPhone case", "2026-11-03T10:00:00"),
         _post("s1", "stocks", "NVDA earnings run-up", "2026-11-03T11:00:00"),
         _post("s2", "stocks", "Market is boring", "2026-11-07T09:00:00"),
         _post("s3", "stocks", "Before the window", "2026-10-31T23:59:59"),
         _post("s4", "stocks", "After the window", "2026-11-13T05:00:00")]


def test_fetch_build_and_write_day_files(tmp_path):
    api = FakeArctic(POSTS)
    assert bf.fetch_subreddits(START, END, ["iphone", "stocks", "investing"], tmp_path / "ck", api) == []
    again = bf.fetch_subreddits(START, END, ["iphone", "stocks"], tmp_path / "ck", FakeArctic([]))
    assert again == []                                           # checkpoints exist: nothing fetched twice

    records = pd.concat([pd.read_parquet(p) for p in (tmp_path / "ck").glob("*.parquet")]).to_dict("records")
    raw, processed = bf.build_day_files(records, datetime(2026, 11, 26, tzinfo=UTC))
    assert sorted(raw) == ["2026-11-03", "2026-11-07"]          # s3 and s4 are outside [start, end)
    assert list(raw["2026-11-03"].columns) == RAW_COLS and list(processed["2026-11-03"].columns) == HOURLY_COLS
    assert sorted(zip(processed["2026-11-03"]["post_id"], processed["2026-11-03"]["ticker"], strict=True)) == [
        ("a1", "AAPL"), ("s1", "NVDA")]

    root = tmp_path / "root"
    paths = bf.write_day_files(str(root), raw, processed)
    assert len(paths) == 3 and paths[0].endswith("raw/reddit/date=2026-11-03/backfill.parquet")
    hourly = storage.read_parquet_dir(root / "processed/reddit_hourly/date=2026-11-03")
    assert hourly["sentiment_label"].isna().all() and str(hourly["sentiment_label"].dtype) in ("string", "object")


def test_backfilled_days_reach_on_demand_counts(tmp_path, monkeypatch):
    monkeypatch.setenv(on_demand.ROOT_ENV, str(tmp_path / "root"))
    monkeypatch.setenv(on_demand.POSTS_URI_ENV, str(tmp_path / "posts"))
    records = [{k: p.get(k) for k in bf.KEEP} for p in POSTS[:3]]
    bf.write_day_files(str(tmp_path / "root"), *bf.build_day_files(records, datetime(2026, 11, 26, tzinfo=UTC)))
    nvda = {"ticker": "NVDA", "market": "us", "short_name": "Nvidia", "aliases": [], "ambiguous_name": False,
            "subreddits": {"company": [], "market": ["stocks"]}}
    posts, missing = on_demand.saved_posts(["stocks"], START, datetime(2026, 11, 8, tzinfo=UTC),
                                           on_demand.search_terms(nvda))
    assert [p["id"] for p in posts] == ["s1"]
    assert "2026-11-03" not in missing and "2026-11-05" in missing
