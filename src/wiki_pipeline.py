"""Build the Wikipedia data: pull views, edits and prices, then write the weekly tables.

    python -m src.wiki_pipeline          # pulls only what is not cached yet, then rebuilds every table

Research data (before the holdout, config `holdout_start`) and recent data are stored in separate
files; the recent files are for the dashboard and the last-3-weeks spike check only.

  data/raw/wikipedia/views_{research,recent}/<ticker>.csv      daily views (article + redirects)
  data/raw/wikipedia/revisions_{research,recent}/<lang>/<ticker>.csv  revisions, edit summaries
  data/raw/wikipedia/prices/daily_close_<market>.csv           Yahoo adjusted closes
  data/shared/attention_weekly_wikipedia_{research,recent}.csv  shared weekly table (team format)
  data/processed/wikipedia/weekly_edits_{research,recent}.csv  edits, editors, bytes, reverts, tags
  data/processed/wikipedia/weekly_prices.csv                   returns 1-4 weeks after, abnormal returns
"""
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.wiki_attention import article_views, flag_spikes, weekly
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


def universe(market: str = "US", strategy: bool = True) -> dict[str, dict[str, str]]:
    """Ticker -> {language: article title}: the tracked stocks, plus the strategy universe if asked."""
    out = {t: dict(cfg["wikipedia"]) for t, cfg in config.stocks(market).items()}
    if strategy:
        extra = config.load()["wikipedia"]["strategy_universe"].get(market) or {}
        out.update({t: dict(titles) for t, titles in extra.items()})
    return out


def _cached_end(f: Path) -> pd.Timestamp:
    """Last date in a cached date-indexed CSV."""
    return pd.read_csv(f, index_col=0, parse_dates=True).index.max()


def load_views(ticker: str, titles: dict[str, str], win: dict, raw: Path = RAW) -> pd.Series:
    """Daily views of one stock's articles summed over languages, cached per period.

    Both periods are pulled together (one request per title) when either cache file is missing or
    the recent file ends before the requested end (so a weekly rerun picks up the new weeks).
    """
    files = {p: raw / f"views_{p}" / f"{ticker}.csv" for p in PERIODS}
    if not all(f.exists() for f in files.values()) or _cached_end(files["recent"]) < win["recent"][1]:
        start, end = win["research"][0], win["recent"][1]
        s = sum(article_views(title, start, end, lang) for lang, title in titles.items()).rename(ticker)
        for p, (a, b) in win.items():
            files[p].parent.mkdir(parents=True, exist_ok=True)
            s.loc[a:b].rename_axis("date").to_csv(files[p])
    return pd.concat([pd.read_csv(files[p], index_col=0, parse_dates=True).iloc[:, 0] for p in PERIODS])


def load_edits(ticker: str, titles: dict[str, str], win: dict, raw: Path = RAW) -> pd.DataFrame:
    """Revisions of one stock's articles across both periods, each period cached in its own file.

    The recent cache is pulled again when the recent window has grown since it was written.
    """
    revs = []
    for p, (a, b) in win.items():
        for lang, title in titles.items():
            f = raw / f"revisions_{p}" / lang / f"{ticker}.csv"
            if p == "recent" and f.exists() and _views_behind(raw, ticker, b):
                f.unlink()
            revs.append(load_revisions(ticker, title, a, b, raw / f"revisions_{p}" / lang, lang).assign(lang=lang))
    # the earlier period's last revision is the later period's `before_start`; keep one copy
    df = pd.concat(revs).drop_duplicates(["lang", "revid"]).sort_values("timestamp")
    df["before_start"] = df["timestamp"] < win["research"][0]
    return pd.concat([edit_table(g) for _, g in df.groupby("lang")]).sort_values("timestamp")


def _views_behind(raw: Path, ticker: str, end: pd.Timestamp) -> bool:
    """True when the recent views cache was written for an earlier end date than `end`."""
    f = raw / "views_recent" / f"{ticker}.csv"
    return not f.exists() or _cached_end(f) < end


def load_prices(tickers: list[str], market: str, end: pd.Timestamp, raw: Path = RAW) -> pd.DataFrame:
    """Daily adjusted closes of the tickers and the market benchmark, cached."""
    f = raw / "prices" / f"daily_close_{market}.csv"
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
        wv = weekly(load_views(ticker, titles, win))
        e = load_edits(ticker, titles, win)
        we = weekly_edits(e, wv.index)
        att.append(attention_rows(wv, we["edits"], ticker, market))
        edits_all.append(we.assign(ticker=ticker, market=market).reset_index())
    for name, df in (("attention", pd.concat(att, ignore_index=True)), ("edits", pd.concat(edits_all, ignore_index=True))):
        for p, part in split_period(df).items():
            f = shared_path(p) if name == "attention" else PROCESSED / f"weekly_edits_{p}.csv"
            f.parent.mkdir(parents=True, exist_ok=True)
            part.assign(week=part["week"].dt.strftime("%Y-%m-%d")).to_csv(f, index=False)
    tickers = list(universe(market))
    panel = weekly_panel(load_prices(tickers, market, win["recent"][1]), tickers, config.benchmark(market), market)
    panel.assign(week=panel["week"].dt.strftime("%Y-%m-%d")).to_csv(PROCESSED / "weekly_prices.csv", index=False)
    log.info("done: %d tickers, weeks up to %s", len(tickers), win["recent"][1].date())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    build()
