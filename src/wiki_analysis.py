"""Week 2 Wikipedia analyses on the pipeline's tables (see src/wiki_pipeline.py).

  spike_returns     returns 1-4 weeks after view (or edit) spike weeks vs normal weeks, bootstrap CIs
  edit_timing       do edit spikes come before, with or after view spikes and big price moves?
  daily_peak_lag    days between the peak-views day and the peak-edits day around view spikes
  tag_lift          how much more often each summary tag appears in view-spike weeks
  summary_tone      VADER tone of edit summaries (do summaries carry tone at all?)
  last_weeks_table  Wikipedia columns of the last-3-weeks spike check (with Joshua)
"""
import numpy as np
import pandas as pd

from src.wiki_prices import FORWARD_WEEKS, bootstrap_diff

LAGS = (-2, -1, 0, 1, 2)       # weeks relative to the event week
PEAK_WINDOW_DAYS = 7           # look for the edits peak within +-7 days of the views peak
BIG_MOVE_QUANTILE = 0.95       # a "big price move": |abnormal return| in a stock's top 5% of weeks
VADER_CUTOFF = 0.05            # VADER authors' neutral band, as in Joshua's scorers


def spike_flags(att: pd.DataFrame, source: str) -> pd.DataFrame:
    """week, ticker, spike, ratio for one source of the shared table (weeks as Timestamps)."""
    a = att[att["source"] == source]
    return a.assign(week=pd.to_datetime(a["week"]))[["week", "ticker", "spike", "ratio"]]


def spike_returns(att: pd.DataFrame, prices: pd.DataFrame, source: str = "wikipedia_views",
                  tickers: list[str] | None = None, **boot) -> pd.DataFrame:
    """Mean return k weeks after spike weeks minus after normal weeks, for k = 1..4, raw and abnormal."""
    f = spike_flags(att, source)
    d = f.merge(prices.assign(week=pd.to_datetime(prices["week"])), on=["week", "ticker"])
    if tickers is not None:
        d = d[d["ticker"].isin(tickers)]
    # k-week returns of neighbouring weeks overlap, so resample blocks of k weeks
    rows = [bootstrap_diff(d, f"{kind}{k}", block=k, **boot) for kind in ("ret_next", "abn_ret_next")
            for k in range(1, FORWARD_WEEKS + 1)]
    return pd.DataFrame(rows).assign(source=source, n_tickers=d["ticker"].nunique())


def _event_rates(events: pd.DataFrame, signal: pd.DataFrame, col: str) -> pd.DataFrame:
    """Share of events with `col` True at each lag, and the same share over all weeks (base rate)."""
    s = signal.set_index(["ticker", "week"])[col].astype(bool)
    out = []
    for lag in LAGS:
        keys = list(zip(events["ticker"], events["week"] + pd.Timedelta(weeks=lag)))
        hit = s.reindex(keys)
        out.append({"lag_weeks": lag, "share": hit.mean(), "n_events": int(hit.notna().sum())})
    return pd.DataFrame(out).assign(base_rate=s.mean())


def edit_timing(att: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Edit-spike rate around view-spike weeks and big-price-move weeks, by lag (negative = edits first).

    Descriptive only: a "big move" uses each stock's whole research-period distribution of |abnormal
    return|, so it is not a tradeable (past-only) signal.
    """
    views, edits = spike_flags(att, "wikipedia_views"), spike_flags(att, "wikipedia_edits")
    p = prices.assign(week=pd.to_datetime(prices["week"])).dropna(subset=["abn_ret"])
    cut = p.groupby("ticker")["abn_ret"].transform(lambda r: r.abs().quantile(BIG_MOVE_QUANTILE))
    big = p[p["abn_ret"].abs() >= cut]
    parts = [
        _event_rates(views[views["spike"]], edits, "spike").assign(event="views spike", signal="edits spike"),
        _event_rates(big, edits, "spike").assign(event="big price move", signal="edits spike"),
        _event_rates(big, views, "spike").assign(event="big price move", signal="views spike"),
    ]
    out = pd.concat(parts, ignore_index=True)
    out["lift"] = out["share"] / out["base_rate"]
    return out[["event", "signal", "lag_weeks", "share", "base_rate", "lift", "n_events"]]


def _mean_peak_day(s: pd.Series) -> pd.Timestamp:
    """Mean date of the days where `s` reaches its maximum."""
    tied = s.index[s == s.max()]
    return tied[0] + (tied - tied[0]).to_series().mean()


def daily_peak_lag(views_daily: pd.Series, edits_daily: pd.Series, spike_weeks: list[pd.Timestamp]) -> pd.Series:
    """For each spike week: (day of most edits) - (day of most views), in days, edits peak within +-7 days.

    Edit counts are small, so several days often tie for the most edits; a tie counts as the mean of
    the tied days (a first-day rule would bias the lag toward "edits first"). Same for tied view peaks.
    """
    lags = {}
    for w in spike_weeks:
        week = views_daily.loc[w: w + pd.Timedelta(days=6)]
        if week.empty:
            continue
        peak_v = _mean_peak_day(week)
        around = edits_daily.loc[peak_v - pd.Timedelta(days=PEAK_WINDOW_DAYS): peak_v + pd.Timedelta(days=PEAK_WINDOW_DAYS)]
        if around.sum() > 0:
            lags[w] = (_mean_peak_day(around) - peak_v) / pd.Timedelta(days=1)
    return pd.Series(lags, dtype=float, name="edit_peak_minus_view_peak_days")


def tag_lift(weekly_edits: pd.DataFrame, att: pd.DataFrame) -> pd.DataFrame:
    """Tagged edits per week in view-spike weeks vs other weeks, per tag."""
    v = spike_flags(att, "wikipedia_views")
    d = weekly_edits.assign(week=pd.to_datetime(weekly_edits["week"])).merge(v, on=["week", "ticker"])
    tags = [c for c in d.columns if c.startswith("tag_")] + ["edits", "reverts"]
    g = d.groupby("spike")[tags].mean().T
    g.columns = ["normal_weeks", "spike_weeks"]
    g["lift"] = g["spike_weeks"] / g["normal_weeks"]
    g["total"] = d[tags].sum()
    return g.sort_values("lift", ascending=False)


def summary_tone(comments: pd.Series) -> dict:
    """Share of edit summaries VADER calls neutral, positive or negative (empty summaries excluded)."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    c = comments[comments.str.strip() != ""]
    s = np.array([sia.polarity_scores(t)["compound"] for t in c])
    return {"n_summaries": len(c), "share_empty": 1 - len(c) / len(comments),
            "share_neutral": float(np.mean(np.abs(s) < VADER_CUTOFF)),
            "share_positive": float(np.mean(s >= VADER_CUTOFF)), "share_negative": float(np.mean(s <= -VADER_CUTOFF))}


def last_weeks_table(att_recent: pd.DataFrame, prices: pd.DataFrame, weeks: list[str], tickers: list[str]) -> pd.DataFrame:
    """ticker x week: Wikipedia views and edits (value, ratio, spike) and the price move that week and the next."""
    a = att_recent[att_recent["week"].isin(weeks) & att_recent["ticker"].isin(tickers)]
    cols = {"wikipedia_views": "views", "wikipedia_edits": "edits"}
    parts = []
    for src, col in cols.items():
        s = a[a["source"] == src][["ticker", "market", "week", col, "ratio", "rz", "spike"]]
        parts.append(s.rename(columns={"ratio": f"wiki_{col}_ratio", "rz": f"wiki_{col}_rz",
                                       "spike": f"wiki_{col}_spike", col: f"wiki_{col}"})
                     .set_index(["ticker", "market", "week"]))
    out = pd.concat(parts, axis=1).reset_index()
    p = prices[["week", "ticker", "ret", "ret_next1", "abn_ret"]].rename(
        columns={"ret": "ret_week", "ret_next1": "ret_next_week", "abn_ret": "abn_ret_week"})
    out = out.merge(p, on=["week", "ticker"], how="left")
    return out.sort_values(["ticker", "week"]).reset_index(drop=True)
