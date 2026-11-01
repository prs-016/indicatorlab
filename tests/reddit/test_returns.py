
import numpy as np
import pandas as pd

from src.reddit.apple_event_study import weekly_returns


def test_weekly_close_to_close_with_holiday():
    # Week of 2024-08-26: Mon-Fri. Week of 2024-09-02: Monday is Labor Day (no row).
    dates = pd.to_datetime(["2024-08-26", "2024-08-30", "2024-09-03", "2024-09-06",
                            "2024-09-09", "2024-09-12"])   # second week's Friday "missing" -> Thursday close used
    closes = [100.0, 110.0, 105.0, 99.0, 101.0, 120.0]
    wk = weekly_returns(pd.DataFrame({"date": dates, "Close": closes})).set_index("week_start")
    assert wk.loc["2024-08-26", "adj_close"] == 110.0
    assert np.isnan(wk.loc["2024-08-26", "weekly_return"])          # no previous week
    assert np.isclose(wk.loc["2024-09-02", "weekly_return"], 99 / 110 - 1)
    assert wk.loc["2024-09-09", "last_trading_date"] == "2024-09-12"
    assert np.isclose(wk.loc["2024-09-09", "weekly_return"], 120 / 99 - 1)


def test_gap_week_does_not_span_two_weeks():
    dates = pd.to_datetime(["2024-01-05", "2024-01-19"])     # week of 2024-01-08 absent
    wk = weekly_returns(pd.DataFrame({"date": dates, "Close": [10.0, 12.0]})).set_index("week_start")
    assert np.isnan(wk.loc["2024-01-15", "weekly_return"])
