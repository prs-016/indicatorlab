"""Prices for the Week 2 Reddit analyses: weekly returns, returns after a week, abnormal returns.

Conventions (weeks labelled by their Monday, like every attention table):
  close_w        last adjusted close of week w (normally Friday)
  ret            close_w / close_{w-1} - 1; NaN when either week has no trading day (never bridged)
  ret_next{k}    return over the k weeks after week w: close_{w+k} / close_w - 1. Reddit week w ends
                 Sunday, after close_w, so the window starts after all of week w's posts.
  beta           OLS beta of ret on the benchmark's ret over the previous 52 weeks (week w excluded)
  abn_ret        ret - beta * benchmark ret

Prices are Yahoo adjusted closes (auto_adjust=True), cached in data/reddit/raw/prices/.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.utils import get_logger, utc_now_iso
from src.reddit.weekly_metrics import week_start

log = get_logger("market_data", "pipeline.log")

PRICE_START = "2021-01-01"   # two years before the Reddit data, so 52-week betas exist from 2023
BETA_WEEKS = 52
FORWARD_WEEKS = 4


def prices_path(market: str):
    """Cached daily-close file of one market."""
    return settings.RAW_PRICES / f"daily_close_{market}.csv"


def load_daily_close(market: str = settings.MARKET, refresh: bool = False) -> pd.DataFrame:
    """Daily adjusted closes (date index, one column per ticker plus the benchmark)."""
    path = prices_path(market)
    if refresh or not path.exists():
        import yfinance as yf
        symbols = config.tickers(market) + [config.benchmark(market)]
        raw = yf.download(symbols, start=PRICE_START, auto_adjust=True, progress=False)["Close"]
        raw = raw[symbols].dropna(how="all")
        path.parent.mkdir(parents=True, exist_ok=True)
        raw.to_csv(path)
        path.with_suffix(".meta.json").write_text(json.dumps({
            "source": "yfinance download(auto_adjust=True)['Close']", "symbols": symbols, "start": PRICE_START,
            "downloaded_at_utc": utc_now_iso(), "last_date": str(raw.index.max().date())}, indent=2))
        log.info("downloaded %d days x %d symbols -> %s", len(raw), len(symbols), path)
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index
    return df


def weekly_close(daily: pd.DataFrame) -> pd.DataFrame:
    """Last close of each Monday-labelled week, on a gap-free weekly index (NaN for no-trade weeks)."""
    wk = week_start(pd.Series(daily.index, index=daily.index))
    out = daily.groupby(wk.to_numpy()).last()
    out.index = pd.DatetimeIndex(out.index, tz="UTC")
    full = pd.date_range(out.index.min(), out.index.max(), freq="7D", tz="UTC")
    return out.reindex(full)


def rolling_beta(r: pd.Series, m: pd.Series, weeks: int = BETA_WEEKS) -> pd.Series:
    """Beta of r on m from the `weeks` weeks before each week (all `weeks` must be present)."""
    both = pd.concat([r, m], axis=1, keys=["r", "m"])
    cov = both["r"].rolling(weeks, min_periods=weeks).cov(both["m"])
    var = both["m"].rolling(weeks, min_periods=weeks).var()
    return (cov / var).shift(1)


def weekly_panel(market: str = settings.MARKET, refresh: bool = False) -> pd.DataFrame:
    """Long table: week, ticker, market, close, ret, bench_ret, beta, abn_ret, ret_next1..4, abn_ret_next1..4."""
    wc = weekly_close(load_daily_close(market, refresh))
    rets = wc / wc.shift(1) - 1
    bench = config.benchmark(market)
    rows = []
    for tk in config.tickers(market):
        r, m = rets[tk], rets[bench]
        beta = rolling_beta(r, m)
        abn = r - beta * m
        d = pd.DataFrame({"week": wc.index, "ticker": tk, "market": market, "close": wc[tk].to_numpy(),
                          "ret": r.to_numpy(), "bench_ret": m.to_numpy(), "beta": beta.to_numpy(),
                          "abn_ret": abn.to_numpy()})
        for k in range(1, FORWARD_WEEKS + 1):
            d[f"ret_next{k}"] = (wc[tk].shift(-k) / wc[tk] - 1).to_numpy()
            # abnormal return over the next k weeks: sum of weekly abnormal returns w+1..w+k
            d[f"abn_ret_next{k}"] = sum(abn.shift(-j) for j in range(1, k + 1)).to_numpy()
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def research_only(df: pd.DataFrame, week_col: str = "week") -> pd.DataFrame:
    """Rows whose week (and any forward window) ends before the holdout date.

    `ret_next{k}` reaches k weeks past the week, so it is blanked where that window crosses the holdout.
    """
    holdout = pd.Timestamp(settings.HOLDOUT_START, tz="UTC")
    out = df[df[week_col] + pd.Timedelta(days=6) < holdout].copy()
    for k in range(1, FORWARD_WEEKS + 1):
        crosses = out[week_col] + pd.Timedelta(days=7 * k + 6) >= holdout
        out.loc[crosses, [f"ret_next{k}", f"abn_ret_next{k}"]] = np.nan
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Download prices and write data/reddit/processed/weekly_prices.csv")
    ap.add_argument("--refresh", action="store_true", help="download again instead of using the cache")
    panel = weekly_panel(refresh=ap.parse_args().refresh)
    out = panel.assign(week=panel["week"].dt.strftime("%Y-%m-%d"))
    out.to_csv(settings.PROCESSED / "weekly_prices.csv", index=False)
    log.info("weekly_prices.csv: %d rows, weeks %s..%s", len(out), out["week"].min(), out["week"].max())
