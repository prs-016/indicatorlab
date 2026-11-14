"""Week 2, Step 6: do product subreddits move before investor subreddits and the stock, or after?

Weekly series per stock (research period only, weeks labelled by Monday):
  prod_chatter   abnormal product-subreddit posts, log((posts + 1) / (baseline + 1)) from the shared spike rule
  prod_sent      product-subreddit sentiment_mean minus its average over the previous 26 weeks
  stock_chatter  abnormal stock-subreddit posts (same definition, reddit_stock source)
  abn_ret        stock return minus beta x SPY return, beta from the previous 52 weeks

Each series is z-scored within its stock so stocks can be pooled. For each pair below the script
reports the Pearson correlation (and Spearman as a check), per stock and pooled, with bootstrap 95%
CIs from 1,000 resamples of weeks (a sampled week brings every stock's row for that week):

  forward  (product leads)     prod_chatter_t / prod_sent_t  ->  stock_chatter_{t+k}, abn_ret_{t+k}
  reverse  (product reacts)    stock_chatter_t / abn_ret_t   ->  prod_chatter_{t+k}, prod_sent_{t+k}
  k = 1, 2

"Which direction is stronger" is the forward minus reverse correlation for matching pairs, with
its own bootstrap CI; a 4-week moving-block bootstrap is reported as a robustness check, since
weekly attention series are autocorrelated. Every input week ends before the holdout date.

    python -m src.reddit.cause_reaction
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.reddit import settings
from src.reddit.market_data import research_only, weekly_panel
from src.reddit.reddit_weekly import OUT_RESEARCH
from src.reddit.utils import get_logger

log = get_logger("cause_reaction", "pipeline.log")

N_BOOT = 1000
BLOCK_WEEKS = 4
SEED = 42
SENT_BASELINE_WEEKS = 26
MIN_OBS = 20            # pairs with fewer complete weeks are not reported for a stock
LAGS = (1, 2)
LEADERS_FORWARD = ["prod_chatter", "prod_sent"]
FOLLOWERS_FORWARD = ["stock_chatter", "abn_ret"]
LEADERS_REVERSE = ["stock_chatter", "abn_ret"]
FOLLOWERS_REVERSE = ["prod_chatter", "prod_sent"]


def build_panel(attention: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """One row per (ticker, week) with the four series, z-scored within stock."""
    att = attention.copy()
    att["week"] = pd.to_datetime(att["week"], utc=True)
    wide = att.pivot_table(index=["ticker", "week"], columns="source", values=["abnormal", "sentiment_mean"],
                           aggfunc="first")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    df = pd.DataFrame({"ticker": wide["ticker"], "week": wide["week"],
                       "prod_chatter": wide.get("abnormal_reddit_product"),
                       "stock_chatter": wide.get("abnormal_reddit_stock"),
                       "prod_sent_raw": wide.get("sentiment_mean_reddit_product")})
    df = df.sort_values(["ticker", "week"])
    base = df.groupby("ticker")["prod_sent_raw"].transform(
        lambda s: s.shift(1).rolling(SENT_BASELINE_WEEKS, min_periods=SENT_BASELINE_WEEKS // 2).mean())
    df["prod_sent"] = df["prod_sent_raw"] - base
    df = df.merge(prices[["ticker", "week", "abn_ret"]], on=["ticker", "week"], how="left")
    holdout = pd.Timestamp(settings.HOLDOUT_START, tz="UTC")
    assert (df["week"] + pd.Timedelta(days=6) < holdout).all(), "holdout weeks in cause/reaction input"
    for c in ["prod_chatter", "prod_sent", "stock_chatter", "abn_ret"]:
        g = df.groupby("ticker")[c]
        df[c] = (df[c] - g.transform("mean")) / g.transform("std")
    return df


def lagged_pairs(panel: pd.DataFrame) -> pd.DataFrame:
    """Long table of (pair, ticker, week t, x_t, y_{t+k}) for every forward and reverse pair."""
    out = []
    specs = [("forward", x, y) for x in LEADERS_FORWARD for y in FOLLOWERS_FORWARD] + \
            [("reverse", x, y) for x in LEADERS_REVERSE for y in FOLLOWERS_REVERSE]
    for tk, g in panel.groupby("ticker"):
        g = g.set_index("week").sort_index()
        full = pd.date_range(g.index.min(), g.index.max(), freq="7D", tz="UTC")
        g = g.reindex(full)
        for direction, x, y in specs:
            for k in LAGS:
                d = pd.DataFrame({"direction": direction, "x": x, "y": y, "lag": k, "ticker": tk, "week": full,
                                  "xv": g[x].to_numpy(), "yv": g[y].shift(-k).to_numpy()}).dropna(subset=["xv", "yv"])
                out.append(d)
    return pd.concat(out, ignore_index=True)


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def _resample_weeks(weeks: np.ndarray, rng: np.random.Generator, block: int) -> np.ndarray:
    """Week labels drawn with replacement, singly (block=1) or in moving blocks of `block` weeks."""
    n = len(weeks)
    if block == 1:
        return weeks[rng.integers(0, n, n)]
    starts = rng.integers(0, n - block + 1, int(np.ceil(n / block)))
    return np.concatenate([weeks[s:s + block] for s in starts])[:n]


def _boot(pairs: pd.DataFrame, rng: np.random.Generator, block: int) -> np.ndarray:
    """Bootstrap distribution of the correlation of one pair (rows: ticker-weeks)."""
    weeks, inv = np.unique(pairs["week"].to_numpy(), return_inverse=True)
    rows_of = [np.flatnonzero(inv == i) for i in range(len(weeks))]
    x, y = pairs["xv"].to_numpy(), pairs["yv"].to_numpy()
    vals = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = np.concatenate([rows_of[i] for i in _resample_weeks(np.arange(len(weeks)), rng, block)])
        vals[b] = _corr(x[idx], y[idx])
    return vals


def correlations(pairs: pd.DataFrame, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pooled and per-stock correlations with CIs, and forward-minus-reverse differences."""
    rows, boots = [], {}
    for (direction, x, y, k), g in pairs.groupby(["direction", "x", "y", "lag"]):
        rng = np.random.default_rng(seed)
        b1 = _boot(g, rng, 1)
        bb = _boot(g, np.random.default_rng(seed + 1), BLOCK_WEEKS)
        boots[(direction, x, y, k)] = b1
        rows.append({"scope": "pooled", "ticker": "ALL", "direction": direction, "x": x, "y": y, "lag": k,
                     "n": len(g), "pearson": _corr(g["xv"].to_numpy(), g["yv"].to_numpy()),
                     "spearman": g["xv"].rank().corr(g["yv"].rank()),
                     "ci_low": np.nanpercentile(b1, 2.5), "ci_high": np.nanpercentile(b1, 97.5),
                     "block_ci_low": np.nanpercentile(bb, 2.5), "block_ci_high": np.nanpercentile(bb, 97.5)})
        for tk, gt in g.groupby("ticker"):
            if len(gt) < MIN_OBS:
                continue
            bt = _boot(gt, np.random.default_rng(seed), 1)
            rows.append({"scope": "stock", "ticker": tk, "direction": direction, "x": x, "y": y, "lag": k,
                         "n": len(gt), "pearson": _corr(gt["xv"].to_numpy(), gt["yv"].to_numpy()),
                         "spearman": gt["xv"].rank().corr(gt["yv"].rank()),
                         "ci_low": np.nanpercentile(bt, 2.5), "ci_high": np.nanpercentile(bt, 97.5)})
    table = pd.DataFrame(rows)
    # Matching pairs: product chatter -> stock chatter vs stock chatter -> product chatter, and so on.
    matches = [(("forward", "prod_chatter", "stock_chatter"), ("reverse", "stock_chatter", "prod_chatter")),
               (("forward", "prod_chatter", "abn_ret"), ("reverse", "abn_ret", "prod_chatter")),
               (("forward", "prod_sent", "abn_ret"), ("reverse", "abn_ret", "prod_sent")),
               (("forward", "prod_sent", "stock_chatter"), ("reverse", "stock_chatter", "prod_sent"))]
    diffs = []
    pooled = table[table["scope"] == "pooled"].set_index(["direction", "x", "y", "lag"])["pearson"]
    for fwd, rev in matches:
        for k in LAGS:
            if (*fwd, k) not in boots or (*rev, k) not in boots:
                continue
            d = np.abs(boots[(*fwd, k)]) - np.abs(boots[(*rev, k)])
            diffs.append({"forward": f"{fwd[1]} -> {fwd[2]}", "reverse": f"{rev[1]} -> {rev[2]}", "lag": k,
                          "forward_r": pooled[(*fwd, k)], "reverse_r": pooled[(*rev, k)],
                          "abs_diff": abs(pooled[(*fwd, k)]) - abs(pooled[(*rev, k)]),
                          "ci_low": np.nanpercentile(d, 2.5), "ci_high": np.nanpercentile(d, 97.5)})
    return table, pd.DataFrame(diffs)


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load research-period inputs, compute both tables and write them to results/reddit/tables/."""
    attention = pd.read_csv(OUT_RESEARCH)
    prices = research_only(weekly_panel())
    panel = build_panel(attention, prices)
    pairs = lagged_pairs(panel)
    table, diffs = correlations(pairs)
    table.insert(0, "market", settings.MARKET)
    table.to_csv(settings.TABLES / "cause_vs_reaction.csv", index=False)
    diffs.to_csv(settings.TABLES / "cause_vs_reaction_direction.csv", index=False)
    log.info("cause vs reaction: %d correlations, %d direction comparisons, weeks %s..%s", len(table), len(diffs),
             panel["week"].min().date(), panel["week"].max().date())
    return table, diffs


if __name__ == "__main__":
    run()
