"""Reddit routes for the single Indicator Lab API (James's service mounts this router).

    from src.api.reddit_routes import router
    app.include_router(router)          # serves /reddit/...

  GET /reddit/attention/{ticker}?market=us&from=YYYY-MM-DD&to=YYYY-MM-DD   weekly attention records
  GET /reddit/sentiment/{ticker}?market=us&from=...&to=...                 weekly FinBERT sentiment, investor
                                                                            vs company/product subreddits
  GET /reddit/top-posts/{ticker}?week=YYYY-MM-DD&market=us&limit=10        that week's top posts by score

Responses use the shared attention-record fields, so the dashboard treats Reddit and Wikipedia the same.
All three are research endpoints: weeks from the holdout date (2025-10-01) on are never returned.
Data comes from src/api/reddit_data.py (local folder or S3 via INDICATORLAB_DATA_URI).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.reddit_data import RedditData, get_reddit_data, research_cutoff
from src.reddit.reddit_weekly import TOP_POSTS_PER_WEEK

router = APIRouter(prefix="/reddit", tags=["reddit"])

Market = Literal["us", "india", "hk"]
From = Annotated[date | None, Query(alias="from", description="first week (inclusive)")]
To = Annotated[date | None, Query(alias="to", description="last week (inclusive)")]
Data = Annotated[RedditData, Depends(get_reddit_data)]
Limit = Annotated[int, Query(ge=1, le=TOP_POSTS_PER_WEEK)]


class AttentionRecord(BaseModel):
    """One ticker x source x week: the shared attention record."""

    ticker: str
    market: Market
    source: Literal["reddit", "wikipedia"]
    week: date
    value: float | None
    baseline: float | None
    ratio: float | None
    spike: bool
    sentiment_pos: float | None
    sentiment_neg: float | None
    sentiment_neu: float | None
    n_scored: int | None


class SentimentRecord(AttentionRecord):
    """An attention record for one subreddit type, plus net sentiment (pos - neg)."""

    subreddit_type: Literal["investor", "product"]
    sentiment_net: float | None


class TopPost(BaseModel):
    """One of the week's highest-scoring posts about the ticker."""

    ticker: str
    market: Market
    week: date
    rank: int
    post_id: str
    subreddit: str
    subreddit_type: Literal["investor", "product"] | None
    title: str
    url: str
    score: int | None
    num_comments: int | None
    sentiment_label: str | None
    sentiment_pos: float | None
    sentiment_neg: float | None
    sentiment_neu: float | None


def _clean(v):
    """NaN / NA -> None and numpy scalars -> Python values, for JSON."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    return v.item() if hasattr(v, "item") else v


def _rows(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def _check_ticker(data: RedditData, ticker: str, market: str) -> str:
    """Upper-cased ticker, or 404 when Reddit has no data for it in that market."""
    t = ticker.upper()
    if t not in data.tickers(market):
        known = ", ".join(sorted(data.tickers(market))) or "none yet"
        raise HTTPException(404, f"No Reddit data for ticker '{t}' in market '{market}' (tracked: {known})")
    return t


def _window(df: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    if start and end and start > end:
        raise HTTPException(422, "'from' must not be after 'to'")
    if start:
        df = df[df["week"] >= start]
    if end:
        df = df[df["week"] <= end]
    return df


@router.get("/attention/{ticker}", response_model=list[AttentionRecord])
def attention(ticker: str, data: Data, market: Market = "us", start: From = None, end: To = None):
    """Weekly Reddit attention records for one ticker (research weeks only)."""
    t = _check_ticker(data, ticker, market)
    df = data.weekly[(data.weekly["ticker"] == t) & (data.weekly["market"] == market)]
    return _rows(_window(df, start, end).sort_values("week"))


@router.get("/sentiment/{ticker}", response_model=list[SentimentRecord])
def sentiment(ticker: str, data: Data, market: Market = "us", start: From = None, end: To = None):
    """Weekly FinBERT sentiment, one row per week and subreddit type (investor / product)."""
    t = _check_ticker(data, ticker, market)
    df = data.by_type[(data.by_type["ticker"] == t) & (data.by_type["market"] == market)]
    df = _window(df, start, end).assign(sentiment_net=lambda x: x["sentiment_pos"] - x["sentiment_neg"])
    return _rows(df.sort_values(["week", "subreddit_type"]))


@router.get("/top-posts/{ticker}", response_model=list[TopPost])
def top_posts(ticker: str, week: date, data: Data, market: Market = "us", limit: Limit = TOP_POSTS_PER_WEEK):
    """The week's top posts by score (any date in the week works; weeks start on Monday)."""
    t = _check_ticker(data, ticker, market)
    monday = week - timedelta(days=week.weekday())
    if pd.Timestamp(monday) >= research_cutoff():
        raise HTTPException(404, f"week {monday} is in the holdout period; research endpoints stop before it")
    df = data.top_posts[(data.top_posts["ticker"] == t) & (data.top_posts["market"] == market)
                        & (data.top_posts["week"] == monday)]
    return _rows(df.sort_values("rank").head(limit))
