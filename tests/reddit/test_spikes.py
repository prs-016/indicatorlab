
import numpy as np
import pandas as pd

from src.reddit.weekly_metrics import add_spike_columns, week_start


def frame(values, ticker="AAPL"):
    weeks = pd.date_range("2024-01-01", periods=len(values), freq="7D", tz="UTC")
    return pd.DataFrame({"ticker": ticker, "week_start": weeks, "posts": values,
                         "comments": values, "upvotes": values})


def test_hand_computed_example():
    # weeks:   0   1   2   3   4    5
    # values: 10  20  30  40  50  100
    # week 4 baseline = median(10,20,30,40) = 25 -> ratio 2.0 (spike, >= 2)
    # week 5 baseline = median(20,30,40,50) = 35 -> ratio 100/35 = 2.857
    out = add_spike_columns(frame([10, 20, 30, 40, 50, 100]), ["ticker"])
    assert out["posts_median_4w"].iloc[:4].isna().all()            # not enough history
    assert out["posts_median_4w"].iloc[4] == 25
    assert out["posts_spike_ratio"].iloc[4] == 2.0
    assert bool(out["posts_spike_flag"].iloc[4]) is True
    assert np.isclose(out["posts_spike_ratio"].iloc[5], 100 / 35)
    assert not out["posts_spike_flag"].iloc[:4].any()


def test_current_week_excluded_and_no_lookahead():
    base = frame([10, 10, 10, 10, 30, 10, 10])
    a = add_spike_columns(base, ["ticker"])
    assert a["posts_median_4w"].iloc[4] == 10          # the spike week itself is not in its baseline
    changed = base.copy()
    changed.loc[6, "posts"] = 10_000                   # change a future value
    b = add_spike_columns(changed, ["ticker"])
    pd.testing.assert_series_equal(a["posts_spike_ratio"].iloc[:6], b["posts_spike_ratio"].iloc[:6])


def test_zero_baseline_undefined():
    out = add_spike_columns(frame([0, 0, 0, 0, 5]), ["ticker"])
    assert np.isnan(out["posts_spike_ratio"].iloc[4])
    assert not out["posts_spike_flag"].iloc[4]
    assert out["posts_zero_base_nonzero"].iloc[4]


def test_missing_week_in_window_gives_nan():
    out = add_spike_columns(frame([10, np.nan, 10, 10, 10, 30]), ["ticker"])
    assert np.isnan(out["posts_median_4w"].iloc[4])     # window contains NaN
    assert np.isnan(out["posts_median_4w"].iloc[5])     # window weeks 1-4 contains NaN
    out2 = add_spike_columns(frame([10, np.nan, 10, 10, 10, 10, 30]), ["ticker"])
    assert out2["posts_median_4w"].iloc[6] == 10        # weeks 2-5 all defined


def test_groups_are_independent():
    df = pd.concat([frame([1, 1, 1, 1, 2], "AAPL"), frame([100, 100, 100, 100, 100], "MSFT")])
    out = add_spike_columns(df, ["ticker"]).set_index("ticker")
    assert out.loc["AAPL", "posts_spike_ratio"].iloc[4] == 2.0
    assert out.loc["MSFT", "posts_spike_ratio"].iloc[4] == 1.0


def test_negative_baseline_undefined():
    out = add_spike_columns(frame([-5, -5, -5, -5, 10]), ["ticker"])
    assert np.isnan(out["upvotes_spike_ratio"].iloc[4])


def test_week_start_is_monday_utc():
    ws = week_start(pd.Series(["2024-09-08", "2024-09-09", "2024-09-15", "2024-09-16"]))
    assert list(ws.dt.strftime("%Y-%m-%d")) == ["2024-09-02", "2024-09-09", "2024-09-09", "2024-09-16"]
    assert (ws.dt.day_of_week == 0).all()
