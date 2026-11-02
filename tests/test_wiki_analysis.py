import numpy as np
import pandas as pd

from src.wiki_analysis import (
    daily_peak_lag,
    edit_timing,
    last_weeks_table,
    spike_returns,
    tag_lift,
)

WEEKS = pd.date_range("2024-01-01", periods=10, freq="7D")


def _att(view_spikes, edit_spikes):
    rows = []
    for i, w in enumerate(WEEKS):
        rows.append({"week": w, "ticker": "A", "market": "US", "source": "wikipedia_views", "views": 100.0,
                     "ratio": 1.0, "rz": 0.0, "spike": i in view_spikes})
        rows.append({"week": w, "ticker": "A", "market": "US", "source": "wikipedia_edits", "edits": 5.0,
                     "ratio": 1.0, "rz": 0.0, "spike": i in edit_spikes})
    return pd.DataFrame(rows)


def _prices(big_move_week):
    abn = [0.001] * len(WEEKS)
    abn[big_move_week] = 0.2
    return pd.DataFrame({"week": WEEKS, "ticker": "A", "abn_ret": abn, "ret": abn, "ret_next1": abn})


def test_edit_timing_finds_edits_one_week_before_views():
    t = edit_timing(_att(view_spikes={5}, edit_spikes={4}), _prices(5))
    v = t[(t["event"] == "views spike")].set_index("lag_weeks")["share"]
    assert v[-1] == 1.0 and v[0] == 0.0 and v[1] == 0.0
    base = t["base_rate"].iloc[0]
    assert base == 0.1


def test_daily_peak_lag_is_edits_minus_views_in_days():
    days = pd.date_range("2024-01-01", periods=21)
    views = pd.Series(1, index=days)
    views[pd.Timestamp("2024-01-10")] = 50     # Wednesday of the week of Jan 8
    edits = pd.Series(0, index=days)
    edits[pd.Timestamp("2024-01-09")] = 7      # edits peak a day earlier
    lag = daily_peak_lag(views, edits, [pd.Timestamp("2024-01-08")])
    assert lag.tolist() == [-1.0]


def test_last_weeks_table_joins_views_edits_and_returns():
    att = _att(view_spikes={8}, edit_spikes={9})
    att["week"] = att["week"].dt.strftime("%Y-%m-%d")
    p = _prices(9).assign(week=lambda d: d["week"].dt.strftime("%Y-%m-%d"))
    out = last_weeks_table(att, p, ["2024-02-26", "2024-03-04"], ["A"])
    assert out["wiki_views_spike"].tolist() == [True, False]
    assert out["wiki_edits_spike"].tolist() == [False, True]
    assert out["ret_next_week"].notna().all() and (out["market"] == "US").all()


def test_daily_peak_lag_counts_ties_as_their_mean_day():
    days = pd.date_range("2024-01-01", periods=21)
    views = pd.Series(1, index=days)
    views[pd.Timestamp("2024-01-10")] = 50
    edits = pd.Series(0, index=days)
    edits[[pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-12")]] = 2   # tied 2 days before and after
    assert daily_peak_lag(views, edits, [pd.Timestamp("2024-01-08")]).tolist() == [0.0]


def test_tag_lift_compares_spike_and_normal_weeks():
    att = _att(view_spikes={2}, edit_spikes=set())
    we = pd.DataFrame({"week": WEEKS, "ticker": "A", "edits": 2, "reverts": 0,
                       "tag_ceo_executive": [0, 0, 3, 0, 0, 0, 0, 0, 0, 0]})
    lift = tag_lift(we, att)
    assert lift.loc["tag_ceo_executive", "spike_weeks"] == 3 and lift.loc["tag_ceo_executive", "normal_weeks"] == 0
    assert lift.loc["edits", "lift"] == 1


def test_spike_returns_reports_every_horizon_with_block_size():
    att = _att(view_spikes={3, 6}, edit_spikes=set())
    p = pd.DataFrame({"week": WEEKS, "ticker": "A",
                      **{f"{c}{k}": 0.01 for c in ("ret_next", "abn_ret_next") for k in range(1, 5)}})
    out = spike_returns(att, p, n_resamples=50)
    assert len(out) == 8 and out["block_weeks"].tolist() == [1, 2, 3, 4] * 2
    assert (out["n_spike"] == 2).all() and np.allclose(out["diff"], 0)
