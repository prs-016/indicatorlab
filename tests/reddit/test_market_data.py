"""Weekly returns, 52-week betas without look-ahead, forward returns and the holdout cut."""
import numpy as np
import pandas as pd

from src.reddit import market_data as md


def _weekly(n=70, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2024-01-01", periods=n, freq="7D", tz="UTC")
    m = pd.Series(rng.normal(0, 0.02, n), index=weeks)
    r = 1.5 * m + pd.Series(rng.normal(0, 0.005, n), index=weeks)
    return r, m


def test_beta_uses_only_the_previous_52_weeks():
    r, m = _weekly()
    beta = md.rolling_beta(r, m)
    assert beta.iloc[:52].isna().all() and abs(beta.iloc[60] - 1.5) < 0.1
    r2 = r.copy()
    r2.iloc[60] = 5.0                                 # a huge move in week 60 ...
    assert md.rolling_beta(r2, m).iloc[60] == beta.iloc[60]   # ... does not change week 60's beta


def test_weekly_close_labels_by_monday_and_leaves_gaps():
    days = pd.DatetimeIndex(["2024-01-02", "2024-01-05", "2024-01-19"], tz="UTC")   # no trading in week of Jan 8
    wc = md.weekly_close(pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=days))
    assert wc.index.day_of_week.tolist() == [0, 0, 0]
    assert wc["A"].tolist()[0] == 2.0 and np.isnan(wc["A"].iloc[1]) and wc["A"].iloc[2] == 3.0


def test_research_only_blanks_forward_windows_that_cross_the_holdout():
    weeks = pd.date_range("2025-09-01", periods=5, freq="7D", tz="UTC")        # Sep 1 .. Sep 29
    df = pd.DataFrame({"week": weeks, **{f"{p}ret_next{k}": 0.01 for p in ("", "abn_") for k in range(1, 5)}})
    out = md.research_only(df)
    assert out["week"].dt.strftime("%m-%d").tolist() == ["09-01", "09-08", "09-15", "09-22"]
    sep15 = out[out["week"] == pd.Timestamp("2025-09-15", tz="UTC")].iloc[0]
    assert sep15["ret_next1"] == 0.01 and np.isnan(sep15["ret_next2"])        # Sep 22-28 ok, Sep 29+ is holdout
