"""Wikipedia tables in the team's attention record format, for the API and dashboard (Week 3, James).

Attention record (Week 3 guide, Shared section): one row per ticker x source x week with
    ticker, market (us / india / hk), source (wikipedia), week (Monday),
    value, baseline (8-week median), ratio, spike, sentiment_pos, sentiment_neg, sentiment_neu, n_scored
For Wikipedia, `value` is weekly page views and the sentiment is FinBERT on the article text added that
week (src/wiki_sentiment.py). Edits ride along in the same row as `edits`, `edits_baseline`,
`edits_ratio` and `edits_spike`, since the dashboard plots both and the record has one value.

  wiki_weekly.parquet    research weeks only (ending before the holdout), from the shared weekly table
  wiki_current.parquet   "Hot right now": trailing 7 days of views to the last day Wikimedia has
                         published, against the median of the 8 full weeks before them
  prices_weekly.parquet  research weeks of the weekly price panel (for the API's /spikes and /prices)
  wiki_edit_summaries.parquet  research-period edits (time, summary, size change, revert, tags; no
                         usernames), for the dashboard's "What happened" panel (/edits)

    python -m src.wiki_export            # writes them to data/processed/, the bucket's processed/ layout
"""
import numpy as np
import pandas as pd

from src import config
from src.wiki_attention import flag_spikes, week_start, weekly
from src.wiki_edits import edit_table

RECORD_COLS = ["ticker", "market", "source", "week", "value", "baseline", "ratio", "spike",
               "sentiment_pos", "sentiment_neg", "sentiment_neu", "n_scored"]
EDIT_COLS = ["edits", "edits_baseline", "edits_ratio", "edits_spike"]
MARKET_NAMES = {"US": "us", "IN": "india", "HK": "hk"}   # config codes -> the record's market names
SENT_COLS = ["sentiment_pos", "sentiment_neg", "sentiment_neu", "n_scored"]
SUMMARY_COLS = ["ticker", "market", "week", "timestamp", "title", "comment", "delta", "revert"]
TRAILING_DAYS = 7


def weekly_records(att: pd.DataFrame, sentiment: pd.DataFrame | None = None) -> pd.DataFrame:
    """Shared-table rows (wikipedia_views + wikipedia_edits) -> one attention record per ticker-week.

    `sentiment` is the weekly edit sentiment (ticker, week, sentiment_pos/neg/neu, n_scored); weeks
    without it get NaN probabilities and n_scored 0.
    """
    a = att.assign(week=pd.to_datetime(att["week"]))
    v = a[a["source"] == "wikipedia_views"].drop(columns=["edits", *SENT_COLS], errors="ignore")
    v = v.rename(columns={"views": "value"})
    e = a[a["source"] == "wikipedia_edits"][["ticker", "week", "edits", "baseline", "ratio", "spike"]]
    e = e.rename(columns={"baseline": "edits_baseline", "ratio": "edits_ratio", "spike": "edits_spike"})
    out = v.merge(e, on=["ticker", "week"], how="left")
    if sentiment is not None:
        s = sentiment.assign(week=pd.to_datetime(sentiment["week"]))[["ticker", "week", *SENT_COLS]]
        out = out.merge(s, on=["ticker", "week"], how="left")
    for c in SENT_COLS:
        if c not in out:
            out[c] = np.nan
    out = out.assign(source="wikipedia", market=out["market"].map(MARKET_NAMES).fillna(out["market"]),
                     n_scored=out["n_scored"].fillna(0).astype(int),
                     edits_spike=out["edits_spike"].astype("boolean"))
    return out[RECORD_COLS + EDIT_COLS].sort_values(["ticker", "week"]).reset_index(drop=True)


def current_record(daily: pd.Series, ticker: str, market: str) -> dict:
    """One stock's "Hot right now" row from its daily views.

    The value is the sum of the last TRAILING_DAYS published days; the baseline is the median of the
    8 full weeks (config `spike.baseline_weeks`) that ended before that window began, and the spike
    flag is the shared rule applied as if the window were the next week.
    """
    daily = daily.dropna().sort_index()
    as_of = daily.index.max()
    start = as_of - pd.Timedelta(days=TRAILING_DAYS - 1)
    full = weekly(daily[daily.index < start]).asfreq("7D")   # full weeks only; gaps as NaN for flag_spikes
    window = daily[daily.index >= start]
    value = float(window.sum()) if len(window) == TRAILING_DAYS else np.nan
    x = pd.concat([full, pd.Series([value], index=[start.normalize()])])
    f = flag_spikes(x.astype(float)).iloc[-1]
    return {"ticker": ticker, "market": MARKET_NAMES.get(market, market), "source": "wikipedia",
            "week": week_start(pd.DatetimeIndex([as_of]))[0], "value": value, "baseline": f["baseline"],
            "ratio": f["ratio"], "spike": bool(f["spike"]), "sentiment_pos": np.nan, "sentiment_neg": np.nan,
            "sentiment_neu": np.nan, "n_scored": 0, "as_of": as_of}


def edit_summaries(revs: pd.DataFrame, ticker: str, market: str, holdout: pd.Timestamp) -> pd.DataFrame:
    """One row per edit in a week ending before the holdout: week, time, article, summary, size change,
    revert and tag flags."""
    e = edit_table(revs.assign(comment=revs["comment"].fillna("")))
    e = e.assign(ticker=ticker, market=MARKET_NAMES[market], week=week_start(e["timestamp"]))
    e = e[e["week"] + pd.Timedelta(days=6) < holdout]
    tags = [c for c in e.columns if c.startswith("tag_")]
    return e[SUMMARY_COLS + tags].reset_index(drop=True)


def build(market: str = "US") -> dict[str, pd.DataFrame]:
    """Write the wiki_*.parquet tables and prices_weekly.parquet from the pipeline's files."""
    from src.wiki_pipeline import (
        PROCESSED,
        RAW,
        ROOT,
        article_titles,
        cache_stem,
        shared_path,
        universe,
    )
    holdout = pd.Timestamp(config.holdout_start())
    # edit sentiment for every stock (`python -m src.wiki_sentiment strategy`), else the tracked stocks only
    sent_f = next((f for f in (PROCESSED / "edit_sentiment_weekly_research_strategy.csv",
                               PROCESSED / "edit_sentiment_weekly_research.csv") if f.exists()), None)
    sent = pd.read_csv(sent_f) if sent_f else None
    wk = weekly_records(pd.read_csv(shared_path("research")), sent)
    wk = wk[wk["week"] + pd.Timedelta(days=6) < holdout]
    rows, summaries = [], []
    for ticker, titles in universe(market).items():
        for lang, title in article_titles(titles):   # the cached research-period revisions, no network
            f = RAW / "revisions_research" / lang / f"{cache_stem(ticker, titles, lang, title)}.csv"
            if f.exists():
                revs = pd.read_csv(f, parse_dates=["timestamp"]).assign(title=title)
                summaries.append(edit_summaries(revs, ticker, market, holdout))
        views = [pd.read_csv(RAW / f"views_{p}" / f"{ticker}.csv", index_col=0, parse_dates=True)[ticker]
                 for p in ("research", "recent")]
        rows.append(current_record(pd.concat(views), ticker, market))
    cur = pd.DataFrame(rows).sort_values("ratio", ascending=False).reset_index(drop=True)
    prices = pd.read_csv(PROCESSED / "weekly_prices.csv", parse_dates=["week"])
    prices = prices[prices["week"] + pd.Timedelta(days=6) < holdout].assign(market=MARKET_NAMES[market])
    out = ROOT / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    wk.to_parquet(out / "wiki_weekly.parquet", index=False)
    cur.to_parquet(out / "wiki_current.parquet", index=False)
    prices.to_parquet(out / "prices_weekly.parquet", index=False)
    edits = pd.concat(summaries, ignore_index=True)
    edits.to_parquet(out / "wiki_edit_summaries.parquet", index=False)
    return {"weekly": wk, "current": cur, "prices": prices, "edits": edits}


if __name__ == "__main__":
    out = build()
    print(len(out["weekly"]), "weekly records, last week", out["weekly"]["week"].max().date())
    print(out["current"].head(10).to_string(index=False))
