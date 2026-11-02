import numpy as np
import pandas as pd

from src.wiki_prices import bootstrap_diff, research_only, weekly_close, weekly_panel


def _daily(n_weeks=60, seed=0):
    days = pd.bdate_range("2024-01-01", periods=5 * n_weeks)
    rng = np.random.default_rng(seed)
    m = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(days)))
    return pd.DataFrame({"SPY": m, "A": m * 2, "B": 50 * np.cumprod(1 + rng.normal(0, 0.02, len(days)))},
                        index=days)


def test_weekly_close_is_friday_close_labelled_monday():
    d = _daily()
    wc = weekly_close(d)
    assert (wc.index.dayofweek == 0).all()
    assert wc.loc["2024-01-01", "A"] == d.loc["2024-01-05", "A"]


def test_forward_returns_and_beta_of_a_copy_of_the_market():
    p = weekly_panel(_daily(), ["A", "B"], "SPY", "US")
    a = p[p["ticker"] == "A"].reset_index(drop=True)
    assert np.isclose(a.loc[10, "ret_next2"], a.loc[12, "close"] / a.loc[10, "close"] - 1)
    assert np.isnan(a.loc[51, "beta"]) and np.isclose(a.loc[53, "beta"], 1.0)   # 52 past weeks needed
    assert np.allclose(a["abn_ret"].dropna(), 0, atol=1e-12)                     # A = 2 x market
    assert (p["market"] == "US").all()


def test_research_only_blanks_windows_that_reach_the_holdout():
    weeks = pd.date_range("2025-09-01", periods=6, freq="7D")
    df = pd.DataFrame({"week": weeks, **{f"{c}{k}": 0.01 for c in ("ret_next", "abn_ret_next") for k in range(1, 5)}})
    out = research_only(df, pd.Timestamp("2025-10-01"))
    assert out["week"].max() == pd.Timestamp("2025-09-22")       # week ending Sep 28
    assert out.loc[out["week"] == pd.Timestamp("2025-09-01"), "ret_next3"].notna().all()
    assert out.loc[out["week"] == pd.Timestamp("2025-09-01"), "ret_next4"].isna().all()


def test_bootstrap_ci_covers_a_known_difference():
    rng = np.random.default_rng(1)
    weeks = np.repeat(np.arange(300), 5)
    spike = rng.random(len(weeks)) < 0.1
    value = rng.normal(0, 0.01, len(weeks)) + np.where(spike, 0.02, 0.0)
    r = bootstrap_diff(pd.DataFrame({"week": weeks, "spike": spike, "v": value}), "v", n_resamples=300)
    assert r["ci_low"] < 0.02 < r["ci_high"] and r["ci_low"] > 0
    assert r["n_spike"] + r["n_normal"] == len(weeks)


def test_block_bootstrap_widens_the_ci_for_autocorrelated_values():
    rng = np.random.default_rng(2)
    n = 400
    shared = np.convolve(rng.normal(0, 0.01, n + 3), np.ones(4), "valid")   # 4-week overlapping sums
    df = pd.DataFrame({"week": np.arange(n), "spike": rng.random(n) < 0.3, "v": shared})
    one = bootstrap_diff(df, "v", n_resamples=400, block=1)
    four = bootstrap_diff(df, "v", n_resamples=400, block=4)
    assert four["block_weeks"] == 4 and one["diff"] == four["diff"]
    assert (four["ci_high"] - four["ci_low"]) > (one["ci_high"] - one["ci_low"])
