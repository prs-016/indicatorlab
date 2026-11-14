"""Reddit routes of the Indicator Lab API (Week 2, Step 8).

  GET /sentiment?ticker=AAPL&start=2024-01-01&end=2025-09-30[&source=reddit_product]
      weekly sentiment per source, plus up to 3 sample posts for every spike week
  GET /spikes?ticker=AAPL&start=...&end=...[&source=...]
      flagged weeks only, with attention, sentiment, and returns 1 to 4 weeks after

Data comes from files the pipeline writes (paths in RedditStore); nothing is computed per request.
The API serves research and recent weeks alike: it feeds the dashboard and the spike check, which
the holdout rule allows. Research code must not read data through it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from src import config
from src.reddit import settings
from src.reddit.reddit_weekly import OUT_RECENT, OUT_RESEARCH, SAMPLES_PATH, SOURCES

router = APIRouter(tags=["reddit"])

Source = Literal["reddit_product", "reddit_stock"]
SAMPLES_PER_SPIKE = 3
PRICES_PATH = settings.PROCESSED / "weekly_prices.csv"
SENTIMENT_COLS = ["posts", "n_scored", "sentiment_mean", "pct_positive", "pct_negative", "spike"]
ATTENTION_COLS = ["posts", "comments", "upvotes", "baseline", "ratio", "rz"]
RETURN_COLS = ["ret", "ret_next1", "ret_next2", "ret_next3", "ret_next4",
               "abn_ret", "abn_ret_next1", "abn_ret_next2", "abn_ret_next3", "abn_ret_next4"]


@dataclass
class RedditStore:
    """The weekly attention table, spike-week sample posts and weekly prices, loaded once."""
    attention: pd.DataFrame
    samples: pd.DataFrame
    prices: pd.DataFrame

    @classmethod
    def from_files(cls, attention_paths: list[Path], samples_path: Path, prices_path: Path) -> "RedditStore":
        att = pd.concat([pd.read_csv(p) for p in attention_paths if p.exists()], ignore_index=True) \
            if any(p.exists() for p in attention_paths) else pd.DataFrame(columns=["week", "ticker", "source"])
        smp = pd.read_parquet(samples_path) if samples_path.exists() else pd.DataFrame(
            columns=["week", "ticker", "source", "rank"])
        prc = pd.read_csv(prices_path) if prices_path.exists() else pd.DataFrame(columns=["week", "ticker"])
        for df in (att, smp, prc):
            df["week"] = pd.to_datetime(df["week"]).dt.strftime("%Y-%m-%d")
        return cls(att, smp, prc)


@lru_cache(maxsize=1)
def get_store() -> RedditStore:
    """The store built from the pipeline's output files (overridden in tests).

    Loaded once per process: restart the API after the pipeline rewrites its tables.
    """
    return RedditStore.from_files([OUT_RESEARCH, OUT_RECENT], SAMPLES_PATH, PRICES_PATH)


def _known_tickers() -> set[str]:
    return {t for m in config.markets() for t in config.tickers(m)}


def _check(ticker: str, start: date, end: date) -> str:
    t = ticker.upper()
    if t not in _known_tickers():
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker}")
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    return t


def _clean(v):
    """JSON-safe scalar: NaN -> None, numpy types -> Python."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    return [{c: _clean(r[c]) for c in cols if c in df.columns} for _, r in df.iterrows()]


def _window(df: pd.DataFrame, ticker: str, start: date, end: date, source: str | None) -> pd.DataFrame:
    m = (df["ticker"] == ticker) & (df["week"] >= start.isoformat()) & (df["week"] <= end.isoformat())
    if source is not None and "source" in df.columns:
        m &= df["source"] == source
    return df[m].sort_values(["week"] + (["source"] if "source" in df.columns else []))


@router.get("/sentiment")
def sentiment(ticker: str, start: date, end: date, source: Source | None = Query(None),
              store: RedditStore = Depends(get_store)) -> dict:
    """Weekly Reddit sentiment per source, and up to 3 top posts for each spike week."""
    t = _check(ticker, start, end)
    att = _window(store.attention, t, start, end, source)
    out = {"ticker": t, "start": start.isoformat(), "end": end.isoformat(), "sources": {}}
    for src in ([source] if source else SOURCES):
        rows = att[att["source"] == src]
        weeks = []
        for _, r in rows.iterrows():
            w = {"week": r["week"], **{c: _clean(r[c]) for c in SENTIMENT_COLS}}
            if bool(r["spike"]):
                s = store.samples[(store.samples["ticker"] == t) & (store.samples["source"] == src) &
                                  (store.samples["week"] == r["week"])].sort_values("rank").head(SAMPLES_PER_SPIKE)
                w["sample_posts"] = _records(s, ["post_id", "subreddit", "title", "score", "num_comments", "url",
                                                 "sentiment_label"])
            weeks.append(w)
        out["sources"][src] = weeks
    out["market"] = _clean(att["market"].iloc[0]) if len(att) else None
    return out


@router.get("/spikes")
def spikes(ticker: str, start: date, end: date, source: Source | None = Query(None),
           store: RedditStore = Depends(get_store)) -> dict:
    """Spike weeks only, with attention, sentiment and the stock's returns 1 to 4 weeks after."""
    t = _check(ticker, start, end)
    att = _window(store.attention, t, start, end, source)
    flagged = att[att["spike"].astype(bool)]
    merged = flagged.merge(store.prices[["week", "ticker", *[c for c in RETURN_COLS if c in store.prices]]],
                           on=["week", "ticker"], how="left")
    cols = ["week", "source", *ATTENTION_COLS, "sentiment_mean", "pct_positive", "pct_negative", "n_scored",
            *RETURN_COLS]
    return {"ticker": t, "start": start.isoformat(), "end": end.isoformat(), "n_spikes": len(merged),
            "spikes": _records(merged, cols)}
