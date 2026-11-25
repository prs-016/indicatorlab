"""On-demand Reddit attention for any stock: weekly counts (Part 1) and spike-week top posts (Part 2).

Both functions take the ``ResolvedStock`` dict that ``src/resolve.py`` returns (final-week Shared
contracts) and return plain JSON-ready dicts::

    from src.reddit.on_demand import reddit_weekly_counts, reddit_spike_posts
    reddit_weekly_counts(stock)                 # {"source": "reddit", "weeks": [{"week", "count", "days_covered"}], "truncated"}
    reddit_spike_posts(stock, "2026-11-16")     # the `reddit` block of the Part 2 object

Weeks are ISO weeks labelled by their Monday 00:00 UTC, like every stored weekly table.

How posts are found (Arctic Shift, checked 2026-11-25)
------------------------------------------------------
* ``posts/search`` with ``query`` needs a ``subreddit`` (HTTP 400 "'query' query parameter requires
  one of: author, subreddit") and rejects ``limit=auto``, so we loop over subreddits and page
  100 posts at a time, newest first.
* ``posts/search/aggregate`` is not used for counts: with ``query`` it returned 0 for weeks where
  search returned 100+ posts, its weekly buckets do not start on Monday 00:00 UTC, and it cannot
  apply the ambiguity rule or de-duplicate posts found by several terms.
* ``query`` is a plain keyword search ("A OR B" is not a boolean OR), so each search term is its
  own query. The API is only the recall step: every post is re-checked here with whole-word rules.
* Scores are a snapshot from when Arctic Shift archived the post, so they can be lower than on
  Reddit today; posts younger than ~36 hours can still show score 0 or 1.

Matching rules (final-week J1 steps 3 and 6)
-------------------------------------------
* Terms: ``$TICKER``, the ticker as a whole word (skipped when it has at most 2 letters or is a
  common word such as ALL, IT, ON, NOW), the short name and every alias. Tickers without letters
  (Hong Kong codes such as 0700) are never searched as text: "700" and "$700" are prices, so
  those stocks are found through their names and ADR aliases.
* When ``ambiguous_name`` is true a post counts only if its title contains ``$TICKER`` or the
  ticker as a whole word, or the name appears next to a finance word (stock, shares, earnings, ...).
* Posts are de-duplicated by Reddit id across terms and subreddits before counting.
"""
from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from src import config, storage
from src.analyze.cache import cache_get, cache_put
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient
from src.reddit.utils import get_logger

log = get_logger("on_demand", "on_demand.log")

# Our fixed investing list (J1 step 4), searched for every stock in every market.
INVESTING_SUBREDDITS = ("stocks", "investing", "wallstreetbets", "StockMarket", "options", "ValueInvesting")
# Words that make an ambiguous name count as the company (J1 step 6); plurals accepted.
FINANCE_WORDS = (r"stocks?", r"shares?", r"earnings", r"calls?", r"puts?", r"buy", r"sell", r"prices?",
                 r"market\s+cap", r"guidance", r"revenues?", r"IPOs?", r"dividends?")
# Bare tickers that are everyday words. James's src/resolve_common_words.txt is added when it exists.
COMMON_TICKER_WORDS = frozenset({
    "ALL", "IT", "ON", "NOW", "ARE", "FOR", "CAN", "ONE", "SO", "GO", "BE", "OUT", "NEW", "BIG", "GOOD",
    "LOVE", "CASH", "FUN", "REAL", "CAR", "TRUE", "LOW", "KEY", "WELL", "ANY", "SEE", "HAS", "OPEN",
    "RUN", "PLAY", "HOME", "BEST", "LIFE", "FAST", "MAIN", "PEAK", "NICE", "HUGE", "EAT", "FLY",
    "SHOP", "MAN", "CEO", "DD", "YOLO", "EV", "AI", "USA", "TV", "IPO", "ATH", "EPS", "GDP", "CPI",
})
COMMON_WORDS_FILE = Path(__file__).resolve().parents[1] / "resolve_common_words.txt"
REMOVED_BODIES = frozenset({"[removed]", "[deleted]"})

MAX_COUNT_POSTS = 20_000       # J1 step 5: hard cap on posts fetched per stock for the weekly counts
MAX_SPIKE_POSTS = 1_000        # J2 step 1: cap on posts fetched for one spike week
PAGE_SIZE = 100                # the API's largest explicit limit (limit=auto is refused with query)
TOP_SIDE = 5                   # top_positive / top_negative length (J2 step 5)
SPIKE_BATCH_SIZE = 16          # J2 step 4: CPU, batch size 16
COUNTS_MAX_AGE_S = 6 * 3600    # analyze/reddit_counts cache: fresh for 6 hours
# Arctic Shift answers 422 "Timeout. Maybe slow down a bit" once the per-minute budget is spent (keyword
# searches cost more of it); the client then waits for the reset, so on demand we allow more retries.
ON_DEMAND_MAX_ATTEMPTS = 8
FIELDS = "id,subreddit,title,selftext,score,num_comments,created_utc"
DATA_URI_ENV = "INDICATORLAB_DATA_URI"   # same folder the /reddit API reads (src/api/reddit_data.py)
WEEK = timedelta(days=7)


# ----------------------------------------------------------------------------- small helpers
def analyze_params() -> dict:
    """The `analyze` block of config.yaml (history_weeks, max_spike_weeks, top_posts)."""
    return dict(config.load()["analyze"])


def monday_of(ts: datetime | date | str) -> datetime:
    """Monday 00:00 UTC of the ISO week containing `ts`."""
    t = pd.Timestamp(ts)
    t = t.tz_localize(UTC) if t.tzinfo is None else t.tz_convert(UTC)
    d = t.normalize() - pd.Timedelta(days=t.day_of_week)
    return d.to_pydatetime()


def _aware(now: datetime | None) -> datetime:
    """`now` as an aware UTC datetime (naive values are taken as UTC); the current time if None."""
    if now is None:
        return datetime.now(UTC)
    return now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)


def days_covered(monday: datetime, now: datetime) -> int:
    """Days of the week seen so far: days since Monday 00:00 UTC, rounded up, between 1 and 7."""
    return max(1, min(7, math.ceil((now - monday).total_seconds() / 86400)))


def _epoch(t: datetime) -> int:
    return int(t.timestamp())


def _ticker(stock: dict) -> str:
    """Upper-case ticker without a Yahoo exchange suffix (RELIANCE.NS -> RELIANCE; BRK.B is kept)."""
    t = str(stock["ticker"]).strip().upper().lstrip("$")
    return re.sub(r"\.(NS|BO|HK)$", "", t)


def _common_words() -> frozenset[str]:
    if COMMON_WORDS_FILE.exists():
        words = {w.strip().upper() for w in COMMON_WORDS_FILE.read_text(encoding="utf-8").split() if w.strip()}
        return COMMON_TICKER_WORDS | words
    return COMMON_TICKER_WORDS


def _dedupe(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        k = x.lower()
        if x and k not in seen:
            seen.add(k)
            out.append(x)
    return out


# ----------------------------------------------------------------------------- terms, subreddits, matching
@dataclass(frozen=True)
class Terms:
    """What to search for and how to recognise the stock in a post."""

    ticker: str
    dollar_ok: bool        # $TICKER is meaningful (the ticker has letters)
    bare_ok: bool          # the ticker alone, as a whole word, is meaningful
    names: tuple[str, ...]  # short name + aliases, without $ forms
    ambiguous: bool

    @property
    def queries(self) -> list[str]:
        """Keyword queries sent to the API, one request stream each."""
        return _dedupe(([self.ticker] if self.bare_ok else []) + list(self.names))


def search_terms(stock: dict) -> Terms:
    """Search terms for a ResolvedStock (J1 step 3)."""
    t = _ticker(stock)
    has_letters = any(c.isalpha() for c in t)
    letters = sum(c.isalpha() for c in t)
    bare_ok = has_letters and letters > 2 and t not in _common_words()
    names = []
    for n in [stock.get("short_name"), *(stock.get("aliases") or [])]:
        if not isinstance(n, str):
            continue
        n = n.strip()
        plain = n.lstrip("$")
        if not plain or plain.upper() == t:      # $NVDA / NVDA aliases are the ticker, handled above
            continue
        names.append(n if not n.startswith("$") else plain)
    return Terms(t, has_letters, bare_ok, tuple(_dedupe(names)), bool(stock.get("ambiguous_name")))


def market_subreddits(market: str) -> list[str]:
    """Jamal's India list or Jack's HK list; config.yaml's market subreddits until their modules land."""
    market = market.lower()
    try:
        if market == "in":
            from src.markets.india_symbols import INDIA_SUBREDDITS  # type: ignore[import-not-found]
            return list(INDIA_SUBREDDITS)
        if market == "hk":
            from src.markets.hk_symbols import HK_SUBREDDITS  # type: ignore[import-not-found]
            return list(HK_SUBREDDITS)
    except ImportError:
        pass
    if market in ("in", "hk"):
        return list((config.market(market.upper()).get("reddit") or {}).get("general") or [])
    return []


def subreddits_for(stock: dict) -> list[str]:
    """Company + market subreddits of the stock, our investing list, then the market's own list."""
    subs = stock.get("subreddits") or {}
    names = [*(subs.get("company") or []), *(subs.get("market") or []), *INVESTING_SUBREDDITS,
             *market_subreddits(stock.get("market", "us"))]
    return _dedupe(s.strip().removeprefix("r/") for s in names if isinstance(s, str) and s.strip())


def _word(term: str, flags: int = re.IGNORECASE) -> re.Pattern:
    return re.compile(rf"(?<![\w$]){re.escape(term)}(?!\w)", flags)


def build_matcher(terms: Terms) -> Callable[[dict], bool]:
    """post dict -> True if the post is about the stock (J1 steps 3 and 6)."""
    dollar = re.compile(rf"\${re.escape(terms.ticker)}(?!\w)", re.IGNORECASE) if terms.dollar_ok else None
    bare = re.compile(rf"(?<![\w$]){re.escape(terms.ticker)}(?!\w)") if terms.bare_ok else None   # case-sensitive
    names = [_word(n) for n in terms.names]
    fin = r"(?:" + "|".join(FINANCE_WORDS) + r")"
    gap = r"\W+(?:[\w'’-]+\W+){0,3}?"          # up to three words in between
    near = [re.compile(rf"(?<!\w){re.escape(n)}(?!\w){gap}(?<!\w){fin}(?!\w)|(?<!\w){fin}(?!\w){gap}(?<!\w){re.escape(n)}(?!\w)",
                       re.IGNORECASE) for n in terms.names]

    def ticker_in(text: str) -> bool:
        return bool((dollar and dollar.search(text)) or (bare and bare.search(text)))

    def match(post: dict) -> bool:
        title = post.get("title") or ""
        text = f"{title}\n{post.get('selftext') or ''}"
        if terms.ambiguous:
            return ticker_in(title) or any(p.search(text) for p in near)
        return ticker_in(text) or any(p.search(text) for p in names)

    return match


# ----------------------------------------------------------------------------- fetching
@dataclass
class _Budget:
    left: int
    truncated: bool = False


def _fetch_stream(client, subreddit: str, query: str, after: int, before: int, budget: _Budget) -> list[dict]:
    """Every post in [after, before) for one (subreddit, query), newest first, within the budget."""
    out: list[dict] = []
    seen: set[str] = set()
    b = before
    while budget.left > 0:
        limit = min(PAGE_SIZE, budget.left)            # never fetch past the cap
        params = {"subreddit": subreddit, "query": query, "after": after, "before": b,
                  "limit": limit, "sort": "desc", "fields": FIELDS}
        data = client.get("posts/search", params).body["data"]
        budget.left -= len(data)
        new = [p for p in data if p.get("id") not in seen]
        seen.update(p.get("id") for p in new)
        out.extend(new)
        if len(data) < limit or not new:               # stream exhausted
            break
        if budget.left <= 0:                           # a full page and no budget left: there may be more
            budget.truncated = True
            break
        oldest = min(int(p["created_utc"]) for p in data)
        if oldest >= b:
            break
        b = oldest
    return out


def fetch_posts(stock: dict, start: datetime, end: datetime, budget: _Budget, client=None) -> list[dict]:
    """Unique posts that match the stock, created in [start, end).

    Every post the API returns uses up `budget` (shared across calls); `budget.truncated` is set
    when the cap stopped the fetch.
    """
    client = client or ArcticShiftClient(max_attempts=ON_DEMAND_MAX_ATTEMPTS)
    terms = search_terms(stock)
    match = build_matcher(terms)
    after, before = _epoch(start), _epoch(end)
    posts: dict[str, dict] = {}
    t0, n0 = time.monotonic(), getattr(client, "n_requests", 0)
    for sub in subreddits_for(stock):
        for q in terms.queries:
            if budget.left <= 0:
                budget.truncated = True
                break
            for p in _fetch_stream(client, sub, q, after, before, budget):
                if p.get("id") and after <= int(p["created_utc"]) < before:
                    posts.setdefault(p["id"], p)
    matched = [p for p in posts.values() if match(p)]
    log.info("%s %s: %d posts fetched, %d match, %s..%s, %.1fs, %s requests%s", stock.get("market"), terms.ticker,
             len(posts), len(matched), start.date(), end.date(), time.monotonic() - t0,
             getattr(client, "n_requests", 0) - n0, " (TRUNCATED)" if budget.truncated else "")
    return matched


# ----------------------------------------------------------------------------- J1: weekly counts
def _stored_counts(stock: dict, mondays: list[datetime]) -> dict[datetime, int]:
    """Counts the stored weekly tables already have for a tracked stock (fast path, J1 step 2)."""
    uri = os.environ.get(DATA_URI_ENV, str(settings.PROCESSED)).rstrip("/")
    frames = []
    for stem in ("reddit_weekly", "reddit_weekly_recent"):
        path = f"{uri}/{stem}.parquet"
        if storage.exists(path):
            frames.append(storage.read_parquet(path, columns=["ticker", "market", "week", "value"]))
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["ticker"].astype(str).str.upper() == _ticker(stock))
            & (df["market"].astype(str).str.lower() == str(stock.get("market", "us")).lower())
            & df["value"].notna()]
    wanted = set(mondays)
    out = {}
    for w, v in zip(pd.to_datetime(df["week"], utc=True), df["value"], strict=True):
        w = w.to_pydatetime()
        if w in wanted:
            out[w] = int(v)
    return out


def _runs(mondays: list[datetime]) -> list[tuple[datetime, datetime]]:
    """Contiguous [first Monday, last Monday + 7 days) ranges covering `mondays`."""
    runs: list[tuple[datetime, datetime]] = []
    for m in sorted(mondays):
        if runs and runs[-1][1] == m:
            runs[-1] = (runs[-1][0], m + WEEK)
        else:
            runs.append((m, m + WEEK))
    return runs


def reddit_weekly_counts(stock: dict, weeks: int | None = None, *, now: datetime | None = None,
                         client=None) -> dict:
    """Weekly Reddit post counts for any stock: `weeks` full weeks plus the current partial week.

    Returns the weekly series format from Shared contracts plus ``truncated`` (True when the
    20,000-post cap was hit; the counts found so far are kept). Tracked stocks read the stored
    weekly table and only fetch the weeks it lacks. Missing weeks are 0, never dropped.
    Results for the default `weeks` are cached for 6 hours under analyze/reddit_counts/.
    """
    default_weeks = int(analyze_params()["history_weeks"])
    weeks = default_weeks if weeks is None else int(weeks)
    market, ticker = str(stock.get("market", "us")).lower(), _ticker(stock)
    key = f"analyze/reddit_counts/{market}/{ticker}.json"
    use_cache = weeks == default_weeks and now is None
    if use_cache and (hit := cache_get(key, COUNTS_MAX_AGE_S)) is not None:
        return hit

    now = _aware(now)
    current = monday_of(now)
    mondays = [current - WEEK * k for k in range(weeks, -1, -1)]
    counts = dict.fromkeys(mondays, 0)
    stored = _stored_counts(stock, mondays[:-1]) if stock.get("tracked") else {}
    counts.update(stored)
    missing = [m for m in mondays if m not in stored]
    budget = _Budget(MAX_COUNT_POSTS)
    if missing:
        client = client or ArcticShiftClient(max_attempts=ON_DEMAND_MAX_ATTEMPTS)
        missing_set = set(missing)
        for start, end in reversed(_runs(missing)):          # newest weeks first, so a cap cuts the oldest
            if budget.left <= 0:
                budget.truncated = True
                break
            for p in fetch_posts(stock, start, min(end, now), budget, client):
                m = monday_of(datetime.fromtimestamp(int(p["created_utc"]), UTC))
                if m in missing_set:
                    counts[m] += 1
    result = {
        "source": "reddit",
        "weeks": [{"week": m.date().isoformat(), "count": int(counts[m]),
                   "days_covered": 7 if m != current else days_covered(m, now)} for m in mondays],
        "truncated": budget.truncated,
    }
    if use_cache:
        cache_put(key, result)
    return result


# ----------------------------------------------------------------------------- J2: spike-week top posts
def finbert_text(post: dict) -> str:
    """Title + newline + body; removed/deleted bodies are dropped but the title is kept (J2 step 3)."""
    title = (post.get("title") or "").strip()
    body = post_body(post)
    return f"{title}\n{body}" if body else title


def post_body(post: dict) -> str:
    """The post's body, or "" when it was removed or deleted."""
    body = (post.get("selftext") or "").strip()
    return "" if body in REMOVED_BODIES else body


def _cpu_scorer():
    """The shared FinBERT scorer (same pinned revision) on CPU with batch size 16."""
    from src.sentiment.finbert_scorer import FinbertScorer, params
    p = params()
    return FinbertScorer(p["model"], str(p["revision"]), SPIKE_BATCH_SIZE, int(p["max_tokens"]), device="cpu")


def _permalink(post: dict) -> str:
    return f"https://www.reddit.com/r/{post['subreddit']}/comments/{post['id']}/"


def reddit_spike_posts(stock: dict, week_monday: str | date | datetime, *, now: datetime | None = None,
                       client=None, scorer=None) -> dict:
    """The `reddit` block of the Part 2 object for one spike week (Shared contracts).

    Fetches every matching post of that week (cap 1,000), ranks by score then comments, keeps the
    top `analyze.top_posts`, scores them with FinBERT and aggregates. Posts get local ids r1..rN in
    rank order. Not cached here: James's job runner caches the whole Part 2 object.
    """
    start = monday_of(week_monday)
    now = _aware(now)
    end = min(start + WEEK, now)
    budget = _Budget(MAX_SPIKE_POSTS)
    posts = fetch_posts(stock, start, end, budget, client) if end > start else []
    ranked = sorted(posts, key=lambda p: (-int(p.get("score") or 0), -int(p.get("num_comments") or 0), p["id"]))
    top = ranked[: int(analyze_params()["top_posts"])]

    probs = pd.DataFrame(columns=["sentiment_label", "sentiment_pos", "sentiment_neg", "sentiment_neu"])
    if top:
        scorer = scorer or _cpu_scorer()
        t0 = time.monotonic()
        probs = scorer.score([finbert_text(p) for p in top]).reset_index(drop=True)
        log.info("FinBERT scored %d posts in %.1fs", len(top), time.monotonic() - t0)

    out_posts = []
    for i, p in enumerate(top):
        row = probs.iloc[i]
        scored = pd.notna(row["sentiment_pos"])
        out_posts.append({
            "id": f"r{i + 1}",
            "reddit_id": p["id"],
            "subreddit": p["subreddit"],
            "title": p.get("title") or "",
            "body": post_body(p)[:300],
            "score": int(p.get("score") or 0),
            "num_comments": int(p.get("num_comments") or 0),
            "created_utc": int(p["created_utc"]),
            "url": _permalink(p),
            "label": row["sentiment_label"] if scored else None,
            "probs": ({"positive": round(float(row["sentiment_pos"]), 4), "negative": round(float(row["sentiment_neg"]), 4),
                       "neutral": round(float(row["sentiment_neu"]), 4)} if scored else None),
        })

    scored_posts = [p for p in out_posts if p["probs"] is not None]
    n = len(scored_posts)

    def mean(k: str) -> float | None:
        return round(sum(p["probs"][k] for p in scored_posts) / n, 4) if n else None

    sentiment = {k: mean(k) for k in ("positive", "negative", "neutral")}
    sentiment["net"] = round(sentiment["positive"] - sentiment["negative"], 4) if n else None
    label_counts = {k: sum(p["label"] == k for p in scored_posts) for k in ("positive", "negative", "neutral")}

    def top_by(k: str) -> list[str]:
        return [p["id"] for p in sorted(scored_posts, key=lambda p: -p["probs"][k])[:TOP_SIDE]]

    return {
        "n_fetched": len(posts),
        "n_scored": n,
        "truncated": budget.truncated,
        "sentiment": sentiment,
        "label_counts": label_counts,
        "top_positive": top_by("positive"),
        "top_negative": top_by("negative"),
        "posts": out_posts,
    }
