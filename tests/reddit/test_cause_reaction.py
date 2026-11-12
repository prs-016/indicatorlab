"""Cause vs reaction on synthetic data with a planted one-week lead."""
import numpy as np
import pandas as pd

from src.reddit import cause_reaction as cr


def _panel(n_weeks=120, n_tickers=4, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2023-01-02", periods=n_weeks, freq="7D", tz="UTC")
    rows = []
    for t in range(n_tickers):
        prod = rng.normal(size=n_weeks)
        stock = 0.8 * np.r_[0.0, prod[:-1]] + 0.6 * rng.normal(size=n_weeks)   # stock chatter follows product
        rows.append(pd.DataFrame({"ticker": f"T{t}", "week": weeks, "prod_chatter": prod, "stock_chatter": stock,
                                  "prod_sent": rng.normal(size=n_weeks), "abn_ret": rng.normal(size=n_weeks)}))
    return pd.concat(rows, ignore_index=True)


def test_planted_lead_shows_as_forward_direction(monkeypatch):
    monkeypatch.setattr(cr, "N_BOOT", 200)
    table, diffs = cr.correlations(cr.lagged_pairs(_panel()))
    pooled = table[table["scope"] == "pooled"].set_index(["direction", "x", "y", "lag"])["pearson"]
    assert pooled[("forward", "prod_chatter", "stock_chatter", 1)] > 0.6
    assert abs(pooled[("reverse", "stock_chatter", "prod_chatter", 1)]) < 0.2
    d = diffs[(diffs["forward"] == "prod_chatter -> stock_chatter") & (diffs["lag"] == 1)].iloc[0]
    assert d["ci_low"] > 0          # forward is stronger, and the CI excludes zero


def test_lag_pairs_use_the_later_week_for_y():
    p = _panel(n_weeks=10, n_tickers=1)
    pairs = cr.lagged_pairs(p)
    one = pairs[(pairs["x"] == "prod_chatter") & (pairs["y"] == "stock_chatter") & (pairs["lag"] == 2)]
    first = one.iloc[0]
    expected = p.loc[p["week"] == first["week"] + pd.Timedelta(weeks=2), "stock_chatter"].iloc[0]
    assert np.isclose(first["yv"], expected)


def test_block_resampling_keeps_consecutive_weeks():
    rng = np.random.default_rng(1)
    s = cr._resample_weeks(np.arange(20), rng, 4)
    assert len(s) == 20 and all(s[i + 1] - s[i] == 1 for i in range(0, 20, 4) if i + 1 < 20)
