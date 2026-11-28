"""Synthetic v2 decision/risk checks; no historical portfolio evaluation."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.india_week3_strategies import (
    UNIVERSES,
    aer_event_eligible,
    attention_features,
    daily_risk,
    entry_close,
    open_holding,
    price_features,
    sentiment_net,
    weekly_exit,
    weekly_plan,
)

NOW = pd.Timestamp("2021-06-08", tz="UTC")


def snapshot(market="IN"):
    frame = pd.DataFrame(index=UNIVERSES[market])
    fields = {
        "close": 110.0,
        "atr": 2.0,
        "sma50": 100.0,
        "momentum": 0.2,
        "hh55": 105.0,
        "volume": 200.0,
        "vr": 2.0,
        "reddit_ratio": 2.0,
        "reddit_rz": 3.0,
        "wiki_ratio": 2.0,
        "wiki_rz": 3.0,
        "sentiment": 0.3,
        "sentiment_delta": 0.4,
        "prior_return5": -0.1,
        "prior_atr_pct": 0.03,
        "prior_reddit_ratio": 3.0,
        "prior_reddit_rz": 3.0,
        "prior_wiki_ratio": 2.0,
        "prior_wiki_rz": 2.0,
        "prior_sentiment": -0.4,
        "prior_close": 80.0,
        "prior_sma20": 100.0,
        "prior_atr": 5.0,
        "prior_rsi": 25.0,
        "prior_posts": 100.0,
        "posts": 70.0,
        "rsi": 40.0,
        "previous_high": 105.0,
    }
    for key, value in fields.items():
        frame[key] = value
    frame["close_at"] = NOW - pd.Timedelta(hours=8)
    frame["published_at"] = NOW - pd.Timedelta(hours=1)
    frame["attention_week"] = NOW - pd.Timedelta(days=8)
    frame["prior_snapshot"] = NOW - pd.Timedelta(days=7)
    frame["prior_published_at"] = NOW - pd.Timedelta(days=7, hours=1)
    benchmark = {
        "close": 110.0,
        "sma200": 100.0,
        "sma200_previous20": 99.0,
        "rv20": 0.2,
        "close_at": NOW - pd.Timedelta(hours=8),
        "published_at": NOW - pd.Timedelta(hours=1),
    }
    return frame, benchmark


@pytest.mark.parametrize("market", ["US", "IN"])
@pytest.mark.parametrize("strategy", ["AGM_v2", "SCB_v2", "AER_v2"])
def test_all_entry_rules_ranking_sizing_and_two_slots(strategy, market):
    frame, benchmark = snapshot(market)
    plan = weekly_plan(strategy, market, NOW, frame, benchmark)
    assert plan.status == "ready" and plan.regime
    assert len(plan.targets) == 2
    assert list(plan.targets) == sorted(UNIVERSES[market])[:2]
    assert all(0 < w <= 0.5 for w in plan.targets.values())
    assert len(plan.scores) == len(frame)


def test_attention_is_only_a_common_agm_risk_multiplier():
    frame, b = snapshot()
    full = frame.assign(reddit_rz=0, wiki_rz=0)
    a = weekly_plan("AGM_v2", "IN", NOW, full, b)
    z = weekly_plan("AGM_v2", "IN", NOW, frame, b)
    pd.testing.assert_series_equal(a.scores, z.scores)
    assert a.ungated == z.ungated
    assert z.targets == {t: w * 0.5 for t, w in a.targets.items()}
    frame.loc[frame.index[:2], ["reddit_ratio", "reddit_rz"]] = np.nan
    missing = weekly_plan("AGM_v2", "IN", NOW, frame, b)
    assert not missing.targets and missing.status.startswith("missing")


@pytest.mark.parametrize("strategy", ["AGM_v2", "SCB_v2", "AER_v2"])
def test_risk_regime_zero_atr_and_missing_inputs_do_not_enter(strategy):
    frame, b = snapshot()
    frame["atr"] = 0
    assert not weekly_plan(strategy, "IN", NOW, frame, b).targets
    frame, b = snapshot()
    b["rv20"] = 0.8
    assert not weekly_plan(strategy, "IN", NOW, frame, b).targets
    b["rv20"] = np.nan
    assert weekly_plan(strategy, "IN", NOW, frame, b).regime is None


def test_scb_confirmation_and_no_pyramiding():
    frame, b = snapshot()
    held = tuple(sorted(frame.index)[:1])
    p = weekly_plan("SCB_v2", "IN", NOW, frame, b, held=held)
    assert len(p.targets) == 1 and held[0] not in p.targets
    for column, value in [
        ("close", 100),
        ("vr", 1),
        ("sentiment", 0.19),
        ("sentiment_delta", 0.09),
        ("wiki_ratio", 1),
        ("volume", 0),
    ]:
        changed = frame.copy()
        changed[column] = value
        assert not weekly_plan("SCB_v2", "IN", NOW, changed, b).targets
    changed = frame.assign(sentiment=np.nan)
    assert weekly_plan("SCB_v2", "IN", NOW, changed, b).scores.isna().all()


def test_aer_shock_recovery_and_event_cooldown():
    frame, b = snapshot()
    for column, value in [
        ("prior_return5", -0.07),
        ("posts", 76),
        ("rsi", 30),
        ("sentiment", -0.1),
        ("prior_sentiment", -0.2),
    ]:
        changed = frame.copy()
        changed[column] = value
        assert not weekly_plan("AER_v2", "IN", NOW, changed, b).targets
    assert aer_event_eligible("shock", set(), sessions_since_exit=None)
    assert not aer_event_eligible("shock", {"shock"}, sessions_since_exit=20)
    assert not aer_event_eligible("new", set(), sessions_since_exit=9)
    assert aer_event_eligible("new", set(), sessions_since_exit=10)


def test_no_future_publication_wrong_week_or_prior_shock():
    frame, b = snapshot()
    for column, value in [
        ("published_at", NOW + pd.Timedelta(seconds=1)),
        ("close_at", NOW),
        ("attention_week", NOW),
    ]:
        changed = frame.copy()
        changed[column] = value
        with pytest.raises(ValueError):
            weekly_plan("SCB_v2", "IN", NOW, changed, b)
    changed = frame.copy()
    changed["prior_published_at"] = NOW
    with pytest.raises(ValueError):
        weekly_plan("AER_v2", "IN", NOW, changed, b)
    with pytest.raises(ValueError):
        weekly_plan("SCB_v2", "IN", "2025-10-01T00:00:00Z", frame, b)


def test_strictly_next_close_two_session_expiry_and_split_boundary():
    closes = pd.date_range(NOW, periods=4, freq="D")
    volume = pd.Series([100, 0, 100, 100], index=closes)
    kwargs = {"split_end": closes[-1], "remaining_sessions": 5}
    assert entry_close(NOW, closes, volume, **kwargs) == closes[2]
    volume.iloc[2] = 0
    assert entry_close(NOW, closes, volume, **kwargs) is None
    assert (
        entry_close(NOW, closes, volume, split_end=closes[-1], remaining_sessions=4)
        is None
    )


@pytest.mark.parametrize(
    "strategy,limit", [("AGM_v2", 63), ("SCB_v2", 42), ("AER_v2", 20)]
)
def test_trailing_stops_ratchet_and_time_exit(strategy, limit):
    h = open_holding(strategy, 100, 2, 0.04)
    up, reason = daily_risk(h, 110)
    assert reason is None and up.stop == 106 and up.held_sessions == 2
    down, reason = daily_risk(up, 105)
    assert reason == "stop" and down.stop >= up.stop
    _, reason = daily_risk(replace(h, held_sessions=limit - 1), 100)
    assert reason == "time"
    with pytest.raises(ValueError):
        daily_risk(h, np.nan)


@pytest.mark.parametrize(
    "strategy,kw,reason",
    [
        ("AGM_v2", {"sma": 101}, "sma50"),
        ("SCB_v2", {"low20": 101}, "prior_low20"),
        ("AER_v2", {"sma": 99}, "sma20_target"),
    ],
)
def test_daily_price_exit_rules(strategy, kw, reason):
    _, got = daily_risk(open_holding(strategy, 100, 2, 0.04), 100, **kw)
    assert got == reason


def test_weekly_exits_and_unknown_sentiment():
    assert weekly_exit("SCB_v2", regime=True, sentiment=-0.01) == "sentiment"
    assert weekly_exit("AER_v2", regime=True, sentiment=0.2) == "sentiment"
    assert weekly_exit("AGM_v2", regime=True, momentum=-0.1) == "selection_or_momentum"
    assert weekly_exit("SCB_v2", regime=False) == "regime"
    assert weekly_exit("SCB_v2", regime=None, sentiment=np.nan) is None


def bars():
    index = pd.date_range("2020-01-01", periods=260, freq="D", tz="UTC")
    c = pd.Series(np.arange(100, 360, dtype=float), index=index)
    return pd.DataFrame({"close": c, "high": c + 1, "low": c - 1, "volume": 100.0})


def test_indicator_formulas_warmup_and_prefix_causality():
    f = bars()
    full = price_features(f)
    prefix = price_features(f.iloc[:240])
    pd.testing.assert_frame_equal(full.iloc[:240], prefix)
    assert full["momentum"].iloc[126] == pytest.approx(
        f.close.iloc[105] / f.close.iloc[0] - 1
    )
    assert full["hh55"].iloc[55] == f.high.iloc[:55].max()
    assert full["vr"].iloc[20] == 1 and full["atr"].iloc[20] == 2
    assert full["rsi"].iloc[14] == 100
    assert full["sma200_previous20"].iloc[:219].isna().all()
    changed = f.copy()
    changed.iloc[225:] = np.nan
    assert price_features(changed).iloc[230]["rsi"] != 50
    assert price_features(f.assign(close=100, high=101, low=99))["rsi"].iloc[-1] == 50


def test_attention_reuses_eight_week_rule_and_preserves_missing_weeks():
    index = pd.date_range("2019-01-07", periods=60, freq="7D", tz="UTC")
    counts = pd.Series(np.arange(60.0) ** 2, index=index)
    full = attention_features(counts)
    pd.testing.assert_frame_equal(full.iloc[:50], attention_features(counts.iloc[:50]))
    assert full["baseline"].iloc[8] == np.median(counts.iloc[:8])
    counts.iloc[40] = np.nan
    assert pd.isna(attention_features(counts)["ratio"].iloc[41])
    with pytest.raises(ValueError):
        attention_features(counts.drop(index[5]))


def test_shared_finbert_probabilities_not_vader_fractions():
    posts = pd.DataFrame(
        {
            "post_id": [str(i) for i in range(20)],
            "ticker": "TCS.NS",
            "sentiment_pos": 0.7,
            "sentiment_neg": 0.1,
            "sentiment_neu": 0.2,
        }
    )
    assert sentiment_net(posts, complete=True) == pytest.approx(0.6)
    assert np.isnan(sentiment_net(posts.iloc[:19], complete=True))
    assert np.isnan(sentiment_net(posts, complete=False))
    with pytest.raises(ValueError):
        sentiment_net(pd.concat([posts, posts.iloc[:1]]), complete=True)
    with pytest.raises(ValueError):
        sentiment_net(posts.assign(sentiment_pos=1.1), complete=True)


def test_protective_exit_never_fills_at_trigger_and_has_no_entry_expiry():
    from src.india_week3_strategies import exit_close

    closes = pd.date_range(NOW, periods=4, freq="D")
    volume = pd.Series([100, 0, 0, 100], index=closes)
    assert exit_close(NOW, closes, volume, split_end=closes[-1]) == closes[-1]
    assert exit_close(NOW, closes, volume, split_end=closes[-2]) is None
