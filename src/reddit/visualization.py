"""Charts: AAPL weekly Reddit post volume vs AAPL price, with Apple events and spike weeks.

Two stacked panels sharing the time axis (no dual y-axis): posts on top, adjusted
close below. Underlying chart data is saved next to the PNGs.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.reddit import settings
from src.reddit.apple_event_study import EVENTS, load_prices
from src.reddit.utils import get_logger

log = get_logger("visualization", "pipeline.log")

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
SERIES, SPIKE, INCOMPLETE = "#2a78d6", "#eb6834", "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def chart_data() -> pd.DataFrame:
    reddit = pd.read_csv(settings.PROCESSED / "reddit_weekly.csv", parse_dates=["week_start"])
    a = reddit[reddit["ticker"] == "AAPL"].set_index("week_start")
    wk = pd.read_csv(settings.PROCESSED / "aapl_weekly_returns.csv", parse_dates=["week_start"]).set_index("week_start")
    df = a[["posts", "posts_observed", "posts_median_4w", "posts_spike_ratio", "posts_spike_flag",
            "comments", "upvotes", "coverage_complete"]].join(wk[["adj_close", "weekly_return", "last_trading_date"]])
    event_weeks = {pd.Timestamp(e["event_date"]) - pd.Timedelta(days=pd.Timestamp(e["event_date"]).weekday())
                   for e in EVENTS}
    df["apple_event_week"] = df.index.isin(event_weeks)
    return df.reset_index()


def _decorate_events(ax, label=False):
    for e in EVENTS:
        d = pd.Timestamp(e["event_date"])
        ax.axvline(d, color=INK, lw=1, ls=(0, (4, 3)), zorder=3)
        if label:
            ax.annotate(f"{e['event_name']}\n{d:%b %d, %Y}", (d, 1), xycoords=("data", "axes fraction"),
                        xytext=(4, -2), textcoords="offset points", va="top", fontsize=8, color=INK2)


def plot_timeline(df: pd.DataFrame, prices: pd.DataFrame, path, title_suffix=""):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True, gridspec_kw={"height_ratios": [1.15, 1]})
    complete = df["coverage_complete"]
    colors = [SPIKE if s else (SERIES if c else INCOMPLETE)
              for s, c in zip(df["posts_spike_flag"], complete)]
    heights = df["posts"].where(complete, df["posts_observed"])
    ax1.bar(df["week_start"] + pd.Timedelta(days=3.5), heights, width=5.6, color=colors, linewidth=0, zorder=2)
    ax1.plot(df["week_start"] + pd.Timedelta(days=3.5), df["posts_median_4w"], color=INK2, lw=1.2,
             label="median of previous 4 weeks", zorder=4)
    _decorate_events(ax1, label=True)
    ax1.set_ylabel("AAPL-matching posts per week")
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [Patch(color=SERIES, label="weekly posts"), Patch(color=SPIKE, label="spike week (≥ 2× 4-week median)"),
               Line2D([], [], color=INK2, lw=1.2, label="median of previous 4 weeks"),
               Line2D([], [], color=INK, lw=1, ls=(0, (4, 3)), label="Apple September event")]
    if (~complete).any():
        handles.insert(2, Patch(color=INCOMPLETE, label="incomplete collection (observed only)"))
    ax1.legend(handles=handles, loc="upper right", frameon=True, facecolor=SURFACE, edgecolor=GRID, framealpha=0.95, fontsize=8, ncol=1)
    ax1.set_title(f"AAPL Reddit chatter vs. AAPL price — r/stocks + r/investing + r/wallstreetbets{title_suffix}",
                  loc="left", fontsize=12, color=INK)

    pr = prices[(prices["date"] >= df["week_start"].min()) &
                (prices["date"] <= df["week_start"].max() + pd.Timedelta(days=7))]
    ax2.plot(pr["date"], pr["Close"], color=SERIES, lw=1.6, zorder=2)
    spike_weeks = df.loc[df["posts_spike_flag"], "week_start"]
    for w in spike_weeks:
        ax2.axvspan(w, w + pd.Timedelta(days=7), color=SPIKE, alpha=0.18, lw=0, zorder=1)
    _decorate_events(ax2)
    ax2.set_ylabel("AAPL adjusted close (USD)")
    ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    fig.text(0.01, 0.005, "Weeks start Monday 00:00 UTC. Shaded price bands = Reddit post-spike weeks. "
             "Prices: yfinance, split/dividend-adjusted. Upvote totals are Arctic Shift archive snapshots.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=300)
    plt.close(fig)
    log.info("wrote %s", path)


def plot_event_windows(df: pd.DataFrame, prices: pd.DataFrame, path, weeks_before=8, weeks_after=6):
    fig, axes = plt.subplots(2, 3, figsize=(14, 6.5), sharex="col")
    for j, e in enumerate(EVENTS):
        d = pd.Timestamp(e["event_date"])
        ws = d - pd.Timedelta(days=d.weekday())
        lo, hi = ws - pd.Timedelta(weeks=weeks_before), ws + pd.Timedelta(weeks=weeks_after)
        sub = df[(df["week_start"] >= lo) & (df["week_start"] <= hi)]
        ax = axes[0, j]
        colors = [SPIKE if s else (SERIES if c else INCOMPLETE) for s, c in zip(sub["posts_spike_flag"], sub["coverage_complete"])]
        ax.bar(sub["week_start"] + pd.Timedelta(days=3.5), sub["posts"].where(sub["coverage_complete"], sub["posts_observed"]),
               width=5.6, color=colors, lw=0, zorder=2)
        ax.plot(sub["week_start"] + pd.Timedelta(days=3.5), sub["posts_median_4w"], color=INK2, lw=1.2, zorder=4)
        ax.axvline(d, color=INK, lw=1, ls=(0, (4, 3)))
        ax.set_title(f"{e['event_name']} — {d:%b %d, %Y}", loc="left", fontsize=10)
        if j == 0:
            ax.set_ylabel("AAPL posts / week")
        ax2 = axes[1, j]
        pr = prices[(prices["date"] >= lo) & (prices["date"] <= hi + pd.Timedelta(days=7))]
        ax2.plot(pr["date"], pr["Close"], color=SERIES, lw=1.6)
        ax2.axvspan(ws, ws + pd.Timedelta(days=7), color=INK2, alpha=0.10, lw=0)
        ax2.axvline(d, color=INK, lw=1, ls=(0, (4, 3)))
        if j == 0:
            ax2.set_ylabel("AAPL adj. close (USD)")
        ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=3))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.suptitle("Apple September events: weekly AAPL Reddit posts (orange = ≥2× spike) and AAPL price (grey band = event week)",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)
    log.info("wrote %s", path)


def run():
    df = chart_data()
    df.to_csv(settings.TABLES / "aapl_chart_data.csv", index=False)
    prices = load_prices()
    settings.CHARTS.mkdir(parents=True, exist_ok=True)
    plot_timeline(df, prices, settings.CHARTS / "aapl_chatter_vs_price.png")
    plot_event_windows(df, prices, settings.CHARTS / "aapl_event_windows.png")


if __name__ == "__main__":
    run()
