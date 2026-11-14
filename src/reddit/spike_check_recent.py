"""Week 2, Step 7: last-3-weeks spike check (with James). Looking only, nothing is tested here.

For the weeks starting Sep 28, Oct 5 and Oct 12, 2026 this builds a ticker x week table with:
  product_spike / stock_spike    the shared spike rule on reddit_product / reddit_stock posts
  wiki_views_spike / wiki_edits_spike   James's columns, joined from his shared weekly rows when present
  ret_week / ret_next_week       the stock's return that week and the week after
  first_spike_day_*              first day of the week a source's daily posts reached 2x its median
                                 daily posts over the previous 8 weeks (which source moved first)
It also writes the top posts of every spiking stock-week to a markdown file, to read before writing
the two or three sentences per stock that the meeting needs.

    python -m src.reddit.spike_check_recent
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.reddit import settings
from src.reddit.build_posts import attach_text
from src.reddit.reddit_weekly import OUT_RECENT, SOURCE_OF_TYPE, SOURCES
from src.reddit.utils import get_logger
from src.reddit.weekly_metrics import week_start

log = get_logger("spike_check_recent", "pipeline.log")

DEFAULT_WEEKS = ["2026-09-28", "2026-10-05", "2026-10-12"]
WIKI_PATH = settings.ROOT / "data" / "shared" / "attention_weekly_wikipedia.csv"   # James's rows
PRICES_PATH = settings.PROCESSED / "weekly_prices.csv"
DAILY_SPIKE_RATIO = 2.0
DAILY_BASE_DAYS = 56
TOP_POSTS = 5
OUT_TABLE = settings.TABLES / "last3weeks_spikes.csv"
OUT_POSTS = settings.TABLES / "last3weeks_top_posts.md"


def daily_counts(mt: pd.DataFrame) -> pd.DataFrame:
    """Posts per (ticker, source, day) on a full daily grid (0 where nothing was posted)."""
    mt = mt.assign(source=mt["subreddit_type"].map(SOURCE_OF_TYPE), day=pd.to_datetime(mt["date"], utc=True))
    n = mt.groupby(["ticker", "source", "day"])["post_id"].nunique().rename("posts")
    days = pd.date_range(mt["day"].min(), mt["day"].max(), freq="D", tz="UTC")
    idx = pd.MultiIndex.from_product([sorted(mt["ticker"].unique()), SOURCES, days], names=["ticker", "source", "day"])
    return n.reindex(idx, fill_value=0).reset_index()


def first_spike_day(daily: pd.DataFrame, ticker: str, source: str, week: pd.Timestamp) -> str | None:
    """First day in `week` whose posts reach DAILY_SPIKE_RATIO x the median of the previous 8 weeks of days."""
    d = daily[(daily["ticker"] == ticker) & (daily["source"] == source)].set_index("day")["posts"]
    base = d.shift(1).rolling(DAILY_BASE_DAYS, min_periods=DAILY_BASE_DAYS).median()
    wk = d[(d.index >= week) & (d.index < week + pd.Timedelta(days=7))]
    hit = wk[wk >= DAILY_SPIKE_RATIO * base.reindex(wk.index).clip(lower=1)]
    return hit.index[0].strftime("%Y-%m-%d (%a)") if len(hit) else None


def build(weeks: list[str]) -> pd.DataFrame:
    """The ticker x week table for `weeks` (Monday dates)."""
    att = pd.read_csv(OUT_RECENT)
    att = att[att["week"].isin(weeks)]
    wide = att.pivot_table(index=["ticker", "week"], columns="source", values=["spike", "ratio", "posts"],
                           aggfunc="first")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    names = {f"{m}_{src}": f"{src.split('_')[1]}_{m}" for m in ("spike", "ratio", "posts") for src in SOURCES}
    out = wide.reset_index().rename(columns=names)   # e.g. spike_reddit_product -> product_spike
    if WIKI_PATH.exists():
        wk = pd.read_csv(WIKI_PATH)
        views = wk[wk["source"].str.contains("views", na=False)][["week", "ticker", "spike"]]
        edits = wk[wk["source"].str.contains("edits", na=False)][["week", "ticker", "spike"]]
        out = out.merge(views.rename(columns={"spike": "wiki_views_spike"}), on=["week", "ticker"], how="left")
        out = out.merge(edits.rename(columns={"spike": "wiki_edits_spike"}), on=["week", "ticker"], how="left")
    else:
        out["wiki_views_spike"], out["wiki_edits_spike"] = np.nan, np.nan   # filled in by James
    prices = pd.read_csv(PRICES_PATH)[["week", "ticker", "ret", "ret_next1"]]
    out = out.merge(prices.rename(columns={"ret": "ret_week", "ret_next1": "ret_next_week"}), on=["week", "ticker"],
                    how="left")
    out.insert(2, "market", settings.MARKET)
    return out.sort_values(["ticker", "week"]).reset_index(drop=True)


def run(weeks: list[str]) -> pd.DataFrame:
    """Write the table and the top-posts file for the spike check."""
    table = build(weeks)
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet", filters=[("period", "==", "recent")],
                         columns=["post_id", "ticker", "subreddit", "subreddit_type", "date", "score", "num_comments",
                                  "permalink", "removed_flag"])
    daily = daily_counts(mt)
    for src, col in (("reddit_product", "first_spike_day_product"), ("reddit_stock", "first_spike_day_stock")):
        table[col] = [first_spike_day(daily, r.ticker, src, pd.Timestamp(r.week, tz="UTC")) for r in table.itertuples()]
    table["spike_weeks_of_3"] = table.groupby("ticker")[["product_spike", "stock_spike"]].transform(
        lambda s: s.fillna(False).astype(bool)).any(axis=1).groupby(table["ticker"]).transform("sum")
    table.to_csv(OUT_TABLE, index=False)

    spiking = table[table[["product_spike", "stock_spike"]].fillna(False).astype(bool).any(axis=1)]
    mt["week"] = week_start(mt["date"]).dt.strftime("%Y-%m-%d")
    mt["source"] = mt["subreddit_type"].map(SOURCE_OF_TYPE)
    lines = ["# Last-3-weeks spike check: top posts of each spiking stock-week", ""]
    for r in spiking.itertuples():
        lines.append(f"## {r.ticker}, week of {r.week}: product spike={bool(r.product_spike)}, "
                     f"stock spike={bool(r.stock_spike)}, return {r.ret_week:+.1%} then {r.ret_next_week:+.1%}"
                     if pd.notna(r.ret_week) and pd.notna(r.ret_next_week) else
                     f"## {r.ticker}, week of {r.week}: product spike={bool(r.product_spike)}, "
                     f"stock spike={bool(r.stock_spike)}")
        for src in SOURCES:
            top = mt[(mt["ticker"] == r.ticker) & (mt["week"] == r.week) & (mt["source"] == src) & ~mt["removed_flag"]]
            top = top.sort_values("score", ascending=False).head(TOP_POSTS)
            if top.empty:
                continue
            top = attach_text(top, ("title",))
            lines.append(f"\n**{src}**\n")
            lines += [f"- [{t.title}](https://www.reddit.com{t.permalink}) (r/{t.subreddit}, {t.date}, score {t.score})"
                      for t in top.itertuples()]
        lines.append("")
    OUT_POSTS.write_text("\n".join(lines))
    log.info("spike check: %d stock-weeks, %d with a Reddit spike -> %s", len(table), len(spiking), OUT_TABLE)
    return table


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weeks", nargs="*", default=DEFAULT_WEEKS, help="Monday dates")
    run(ap.parse_args().weeks)
