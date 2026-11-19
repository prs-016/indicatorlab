"""Build the Wikipedia data: pull views, edits and prices, then write the weekly tables.

    python -m src.wiki_pipeline          # pulls only what is not cached yet, then rebuilds every table

Research data (before the holdout, config `holdout_start`) and recent data are stored in separate
files; the recent files are for the dashboard and the last-3-weeks spike check only.

  data/raw/wikipedia/views_{research,recent}_<tag>/<ticker>.csv      daily views: the stock's total, then each article
  data/raw/wikipedia/revisions_{research,recent}_<tag>/<lang>/<ticker>.csv  revisions, edit summaries
                                                   (a stock's 2nd+ article in a language: <ticker>__<title>.csv)
  data/raw/wikipedia/prices/daily_close_<market>_<tag>.csv           Yahoo adjusted closes

<tag> is the research cutoff (`holdout_start`, e.g. 20261101; see `cache_tag`). Moving the cutoff starts
new raw caches and leaves the old ones as they were, so results built under an earlier cutoff can still
be reproduced. Folders without a tag were written under the first cutoff (2025-10-01).
  data/shared/attention_weekly_wikipedia_{research,recent}.csv  shared weekly table (team format)
  data/shared/attention_weekly_wikipedia.csv                   both periods together, for the Reddit code
  data/processed/wikipedia/weekly_edits_{research,recent}.csv  edits, editors, bytes, reverts, tags
  data/processed/wikipedia/weekly_prices.csv                   returns 1-4 weeks after, abnormal returns
"""
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.wiki_attention import article_views, flag_spikes, week_start, weekly
from src.wiki_edits import edit_table, load_revisions, weekly_edits
from src.wiki_prices import weekly_panel

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "wikipedia"
PROCESSED = ROOT / "data" / "processed" / "wikipedia"
SHARED = ROOT / "data" / "shared"
PERIODS = ("research", "recent")
PRICE_START = "2014-01-01"   # 52-week betas and 200-day averages exist from the first Wikipedia week
SHARED_COLS = ["week", "ticker", "market", "source", "posts", "comments", "upvotes", "views", "edits",
               "sentiment_mean", "pct_positive", "pct_negative", "baseline", "ratio", "spike"]
EXTRA_COLS = ["abnormal", "rz"]

log = logging.getLogger("wiki_pipeline")


def cache_tag() -> str:
    """Suffix of every raw cache name: the research cutoff (config `holdout_start`) as YYYYMMDD."""
    return f"{config.holdout_start():%Y%m%d}"


def period_dir(kind: str, period: str, raw: Path = RAW) -> Path:
    """Raw cache folder of one kind (views, revisions, diffs) and period under the current cutoff."""
    return raw / f"{kind}_{period}_{cache_tag()}"


def untagged_dir(kind: str, period: str, raw: Path = RAW) -> Path:
    """The same folder as written before caches were tagged (first cutoff); only ever read."""
    return raw / f"{kind}_{period}"


def prices_path(market: str, raw: Path = RAW) -> Path:
    """Cached daily adjusted closes of one market under the current cutoff."""
    return raw / "prices" / f"daily_close_{market}_{cache_tag()}.csv"


def shared_path(period: str) -> Path:
    """Shared weekly Wikipedia table of one period."""
    return SHARED / f"attention_weekly_wikipedia_{period}.csv"


def last_complete_sunday(today: date | None = None) -> pd.Timestamp:
    """End of the last full Monday-Sunday week before today."""
    today = today or date.today()
    return pd.Timestamp(today - timedelta(days=today.weekday() + 1))


def windows(end: pd.Timestamp | None = None) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """Research and recent date windows (inclusive)."""
    holdout = pd.Timestamp(config.holdout_start())
    return {"research": (pd.Timestamp(config.load()["wikipedia"]["research_start"]), holdout - pd.Timedelta(days=1)),
            "recent": (holdout, end or last_complete_sunday())}


def universe(market: str = "US", strategy: bool = True) -> dict[str, dict[str, str | list[str]]]:
    """Ticker -> {language: article title(s)}: the tracked stocks, plus the strategy universe if asked."""
    out = {t: dict(cfg["wikipedia"]) for t, cfg in config.stocks(market).items()}
    if strategy:
        extra = config.load()["wikipedia"]["strategy_universe"].get(market) or {}
        out.update({t: dict(titles) for t, titles in extra.items()})
    return out


def article_titles(titles: dict[str, str | list[str]]) -> list[tuple[str, str]]:
    """(language, title) pairs of one stock; a language may list several articles (GOOGL: Alphabet and Google)."""
    return [(lang, t) for lang, ts in titles.items() for t in ([ts] if isinstance(ts, str) else ts)]


def title_key(lang: str, title: str) -> str:
    """Column name of one article in the views cache and key of `article_starts`, e.g. 'en:Google'."""
    return f"{lang}:{title}"


def cache_stem(ticker: str, titles: dict, lang: str, title: str) -> str:
    """Revision and diff cache name: the ticker for a stock's first article in a language, else ticker__title."""
    first = next(t for lg, t in article_titles(titles) if lg == lang)
    return ticker if title == first else f"{ticker}__{title}"


def article_start(revs: pd.DataFrame, min_bytes: int | None = None) -> pd.Timestamp:
    """Monday of the first full week in which a page was an article (a revision of >= `min_bytes`).

    Before that the title was missing or a redirect (Meta_Platforms redirected to Facebook until
    Nov 2019), so its views and edits were not the company article's. Only the first article-sized
    revision counts: vandals often blank a page for a few minutes, which does not end it.
    """
    min_bytes = min_bytes or config.load()["wikipedia"]["min_article_bytes"]
    big = revs.loc[revs["size"] >= min_bytes, "timestamp"]
    if big.empty:
        raise ValueError("the page was never an article")
    monday = week_start(pd.DatetimeIndex([big.min()]))[0]
    return monday if big.min() == monday else monday + pd.Timedelta(days=7)


def _cached_end(f: Path) -> pd.Timestamp:
    """Last date in a cached date-indexed CSV."""
    return pd.read_csv(f, index_col=0, parse_dates=True).index.max()


def load_views(ticker: str, titles: dict, win: dict, starts: dict[str, pd.Timestamp] | None = None,
               raw: Path = RAW) -> pd.Series:
    """Daily views of one stock: its articles summed, each from its `starts` week (see `article_start`).

    The cache keeps each article's own views next to the total, so the total is recomputed from them.
    Days before every article's start are dropped. Both periods are pulled together (one request per
    title) when a cache file is missing, lists other articles than the config, or the recent file ends
    before the requested end (so a weekly rerun picks up the new weeks).
    """
    keys = [title_key(lang, t) for lang, t in article_titles(titles)]
    files = {p: period_dir("views", p, raw) / f"{ticker}.csv" for p in PERIODS}
    cached = {p: pd.read_csv(f, index_col=0, parse_dates=True) for p, f in files.items() if f.exists()}
    if len(keys) == 1:   # a cache written before per-article columns: its one column is that article
        cached = {p: c if keys[0] in c else c.iloc[:, :1].set_axis(keys, axis=1) for p, c in cached.items()}
    if (len(cached) < len(PERIODS) or any(not set(keys) <= set(c) for c in cached.values())
            or cached["recent"].index.max() < win["recent"][1]):
        start, end = win["research"][0], win["recent"][1]
        raw_views = pd.DataFrame({title_key(lang, t): article_views(t, start, end, lang)
                                  for lang, t in article_titles(titles)})
        cached = {p: raw_views.loc[a:b] for p, (a, b) in win.items()}
    starts = starts or {}
    out = []
    for p, c in cached.items():
        c = c[keys]
        total = pd.concat([c[k].where(c.index >= starts.get(k, c.index.min())) for k in keys], axis=1)
        c.insert(0, ticker, total.sum(axis=1, min_count=1))
        files[p].parent.mkdir(parents=True, exist_ok=True)
        c.rename_axis("date").to_csv(files[p])
        out.append(c[ticker].dropna())
    return pd.concat(out)


def title_revisions(ticker: str, titles: dict, win: dict, raw: Path = RAW) -> pd.DataFrame:
    """Revisions of each of one stock's articles across both periods (`lang`, `title`, `key` columns).

    Each period is cached in its own file; the recent one is pulled again when the recent window has
    grown since it was written. `before_start` marks the revision live when the research window opens.
    """
    revs = []
    for p, (a, b) in win.items():
        for lang, title in article_titles(titles):
            stem = cache_stem(ticker, titles, lang, title)
            f = period_dir("revisions", p, raw) / lang / f"{stem}.csv"
            if p == "recent" and f.exists() and _views_behind(raw, ticker, b):
                f.unlink()
            revs.append(load_revisions(stem, title, a, b, period_dir("revisions", p, raw) / lang, lang)
                        .assign(lang=lang, title=title, key=title_key(lang, title)))
    # the earlier period's last revision is the later period's `before_start`; keep one copy
    df = pd.concat(revs).drop_duplicates(["key", "revid"]).sort_values("timestamp")
    df["before_start"] = df["timestamp"] < win["research"][0]
    return df


def article_starts(revs: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """`title_key` -> first full week as an article, for the revisions of `title_revisions`."""
    return {k: article_start(g) for k, g in revs.groupby("key")}


def load_edits(ticker: str, titles: dict, win: dict, raw: Path = RAW) -> pd.DataFrame:
    """Edits of one stock's articles across both periods, each article from its first week as an article."""
    revs = title_revisions(ticker, titles, win, raw)
    starts = article_starts(revs)
    e = pd.concat([edit_table(g) for _, g in revs.groupby("key")])
    return e[e["timestamp"] >= e["key"].map(starts)].sort_values("timestamp")


def _views_behind(raw: Path, ticker: str, end: pd.Timestamp) -> bool:
    """True when the recent views cache was written for an earlier end date than `end`."""
    f = period_dir("views", "recent", raw) / f"{ticker}.csv"
    return not f.exists() or _cached_end(f) < end


def load_prices(tickers: list[str], market: str, end: pd.Timestamp, raw: Path = RAW) -> pd.DataFrame:
    """Daily adjusted closes of the tickers and the market benchmark, cached."""
    f = prices_path(market, raw)
    symbols = tickers + [config.benchmark(market)]
    if f.exists():
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        if set(symbols) <= set(df.columns) and df.index.max() >= end - pd.Timedelta(days=3):
            return df[symbols]
    import yfinance as yf
    df = yf.download(symbols, start=PRICE_START, end=f"{end + pd.Timedelta(days=1):%Y-%m-%d}",
                     auto_adjust=True, progress=False)["Close"][symbols]
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(f)
    return df


def attention_rows(wk_views: pd.Series, wk_edits: pd.Series, ticker: str, market: str) -> pd.DataFrame:
    """Shared-format weekly rows for one stock: source wikipedia_views and wikipedia_edits."""
    parts = []
    for source, col, x in (("wikipedia_views", "views", wk_views), ("wikipedia_edits", "edits", wk_edits)):
        f = flag_spikes(x.astype(float))
        parts.append(f.assign(**{col: x}, ticker=ticker, market=market, source=source)
                     .rename_axis("week").reset_index())
    out = pd.concat(parts, ignore_index=True)
    for c in SHARED_COLS:
        if c not in out:
            out[c] = np.nan
    return out[SHARED_COLS + EXTRA_COLS]


def split_period(df: pd.DataFrame, week_col: str = "week") -> dict[str, pd.DataFrame]:
    """Rows of weeks ending before the holdout (research) and the rest (recent)."""
    research = df[week_col] + pd.Timedelta(days=6) < pd.Timestamp(config.holdout_start())
    return {"research": df[research], "recent": df[~research]}


def build(market: str = "US", end: pd.Timestamp | None = None) -> None:
    """Pull anything missing, then write the shared weekly table, weekly edits and weekly prices."""
    win = windows(end)
    att, edits_all = [], []
    for ticker, titles in universe(market).items():
        log.info("%s: views and edits", ticker)
        starts = article_starts(title_revisions(ticker, titles, win))
        wv = weekly(load_views(ticker, titles, win, starts))
        e = load_edits(ticker, titles, win)
        we = weekly_edits(e, wv.index)
        att.append(attention_rows(wv, we["edits"], ticker, market))
        edits_all.append(we.assign(ticker=ticker, market=market).reset_index())
    for name, df in (("attention", pd.concat(att, ignore_index=True)), ("edits", pd.concat(edits_all, ignore_index=True))):
        for p, part in split_period(df).items():
            f = shared_path(p) if name == "attention" else PROCESSED / f"weekly_edits_{p}.csv"
            f.parent.mkdir(parents=True, exist_ok=True)
            part.assign(week=part["week"].dt.strftime("%Y-%m-%d")).to_csv(f, index=False)
        if name == "attention":   # src/reddit reads one file; its own split keeps it before the holdout
            df.assign(week=df["week"].dt.strftime("%Y-%m-%d")).to_csv(SHARED / "attention_weekly_wikipedia.csv",
                                                                      index=False)
    tickers = list(universe(market))
    panel = weekly_panel(load_prices(tickers, market, win["recent"][1]), tickers, config.benchmark(market), market)
    panel.assign(week=panel["week"].dt.strftime("%Y-%m-%d")).to_csv(PROCESSED / "weekly_prices.csv", index=False)
    log.info("done: %d tickers, weeks up to %s", len(tickers), win["recent"][1].date())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    build()
