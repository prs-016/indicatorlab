"""The shared spike rule: hand-checked values and no look-ahead."""
import numpy as np
import pandas as pd

from src.reddit.spike_rule import add_spikes, flag_spikes

RULE = {"ratio": 1.5, "rz_threshold": 2.0, "baseline_weeks": 8, "rz_min_history": 26, "mad_scale": 1.4826,
        "offset": 1.0}


def _weekly(values):
    idx = pd.date_range("2023-01-02", periods=len(values), freq="7D")   # Mondays
    return pd.Series(values, index=idx, dtype=float)


def _noisy(n, seed=0):
    return _weekly(100 + np.random.default_rng(seed).integers(-10, 11, n))


def test_baseline_excludes_current_week_and_abnormal_is_log_ratio():
    out = flag_spikes(_weekly([99] * 8 + [199]), RULE)
    assert out["baseline"].iloc[-1] == 99
    assert np.isclose(out["abnormal"].iloc[-1], np.log(200 / 100))


def test_no_flags_before_enough_history():
    x = _noisy(60)
    x.iloc[20] = 1000
    out = flag_spikes(x, RULE)
    assert not out["spike"].iloc[: 8 + 26].any()   # 8 weeks for a baseline, then 26 abnormal values for rz


def test_clear_spike_is_flagged():
    x = _noisy(60)
    x.iloc[50] = 400
    out = flag_spikes(x, RULE)
    assert out["spike"].iloc[50] and out["spike"].sum() == 1


def test_changing_future_weeks_leaves_past_flags_unchanged():
    x = _noisy(80, seed=3)
    x.iloc[45] = 350
    t = 55
    before = flag_spikes(x, RULE)
    y = x.copy()
    y.iloc[t + 1:] = y.iloc[t + 1:] * 10 + 500     # only weeks after t change
    after = flag_spikes(y, RULE)
    cols = ["baseline", "abnormal", "rz", "spike"]
    pd.testing.assert_frame_equal(before[cols].iloc[: t + 1], after[cols].iloc[: t + 1])


def test_missing_week_gives_no_baseline_and_no_spike():
    x = _noisy(60)
    x.iloc[45] = np.nan
    out = flag_spikes(x, RULE)
    assert np.isnan(out["baseline"].iloc[46]) and not out["spike"].iloc[45]


def test_add_spikes_works_per_group():
    a, b = _noisy(60, 1), _noisy(60, 2)
    b.iloc[50] = 500
    df = pd.concat([pd.DataFrame({"ticker": t, "week": s.index, "posts": s.values}) for t, s in (("A", a), ("B", b))])
    out = add_spikes(df, ["ticker"], "posts", rule=RULE)
    b_out = out[out["ticker"] == "B"].reset_index(drop=True)
    assert b_out["spike"].sum() == 1 and b_out["spike"].iloc[50]
    a_alone = flag_spikes(a, RULE)["spike"].to_numpy()
    assert (out.loc[out["ticker"] == "A", "spike"].to_numpy() == a_alone).all()   # groups don't mix
