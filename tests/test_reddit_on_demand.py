"""On-demand Reddit counts and spike-week posts (src/reddit/on_demand.py), no network and no model.

Arctic Shift is replaced by FakeArctic, which serves tests/fixtures/reddit_on_demand/posts.json and
filters like posts/search does: subreddit, case-insensitive keyword `query`, [after, before),
newest first, at most `limit` per page. FinBERT is replaced by FakeScorer with fixed probabilities.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.analyze import cache
from src.reddit import on_demand
from src.reddit.on_demand import reddit_spike_posts, reddit_weekly_counts, search_terms

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "reddit_on_demand" / "posts.json"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)          # a Wednesday: current week 2026-11-23, 3 days in


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp())


def stock(ticker="NVDA", **kw) -> dict:
    """A ResolvedStock in the Shared contracts shape."""
    base = {"ticker": ticker, "market": "us", "yf_symbol": ticker, "name": f"{ticker} Inc.", "short_name": ticker.title(),
            "aliases": [], "ambiguous_name": False, "wiki": {"en": None, "hi": None, "zh": None},
            "subreddits": {"company": [], "market": ["stocks", "investing", "wallstreetbets"]},
            "tracked": False, "source": "local_list"}
    base.update(kw)
    return base


NVDA = stock("NVDA", name="NVIDIA Corporation", short_name="Nvidia", aliases=["Nvidia", "NVIDIA", "$NVDA"],
             subreddits={"company": ["nvidia"], "market": ["stocks", "investing", "wallstreetbets"]})
AAPL = stock("AAPL", name="Apple Inc.", short_name="Apple", aliases=["Apple", "$AAPL"], ambiguous_name=True)


class FakeArctic:
    """Stands in for ArcticShiftClient: same `get(path, params)` call, records every call."""

    def __init__(self, posts: list[dict]):
        self.posts = posts
        self.calls: list[dict] = []
        self.n_requests = 0

    def get(self, path: str, params: dict):
        assert path == "posts/search"
        assert params["subreddit"] and params["query"], "query without subreddit is refused by the API"
        assert params["limit"] != "auto", "limit=auto is refused together with query"
        self.calls.append(dict(params))
        self.n_requests += 1
        word = re.compile(rf"(?<!\w){re.escape(params['query'])}(?!\w)", re.IGNORECASE)
        after, before = int(params["after"]), int(params["before"])
        hits = [dict(p) for p in self.posts
                if p["subreddit"].lower() == params["subreddit"].lower()
                and after <= p["created_utc"] < before
                and word.search(f"{p['title']} {p['selftext']}")]
        hits.sort(key=lambda p: -p["created_utc"])
        return SimpleNamespace(body={"data": hits[: int(params["limit"])]})


@pytest.fixture
def posts() -> list[dict]:
    return json.loads(FIXTURE.read_text())["posts"]


@pytest.fixture
def api(posts) -> FakeArctic:
    return FakeArctic(posts)


def by_week(result: dict) -> dict[str, int]:
    return {w["week"]: w["count"] for w in result["weeks"]}


# ----------------------------------------------------------------------------- J1 weekly counts
def test_nvda_gives_104_full_weeks_plus_current_with_no_gaps(api):
    out = reddit_weekly_counts(NVDA, now=NOW, client=api)
    weeks = out["weeks"]
    assert out["source"] == "reddit" and out["truncated"] is False
    assert len(weeks) == 105
    mondays = pd.to_datetime([w["week"] for w in weeks])
    assert (mondays.day_of_week == 0).all()
    assert (mondays.to_series().diff().dropna() == pd.Timedelta(days=7)).all()
    assert weeks[0]["week"] == "2024-11-25" and weeks[-1]["week"] == "2026-11-23"
    assert [w["days_covered"] for w in weeks[:-1]] == [7] * 104
    assert weeks[-1]["days_covered"] == 3                   # Mon, Tue and half of Wed, rounded up


def test_nvda_counts_match_the_fixture_by_hand(api):
    counts = by_week(reddit_weekly_counts(NVDA, now=NOW, client=api))
    # n01 Nvidia, n02 $NVDA, n03 "Nvidia" in the body of r/nvidia
    assert counts["2026-11-23"] == 3
    # n04 NVDA in body, n05, dup1 once; n10 never mentions it; n11 only has NVDAX and lower-case nvda
    assert counts["2026-11-16"] == 3
    assert counts["2025-01-06"] == 1                        # n07
    assert counts["2024-11-25"] == 1                        # n08 at exactly Monday 00:00; n09 is before the window
    assert sum(counts.values()) == 8


def test_ambiguous_name_skips_apple_the_fruit(api):
    counts = by_week(reddit_weekly_counts(AAPL, now=NOW, client=api))
    # a01 "Apple earnings", a02 AAPL in the title, a05 "Apple's guidance"; a03, a04, a06 are fruit
    assert counts["2026-11-16"] == 3
    assert sum(counts.values()) == 3


def test_ticker_with_no_posts_is_an_all_zero_series(api):
    out = reddit_weekly_counts(stock("ZZZZQ", short_name="Zzzzq"), now=NOW, client=api)
    assert len(out["weeks"]) == 105
    assert all(w["count"] == 0 for w in out["weeks"])


def test_duplicate_post_across_subreddits_counts_once(posts):
    dup = [p for p in posts if p["id"] == "dup1"]
    assert {p["subreddit"] for p in dup} == {"stocks", "investing"}
    out = reddit_weekly_counts(NVDA, now=NOW, client=FakeArctic(dup))
    assert by_week(out)["2026-11-16"] == 1


def test_tracked_ticker_reads_stored_weeks_and_only_fetches_the_rest(api, tmp_path, monkeypatch):
    stored_weeks = pd.date_range("2024-11-25", "2026-10-26", freq="7D")
    table = pd.DataFrame({"ticker": "NVDA", "market": "us", "source": "reddit",
                          "week": [w.date() for w in stored_weeks], "value": 5.0})
    other = table.assign(ticker="AMD", value=99.0)
    pd.concat([table, other]).to_parquet(tmp_path / "reddit_weekly.parquet")
    monkeypatch.setenv(on_demand.DATA_URI_ENV, str(tmp_path))

    counts = by_week(reddit_weekly_counts({**NVDA, "tracked": True}, now=NOW, client=api))

    assert counts["2024-11-25"] == 5 and counts["2026-10-26"] == 5   # stored values, not the fixture's n08
    assert (counts["2026-11-02"], counts["2026-11-09"], counts["2026-11-16"], counts["2026-11-23"]) == (0, 0, 3, 3)
    assert api.calls, "the four unstored weeks are fetched"
    assert min(int(c["after"]) for c in api.calls) >= ts("2026-11-02T00:00:00")   # never a stored week


def test_fetch_cap_sets_truncated_and_keeps_counts(api, monkeypatch):
    monkeypatch.setattr(on_demand, "MAX_COUNT_POSTS", 2)
    monkeypatch.setattr(on_demand, "PAGE_SIZE", 1)
    out = reddit_weekly_counts(NVDA, now=NOW, client=api)
    assert out["truncated"] is True
    assert 1 <= sum(w["count"] for w in out["weeks"]) <= 2


def test_counts_are_cached_for_six_hours(api, tmp_path, monkeypatch):
    monkeypatch.setenv(cache.CACHE_ENV, "local")
    monkeypatch.setattr(cache, "LOCAL_ROOT", tmp_path)
    first = reddit_weekly_counts(NVDA, client=api)
    assert (tmp_path / "analyze" / "reddit_counts" / "us" / "NVDA.json").exists()

    class Boom:
        def get(self, *a, **k):
            raise AssertionError("cache hit must not call the API")
    assert reddit_weekly_counts(NVDA, client=Boom()) == first


def test_search_terms_follow_the_rules():
    t = search_terms(NVDA)
    assert t.queries == ["NVDA", "Nvidia"]                       # NVIDIA and $NVDA fold into these
    on = search_terms(stock("ON", short_name="onsemi", aliases=["ON Semiconductor"]))
    assert not on.bare_ok and on.dollar_ok and "ON" not in on.queries   # common word: only $ON counts
    hk = search_terms(stock("0700", market="hk", short_name="Tencent", aliases=["TCEHY", "$TCEHY"]))
    assert not hk.dollar_ok and not hk.bare_ok and hk.queries == ["Tencent", "TCEHY"]
    assert search_terms(stock("RELIANCE.NS", market="in")).ticker == "RELIANCE"


# ----------------------------------------------------------------------------- J2 spike-week posts
class FakeScorer:
    """Fixed probabilities picked by a keyword in the text; records what it was asked to score."""

    RULES = (("printing", (0.9, 0.05, 0.05)), ("preview", (0.2, 0.6, 0.2)), ("driver", (0.1, 0.1, 0.8)))

    def __init__(self):
        self.texts: list[str] = []

    def score(self, texts):
        self.texts = list(texts)
        rows = []
        for t in texts:
            pos, neg, neu = next((p for k, p in self.RULES if k in t.lower()), (0.3, 0.3, 0.4))
            label = max((("positive", pos), ("negative", neg), ("neutral", neu)), key=lambda x: x[1])[0]
            rows.append({"sentiment_label": label, "sentiment_pos": pos, "sentiment_neg": neg, "sentiment_neu": neu})
        return pd.DataFrame(rows)


def test_spike_posts_rank_aggregate_and_assign_ids(api):
    scorer = FakeScorer()
    out = reddit_spike_posts(NVDA, "2026-11-23", now=NOW, client=api, scorer=scorer)
    assert [p["reddit_id"] for p in out["posts"]] == ["n01", "n02", "n03"]          # score 812, 640, 55
    assert [p["id"] for p in out["posts"]] == ["r1", "r2", "r3"]
    assert out["n_fetched"] == 3 and out["n_scored"] == 3
    assert out["sentiment"] == {"positive": 0.4, "negative": 0.25, "neutral": 0.35, "net": 0.15}
    assert out["label_counts"] == {"positive": 1, "negative": 1, "neutral": 1}
    assert out["top_positive"] == ["r2", "r1", "r3"]
    assert out["top_negative"] == ["r1", "r3", "r2"]
    p1 = out["posts"][0]
    assert p1["url"] == "https://www.reddit.com/r/stocks/comments/n01/"
    assert p1["label"] == "negative" and p1["probs"] == {"positive": 0.2, "negative": 0.6, "neutral": 0.2}


def make_posts(n: int, **kw) -> list[dict]:
    base = ts("2026-11-17T00:00:00")
    return [{"id": f"p{i:03d}", "subreddit": "stocks", "title": f"NVDA thread {i}", "selftext": "",
             "score": i, "num_comments": 0, "created_utc": base + 60 * i, **kw} for i in range(n)]


def test_spike_posts_keep_the_top_100_of_more(monkeypatch):
    api = FakeArctic(make_posts(150))
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=api, scorer=FakeScorer())
    assert out["n_fetched"] == 150 and out["n_scored"] == 100 and len(out["posts"]) == 100
    assert out["posts"][0]["reddit_id"] == "p149" and out["posts"][-1]["reddit_id"] == "p050"
    assert [p["id"] for p in out["posts"]] == [f"r{i}" for i in range(1, 101)]
    assert len(out["top_positive"]) == len(out["top_negative"]) == 5


def test_ties_on_score_break_on_comments():
    posts = make_posts(3, score=10)
    for p, nc in zip(posts, (5, 50, 20), strict=True):
        p["num_comments"] = nc
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=FakeArctic(posts), scorer=FakeScorer())
    assert [p["reddit_id"] for p in out["posts"]] == ["p001", "p002", "p000"]


def test_removed_body_is_dropped_but_title_kept():
    posts = make_posts(2)
    posts[0]["selftext"] = "[removed]"
    posts[1]["selftext"] = "Long thesis on NVDA margins."
    scorer = FakeScorer()
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=FakeArctic(posts), scorer=scorer)
    assert scorer.texts == ["NVDA thread 1\nLong thesis on NVDA margins.", "NVDA thread 0"]
    assert out["posts"][1]["body"] == ""


def test_week_with_no_posts_returns_empty_lists():
    class NeverScore:
        def score(self, texts):
            raise AssertionError("nothing to score")
    out = reddit_spike_posts(NVDA, "2025-06-02", now=NOW, client=FakeArctic([]), scorer=NeverScore())
    assert out["n_fetched"] == 0 and out["n_scored"] == 0
    assert out["posts"] == [] and out["top_positive"] == [] and out["top_negative"] == []
    assert out["label_counts"] == {"positive": 0, "negative": 0, "neutral": 0}
    assert all(v is None for v in out["sentiment"].values())


def test_spike_fetch_is_capped_at_1000(monkeypatch):
    monkeypatch.setattr(on_demand, "MAX_SPIKE_POSTS", 120)
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=FakeArctic(make_posts(300)), scorer=FakeScorer())
    assert out["truncated"] is True and out["n_fetched"] <= 120


# ----------------------------------------------------------------------------- cache helper
def test_cache_put_get_and_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv(cache.CACHE_ENV, "local")
    monkeypatch.setattr(cache, "LOCAL_ROOT", tmp_path)
    cache.cache_put("analyze/x/us/T.json", {"a": 1})
    assert cache.cache_get("analyze/x/us/T.json", max_age=60) == {"a": 1}
    assert cache.cache_get("analyze/x/us/T.json", max_age=None) == {"a": 1}
    assert cache.cache_get("analyze/missing.json", max_age=60) is None
    path = tmp_path / "analyze" / "x" / "us" / "T.json"
    entry = json.loads(path.read_text())
    entry["saved_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(entry))
    assert cache.cache_get("analyze/x/us/T.json", max_age=60) is None
    assert cache.cache_get("analyze/x/us/T.json", max_age=None) == {"a": 1}
