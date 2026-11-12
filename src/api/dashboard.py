"""Dashboard routes of the single Indicator Lab API (Week 3, James section 2).

  GET /health                        status, and when each source's tables were last written
  GET /attention/{ticker}            weekly attention records (?source=reddit|wikipedia&market=&from=&to=)
  GET /sentiment/{ticker}            weekly sentiment: Reddit by subreddit group, Wikipedia edits
  GET /spikes                        every stock that spiked in a week (?week=YYYY-MM-DD&market=)
  GET /hot                           stocks above their 8-week baseline right now (?market=us|india|hk|all)
  GET /live/{market}                 latest quote per symbol, and whether the market is open
  GET /runs, GET /runs/{run_id}      backtest results, proxied from the Vibe-Trading server

Tables (processed/ in the bucket, see src/api/storage.py): wiki_weekly / reddit_weekly.parquet and
wiki_current / reddit_current.parquet in the attention record format, prices_weekly.parquet for moves.
Research endpoints (/attention, /sentiment, /spikes) never return a week that ends on or after the
holdout start; /hot and /live are display of the current week, which the holdout rule allows.
"""
from __future__ import annotations

import math
import os
from datetime import UTC, date, datetime, time
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src import config
from src.api.storage import Storage, from_env

router = APIRouter(tags=["dashboard"])

SOURCES = ("reddit", "wikipedia")
TABLE_PREFIX = {"reddit": "reddit", "wikipedia": "wiki"}   # processed/reddit_weekly.parquet, wiki_weekly.parquet
MARKETS = ("us", "india", "hk")
VIBE_TIMEOUT_S = 20


class AttentionRecord(BaseModel):
    """The team's attention record (Week 3 guide, Shared section); edits_* are Wikipedia only."""
    ticker: str
    market: str
    source: str
    week: date
    value: float | None
    baseline: float | None
    ratio: float | None
    spike: bool
    sentiment_pos: float | None = None
    sentiment_neg: float | None = None
    sentiment_neu: float | None = None
    n_scored: int = 0
    edits: float | None = None
    edits_ratio: float | None = None
    edits_spike: bool | None = None


class SentimentWeek(BaseModel):
    week: date
    source: str
    group: str            # Reddit: investor / product (or all); Wikipedia: edits
    sentiment_pos: float | None
    sentiment_neg: float | None
    sentiment_neu: float | None
    sentiment_net: float | None
    n_scored: int


class Spike(BaseModel):
    ticker: str
    market: str
    source: str
    ratio: float | None
    sentiment_net: float | None
    repeat: bool          # the same source also spiked in the `api.repeat_weeks` weeks before
    abn_ret_week: float | None
    abn_ret_next_week: float | None
    timing: str | None    # "after": the bigger abnormal move was the spike week itself; "before": the next week


class HotRow(BaseModel):
    ticker: str
    market: str
    source: str
    ratio: float
    spike: bool
    sentiment_net: float | None
    price_change_today_pct: float | None
    as_of: datetime | None


class Quote(BaseModel):
    symbol: str
    price: float | None
    change_pct: float | None
    volume: float | None
    ts_exchange: str | None
    ts_received: str | None
    source: str | None
    hot: bool = False


class LiveMarket(BaseModel):
    market: str
    open: bool
    local_time: datetime
    quotes: list[Quote]


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """The process-wide storage (overridden in tests)."""
    return from_env()


StorageDep = Annotated[Storage, Depends(get_storage)]


def _api() -> dict:
    return config.load()["api"]


def _holdout() -> pd.Timestamp:
    return pd.Timestamp(config.holdout_start())


def _num(v):
    """JSON-safe number: NaN / NA -> None."""
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _rows(df: pd.DataFrame) -> list[dict]:
    return [{k: _num(v) for k, v in r.items()} for r in df.to_dict("records")]


def research_weeks(df: pd.DataFrame) -> pd.DataFrame:
    """Only weeks that end before the holdout start (the research rule), whatever a table holds."""
    if df.empty:
        return df
    w = pd.to_datetime(df["week"])
    return df[w + pd.Timedelta(days=6) < _holdout()].assign(week=w)


def spike_flags(df: pd.DataFrame) -> pd.DataFrame:
    """`spike` as a plain bool (a missing flag is no spike), so one gap cannot fail a whole response."""
    if df.empty or "spike" not in df:
        return df
    return df.assign(spike=df["spike"].astype("boolean").fillna(False).astype(bool))


def weekly(storage: Storage, source: str) -> pd.DataFrame:
    """A source's weekly attention records, holdout weeks removed (for the research routes)."""
    return spike_flags(research_weeks(storage.table(f"processed/{TABLE_PREFIX[source]}_weekly.parquet")))


def current(storage: Storage, source: str) -> pd.DataFrame:
    """A source's "Hot right now" records for the current week (display only, so no holdout cut)."""
    return spike_flags(storage.table(f"processed/{TABLE_PREFIX[source]}_current.parquet"))


def _sources(source: str | None) -> list[str]:
    if source is None:
        return list(SOURCES)
    if source not in SOURCES:
        raise HTTPException(422, f"source must be one of {', '.join(SOURCES)}")
    return [source]


def _known(frames: list[pd.DataFrame], ticker: str) -> None:
    if not any(not f.empty and (f["ticker"] == ticker).any() for f in frames):
        raise HTTPException(404, f"unknown ticker {ticker}: no attention data for it")


@router.get("/health")
def health(storage: StorageDep) -> dict:
    """Up, plus when each processed table was last written (UTC)."""
    keys = [k for k in storage.keys("processed/") if k.endswith(".parquet")]
    fresh = {k.split("/")[-1].removesuffix(".parquet"): storage.modified(k) for k in keys}
    return {"status": "ok", "data_root": "s3" if storage.is_s3 else "local",
            "tables": {k: v.isoformat() if v else None for k, v in fresh.items()}}


@router.get("/attention/{ticker}", response_model=list[AttentionRecord])
def attention(ticker: str, storage: StorageDep, source: str | None = None, market: str | None = None,
              start: Annotated[date | None, Query(alias="from")] = None,
              end: Annotated[date | None, Query(alias="to")] = None) -> list[dict]:
    """Weekly attention records for one stock, oldest first (research weeks only)."""
    t = ticker.upper()
    frames = [weekly(storage, s) for s in _sources(source)]
    _known(frames, t)
    df = pd.concat([f[f["ticker"] == t] for f in frames if not f.empty], ignore_index=True)
    if market:
        df = df[df["market"] == market.lower()]
    if start:
        df = df[df["week"] >= pd.Timestamp(start)]
    if end:
        df = df[df["week"] <= pd.Timestamp(end)]
    cols = [c for c in AttentionRecord.model_fields if c in df.columns]
    return _rows(df.sort_values(["week", "source"])[cols])


@router.get("/sentiment/{ticker}", response_model=list[SentimentWeek])
def sentiment(ticker: str, storage: StorageDep, market: str | None = None) -> list[dict]:
    """Weekly net sentiment per source and group, oldest first (research weeks only).

    Reddit rows use the table's `group` column (investor / product) when it has one; Wikipedia rows
    are FinBERT on the article text added that week.
    """
    t = ticker.upper()
    frames = {s: weekly(storage, s) for s in SOURCES}
    _known(list(frames.values()), t)
    out = []
    for s, f in frames.items():
        if f.empty:
            continue
        d = f[(f["ticker"] == t) & (f["n_scored"] > 0)]
        if market:
            d = d[d["market"] == market.lower()]
        group = d["group"] if "group" in d else pd.Series("edits" if s == "wikipedia" else "all", index=d.index)
        out.append(pd.DataFrame({"week": d["week"], "source": s, "group": group,
                                 "sentiment_pos": d["sentiment_pos"], "sentiment_neg": d["sentiment_neg"],
                                 "sentiment_neu": d["sentiment_neu"],
                                 "sentiment_net": d["sentiment_pos"] - d["sentiment_neg"],
                                 "n_scored": d["n_scored"].astype(int)}))
    df = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=list(SentimentWeek.model_fields))
    return _rows(df.sort_values(["week", "source", "group"]))


@router.get("/spikes", response_model=list[Spike])
def spikes(storage: StorageDep, week: date | None = None, market: str | None = None) -> list[dict]:
    """Every stock and source that spiked in `week` (default: the latest research week), biggest first."""
    frames = [f.assign(source=s) for s in SOURCES if not (f := weekly(storage, s)).empty]
    if not frames:
        return []
    att = pd.concat(frames, ignore_index=True)
    w = pd.Timestamp(week) if week else att["week"].max()
    if w + pd.Timedelta(days=6) >= _holdout():
        raise HTTPException(422, f"week {w.date()} is in the holdout (from {_holdout().date()}); "
                                 "use /hot for the current week")
    if market:
        att = att[att["market"] == market.lower()]
    now = att[(att["week"] == w) & att["spike"]]
    earlier = att[(att["week"] < w) & (att["week"] >= w - pd.Timedelta(weeks=_api()["repeat_weeks"])) & att["spike"]]
    repeat = set(zip(earlier["ticker"], earlier["source"]))
    prices = research_weeks(storage.table("processed/prices_weekly.parquet"))
    p = (prices[prices["week"] == w].drop_duplicates(["ticker", "market"]).set_index(["ticker", "market"])
         if not prices.empty else pd.DataFrame())
    rows = []
    for r in now.sort_values("ratio", ascending=False).itertuples():
        a = _num(p["abn_ret"].get((r.ticker, r.market))) if "abn_ret" in p else None
        n = _num(p["abn_ret_next1"].get((r.ticker, r.market))) if "abn_ret_next1" in p else None
        pos, neg = getattr(r, "sentiment_pos", None), getattr(r, "sentiment_neg", None)
        rows.append({"ticker": r.ticker, "market": r.market, "source": r.source, "ratio": _num(r.ratio),
                     "sentiment_net": _num(pos - neg) if pos is not None and neg is not None else None,
                     "repeat": (r.ticker, r.source) in repeat, "abn_ret_week": a, "abn_ret_next_week": n,
                     "timing": None if a is None or n is None else ("after" if abs(a) >= abs(n) else "before")})
    return rows


def market_open(market: str, now: datetime | None = None) -> tuple[bool, datetime]:
    """Whether `market` is in a trading session now (weekdays; holidays not modelled), and its local time."""
    s = _api()["sessions"][market]
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo(s["tz"]))
    t = local.time()
    in_session = any(time.fromisoformat(a) <= t < time.fromisoformat(b) for a, b in s["hours"])
    return local.weekday() < 5 and in_session, local


def _hot_symbols(storage: Storage) -> set[str]:
    cur = [current(storage, s) for s in SOURCES]
    return {t for c in cur if not c.empty for t in c.loc[c["ratio"] > _api()["hot_ratio"], "ticker"]}


@router.get("/hot", response_model=list[HotRow])
def hot(storage: StorageDep, market: Literal["us", "india", "hk", "all"] = "all") -> list[dict]:
    """Stocks whose trailing-7-day attention is above their 8-week baseline, highest ratio first."""
    frames = [f.assign(source=s) for s in SOURCES if not (f := current(storage, s)).empty]
    if not frames:
        return []
    cur = pd.concat(frames, ignore_index=True)
    cur = cur[cur["ratio"] > _api()["hot_ratio"]]
    if market != "all":
        cur = cur[cur["market"] == market]
    change = {q["symbol"]: q.get("change_pct") for m in ("india", "hk") for q in storage.live(m)}
    net = cur["sentiment_pos"] - cur["sentiment_neg"] if "sentiment_pos" in cur else pd.Series(None, index=cur.index)
    out = pd.DataFrame({"ticker": cur["ticker"], "market": cur["market"], "source": cur["source"],
                        "ratio": cur["ratio"], "spike": cur["spike"], "sentiment_net": net,
                        "price_change_today_pct": cur["ticker"].map(change),
                        "as_of": cur.get("as_of")})
    return _rows(out.sort_values("ratio", ascending=False))


@router.get("/live/{market}", response_model=LiveMarket)
def live(market: Literal["india", "hk"], storage: StorageDep) -> dict:
    """Latest quote per symbol from the live table (the last price when the market is closed)."""
    is_open, local = market_open(market)
    hot_now = _hot_symbols(storage)
    quotes = [{**{k: q.get(k) for k in Quote.model_fields if k != "hot"}, "hot": q.get("symbol") in hot_now}
              for q in sorted(storage.live(market), key=lambda q: q.get("symbol", ""))]
    return {"market": market, "open": is_open, "local_time": local, "quotes": quotes}


def _vibe(path: str) -> object:
    """GET a Vibe-Trading API path with the server-side key; the key never reaches the browser."""
    url, key = os.getenv("VIBE_API_URL"), os.getenv("VIBE_API_KEY")
    if not url:
        raise HTTPException(503, "the Vibe-Trading server is not configured (VIBE_API_URL)")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        r = requests.get(url.rstrip("/") + path, headers=headers, timeout=VIBE_TIMEOUT_S)
    except requests.RequestException as e:
        raise HTTPException(502, f"Vibe-Trading server unreachable: {type(e).__name__}") from None
    if r.status_code == 404:
        raise HTTPException(404, "no such run")
    if not r.ok:
        raise HTTPException(502, f"Vibe-Trading server answered {r.status_code}")
    return r.json()


@router.get("/runs")
def runs() -> object:
    """Backtest runs on the Vibe-Trading server."""
    return _vibe("/runs")


@router.get("/runs/{run_id}")
def run(run_id: str) -> object:
    """One backtest run's results from the Vibe-Trading server."""
    return _vibe(f"/runs/{requests.utils.quote(run_id, safe='')}")
