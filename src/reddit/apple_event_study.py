"""Apple September launch-event study (2023-2025): Reddit chatter vs AAPL weekly returns.

Return convention
-----------------
* Prices: yfinance daily AAPL with auto_adjust=True (split- and dividend-adjusted closes).
* Each U.S. trading date belongs to the Monday-Sunday week that contains it.
  The weekly close is the adjusted close of the last trading day of that week
  (usually Friday; Thursday when Friday is a market holiday).
* Weekly return_w = close_w / close_{w-1} - 1, where w-1 is the previous calendar week.
* Reddit weeks start Monday 00:00 UTC = Sunday 19:00/20:00 New York time, so every
  regular U.S. session (09:30-16:00 ET, Mon-Fri) falls entirely inside one Reddit week.
  Posts from Friday after the close through Sunday evening ET belong to week w-1 but
  can only affect prices from Monday's open of week w onward.
* Event-week chatter vs event-week return is a contemporaneous association.
  Chatter in week w vs return in week w+1 ("next week") is the predictive test.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import yfinance as yf

from src.reddit import settings
from src.reddit.utils import get_logger, utc_now_iso
from src.reddit.weekly_metrics import week_start

log = get_logger("apple_event_study", "pipeline.log")

EVENTS = [
    {"year": 2023, "event_name": "Wonderlust", "event_date": "2023-09-12", "event_time": "10:00 PT (17:00 UTC)",
     "products": "iPhone 15 / 15 Pro, Apple Watch Series 9, Apple Watch Ultra 2",
     "source_invitation": "https://developer.apple.com/news/?id=29c7dtwk",
     "source_press_release": "https://www.apple.com/newsroom/2023/09/apple-unveils-iphone-15-pro-and-iphone-15-pro-max/"},
    {"year": 2024, "event_name": "It's Glowtime", "event_date": "2024-09-09", "event_time": "10:00 PT (17:00 UTC)",
     "products": "iPhone 16 / 16 Pro, Apple Watch Series 10, AirPods 4",
     "source_invitation": "https://developer.apple.com/news/?id=zvdnvggt",
     "source_press_release": "https://www.apple.com/newsroom/2024/09/apple-debuts-iphone-16-pro-and-iphone-16-pro-max/"},
    {"year": 2025, "event_name": "Awe dropping", "event_date": "2025-09-09", "event_time": "10:00 PT (17:00 UTC)",
     "products": "iPhone 17 / 17 Pro / iPhone Air, Apple Watch, AirPods Pro 3",
     "source_invitation": "https://developer.apple.com/news/?id=p9nukitr",
     "source_press_release": "https://www.apple.com/newsroom/2025/09/apple-unveils-iphone-17-pro-and-iphone-17-pro-max/"},
]


def load_prices(refresh: bool = False) -> pd.DataFrame:
    path = settings.RAW_PRICES / "AAPL_daily_yfinance.csv"
    meta = settings.RAW_PRICES / "AAPL_daily_yfinance.meta.json"
    if refresh or not path.exists():
        df = yf.download("AAPL", start="2022-10-01", end=None, auto_adjust=True, progress=False, actions=False)
        if df.empty:
            raise RuntimeError("yfinance returned no AAPL data")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index.name = "date"
        settings.RAW_PRICES.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)
        meta.write_text(json.dumps({"ticker": "AAPL", "source": "yfinance", "yfinance_version": yf.__version__,
                                    "auto_adjust": True, "retrieved_at_utc": utc_now_iso(),
                                    "first_date": str(df.index.min().date()), "last_date": str(df.index.max().date()),
                                    "rows": len(df)}, indent=2))
        log.info("downloaded %d AAPL rows -> %s", len(df), path)
    df = pd.read_csv(path, parse_dates=["date"])
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="raise")
    assert df["date"].is_unique and df["Close"].gt(0).all()
    return df


def weekly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    p = prices[["date", "Close"]].copy()
    p["week_start"] = week_start(p["date"].dt.strftime("%Y-%m-%d")).dt.strftime("%Y-%m-%d")
    wk = (p.sort_values("date").groupby("week_start")
            .agg(last_trading_date=("date", "max"), adj_close=("Close", "last"), trading_days=("date", "size"))
            .reset_index())
    # Require the previous *calendar* week, so a gap never silently spans two weeks.
    wk["prev_week"] = (pd.to_datetime(wk["week_start"]) - pd.Timedelta(days=7)).dt.strftime("%Y-%m-%d")
    prev = wk.set_index("week_start")["adj_close"]
    wk["prev_adj_close"] = wk["prev_week"].map(prev)
    wk["weekly_return"] = wk["adj_close"] / wk["prev_adj_close"] - 1
    wk["last_trading_date"] = wk["last_trading_date"].dt.strftime("%Y-%m-%d")
    return wk.drop(columns="prev_week")


def run(refresh_prices: bool = False) -> pd.DataFrame:
    prices = load_prices(refresh_prices)
    wk = weekly_returns(prices)
    wk.to_csv(settings.PROCESSED / "aapl_weekly_returns.csv", index=False)

    reddit = pd.read_csv(settings.PROCESSED / "reddit_weekly.csv")
    aapl = reddit[reddit["ticker"] == "AAPL"].set_index("week_start")
    by_sub = pd.read_csv(settings.PROCESSED / "reddit_weekly_by_subreddit.csv")
    by_sub = by_sub[by_sub["ticker"] == "AAPL"].pivot(index="week_start", columns="subreddit", values="posts")
    wkr = wk.set_index("week_start")

    ev = pd.DataFrame(EVENTS)
    ev["event_week_start"] = week_start(ev["event_date"]).dt.strftime("%Y-%m-%d")
    ev["event_week_end"] = (pd.to_datetime(ev["event_week_start"]) + pd.Timedelta(days=6)).dt.strftime("%Y-%m-%d")
    ev["next_week_start"] = (pd.to_datetime(ev["event_week_start"]) + pd.Timedelta(days=7)).dt.strftime("%Y-%m-%d")
    ev.drop(columns=[]).to_csv(settings.VALIDATION / "apple_events.csv", index=False)

    rows = []
    for e in ev.to_dict("records"):
        w, n = e["event_week_start"], e["next_week_start"]
        r = {k: e[k] for k in ["year", "event_name", "event_date", "event_week_start", "event_week_end"]}
        a = aapl.loc[w] if w in aapl.index else None
        r["reddit_coverage_complete"] = bool(a["coverage_complete"]) if a is not None else False
        for m in ["posts", "comments", "upvotes"]:
            for suffix in ["", "_median_4w", "_spike_ratio", "_spike_flag"]:
                r[f"{m}{suffix}"] = a[f"{m}{suffix}"] if a is not None else np.nan
        for s in settings.SUBREDDITS:
            r[f"posts_{s}"] = by_sub.loc[w, s] if w in by_sub.index else np.nan
        r["next_week_posts"] = aapl.loc[n, "posts"] if n in aapl.index else np.nan
        r["event_week_last_trading_date"] = wkr.loc[w, "last_trading_date"] if w in wkr.index else None
        r["event_week_return"] = wkr.loc[w, "weekly_return"] if w in wkr.index else np.nan
        r["next_week_last_trading_date"] = wkr.loc[n, "last_trading_date"] if n in wkr.index else None
        r["next_week_return"] = wkr.loc[n, "weekly_return"] if n in wkr.index else np.nan
        r["event_week_return_pctile_in_sample"] = (wk["weekly_return"].dropna() <= r["event_week_return"]).mean()
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(settings.TABLES / "apple_event_study.csv", index=False)

    # Context: how unusual are these numbers relative to all complete weeks?
    sample = aapl[aapl["coverage_complete"]].join(wkr["weekly_return"], how="inner")
    sample["next_week_return"] = sample.index.map(
        lambda w: wkr["weekly_return"].get((pd.Timestamp(w) + pd.Timedelta(days=7)).strftime("%Y-%m-%d"), np.nan))
    ctx = {
        "weeks_with_complete_reddit_and_price": int(len(sample)),
        "aapl_mean_weekly_return": float(wk["weekly_return"].mean()),
        "aapl_std_weekly_return": float(wk["weekly_return"].std()),
        "share_positive_weeks": float((wk["weekly_return"] > 0).mean()),
        "aapl_posts_spike_weeks": int(sample["posts_spike_flag"].sum()),
        "mean_next_week_return_after_posts_spike": float(sample.loc[sample["posts_spike_flag"], "next_week_return"].mean()),
        "mean_next_week_return_no_spike": float(sample.loc[~sample["posts_spike_flag"], "next_week_return"].mean()),
        "corr_posts_vs_same_week_return": float(sample["posts"].corr(sample["weekly_return"])),
        "corr_posts_vs_next_week_return": float(sample["posts"].corr(sample["next_week_return"])),
        "corr_posts_spike_ratio_vs_next_week_return": float(sample["posts_spike_ratio"].corr(sample["next_week_return"])),
    }
    (settings.TABLES / "apple_event_context.json").write_text(json.dumps(ctx, indent=2))
    log.info("event study:\n%s\ncontext: %s", out[["year", "event_week_start", "posts", "posts_median_4w",
                                                     "posts_spike_ratio", "posts_spike_flag", "event_week_return",
                                                     "next_week_return"]].to_string(index=False), ctx)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-prices", action="store_true")
    run(ap.parse_args().refresh_prices)
