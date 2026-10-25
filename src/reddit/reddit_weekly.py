"""Week 2 weekly Reddit attention and sentiment per stock and source, in the shared team format.

One row per (week, ticker, source), weeks labelled by their Monday (00:00 UTC):

    week, ticker, market, source, posts, comments, upvotes, views, edits, sentiment_mean,
    pct_positive, pct_negative, baseline, ratio, spike   (+ n_scored, abnormal, rz, coverage_complete)

Sources:
  reddit_product  product subreddits (every post is the company's) and sector subreddits (text-matched)
  reddit_stock    the ticker's own stock subreddits and the general investor subreddits (text-matched)

`views` and `edits` are Wikipedia columns and stay empty here. A (ticker, source) week counts only
when every subreddit feeding it was collected on all 7 days; otherwise its metrics are NaN, never 0.
Sentiment columns come from data/reddit/processed/post_sentiment.parquet when it exists.
`baseline`, `ratio` and `spike` apply the shared rule (src/reddit/spike_rule.py) to `posts`.

Research rows (weeks ending before the holdout date) and recent rows go to separate files:
attention_weekly_research.csv and attention_weekly_recent.csv. spike_week_samples.parquet keeps the
top posts (by score) of every spike week, for the API and for reading what happened.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.build_posts import attach_text
from src.reddit.spike_rule import add_spikes
from src.reddit.utils import get_logger
from src.reddit.weekly_metrics import week_start

log = get_logger("reddit_weekly", "pipeline.log")

SOURCE_OF_TYPE = {"product": "reddit_product", "sector": "reddit_product",
                  "stock": "reddit_stock", "general": "reddit_stock"}
SOURCES = ["reddit_product", "reddit_stock"]
SHARED_COLS = ["week", "ticker", "market", "source", "posts", "comments", "upvotes", "views", "edits",
               "sentiment_mean", "pct_positive", "pct_negative", "baseline", "ratio", "spike"]
EXTRA_COLS = ["n_scored", "abnormal", "rz", "coverage_complete", "subreddits", "days_missing"]
SENTIMENT_PATH = settings.PROCESSED / "post_sentiment.parquet"
OUT_RESEARCH = settings.PROCESSED / "attention_weekly_research.csv"
OUT_RECENT = settings.PROCESSED / "attention_weekly_recent.csv"
SAMPLES_PATH = settings.PROCESSED / "spike_week_samples.parquet"
SAMPLES_PER_WEEK = 3


def source_subreddits(market: str = settings.MARKET) -> dict[tuple[str, str], list[str]]:
    """(ticker, source) -> the subreddits whose posts can count for it."""
    sm = config.subreddit_map(market)
    shared = {src: [v["subreddit"].lower() for v in sm.values()
                    if v["ticker"] is None and SOURCE_OF_TYPE[v["type"]] == src] for src in SOURCES}
    out = {}
    for tk in config.tickers(market):
        for src in SOURCES:
            own = [v["subreddit"].lower() for v in sm.values()
                   if v["ticker"] == tk and SOURCE_OF_TYPE[v["type"]] == src]
            out[(tk, src)] = own + shared[src]
    return out


def week_coverage(day_status: pd.DataFrame, weeks: pd.DatetimeIndex, subreddits: list[str]) -> pd.DataFrame:
    """Per (subreddit, week): number of the 7 days collected `complete` (0 for never-collected subreddits)."""
    ds = day_status.assign(date=pd.to_datetime(day_status["date"], utc=True))
    ds = ds[ds["day_status"] == "complete"]
    ds["week"] = week_start(ds["date"])
    n = ds.groupby(["subreddit", "week"]).size().rename("days_complete").reset_index()
    grid = pd.MultiIndex.from_product([sorted(set(subreddits)), weeks],
                                      names=["subreddit", "week"]).to_frame(index=False)
    return grid.merge(n, on=["subreddit", "week"], how="left").fillna({"days_complete": 0})


def build(matches: pd.DataFrame, day_status: pd.DataFrame, sentiment: pd.DataFrame | None = None,
          market: str = settings.MARKET) -> pd.DataFrame:
    """Weekly rows for every (ticker, source, week) between the first and last collected week."""
    mt = matches.copy()
    mt["source"] = mt["subreddit_type"].map(SOURCE_OF_TYPE)
    mt["week"] = week_start(mt["date"])
    if sentiment is not None and len(sentiment):
        mt = mt.merge(sentiment[["post_id", "sentiment_label", "sentiment_score"]], on="post_id", how="left")
    else:
        mt["sentiment_label"], mt["sentiment_score"] = np.nan, np.nan
    days = pd.to_datetime(day_status["date"], utc=True)
    weeks = pd.date_range(week_start(pd.Series([days.min()])).iloc[0], week_start(pd.Series([days.max()])).iloc[0],
                          freq="7D")

    g = mt.groupby(["ticker", "source", "week"])
    agg = g.agg(posts=("post_id", "nunique"), comments=("num_comments", "sum"), upvotes=("score", "sum"),
                sentiment_mean=("sentiment_score", "mean"), n_scored=("sentiment_score", "count"),
                pct_positive=("sentiment_label", lambda s: (s == "positive").sum()),
                pct_negative=("sentiment_label", lambda s: (s == "negative").sum())).reset_index()
    for c in ("pct_positive", "pct_negative"):
        agg[c] = agg[c] / agg["n_scored"].where(agg["n_scored"] > 0)

    src_subs = source_subreddits(market)
    cov = week_coverage(day_status, weeks, [s for subs in src_subs.values() for s in subs])
    rows = []
    for (tk, src), subs in src_subs.items():
        c = cov[cov["subreddit"].isin(subs)].groupby("week")["days_complete"].agg(["min", "sum"])
        rows.append(pd.DataFrame({"ticker": tk, "source": src, "week": weeks, "subreddits": ";".join(subs),
                                  "coverage_complete": c["min"].reindex(weeks).fillna(0).to_numpy() == 7,
                                  "days_missing": (7 * len(subs) - c["sum"].reindex(weeks).fillna(0)).to_numpy()}))
    grid = pd.concat(rows, ignore_index=True)
    df = grid.merge(agg, on=["ticker", "source", "week"], how="left")
    df[["posts", "comments", "upvotes", "n_scored"]] = df[["posts", "comments", "upvotes", "n_scored"]].fillna(0)
    metric_cols = ["posts", "comments", "upvotes", "sentiment_mean", "pct_positive", "pct_negative", "n_scored"]
    df.loc[~df["coverage_complete"], metric_cols] = np.nan
    df["market"], df["views"], df["edits"] = market, np.nan, np.nan
    df = add_spikes(df, ["ticker", "source"], "posts")
    df = df[SHARED_COLS + EXTRA_COLS].sort_values(["week", "ticker", "source"]).reset_index(drop=True)
    assert (df["week"].dt.day_of_week == 0).all(), "weeks must be labelled by Monday"
    return df


def split_holdout(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Research rows (whole week before the holdout date) and recent rows."""
    holdout = pd.Timestamp(settings.HOLDOUT_START, tz="UTC")
    research = df["week"] + pd.Timedelta(days=6) < holdout
    return df[research], df[~research]


def spike_samples(weekly: pd.DataFrame, matches: pd.DataFrame, sentiment: pd.DataFrame | None,
                  n: int = SAMPLES_PER_WEEK) -> pd.DataFrame:
    """Top-`n` posts by score for every flagged (ticker, source, week), with title and link."""
    flagged = weekly.loc[weekly["spike"], ["week", "ticker", "source"]]
    mt = matches.assign(source=matches["subreddit_type"].map(SOURCE_OF_TYPE), week=week_start(matches["date"]))
    mt = mt.merge(flagged, on=["week", "ticker", "source"])
    mt = mt[~mt["removed_flag"]].sort_values("score", ascending=False)
    top = mt.groupby(["week", "ticker", "source"]).head(n).copy()
    top["rank"] = top.groupby(["week", "ticker", "source"]).cumcount() + 1
    if top.empty:
        return pd.DataFrame(columns=["week", "ticker", "source", "rank", "post_id", "subreddit", "title", "score",
                                     "num_comments", "url", "sentiment_label"])
    top = attach_text(top, ("title",))
    top["url"] = "https://www.reddit.com" + top["permalink"].fillna("")
    if sentiment is not None and len(sentiment):
        top = top.merge(sentiment[["post_id", "sentiment_label"]], on="post_id", how="left")
    else:
        top["sentiment_label"] = None
    top["week"] = top["week"].dt.strftime("%Y-%m-%d")
    return top[["week", "ticker", "source", "rank", "post_id", "subreddit", "title", "score", "num_comments", "url",
                "sentiment_label"]].sort_values(["week", "ticker", "source", "rank"])


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build both files from the processed matches, day status and (if present) post sentiment."""
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet",
                         columns=["post_id", "ticker", "subreddit", "subreddit_type", "date", "score", "num_comments",
                                  "permalink", "removed_flag"])
    ds = pd.read_csv(settings.PROCESSED / "day_status.csv")
    sent = pd.read_parquet(SENTIMENT_PATH) if SENTIMENT_PATH.exists() else None
    df = build(mt, ds, sent)
    spike_samples(df, mt, sent).to_parquet(SAMPLES_PATH, index=False)
    research, recent = split_holdout(df)
    for part, path in ((research, OUT_RESEARCH), (recent, OUT_RECENT)):
        out = part.copy()
        out["week"] = out["week"].dt.strftime("%Y-%m-%d")
        out.to_csv(path, index=False)
        log.info("%s: %d rows, %d weeks, %d spikes", path.name, len(out), out["week"].nunique(),
                 int(out["spike"].sum()))
    return research, recent


if __name__ == "__main__":
    run()
