"""Prices for the Wikipedia analyses: weekly returns, returns 1-4 weeks after, abnormal returns, bootstrap CIs.

Same conventions as Joshua's src/reddit/market_data.py (weeks labelled by their Monday):
  close        last adjusted close of week w (normally Friday)
  ret          close_w / close_{w-1} - 1 (NaN when either week has no trading day)
  ret_next{k}  close_{w+k} / close_w - 1: the k weeks after week w. Week w's page views end on Sunday,
               after close_w, so this window starts after all of week w's attention is known.
  beta         OLS beta of ret on the benchmark's ret over the previous 52 weeks (week w excluded)
  abn_ret      ret - beta * benchmark ret; abn_ret_next{k} sums abn_ret over weeks w+1..w+k
"""
import numpy as np
import pandas as pd

from src.wiki_attention import week_start

BETA_WEEKS = 52
FORWARD_WEEKS = 4


def weekly_close(daily: pd.DataFrame) -> pd.DataFrame:
    """Last close of each Monday-labelled week, on a gap-free weekly index (NaN for no-trade weeks)."""
    out = daily.groupby(week_start(daily.index)).last()
    full = pd.date_range(out.index.min(), out.index.max(), freq="7D")
    out = out.reindex(full)
    out.index.name = "week"
    return out


def rolling_beta(r: pd.Series, m: pd.Series, weeks: int = BETA_WEEKS) -> pd.Series:
    """Beta of r on m from the `weeks` weeks before each week (all of them must be present)."""
    cov = r.rolling(weeks, min_periods=weeks).cov(m)
    var = m.rolling(weeks, min_periods=weeks).var()
    return (cov / var).shift(1)


def weekly_panel(daily: pd.DataFrame, tickers: list[str], benchmark: str, market: str) -> pd.DataFrame:
    """Long table: week, ticker, market, close, ret, bench_ret, beta, abn_ret, ret_next1..4, abn_ret_next1..4."""
    wc = weekly_close(daily)
    rets = wc / wc.shift(1) - 1
    m = rets[benchmark]
    rows = []
    for tk in tickers:
        r = rets[tk]
        beta = rolling_beta(r, m)
        abn = r - beta * m
        d = pd.DataFrame({"week": wc.index, "ticker": tk, "market": market, "close": wc[tk].to_numpy(),
                          "ret": r.to_numpy(), "bench_ret": m.to_numpy(), "beta": beta.to_numpy(),
                          "abn_ret": abn.to_numpy()})
        for k in range(1, FORWARD_WEEKS + 1):
            d[f"ret_next{k}"] = (wc[tk].shift(-k) / wc[tk] - 1).to_numpy()
            d[f"abn_ret_next{k}"] = sum(abn.shift(-j) for j in range(1, k + 1)).to_numpy()
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def research_only(df: pd.DataFrame, holdout: pd.Timestamp, week_col: str = "week") -> pd.DataFrame:
    """Rows whose week ends before the holdout, with forward returns blanked where they reach into it."""
    out = df[df[week_col] + pd.Timedelta(days=6) < holdout].copy()
    for k in range(1, FORWARD_WEEKS + 1):
        crosses = out[week_col] + pd.Timedelta(days=7 * k + 6) >= holdout
        out.loc[crosses, [f"ret_next{k}", f"abn_ret_next{k}"]] = np.nan
    return out


def bootstrap_diff(df: pd.DataFrame, value: str, flag: str = "spike", cluster: str = "week",
                   n_resamples: int = 1000, ci: float = 0.95, seed: int = 42, block: int = 1) -> dict:
    """Mean of `value` in flagged rows minus non-flagged rows, with a block-bootstrap CI.

    Whole weeks are resampled (all tickers of a drawn week come together), because stocks move
    together within a week. Weeks are drawn in runs of `block` consecutive weeks (circular moving
    blocks): use block = k for k-week forward returns, whose neighbouring weeks overlap.
    Rows with a missing `value` are dropped first; `cluster` must be a gap-free weekly grid.
    """
    d = df[[cluster, flag, value]].dropna()
    d = d.assign(**{flag: d[flag].astype(bool)})
    # per-week sums and counts turn each resample into one matrix product instead of a concat
    s = d.assign(v_spike=d[value].where(d[flag], 0.0), n_spike=d[flag].astype(int),
                 v_norm=d[value].where(~d[flag], 0.0), n_norm=(~d[flag]).astype(int))
    per_week = s.groupby(cluster)[["v_spike", "n_spike", "v_norm", "n_norm"]].sum().to_numpy()
    n_weeks = len(per_week)
    rng = np.random.default_rng(seed)
    n_blocks = -(-n_weeks // block)
    starts = rng.integers(0, n_weeks, size=(n_resamples, n_blocks))
    draws = ((starts[:, :, None] + np.arange(block)) % n_weeks).reshape(n_resamples, -1)[:, :n_weeks]
    counts = np.apply_along_axis(np.bincount, 1, draws, minlength=n_weeks)
    tot = counts @ per_week
    with np.errstate(invalid="ignore", divide="ignore"):
        diffs = tot[:, 0] / tot[:, 1] - tot[:, 2] / tot[:, 3]
    lo, hi = np.nanquantile(diffs, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    spike, normal = d.loc[d[flag], value], d.loc[~d[flag], value]
    return {"value": value, "block_weeks": block, "n_spike": len(spike), "n_normal": len(normal), "mean_spike": spike.mean(),
            "mean_normal": normal.mean(), "diff": spike.mean() - normal.mean(), "ci_low": lo, "ci_high": hi}
