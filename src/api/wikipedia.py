"""Shared-table and price routes of the Indicator Lab API (Week 2, James step 9).

  GET /tickers
      every stock and source in the shared weekly tables, with first week, last week and week count
  GET /attention?ticker=AAPL&start=2024-01-01&end=2025-09-30&source=wikipedia,reddit_product
      weekly rows of the shared table; a source matches exactly or as a prefix
      (`wikipedia` = wikipedia_views + wikipedia_edits); no source = all sources
  GET /price?ticker=AAPL&start=...&end=...
      weekly close, return, returns 1 to 4 weeks after, and abnormal returns against the benchmark

Data comes from files the pipelines write (every data/shared/attention_weekly_*.csv, so Reddit rows
appear once they are there, and the weekly price file); nothing is computed per request. The API feeds
the dashboard and the spike check, which the holdout rule allows; research code must not read through it.
"""
import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from src import config
from src.wiki_pipeline import PROCESSED, SHARED

router = APIRouter(tags=["attention and prices"])

PRICE_COLS = ["week", "close", "ret", "ret_next1", "ret_next2", "ret_next3", "ret_next4",
              "beta", "abn_ret", "abn_ret_next1", "abn_ret_next2", "abn_ret_next3", "abn_ret_next4"]


@dataclass
class Store:
    """The shared weekly attention rows and weekly prices, loaded once."""
    attention: pd.DataFrame
    prices: pd.DataFrame

    @classmethod
    def from_files(cls, attention_paths: list[Path], prices_path: Path) -> "Store":
        att = pd.concat([pd.read_csv(p) for p in attention_paths], ignore_index=True) if attention_paths \
            else pd.DataFrame(columns=["week", "ticker", "market", "source"])
        prc = pd.read_csv(prices_path) if prices_path.exists() else pd.DataFrame(columns=["week", "ticker"])
        return cls(att, prc)


@lru_cache(maxsize=1)
def get_store() -> Store:
    """The store built from the pipeline output files (overridden in tests).

    Loaded once per process: restart the API after a pipeline rewrites its tables.
    """
    return Store.from_files(sorted(SHARED.glob("attention_weekly_*.csv")), PROCESSED / "weekly_prices.csv")


def _clean(v):
    """JSON-safe scalar: NaN -> None, numpy types -> Python."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{c: _clean(v) for c, v in row.items()} for row in df.to_dict("records")]


def _check(store: Store, ticker: str, start: date, end: date) -> str:
    t = ticker.upper()
    if t not in set(store.attention["ticker"]) | set(store.prices["ticker"]):
        raise HTTPException(status_code=404, detail=f"unknown ticker {ticker}")
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    return t


def _window(df: pd.DataFrame, ticker: str, start: date, end: date) -> pd.DataFrame:
    m = (df["ticker"] == ticker) & (df["week"] >= start.isoformat()) & (df["week"] <= end.isoformat())
    return df[m].sort_values("week")


def _name(ticker: str, market: str) -> str | None:
    try:
        return config.stocks(market).get(ticker, {}).get("name")
    except KeyError:
        return None


StoreDep = Annotated[Store, Depends(get_store)]


@router.get("/tickers")
def tickers(store: StoreDep) -> dict:
    """Stocks and sources in the shared table, with the weeks each source covers."""
    a = store.attention.dropna(subset=["week"])
    cov = a.groupby(["ticker", "market", "source"])["week"].agg(["min", "max", "count"]).reset_index()
    out = []
    for (t, m), g in cov.groupby(["ticker", "market"]):
        out.append({"ticker": t, "market": m, "name": _name(t, m),
                    "sources": [{"source": r.source, "first_week": r.min, "last_week": r.max, "weeks": int(r.count)}
                                for r in g.itertuples()]})
    return {"n_tickers": len(out), "tickers": out}


@router.get("/attention")
def attention(ticker: str, start: date, end: date, store: StoreDep,
              source: Annotated[str | None, Query(description="comma-separated, e.g. wikipedia,reddit_product")]
              = None) -> dict:
    """Weekly rows of the shared attention table for one stock."""
    t = _check(store, ticker, start, end)
    rows = _window(store.attention, t, start, end)
    if source:
        wanted = [s.strip() for s in source.split(",") if s.strip()]
        rows = rows[rows["source"].apply(lambda s: any(s == w or s.startswith(w + "_") for w in wanted))]
    rows = rows.sort_values(["week", "source"])
    return {"ticker": t, "start": start.isoformat(), "end": end.isoformat(),
            "sources": sorted(rows["source"].unique()), "n_rows": len(rows), "rows": _records(rows)}


@router.get("/price")
def price(ticker: str, start: date, end: date, store: StoreDep) -> dict:
    """Weekly close, return, and returns 1 to 4 weeks after, for one stock."""
    t = _check(store, ticker, start, end)
    rows = _window(store.prices, t, start, end)
    cols = [c for c in PRICE_COLS if c in rows.columns]
    return {"ticker": t, "start": start.isoformat(), "end": end.isoformat(), "n_weeks": len(rows),
            "weeks": _records(rows[cols])}
