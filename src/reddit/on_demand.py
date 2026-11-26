"""On-demand Reddit attention for any stock: weekly counts (Part 1) and spike-week top posts (Part 2).

Both functions take the ``ResolvedStock`` dict that ``src/resolve.py`` returns (final-week Shared
contracts) and return plain JSON-ready dicts::

    from src.reddit.on_demand import reddit_weekly_counts, reddit_spike_posts
    reddit_weekly_counts(stock)                 # {"source": "reddit", "weeks": [{"week", "count", "days_covered"}], ...}
    reddit_spike_posts(stock, "2026-11-16")     # the `reddit` block of the Part 2 object

Weeks are ISO weeks labelled by their Monday 00:00 UTC, like every stored weekly table.

Where posts come from (changed 2026-11-25)
------------------------------------------
1. **Saved posts.** We already store every post of the 33 subreddits in config.yaml's US subreddit
   map (r/wallstreetbets, r/stocks, r/investing, sector and company subreddits): the research
   corpus up to Oct 31, 2026 (one parquet file per subreddit: ``data/reddit/processed/posts/`` on a
   laptop, ``processed/reddit_state/posts/`` on S3), then the hourly job's
   ``raw/reddit/date=YYYY-MM-DD/`` files from ``holdout_start`` (Nov 1) on. Posts of those
   subreddits are matched here, with no API call.
2. **Keyword backup.** The stock's other subreddits (r/StockMarket, r/options, r/ValueInvesting and
   the India / Hong Kong lists) are not saved, so they go through Arctic Shift's keyword search
   (``posts/search`` with ``query``). Arctic Shift often refuses it with "Timeout. Maybe slow down a
   bit" (1 of 3 tries on 2026-11-25). Each request gets a time limit. A subreddit counts only if
   all of its searches finished; otherwise it is listed in ``coverage["skipped"]`` and left out, so
   a week never mixes complete and partial subreddits. What each search fetched is cached per
   (subreddit, search term), so the next request continues where this one stopped.

API facts (checked 2026-11-25): ``query`` needs a ``subreddit`` and rejects ``limit=auto``;
``query`` is a plain keyword search ("A OR B" is not a boolean OR), so the API is only the recall
step and every post is re-checked here; ``posts/ids`` returns current scores quickly. Scores are a
snapshot from when the post was archived, so they can be lower than on Reddit today.

Matching rules (final-week J1 steps 3 and 6)
-------------------------------------------
* Terms: ``$TICKER``, the ticker as a whole word (skipped when it has at most 2 letters or is a
  common word such as ALL, IT, ON, NOW), the short name and every alias. Tickers without letters
  (Hong Kong codes such as 0700) are never matched as text: "700" and "$700" are prices, so
  those stocks are found through their names and ADR aliases.
* When ``ambiguous_name`` is true a post counts only if its title contains ``$TICKER`` or the
  ticker as a whole word, or the name appears next to a finance word (stock, shares, earnings, ...).
* Posts are de-duplicated by Reddit id across terms and subreddits before counting.
"""
from __future__ import annotations

import functools
import math
import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from src import config, storage
from src.analyze.cache import cache_get, cache_put
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient, ArcticShiftError
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

MAX_COUNT_POSTS = 20_000       # J1 step 5: cap on posts fetched by keyword search in one counts request
MAX_SPIKE_POSTS = 1_000        # J2 step 1: cap on posts fetched by keyword search for one spike week
PAGE_SIZE = 100                # the API's largest explicit limit (limit=auto is refused with query)
TOP_SIDE = 5                   # top_positive / top_negative length (J2 step 5)
SPIKE_BATCH_SIZE = 16          # J2 step 4: CPU, batch size 16
COUNTS_MAX_AGE_S = 6 * 3600    # analyze/reddit_counts cache: fresh for 6 hours ...
PARTIAL_COUNTS_MAX_AGE_S = 30 * 60   # ... or 30 minutes when the keyword backup skipped a subreddit
COUNTS_BACKUP_S = 45.0         # time limit for the keyword backup in one counts request
SPIKE_BACKUP_S = 30.0          # time limit for the keyword backup in one spike request
REFRESH_S = 30.0               # time limit for refreshing the hourly posts' scores in one spike request
BACKUP_MAX_ATTEMPTS = 3        # tries per keyword request (the client waits for the rate-limit reset)
BACKUP_REQUEST_TIMEOUT_S = 20.0
IDS_BATCH = 100                # posts per posts/ids request (score refresh)
CACHED_BODY_CHARS = 2_000      # the keyword-search cache keeps this much of each body
FIELDS = "id,subreddit,title,selftext,score,num_comments,created_utc"
POST_COLS = ["id", "subreddit", "created_utc", "title", "selftext", "score", "num_comments"]

DATA_URI_ENV = "INDICATORLAB_DATA_URI"         # stored weekly tables (same folder the /reddit API reads)
ROOT_ENV, BUCKET_ENV = "INDICATORLAB_ROOT_URI", "INDICATORLAB_BUCKET"   # as src/reddit/pipeline.py
DEFAULT_BUCKET = "indicatorlab-data"
POSTS_URI_ENV = "INDICATORLAB_POSTS_URI"       # folder of saved <subreddit>.parquet files
MATCHES_URI_ENV = "INDICATORLAB_MATCHES_URI"   # post_ticker_matches.parquet (tracked stocks)
WEEK, DAY = timedelta(days=7), timedelta(days=1)
_MONDAY_EPOCH = 4 * 86400      # 1970-01-05 00:00 UTC, a Monday


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


def _monday_epoch(created_utc: int) -> int:
    """Monday 00:00 UTC (epoch seconds) of the week a post was created in."""
    return created_utc - (created_utc - _MONDAY_EPOCH) % (7 * 86400)


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


def _days(start: datetime, end: datetime) -> list[date]:
    """Every UTC date from start's to end's, both included."""
    d, out = start.date(), []
    while d <= end.date():
        out.append(d)
        d += DAY
    return out


def _full_days_without(seen: set[date], start: datetime, end: datetime) -> list[str]:
    """Complete days in [start, end) that are not in `seen`, as ISO dates."""
    return [d.isoformat() for d in _days(start, end)
            if datetime(d.year, d.month, d.day, tzinfo=UTC) + DAY <= end and d not in seen]


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


# ----------------------------------------------------------------------------- where the data lives
def data_root() -> str:
    """INDICATORLAB_ROOT_URI, else s3://$INDICATORLAB_BUCKET, else s3://indicatorlab-data."""
    root = os.environ.get(ROOT_ENV) or f"s3://{os.environ.get(BUCKET_ENV) or DEFAULT_BUCKET}"
    return root.rstrip("/")


def saved_end() -> datetime:
    """Where the saved corpus stops and the hourly files take over: holdout_start, 00:00 UTC."""
    d = config.holdout_start()
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _local_or_remote(env: str, local: Path, remote: str) -> str:
    """The env variable if set, else the laptop copy if it exists, else <data root>/<remote>."""
    if os.environ.get(env):
        return os.environ[env].rstrip("/")
    return str(local) if local.exists() else f"{data_root()}/{remote}"


def posts_uri() -> str:
    """Folder of the saved corpus, one <subreddit>.parquet per subreddit."""
    return _local_or_remote(POSTS_URI_ENV, settings.POSTS, "processed/reddit_state/posts")


def matches_uri() -> str:
    """post_ticker_matches.parquet: every (post, ticker) match of the saved corpus."""
    return _local_or_remote(MATCHES_URI_ENV, settings.PROCESSED / "post_ticker_matches.parquet",
                            "processed/reddit_state/post_ticker_matches.parquet")


def saved_subreddits() -> set[str]:
    """Lower-case names of the subreddits whose every post we store (the hourly job collects the same list)."""
    return set(config.subreddit_map(settings.MARKET))


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

    @property
    def needles(self) -> list[str]:
        """Text a matching post must contain (any case): the fast first pass over saved posts."""
        return _dedupe(([self.ticker] if self.dollar_ok or self.bare_ok else []) + list(self.names))


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


def split_subreddits(stock: dict) -> tuple[list[str], list[str]]:
    """(saved, backup): the stock's subreddits we store, and the rest with stock-specific ones first."""
    saved = saved_subreddits()
    subs = subreddits_for(stock)
    backup = [s for s in subs if s.lower() not in saved]
    return [s for s in subs if s.lower() in saved], sorted(backup, key=lambda s: s in INVESTING_SUBREDDITS)


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


# ----------------------------------------------------------------------------- saved posts
def _candidates(table: pa.Table, needles: list[str]) -> list[dict]:
    """Rows whose title or body contains any needle (any case), as dicts. Exact rules come after."""
    if not table.num_rows or not needles:
        return []
    mask = None
    for col in ("title", "selftext"):
        text = pc.fill_null(table[col].cast(pa.large_string()), "")
        for n in needles:
            m = pc.match_substring(text, n, ignore_case=True)
            mask = m if mask is None else pc.or_(mask, m)
    return table.filter(mask).to_pylist()


@functools.lru_cache(maxsize=96)
def _finished_day(uri: str, columns: tuple[str, ...]) -> pd.DataFrame | None:
    return storage.read_parquet_dir(uri, columns=list(columns))


def _day_files(prefix: str, d: date, columns: list[str]) -> pd.DataFrame | None:
    """One date=YYYY-MM-DD folder of hourly files. Days before today (UTC) are kept in memory: the
    hourly job only writes today's folder, so a finished day no longer changes."""
    uri = f"{data_root()}/{prefix}/date={d.isoformat()}"
    if d < datetime.now(UTC).date():
        return _finished_day(uri, tuple(columns))
    return storage.read_parquet_dir(uri, columns=columns)


def _hourly_raw(subs: list[str], start: datetime, end: datetime) -> pd.DataFrame:
    """Posts of `subs` (lower-case) created in [start, end) from the hourly job's raw/reddit files."""
    frames = []
    for d in _days(start, end + DAY):           # a post can land in the next day's file
        df = _day_files("raw/reddit", d, POST_COLS)
        if df is None or df.empty:
            continue
        keep = (df["subreddit"].str.lower().isin(subs) & (df["created_utc"] >= _epoch(start))
                & (df["created_utc"] < _epoch(end)))
        frames.append(df[keep])
    if not frames:
        return pd.DataFrame(columns=POST_COLS)
    return pd.concat(frames, ignore_index=True).drop_duplicates("id")


def saved_posts(subs: list[str], start: datetime, end: datetime, terms: Terms) -> tuple[list[dict], list[str]]:
    """Matching posts of saved subreddits created in [start, end), and the days after the corpus with
    no saved post at all (the hourly job was down, so counts there are too low).

    Posts from the hourly files carry ``_fresh=True``: their score was read within an hour of posting.
    """
    match = build_matcher(terms)
    subs = [s.lower() for s in subs]
    cut = saved_end()
    found: list[dict] = []
    if start < cut and subs:
        flt = [("created_utc", ">=", _epoch(start)), ("created_utc", "<", _epoch(min(end, cut)))]
        for sub in subs:
            path = f"{posts_uri()}/{sub}.parquet"
            if storage.exists(path):
                found += _candidates(storage.read_table(path, columns=POST_COLS, filters=flt), terms.needles)
            else:
                log.warning("saved posts missing for r/%s at %s", sub, path)
    missing: list[str] = []
    if end > cut and subs:
        lo = max(start, cut)
        df = _hourly_raw(subs, lo, end)
        seen = set(pd.to_datetime(df["created_utc"], unit="s", utc=True).dt.date) if len(df) else set()
        missing = _full_days_without(seen, lo, end)
        if len(df):
            table = pa.Table.from_pandas(df[POST_COLS], preserve_index=False)
            found += [{**p, "_fresh": True} for p in _candidates(table, terms.needles)]
    out: dict[str, dict] = {}
    for p in found:
        if match(p):
            out.setdefault(p["id"], p)
    return list(out.values()), missing


# ----------------------------------------------------------------------------- keyword backup
class _Stop(Exception):
    """The keyword backup has to stop: out of time or out of posts budget."""


@dataclass
class _Budget:
    left: int
    truncated: bool = False


@dataclass
class _Deadline:
    """Time limit for Arctic Shift calls. Its `sleep` (the client's wait for the rate-limit reset)
    refuses to wait past the limit and then blocks every later call: until the reset, Arctic Shift
    refuses everything, so more requests would only add load."""

    seconds: float
    at: float = field(init=False)
    blocked: bool = False

    def __post_init__(self):
        self.at = time.monotonic() + self.seconds

    def left(self) -> float:
        return 0.0 if self.blocked else self.at - time.monotonic()

    def check(self) -> None:
        if self.left() <= 0:
            raise _Stop("rate limited past the time limit" if self.blocked else "time limit")

    def sleep(self, s: float) -> None:
        if s >= self.left():
            self.blocked = True
            raise _Stop("rate limited past the time limit")
        time.sleep(s)


def _backup_client(deadline: _Deadline) -> ArcticShiftClient:
    return ArcticShiftClient(max_attempts=BACKUP_MAX_ATTEMPTS, timeout=BACKUP_REQUEST_TIMEOUT_S, sleep=deadline.sleep)


@dataclass
class _Stream:
    """Cached keyword-search results of one (subreddit, term): every post in [after, before) is in `posts`."""

    after: int
    before: int
    posts: dict[str, dict]


def _stream_key(sub: str, query: str) -> str:
    return f"analyze/reddit_keyword/{sub.lower()}/{re.sub(r'[^a-z0-9]+', '_', query.lower()).strip('_')}.json"


def _compact(p: dict) -> dict:
    return {"id": p["id"], "subreddit": p.get("subreddit"), "created_utc": int(p["created_utc"]),
            "title": p.get("title") or "", "selftext": (p.get("selftext") or "")[:CACHED_BODY_CHARS],
            "score": int(p.get("score") or 0), "num_comments": int(p.get("num_comments") or 0)}


def _page(client, sub: str, query: str, after: int, before: int, asc: bool, budget: _Budget,
          deadline: _Deadline) -> tuple[list[dict], int]:
    """One page of keyword results in the API's window (after, before); returns (posts, limit asked)."""
    deadline.check()
    if budget.left <= 0:
        budget.truncated = True
        raise _Stop("post cap")
    limit = min(PAGE_SIZE, budget.left)
    params = {"subreddit": sub, "query": query, "after": after, "before": before, "limit": limit,
              "sort": "asc" if asc else "desc", "fields": FIELDS}
    data = client.get("posts/search", params).body["data"]
    budget.left -= len(data)
    return data, limit


def _extend(client, sub: str, query: str, st: _Stream, start: int, end: int, budget: _Budget,
            deadline: _Deadline) -> None:
    """Grow `st` to cover [start, end): newer posts oldest first, then older posts newest first.

    Each page overlaps the covered range by one second (posts are de-duplicated by id), and the
    covered range moves after every page, so a stop keeps all progress.
    """
    while st.before < end:
        data, limit = _page(client, sub, query, st.before - 1, end, True, budget, deadline)
        st.posts.update({p["id"]: _compact(p) for p in data})
        newest = max((int(p["created_utc"]) for p in data), default=end)
        st.before = end if len(data) < limit else max(newest, st.before + 1)
    while st.after > start:
        data, limit = _page(client, sub, query, start - 1, st.after + 1, False, budget, deadline)
        st.posts.update({p["id"]: _compact(p) for p in data})
        oldest = min((int(p["created_utc"]) for p in data), default=start)
        st.after = start if len(data) < limit else min(oldest + 1, st.after - 1)


def keyword_stream(client, sub: str, query: str, start: int, end: int, budget: _Budget, deadline: _Deadline,
                   keep_from: int) -> tuple[list[dict], bool]:
    """Keyword hits for `query` in r/`sub` created in [start, end): (posts, complete).

    Reads the cache, fetches only what it lacks, and saves the progress even when it has to stop.
    Cached posts older than `keep_from` (the start of the counts window) are dropped.
    """
    key = _stream_key(sub, query)
    hit = cache_get(key, None)
    cached = _Stream(int(hit["after"]), int(hit["before"]), {p["id"]: p for p in hit["posts"]}) if hit else None
    usable = cached is not None and cached.before >= start and cached.after <= end
    st = cached if usable else _Stream(end, end, {})
    complete = False
    try:
        _extend(client, sub, query, st, start, end, budget, deadline)
        complete = True
    except (ArcticShiftError, _Stop) as e:
        log.warning("keyword search r/%s %r stopped: %s", sub, query, e)
    finally:
        if usable or cached is None or cached.before < start:      # never overwrite a newer cache
            lo = max(st.after, keep_from)
            cache_put(key, {"after": lo, "before": st.before,
                            "posts": sorted((p for p in st.posts.values() if p["created_utc"] >= lo),
                                            key=lambda p: p["created_utc"])})
    return [p for p in st.posts.values() if start <= p["created_utc"] < end], complete


@dataclass
class _Backup:
    posts: list[dict] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def keyword_backup(terms: Terms, subs: list[str], start: datetime, end: datetime, budget: _Budget,
                   deadline: _Deadline, client, keep_from: datetime) -> _Backup:
    """Matching posts of the unsaved subreddits `subs`; a subreddit counts only if every search finished."""
    match = build_matcher(terms)
    out = _Backup()
    t0, n0 = time.monotonic(), getattr(client, "n_requests", 0)
    for sub in subs:
        if deadline.left() <= 0 or budget.left <= 0:
            budget.truncated |= budget.left <= 0
            out.skipped.append(sub)
            continue
        found: dict[str, dict] = {}
        ok = True
        for q in terms.queries:
            posts, complete = keyword_stream(client, sub, q, _epoch(start), _epoch(end), budget, deadline,
                                             _epoch(keep_from))
            ok &= complete
            found.update({p["id"]: p for p in posts})
        if ok:
            out.searched.append(sub)
            out.posts += [p for p in found.values() if match(p)]
        else:
            out.skipped.append(sub)
    if subs:
        log.info("keyword backup %s: searched %s, skipped %s, %d posts, %.1fs, %s requests", terms.ticker,
                 out.searched, out.skipped, len(out.posts), time.monotonic() - t0,
                 getattr(client, "n_requests", 0) - n0)
    return out


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


def tracked_subreddits(stock: dict) -> list[str]:
    """Subreddits the stored weekly table counts for a tracked stock (its own + the shared ones)."""
    from src.reddit.reddit_weekly import COMBINED_OF_TYPE, source_subreddits
    return source_subreddits(settings.MARKET, COMBINED_OF_TYPE).get((_ticker(stock), "reddit"), [])


def _tracked_rows(stock: dict, start: datetime, end: datetime) -> tuple[dict[int, set[str]], list[str]]:
    """Post ids matched to a tracked stock per week (Monday epoch) in [start, end), from the rows the
    stored table is built from: post_ticker_matches before the cutoff, the hourly job's reddit_hourly
    rows after it. Also the days after the cutoff with no hourly rows at all."""
    ticker, cut = _ticker(stock), saved_end()
    ids: dict[int, set[str]] = {}

    def add(post_ids, created) -> None:
        for pid, c in zip(post_ids, created, strict=True):
            ids.setdefault(_monday_epoch(int(c)), set()).add(pid)

    if start < cut and storage.exists(matches_uri()):
        t = storage.read_table(matches_uri(), columns=["post_id", "ticker", "created_utc"],
                               filters=[("ticker", "==", ticker), ("created_utc", ">=", _epoch(start)),
                                        ("created_utc", "<", _epoch(min(end, cut)))])
        add(t["post_id"].to_pylist(), t["created_utc"].to_pylist())
    missing: list[str] = []
    if end > cut:
        lo, seen = max(start, cut), set()
        for d in _days(lo, end + DAY):
            df = _day_files("processed/reddit_hourly", d, ["post_id", "ticker", "created_utc"])
            if df is None or df.empty:
                continue
            df = df[(df["created_utc"] >= _epoch(lo)) & (df["created_utc"] < _epoch(end))]
            seen |= set(pd.to_datetime(df["created_utc"], unit="s", utc=True).dt.date)
            mine = df[df["ticker"].astype(str).str.upper() == ticker]
            add(mine["post_id"].tolist(), mine["created_utc"].tolist())
        missing = _full_days_without(seen, lo, end)
    return ids, missing


def _tracked_counts(stock: dict, mondays: list[datetime], now: datetime,
                    stored: dict[datetime, int]) -> tuple[dict, dict, bool]:
    """Stored weekly values where the table has them; the other weeks from the same match rows, so every
    week uses the stored definition (unique posts matched to the ticker; every post of its company
    subreddits counts). No keyword backup: it would change that definition."""
    counts = dict.fromkeys(mondays, 0)
    counts.update(stored)
    rest = [m for m in mondays if m not in stored]
    missing_days: list[str] = []
    if rest:
        ids, missing_days = _tracked_rows(stock, min(rest), now)
        for m in rest:
            counts[m] = len(ids.get(_epoch(m), ()))
    coverage = {"saved": tracked_subreddits(stock), "searched": [], "skipped": [], "missing_days": missing_days}
    return counts, coverage, False


def _matched_counts(stock: dict, mondays: list[datetime], now: datetime, client) -> tuple[dict, dict, bool]:
    """Counts from saved posts plus the keyword backup, matched with the J1 rules."""
    terms = search_terms(stock)
    saved, backup_subs = split_subreddits(stock)
    start = mondays[0]
    t0 = time.monotonic()
    posts, missing_days = saved_posts(saved, start, now, terms)
    log.info("saved posts %s: %d match in %s, %.1fs", terms.ticker, len(posts), saved, time.monotonic() - t0)
    budget, deadline = _Budget(MAX_COUNT_POSTS), _Deadline(COUNTS_BACKUP_S)
    backup = keyword_backup(terms, backup_subs, start, now, budget, deadline, client or _backup_client(deadline),
                            start)
    by_epoch = {_epoch(m): m for m in mondays}
    counts = dict.fromkeys(mondays, 0)
    for p in {p["id"]: p for p in [*posts, *backup.posts]}.values():
        m = by_epoch.get(_monday_epoch(int(p["created_utc"])))
        if m is not None:
            counts[m] += 1
    coverage = {"saved": saved, "searched": backup.searched, "skipped": backup.skipped, "missing_days": missing_days}
    return counts, coverage, budget.truncated


def reddit_weekly_counts(stock: dict, weeks: int | None = None, *, now: datetime | None = None,
                         client=None) -> dict:
    """Weekly Reddit post counts for any stock: `weeks` full weeks plus the current partial week.

    Returns the weekly series format from Shared contracts plus:

    * ``truncated``: True when the keyword backup hit the 20,000-post cap (that subreddit is skipped).
    * ``coverage``: ``saved`` (subreddits read from saved posts), ``searched`` (keyword backup
      finished), ``skipped`` (keyword backup failed or ran out of time: not in the counts) and
      ``missing_days`` (days after Oct 31 with no saved posts, so those weeks are too low).

    Tracked stocks that the stored weekly table has read it and count the weeks it lacks from the
    same match rows; other stocks are matched in saved posts. Missing weeks are 0, never dropped. Results for the default `weeks` are cached for
    6 hours under analyze/reddit_counts/ (30 minutes if a subreddit was skipped).
    """
    default_weeks = int(analyze_params()["history_weeks"])
    weeks = default_weeks if weeks is None else int(weeks)
    market, ticker = str(stock.get("market", "us")).lower(), _ticker(stock)
    key = f"analyze/reddit_counts/{market}/{ticker}.json"
    use_cache = weeks == default_weeks and now is None
    if use_cache and (hit := cache_get(key, COUNTS_MAX_AGE_S)) is not None and (
            not hit.get("coverage", {}).get("skipped") or cache_get(key, PARTIAL_COUNTS_MAX_AGE_S) is not None):
        return hit

    now = _aware(now)
    current = monday_of(now)
    mondays = [current - WEEK * k for k in range(weeks, -1, -1)]
    # The stored path only if the table really has this stock: India / HK lists mark stocks tracked too.
    stored = _stored_counts(stock, mondays[:-1]) if stock.get("tracked") else {}
    if stored:
        counts, coverage, truncated = _tracked_counts(stock, mondays, now, stored)
    else:
        counts, coverage, truncated = _matched_counts(stock, mondays, now, client)
    result = {
        "source": "reddit",
        "weeks": [{"week": m.date().isoformat(), "count": int(counts[m]),
                   "days_covered": 7 if m != current else days_covered(m, now)} for m in mondays],
        "truncated": truncated,
        "coverage": coverage,
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


def refresh_scores(posts: list[dict], client, deadline: _Deadline) -> bool:
    """Replace score and num_comments with Arctic Shift's current values (posts/ids, a cheap lookup).

    Used for posts from the hourly files, read within an hour of posting, whose score is still near
    0. Returns False if a lookup failed; the posts it reached are updated anyway.
    """
    by_id = {p["id"]: p for p in posts}
    ids = list(by_id)
    try:
        for i in range(0, len(ids), IDS_BATCH):
            deadline.check()
            data = client.get("posts/ids", {"ids": ",".join(ids[i:i + IDS_BATCH]),
                                            "fields": "id,score,num_comments"}).body["data"]
            for d in data:
                if d.get("id") in by_id:
                    by_id[d["id"]]["score"] = int(d.get("score") or 0)
                    by_id[d["id"]]["num_comments"] = int(d.get("num_comments") or 0)
    except (ArcticShiftError, _Stop) as e:
        log.warning("score refresh stopped: %s", e)
        return False
    return True


def reddit_spike_posts(stock: dict, week_monday: str | date | datetime, *, now: datetime | None = None,
                       client=None, scorer=None) -> dict:
    """The `reddit` block of the Part 2 object for one spike week (Shared contracts).

    Collects every matching post of that week (saved posts + keyword backup, which fetches at
    most 1,000 posts), refreshes the scores of posts from the hourly files (read within an hour of
    posting; keyword hits already carry Arctic Shift's stored score), ranks by score then comments, keeps the top `analyze.top_posts`, scores them with FinBERT and aggregates. Posts
    get local ids r1..rN in rank order. Extra keys: ``truncated`` and ``coverage`` (as in
    reddit_weekly_counts, plus ``scores_refreshed``). Not cached here: James's job runner caches
    the whole Part 2 object.
    """
    start = monday_of(week_monday)
    now = _aware(now)
    end = min(start + WEEK, now)
    terms = search_terms(stock)
    saved, backup_subs = split_subreddits(stock)
    budget = _Budget(MAX_SPIKE_POSTS)
    posts: list[dict] = []
    missing_days: list[str] = []
    backup, refreshed = _Backup(), True
    if end > start:
        posts, missing_days = saved_posts(saved, start, end, terms)
        fresh = [p for p in posts if p.get("_fresh")]
        if fresh:          # first, so the keyword backup can't use up Arctic Shift's budget before it
            dl = _Deadline(REFRESH_S)
            refreshed = refresh_scores(fresh, client or _backup_client(dl), dl)
        keep_from = monday_of(now) - WEEK * int(analyze_params()["history_weeks"])
        dl = _Deadline(SPIKE_BACKUP_S)
        backup = keyword_backup(terms, backup_subs, start, end, budget, dl, client or _backup_client(dl), keep_from)
        posts = list({p["id"]: p for p in [*posts, *backup.posts]}.values())
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
        "coverage": {"saved": saved, "searched": backup.searched, "skipped": backup.skipped,
                     "missing_days": missing_days, "scores_refreshed": refreshed},
        "sentiment": sentiment,
        "label_counts": label_counts,
        "top_positive": top_by("positive"),
        "top_negative": top_by("negative"),
        "posts": out_posts,
    }
