"""On-demand Reddit counts and spike-week posts (src/reddit/on_demand.py), no network and no model.

Each test gets its own temporary data folder. Fixture posts of the subreddits we save (config.yaml's
US subreddit map) are written there: posts created before Nov 1, 2026 to the corpus
(posts/<subreddit>.parquet), later ones to the hourly files (root/raw/reddit/date=.../0000.parquet).
Posts of other subreddits (r/StockMarket here) are only reachable through FakeArctic, which filters
like posts/search (subreddit, case-insensitive keyword `query`, [after, before), sort, `limit`) and
answers posts/ids. FinBERT is replaced by FakeScorer with fixed probabilities.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src import storage
from src.analyze import cache
from src.reddit import on_demand
from src.reddit.arctic_client import ArcticShiftClient, ArcticShiftError
from src.reddit.on_demand import (
    POST_COLS,
    reddit_spike_posts,
    reddit_weekly_counts,
    search_terms,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "reddit_on_demand" / "posts.json"
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)          # a Wednesday: current week 2026-11-23, 3 days in
SAVED = on_demand.saved_subreddits()
BACKUP = ["StockMarket", "options", "ValueInvesting"]   # NVDA's subreddits that are not saved


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp())


CUT = ts("2026-11-01T00:00:00")


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
    """Stands in for ArcticShiftClient: same `get(path, params)` call, records every call.

    `fail(path, params)` -> True makes that call raise like exhausted retries. `fail_after` makes every
    call after that many successful keyword searches fail. `scores` overrides posts/ids answers.
    """

    def __init__(self, posts: list[dict], fail=None, fail_after: int | None = None, scores: dict | None = None):
        self.posts = posts
        self.fail = fail or (lambda path, params: False)
        self.fail_after = fail_after
        self.scores = scores or {}
        self.calls: list[dict] = []
        self.n_requests = 0
        self.searches_ok = 0

    def get(self, path: str, params: dict):
        self.calls.append({"path": path, **params})
        self.n_requests += 1
        if self.fail(path, params) or (self.fail_after is not None and self.searches_ok >= self.fail_after):
            raise ArcticShiftError("Timeout. Maybe slow down a bit", [])
        if path == "posts/ids":
            by_id = {p["id"]: p for p in self.posts}
            data = [{"id": i, **self.scores.get(i, {"score": by_id[i]["score"], "num_comments": by_id[i]["num_comments"]})}
                    for i in params["ids"].split(",") if i in by_id]
            return SimpleNamespace(body={"data": data})
        assert path == "posts/search"
        assert params["subreddit"] and params["query"], "query without subreddit is refused by the API"
        assert params["limit"] != "auto", "limit=auto is refused together with query"
        assert params["subreddit"].lower() not in SAVED, "saved subreddits are never searched"
        self.searches_ok += 1
        word = re.compile(rf"(?<!\w){re.escape(params['query'])}(?!\w)", re.IGNORECASE)
        after, before = int(params["after"]), int(params["before"])
        hits = [dict(p) for p in self.posts
                if p["subreddit"].lower() == params["subreddit"].lower()
                and after <= p["created_utc"] < before
                and word.search(f"{p['title']} {p['selftext']}")]
        hits.sort(key=lambda p: p["created_utc"], reverse=params["sort"] == "desc")
        return SimpleNamespace(body={"data": hits[: int(params["limit"])]})

    def searches(self, sub: str | None = None, query: str | None = None) -> list[dict]:
        return [c for c in self.calls if c["path"] == "posts/search"
                and (sub is None or c["subreddit"] == sub) and (query is None or c["query"] == query)]


class Boom:
    n_requests = 0

    def get(self, *a, **k):
        raise AssertionError("must not call the API")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch) -> Path:
    """Every test gets its own data root, saved-post folder, stored tables and local cache."""
    monkeypatch.setenv(on_demand.ROOT_ENV, str(tmp_path / "root"))
    monkeypatch.setenv(on_demand.POSTS_URI_ENV, str(tmp_path / "posts"))
    monkeypatch.setenv(on_demand.MATCHES_URI_ENV, str(tmp_path / "matches.parquet"))
    monkeypatch.setenv(on_demand.DATA_URI_ENV, str(tmp_path / "processed"))
    monkeypatch.setenv(cache.CACHE_ENV, "local")
    monkeypatch.setattr(cache, "LOCAL_ROOT", tmp_path / "cache")
    return tmp_path


def save_posts(root: Path, posts: list[dict]) -> None:
    """Write the posts of saved subreddits as corpus files (before Nov 1) or hourly files (after)."""
    corpus, hourly = defaultdict(list), defaultdict(list)
    for p in posts:
        if p["subreddit"].lower() not in SAVED:
            continue
        if p["created_utc"] < CUT:
            corpus[p["subreddit"].lower()].append(p)
        else:
            hourly[datetime.fromtimestamp(p["created_utc"], UTC).date()].append(p)
    for sub, ps in corpus.items():
        storage.write_parquet(pd.DataFrame(ps)[POST_COLS], root / "posts" / f"{sub}.parquet")
    for d, ps in hourly.items():
        storage.write_parquet(pd.DataFrame(ps)[POST_COLS], root / "root" / "raw" / "reddit" / f"date={d}" / "0000.parquet")


def setup(root: Path, posts: list[dict], **kw) -> FakeArctic:
    save_posts(root, posts)
    return FakeArctic(posts, **kw)


@pytest.fixture
def posts() -> list[dict]:
    return json.loads(FIXTURE.read_text())["posts"]


@pytest.fixture
def api(isolated, posts) -> FakeArctic:
    return setup(isolated, posts)


def by_week(result: dict) -> dict[str, int]:
    return {w["week"]: w["count"] for w in result["weeks"]}


def make_posts(n: int, start: str = "2026-11-17T00:00:00", **kw) -> list[dict]:
    base = ts(start)
    return [{"id": f"p{i:03d}", "subreddit": "stocks", "title": f"NVDA thread {i}", "selftext": "",
             "score": i, "num_comments": 0, "created_utc": base + 60 * i, **kw} for i in range(n)]


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
    out = reddit_weekly_counts(NVDA, now=NOW, client=api)
    counts = by_week(out)
    # hourly files: n01 Nvidia, n02 $NVDA, n03 "Nvidia" in the body of r/nvidia
    assert counts["2026-11-23"] == 3
    # hourly files: n04 NVDA in body, n05, dup1 once; n10 never mentions it; n11 only has NVDAX and lower-case nvda
    assert counts["2026-11-16"] == 3
    assert counts["2025-01-06"] == 1                        # n07, saved corpus
    assert counts["2024-11-25"] == 1                        # n08, r/StockMarket via keyword search, at Monday 00:00
    assert sum(counts.values()) == 8                        # n09 (r/stocks) is one second before the window
    assert out["coverage"]["saved"] == ["nvidia", "stocks", "investing", "wallstreetbets"]
    assert out["coverage"]["searched"] == BACKUP and out["coverage"]["skipped"] == []


def test_only_unsaved_subreddits_go_to_keyword_search(api):
    reddit_weekly_counts(NVDA, now=NOW, client=api)
    assert {c["subreddit"] for c in api.searches()} == set(BACKUP)   # FakeArctic also asserts it per call


def test_ambiguous_name_skips_apple_the_fruit(api):
    counts = by_week(reddit_weekly_counts(AAPL, now=NOW, client=api))
    # a01 "Apple earnings", a02 AAPL in the title, a05 "Apple's guidance"; a03, a04, a06 are fruit
    assert counts["2026-11-16"] == 3
    assert sum(counts.values()) == 3


def test_ticker_with_no_posts_is_an_all_zero_series(api):
    out = reddit_weekly_counts(stock("ZZZZQ", short_name="Zzzzq"), now=NOW, client=api)
    assert len(out["weeks"]) == 105
    assert all(w["count"] == 0 for w in out["weeks"])


def test_duplicate_post_across_subreddits_counts_once(isolated, posts):
    dup = [p for p in posts if p["id"] == "dup1"]
    assert {p["subreddit"] for p in dup} == {"stocks", "investing"}
    out = reddit_weekly_counts(NVDA, now=NOW, client=setup(isolated, dup))
    assert by_week(out)["2026-11-16"] == 1


def test_unfinished_backup_subreddit_is_skipped_not_half_counted(isolated, posts):
    api = setup(isolated, posts, fail=lambda path, p: p.get("subreddit") == "StockMarket")
    out = reddit_weekly_counts(NVDA, now=NOW, client=api)
    assert out["coverage"]["skipped"] == ["StockMarket"]
    assert out["coverage"]["searched"] == ["options", "ValueInvesting"]
    assert by_week(out)["2024-11-25"] == 0 and sum(by_week(out).values()) == 7      # n08 left out


def test_out_of_time_skips_the_backup_but_keeps_saved_counts(api, monkeypatch):
    monkeypatch.setattr(on_demand, "COUNTS_BACKUP_S", 0.0)
    out = reddit_weekly_counts(NVDA, now=NOW, client=api)
    assert api.calls == []
    assert out["coverage"]["skipped"] == BACKUP and out["coverage"]["searched"] == []
    assert sum(by_week(out).values()) == 7


def test_tracked_stock_missing_from_the_stored_table_is_matched_instead(api):
    # e.g. an India stock on Jamal's list: tracked, but our stored weekly table is US only
    out = reddit_weekly_counts({**NVDA, "tracked": True}, now=NOW, client=api)
    assert sum(by_week(out).values()) == 8 and out["coverage"]["searched"] == BACKUP


def test_keyword_search_resumes_from_the_cache(isolated, monkeypatch):
    monkeypatch.setattr(on_demand, "PAGE_SIZE", 10)
    market = make_posts(25, start="2026-03-02T00:00:00", subreddit="StockMarket")

    first = setup(isolated, market, fail_after=2)              # two pages, then Arctic Shift refuses
    out = reddit_weekly_counts(NVDA, now=NOW, client=first)
    assert "StockMarket" in out["coverage"]["skipped"]
    assert sum(by_week(out).values()) == 0                    # the 20 fetched posts are not half-counted

    second = FakeArctic(market)
    out = reddit_weekly_counts(NVDA, now=NOW, client=second)
    assert out["coverage"]["skipped"] == [] and sum(by_week(out).values()) == 25
    assert len(second.searches("StockMarket", "NVDA")) == 1   # only the 5 older posts were left to fetch

    third = FakeArctic(market)
    assert reddit_weekly_counts(NVDA, now=NOW, client=third) == out
    assert third.calls == []                                  # everything came from the cache


class RateLimitedSession:
    """requests.Session stand-in that always answers Arctic Shift's rate-limit reply."""

    def __init__(self):
        self.headers: dict = {}
        self.n = 0

    def get(self, url, params=None, timeout=None):
        self.n += 1
        return SimpleNamespace(status_code=422, headers={"X-RateLimit-Reset": "50"},
                               text='{"data":null,"error":"Timeout. Maybe slow down a bit"}')


def test_a_reset_past_the_time_limit_stops_every_later_keyword_call():
    session = RateLimitedSession()
    dl = on_demand._Deadline(10.0)
    client = ArcticShiftClient(min_interval=0, max_attempts=3, session=session, sleep=dl.sleep)
    out = on_demand.keyword_backup(search_terms(NVDA), BACKUP, datetime(2026, 1, 5, tzinfo=UTC), NOW,
                                   on_demand._Budget(100), dl, client, datetime(2024, 11, 25, tzinfo=UTC))
    assert session.n == 1                                     # the 50 s reset doesn't fit in 10 s: stop
    assert out.skipped == BACKUP and out.searched == [] and dl.blocked


def test_tracked_ticker_uses_stored_weeks_then_the_same_match_rows(isolated):
    stored_weeks = pd.date_range("2024-11-25", "2026-10-26", freq="7D")
    table = pd.DataFrame({"ticker": "NVDA", "market": "us", "source": "reddit",
                          "week": [w.date() for w in stored_weeks], "value": 5.0})
    table.loc[table["week"] == pd.Timestamp("2026-10-26").date(), "value"] = float("nan")   # straddles the cutoff
    other = table.assign(ticker="AMD", value=99.0)
    storage.write_parquet(pd.concat([table, other]), isolated / "processed" / "reddit_weekly.parquet")
    storage.write_parquet(pd.DataFrame({"post_id": ["m1", "m2", "m3"], "ticker": ["NVDA", "NVDA", "AMD"],
                                        "created_utc": [ts("2026-10-27T10:00:00"), ts("2026-10-30T10:00:00"),
                                                        ts("2026-10-28T10:00:00")]}), isolated / "matches.parquet")
    hourly = isolated / "root" / "processed" / "reddit_hourly"
    storage.write_parquet(pd.DataFrame({"post_id": ["h1", "h2", "h2", "h3"], "ticker": ["NVDA", "NVDA", "NVDA", "AMD"],
                                        "created_utc": [ts("2026-11-03T01:00:00")] * 4}),
                          hourly / "date=2026-11-03" / "0100.parquet")
    storage.write_parquet(pd.DataFrame({"post_id": ["h4"], "ticker": ["NVDA"],
                                        "created_utc": [ts("2026-11-24T09:00:00")]}),
                          hourly / "date=2026-11-24" / "0900.parquet")

    out = reddit_weekly_counts({**NVDA, "tracked": True}, now=NOW, client=Boom())
    counts = by_week(out)
    assert counts["2024-11-25"] == 5 and counts["2026-10-19"] == 5     # stored values
    assert counts["2026-10-26"] == 2                                   # m1, m2 from post_ticker_matches
    assert (counts["2026-11-02"], counts["2026-11-09"], counts["2026-11-16"], counts["2026-11-23"]) == (2, 0, 0, 1)
    assert "nvidia" in out["coverage"]["saved"] and out["coverage"]["skipped"] == []
    assert "2026-11-05" in out["coverage"]["missing_days"] and "2026-11-03" not in out["coverage"]["missing_days"]


def test_fetch_cap_sets_truncated_and_skips_that_subreddit(isolated, posts, monkeypatch):
    monkeypatch.setattr(on_demand, "MAX_COUNT_POSTS", 2)
    monkeypatch.setattr(on_demand, "PAGE_SIZE", 1)
    api = setup(isolated, posts + make_posts(3, start="2026-06-01T00:00:00", subreddit="StockMarket"))
    out = reddit_weekly_counts(NVDA, now=NOW, client=api)
    assert out["truncated"] is True and "StockMarket" in out["coverage"]["skipped"]
    assert sum(by_week(out).values()) == 7                    # the saved posts are all still counted


def test_days_without_saved_posts_are_reported(isolated):
    days = pd.date_range("2026-11-01 12:00", "2026-11-25 06:00", freq="D", tz="UTC")
    filler = [{"id": f"f{i}", "subreddit": "stocks", "title": "Market wrap", "selftext": "", "score": 1,
               "num_comments": 0, "created_utc": int(d.timestamp())} for i, d in enumerate(days) if d.day != 5]
    out = reddit_weekly_counts(NVDA, now=NOW, client=setup(isolated, filler))
    assert out["coverage"]["missing_days"] == ["2026-11-05"]   # today (Nov 25) is not a full day yet


def test_counts_are_cached_for_six_hours(api, isolated):
    first = reddit_weekly_counts(NVDA, client=api)
    assert (isolated / "cache" / "analyze" / "reddit_counts" / "us" / "NVDA.json").exists()
    assert reddit_weekly_counts(NVDA, client=Boom()) == first


def test_partial_counts_are_retried_after_30_minutes(isolated, posts):
    failing = setup(isolated, posts, fail=lambda path, p: p.get("subreddit") == "StockMarket")
    assert reddit_weekly_counts(NVDA, client=failing)["coverage"]["skipped"] == ["StockMarket"]
    assert reddit_weekly_counts(NVDA, client=Boom())["coverage"]["skipped"] == ["StockMarket"]   # < 30 min: cached
    path = isolated / "cache" / "analyze" / "reddit_counts" / "us" / "NVDA.json"
    entry = json.loads(path.read_text())
    entry["saved_at"] = (datetime.now(UTC) - pd.Timedelta(hours=1)).isoformat()
    path.write_text(json.dumps(entry))
    assert reddit_weekly_counts(NVDA, client=FakeArctic(posts))["coverage"]["skipped"] == []


def test_search_terms_follow_the_rules():
    t = search_terms(NVDA)
    assert t.queries == ["NVDA", "Nvidia"]                       # NVIDIA and $NVDA fold into these
    on = search_terms(stock("ON", short_name="onsemi", aliases=["ON Semiconductor"]))
    assert not on.bare_ok and on.dollar_ok and "ON" not in on.queries   # common word: only $ON counts
    hk = search_terms(stock("0700", market="hk", short_name="Tencent", aliases=["TCEHY", "$TCEHY"]))
    assert not hk.dollar_ok and not hk.bare_ok and hk.queries == ["Tencent", "TCEHY"]
    assert hk.needles == ["Tencent", "TCEHY"]                    # "0700" is never looked for in text
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
    out = reddit_spike_posts(NVDA, "2026-11-23", now=NOW, client=api, scorer=FakeScorer())
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
    assert out["coverage"]["scores_refreshed"] is True and out["coverage"]["searched"] == BACKUP


def test_hourly_scores_are_refreshed_before_ranking(isolated):
    posts = make_posts(3, score=1)                            # read within the hour: score still 1
    api = setup(isolated, posts, scores={"p000": {"score": 5, "num_comments": 1}, "p001": {"score": 50, "num_comments": 9},
                                         "p002": {"score": 20, "num_comments": 4}})
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=api, scorer=FakeScorer())
    assert [(p["reddit_id"], p["score"]) for p in out["posts"]] == [("p001", 50), ("p002", 20), ("p000", 5)]
    paths = [c["path"] for c in api.calls]
    assert paths[0] == "posts/ids" and "posts/search" in paths  # refresh first, then the keyword backup


def test_failed_score_refresh_keeps_the_posts(isolated):
    api = setup(isolated, make_posts(3), fail=lambda path, p: path == "posts/ids")
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=api, scorer=FakeScorer())
    assert out["coverage"]["scores_refreshed"] is False and len(out["posts"]) == 3


def test_corpus_week_keeps_its_saved_scores(api):
    out = reddit_spike_posts(NVDA, "2025-01-06", now=NOW, client=api, scorer=FakeScorer())
    assert [p["reddit_id"] for p in out["posts"]] == ["n07"]
    assert not [c for c in api.calls if c["path"] == "posts/ids"]


def test_spike_posts_keep_the_top_100_of_more(isolated):
    api = setup(isolated, make_posts(150))
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=api, scorer=FakeScorer())
    assert out["n_fetched"] == 150 and out["n_scored"] == 100 and len(out["posts"]) == 100
    assert out["posts"][0]["reddit_id"] == "p149" and out["posts"][-1]["reddit_id"] == "p050"
    assert [p["id"] for p in out["posts"]] == [f"r{i}" for i in range(1, 101)]
    assert len(out["top_positive"]) == len(out["top_negative"]) == 5


def test_ties_on_score_break_on_comments(isolated):
    posts = make_posts(3, score=10)
    for p, nc in zip(posts, (5, 50, 20), strict=True):
        p["num_comments"] = nc
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=setup(isolated, posts), scorer=FakeScorer())
    assert [p["reddit_id"] for p in out["posts"]] == ["p001", "p002", "p000"]


def test_removed_body_is_dropped_but_title_kept(isolated):
    posts = make_posts(2)
    posts[0]["selftext"] = "[removed]"
    posts[1]["selftext"] = "Long thesis on NVDA margins."
    scorer = FakeScorer()
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=setup(isolated, posts), scorer=scorer)
    assert scorer.texts == ["NVDA thread 1\nLong thesis on NVDA margins.", "NVDA thread 0"]
    assert out["posts"][1]["body"] == ""


def test_week_with_no_posts_returns_empty_lists(isolated):
    class NeverScore:
        def score(self, texts):
            raise AssertionError("nothing to score")
    out = reddit_spike_posts(NVDA, "2025-06-02", now=NOW, client=setup(isolated, []), scorer=NeverScore())
    assert out["n_fetched"] == 0 and out["n_scored"] == 0
    assert out["posts"] == [] and out["top_positive"] == [] and out["top_negative"] == []
    assert out["label_counts"] == {"positive": 0, "negative": 0, "neutral": 0}
    assert all(v is None for v in out["sentiment"].values())


def test_spike_keyword_fetch_is_capped_at_1000(isolated, monkeypatch):
    monkeypatch.setattr(on_demand, "MAX_SPIKE_POSTS", 120)
    api = setup(isolated, make_posts(300, subreddit="StockMarket"))
    out = reddit_spike_posts(NVDA, "2026-11-16", now=NOW, client=api, scorer=FakeScorer())
    assert out["truncated"] is True and "StockMarket" in out["coverage"]["skipped"]
    assert len(api.searches("StockMarket")) == 2              # 100 + 20 posts, then the cap stops it


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
