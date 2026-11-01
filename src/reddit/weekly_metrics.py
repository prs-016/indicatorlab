"""Week 1 (legacy) weekly Reddit chatter metrics per ticker (combined and by subreddit) with 2x spike flags.

Week 2 analyses use reddit_weekly.py (shared format, shared spike rule in spike_rule.py). The tables
written here keep the Week 1 rule so Week 1 results reproduce; every row says so in `spike_rule`.
`week_start` from this module is shared by all Week 2 code.

Weeks start Monday 00:00 UTC. For each (ticker[, subreddit], week):
  posts     number of matching posts
  comments  sum of num_comments (archived snapshot)
  upvotes   sum of score (archived Arctic Shift snapshot, not the live Reddit score)

Completeness: a subreddit-week is complete only if all 7 UTC days were collected
with status `complete`. The combined (all-subreddit) week is complete only if all
three subreddit-weeks are complete. Incomplete weeks get NaN metrics (never 0);
`*_observed` columns keep the counts from whatever days were collected.

Spike definition (same as the team's Google Trends work):
  median_4w   = median of the previous 4 weeks (current week excluded), requiring
                all 4 to be defined (min_periods=4), computed per ticker[/subreddit]
  spike_ratio = current / median_4w, only when median_4w > 0; otherwise NaN
  spike_flag  = spike_ratio >= 2 (False when the ratio is undefined)
Zero-baseline convention: a 0 median makes the ratio undefined (NaN, no spike);
`*_zero_base_nonzero` marks weeks with a 0 baseline but non-zero current activity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.reddit import settings
from src.reddit.utils import get_logger

log = get_logger("weekly_metrics", "pipeline.log")

METRICS = ["posts", "comments", "upvotes"]
# Robustness metric: matching posts that moderators/Reddit/authors had NOT removed when archived.
ALL_METRICS = METRICS + ["posts_visible"]
MIN_BASELINE_POSTS = 5   # for the ranked spike table only
SPIKE_RULE_LABEL = "week1: >= 2x median of previous 4 weeks"   # not the shared Week 2 rule


def week_start(dates: pd.Series) -> pd.Series:
    """Monday 00:00 UTC of the week containing each date/datetime."""
    d = pd.to_datetime(dates, utc=True).dt.normalize()
    return d - pd.to_timedelta(d.dt.day_of_week, unit="D")


def add_spike_columns(df: pd.DataFrame, group_cols: list[str], metrics=METRICS,
                      window: int = settings.SPIKE_WINDOW, threshold: float = settings.SPIKE_THRESHOLD) -> pd.DataFrame:
    """Rolling-median spike ratios using only strictly earlier weeks (no look-ahead).

    `df` must contain one row per group per consecutive week (a full grid).
    """
    df = df.sort_values(group_cols + ["week_start"]).copy()
    g = df.groupby(group_cols, sort=False)
    for m in metrics:
        med = g[m].transform(lambda s: s.shift(1).rolling(window, min_periods=window).median())
        ratio = np.where(med > 0, df[m] / med.where(med > 0), np.nan)
        df[f"{m}_median_4w"] = med
        df[f"{m}_spike_ratio"] = ratio
        df[f"{m}_spike_flag"] = pd.Series(ratio, index=df.index).ge(threshold)
        df[f"{m}_zero_base_nonzero"] = (med == 0) & (df[m] > 0)
    return df


def _week_coverage(day_status: pd.DataFrame, weeks: pd.DatetimeIndex, start, end) -> pd.DataFrame:
    rows = []
    ds = day_status.set_index(["subreddit", "date"])["day_status"].to_dict()
    for s in settings.SUBREDDITS:
        for w in weeks:
            days = pd.date_range(w, periods=7, freq="D")
            st = [ds.get((s, d.strftime("%Y-%m-%d")), "missing") for d in days]
            in_range = [(start <= d.date() <= end) for d in days]
            rows.append({"subreddit": s, "week_start": w, "days_in_range": sum(in_range),
                         "days_complete": st.count("complete"),
                         "days_failed_or_partial": sum(x in ("failed", "partial") for x in st),
                         "coverage_complete": st.count("complete") == 7})
    return pd.DataFrame(rows)


def build(start=settings.START_DATE, end=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write the Week 1 combined and by-subreddit weekly tables and the ranked spike tables.

    Returns (combined, by_subreddit). `end` defaults to the last complete UTC day.
    """
    end = end or settings.default_end_date()
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet")
    day_status = pd.read_csv(settings.PROCESSED / "day_status.csv")
    mt = mt[(mt["date"] >= start.isoformat()) & (mt["date"] <= end.isoformat())]
    mt["week_start"] = week_start(mt["date"])
    mt["visible_id"] = mt["post_id"].where(mt["removed_by_category"].isna())

    weeks = pd.date_range(week_start(pd.Series([str(start)])).iloc[0],
                          week_start(pd.Series([str(end)])).iloc[0], freq="7D")
    cov = _week_coverage(day_status, weeks, start, end)

    agg = (mt.groupby(["ticker", "subreddit", "week_start"])
             .agg(posts=("post_id", "nunique"), comments=("num_comments", "sum"), upvotes=("score", "sum"),
                  posts_visible=("visible_id", "nunique"))
             .reset_index())
    grid = pd.MultiIndex.from_product([list(settings.TICKERS), settings.SUBREDDITS, weeks],
                                      names=["ticker", "subreddit", "week_start"]).to_frame(index=False)
    sub = grid.merge(agg, on=["ticker", "subreddit", "week_start"], how="left")
    sub[ALL_METRICS] = sub[ALL_METRICS].fillna(0)
    sub = sub.merge(cov, on=["subreddit", "week_start"], how="left")
    for m in ALL_METRICS:
        sub[f"{m}_observed"] = sub[m]
        sub.loc[~sub["coverage_complete"], m] = np.nan
    sub = add_spike_columns(sub, ["ticker", "subreddit"], ALL_METRICS)

    comb = (sub.groupby(["ticker", "week_start"])
               .agg(posts_observed=("posts_observed", "sum"), comments_observed=("comments_observed", "sum"),
                    upvotes_observed=("upvotes_observed", "sum"), posts_visible_observed=("posts_visible_observed", "sum"),
                    subreddits_complete=("coverage_complete", "sum"),
                    days_failed_or_partial=("days_failed_or_partial", "sum"))
               .reset_index())
    comb["coverage_complete"] = comb["subreddits_complete"] == len(settings.SUBREDDITS)
    for m in ALL_METRICS:
        comb[m] = comb[f"{m}_observed"].where(comb["coverage_complete"])
    comb = add_spike_columns(comb, ["ticker"], ALL_METRICS)

    # sanity checks
    for df in (sub, comb):
        assert (df["week_start"].dt.day_of_week == 0).all(), "week_start must be Monday"
        assert (df["week_start"].dt.hour == 0).all()
    assert comb.groupby("week_start").size().eq(len(settings.TICKERS)).all()
    assert not comb.duplicated(["ticker", "week_start"]).any()

    spike_cols = [f"{m}_{s}" for m in ALL_METRICS for s in ("median_4w", "spike_ratio", "spike_flag")]
    comb["week_start"] = comb["week_start"].dt.strftime("%Y-%m-%d")
    sub["week_start"] = sub["week_start"].dt.strftime("%Y-%m-%d")
    comb_out = comb[["week_start", "ticker"] + ALL_METRICS + spike_cols +
                    [f"{m}_zero_base_nonzero" for m in ALL_METRICS] +
                    ["coverage_complete", "subreddits_complete", "days_failed_or_partial"] +
                    [f"{m}_observed" for m in ALL_METRICS]].sort_values(["week_start", "ticker"])
    comb_out.insert(2, "subreddit", "all")
    sub_out = sub[["week_start", "ticker", "subreddit"] + ALL_METRICS + spike_cols +
                  [f"{m}_zero_base_nonzero" for m in ALL_METRICS] +
                  ["coverage_complete", "days_complete", "days_in_range", "days_failed_or_partial"] +
                  [f"{m}_observed" for m in ALL_METRICS]].sort_values(["week_start", "ticker", "subreddit"])
    comb_out["spike_rule"] = SPIKE_RULE_LABEL
    sub_out["spike_rule"] = SPIKE_RULE_LABEL
    comb_out.to_csv(settings.PROCESSED / "reddit_weekly.csv", index=False)
    sub_out.to_csv(settings.PROCESSED / "reddit_weekly_by_subreddit.csv", index=False)
    log.info("reddit_weekly.csv: %d rows (%d weeks, %d complete)", len(comb_out), comb_out["week_start"].nunique(),
             comb_out.loc[comb_out["coverage_complete"], "week_start"].nunique())
    spike_table(comb_out, sub_out)
    return comb_out, sub_out


def spike_table(comb: pd.DataFrame, sub: pd.DataFrame) -> pd.DataFrame:
    """All Week 1 spike rows (combined and by subreddit) plus the top-50 combined spikes with a real baseline."""
    rows = []
    for label, df in (("all", comb), ("by_subreddit", sub)):
        for m in METRICS:
            s = df[df[f"{m}_spike_flag"]].copy()
            if s.empty:
                continue
            s["metric"] = m
            s["value"] = s[m]
            s["median_4w"] = s[f"{m}_median_4w"]
            s["spike_ratio"] = s[f"{m}_spike_ratio"]
            s["level"] = label
            rows.append(s[["level", "week_start", "ticker", "subreddit", "metric", "value", "median_4w",
                           "spike_ratio", "posts", "posts_median_4w"]])
    cols = ["level", "week_start", "ticker", "subreddit", "metric", "value", "median_4w", "spike_ratio",
            "posts", "posts_median_4w"]
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)
    out["meets_min_baseline"] = out["posts_median_4w"] >= MIN_BASELINE_POSTS
    out["spike_rule"] = SPIKE_RULE_LABEL
    out = out.sort_values(["level", "meets_min_baseline", "spike_ratio"], ascending=[True, False, False])
    out.to_csv(settings.TABLES / "chatter_spikes_all.csv", index=False)
    top = out[(out["level"] == "all") & out["meets_min_baseline"]].head(50)
    top.insert(0, "rank", range(1, len(top) + 1))
    top.to_csv(settings.TABLES / "top_chatter_spikes.csv", index=False)
    log.info("spikes: %d flagged (all-subreddit level: %d, of which %d meet baseline >= %d posts)",
             len(out), (out["level"] == "all").sum(), len(out[(out["level"] == "all") & out["meets_min_baseline"]]),
             MIN_BASELINE_POSTS)
    return out


if __name__ == "__main__":
    build()
