"""Week 4 strategy engine on synthetic data: timing (no look-ahead), costs, trades, random baseline, rules."""
import numpy as np
import pandas as pd
import pytest

from src.reddit import strategies_week4 as sw

DAYS = pd.bdate_range("2020-01-06", "2020-03-27")      # Mondays 2020-01-06 ...
WEEKS = pd.date_range("2020-01-06", "2020-03-23", freq="W-MON")


def _close(rets: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({tk: 100 * np.cumprod(np.full(len(DAYS), 1 + r)) for tk, r in rets.items()}, index=DAYS)


def test_week_w_weights_start_on_the_first_trading_day_after_its_sunday():
    weekly = pd.DataFrame({"AAA": 0.0}, index=WEEKS)
    weekly.loc["2020-01-13", "AAA"] = 1.0            # week of Jan 13 (ends Sun Jan 19)
    d = sw.daily_weights(weekly, DAYS)
    assert d.loc["2020-01-17", "AAA"] == 0.0         # still inside week W
    assert d.loc["2020-01-20", "AAA"] == 1.0         # Monday of W+1
    assert d.loc["2020-01-27", "AAA"] == 0.0         # the next week's target (0) replaces it


def test_weight_on_day_d_earns_the_return_of_d_plus_one_and_pays_costs():
    close = _close({"AAA": 0.01})
    weekly = pd.DataFrame({"AAA": 0.0}, index=WEEKS)
    weekly.loc["2020-01-13", "AAA"] = 1.0
    sim = sw.simulate(weekly, close)
    assert sim.loc["2020-01-17", "net"] == 0.0
    assert sim.loc["2020-01-20", "net"] == pytest.approx(0.01 - sw.COST_BPS / 1e4)   # entry cost, next-day return
    assert sim.loc["2020-01-21", "net"] == pytest.approx(0.01)


def test_shorts_pay_borrow():
    close = _close({"AAA": 0.0})
    weekly = pd.DataFrame({"AAA": -1.0}, index=WEEKS)
    sim = sw.simulate(weekly, close)
    assert sim.loc["2020-02-04", "net"] == pytest.approx(-sw.BORROW_BPS_YR / 1e4 / sw.TRADING_DAYS)


def test_trades_are_runs_of_same_sign_weights():
    weekly = pd.DataFrame({"AAA": [0, 0.5, 0.5, 0, -0.2, 0.3], "BBB": [0.1] * 6}, index=WEEKS[:6])
    t = sw.trades_of(weekly)
    a = t[t["ticker"] == "AAA"].reset_index(drop=True)
    assert a[["weeks", "side"]].values.tolist() == [[2, 1], [1, -1], [1, 1]]
    assert t[t["ticker"] == "BBB"]["weeks"].tolist() == [6]


def test_random_baseline_keeps_holding_lengths_sides_and_sizes():
    trades = pd.DataFrame({"ticker": ["AAA", "BBB"], "start": WEEKS[[1, 3]], "weeks": [2, 3], "side": [1, -1],
                           "size": [0.5, 0.25]})
    rw = sw.random_weekly(trades, WEEKS, ["AAA", "BBB", "CCC"], (WEEKS[0], WEEKS[-1]), np.random.default_rng(0))
    assert (rw > 0).sum().sum() == 2 and (rw < 0).sum().sum() == 3
    assert set(np.round(rw.to_numpy()[rw.to_numpy() != 0], 6)) <= {0.5, -0.25, 0.25, 0.75}
    again = sw.random_weekly(trades, WEEKS, ["AAA", "BBB", "CCC"], (WEEKS[0], WEEKS[-1]), np.random.default_rng(0))
    pd.testing.assert_frame_equal(rw, again)


def _features():
    idx, cols = WEEKS, ["A", "B", "C", "D", "E", "F"]
    z = pd.DataFrame(0.0, index=idx, columns=cols)
    return {"att": z + [3, 0, 2.5, 0, 0, 0], "abn_vol": z + 2.0, "ret_1w": z + [-0.1, 0.0, 0.1, 0, 0, 0],
            "sent_dev": z + 0.1, "mkt_att_z": pd.Series(0.0, index=idx), "regime_40w": pd.Series(1.0, index=idx),
            "regime_200d": pd.Series(1.0, index=idx), "mom_12_1": z + [0.3, 0.2, 0.1, 0, -0.1, -0.2],
            "n_scored": z + 50, "vol12": z + 0.02, "att_prod": z + [1.0, 0, 0, 0, 0, 0],
            "prod_net": z + 0.2, "rel20": z - 0.01}


def test_s1_longs_hot_losers_shorts_hot_winners_and_halves_on_market_attention():
    f = _features()
    w = sw.s1_weights(f)
    assert w.iloc[0].to_dict() == {"A": 0.25, "B": 0.0, "C": -0.25, "D": 0.0, "E": 0.0, "F": 0.0}   # 25% name cap
    f["mkt_att_z"].iloc[0] = 2.0
    assert sw.s1_weights(f).iloc[0]["A"] == 0.125
    f["sent_dev"].loc[:, "A"] = -0.5                 # bad-news loser is skipped; short side alone is capped at 20%
    assert sw.s1_weights(f).iloc[1].to_dict()["C"] == -0.2


def test_s2_holds_at_most_four_weeks_and_caps_names():
    w = sw.s2_weights(_features())
    assert (w > 0).sum(axis=1).max() <= sw.S2_TOP and w.max().max() <= sw.S2_NAME_CAP + 1e-12
    run = (w["A"] > 0).astype(int)
    longest = run.groupby((run != run.shift()).cumsum()).sum().max()
    assert longest <= sw.S2_MAX_WEEKS


def test_s3_needs_a_product_spike_with_positive_tone_and_no_investor_spike():
    f = _features()
    f["att"].loc[:, "A"] = 0.0
    w = sw.s3_weights(f)
    assert w.iloc[0]["A"] == sw.S3_WEIGHT and w.iloc[0].drop("A").eq(0).all()
    f["att"].loc[:, "A"] = 1.0                       # investors already spiking: no entry
    assert sw.s3_weights(f)["A"].eq(0).all()


def test_decide_requires_30_train_entries_and_both_random_tests_and_spy():
    base = {"entries": 40, "pct_random_beaten": 95.0, "sharpe": 1.0, "index_sharpe": 0.5}
    assert sw.decide({"train": base, "test": base})[0] == "Keep"
    assert sw.decide({"train": {**base, "entries": 12}, "test": base})[0] == "Insufficient trades"
    assert sw.decide({"train": base, "test": {**base, "index_sharpe": 1.2}})[0] == "Drop"


def test_deflated_sharpe_comes_from_vibe_and_counts_trials():
    if not sw.MULTITEST.exists():
        pytest.skip("Vibe-Trading clone not next to the repo")
    test = {"sharpe_daily": 0.05, "n_days": 1200, "skew": 0.0, "kurtosis": 3.0}
    out = sw.deflated(test, [0.2, -0.1, 0.5, 0.9, 0.0])
    assert out["n_trials"] == 5 and 0.0 <= out["dsr"] <= 1.0
