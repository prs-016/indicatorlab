"""Offline fixtures are never historical backtest or registration evidence."""

import socket

import numpy as np
import pandas as pd
import pytest
from india_week3_test_support import vibe_checkout

from src.india_week3_costs import OriginalIndiaCosts
from src.india_week3_portfolio import AccountingPolicy
from src.india_week3_runner import TrialLedger
from src.india_week3_strategies import UNIVERSES
from src.india_week3_wiki_strategies import (
    COMPONENTS,
    VERSIONS,
    build_wiki_orders,
    evaluate_wiki_run,
    prepare_wiki_snapshots,
    run_wiki_ablations,
    wiki_plan,
    wiki_price_features,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("No network in fixture tests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def data(market="US", days=30, weekly=False):
    dates = pd.bdate_range("2022-01-03", periods=days, tz="UTC") + pd.Timedelta(
        hours=16
    )
    close = pd.DataFrame({t: 100.0 for t in UNIVERSES[market]}, index=dates)
    vol = close * 0 + 1000
    daily = {
        t: pd.DataFrame({"sma20": 110.0, "ll10": 90.0, "rsi": 40.0}, index=dates)
        for t in close
    }
    f = pd.DataFrame(index=close.columns)
    for k, v in {
        "close": 100.0,
        "atr": 1.0,
        "momentum": 0.2,
        "sma50": 90.0,
        "hh20": 99.0,
        "volume_mean_ratio": 1.3,
        "wiki_ratio": 1.3,
        "wiki_rz": 1.0,
        "wiki_valid": True,
        "prior_wiki_ratio": 2.0,
        "prior_wiki_rz": 3.0,
        "prior_wiki_valid": True,
        "sma20": 110.0,
        "rsi": 40.0,
        "return1": 0.01,
    }.items():
        f[k] = v
    f["momentum"] = np.linspace(0.1, 0.3, len(f))
    snaps = {}
    for at in pd.date_range(
        pd.Timestamp("2022-01-04", tz="UTC"), dates[-1].normalize(), freq="7D"
    ):
        c = dates[dates < at][-1]
        row = f.copy()
        row["close_at"] = c
        row["published_at"] = c + pd.Timedelta(seconds=1)
        snaps[at] = (
            row,
            {"close": 110.0, "sma200": 100.0, "close_at": c, "published_at": c},
        )
        if not weekly:
            break
    return close, vol, daily, snaps


def run(strategy=VERSIONS[0], market="US", **updates):
    close, vol, daily, snaps = data(market)
    ledger = TrialLedger()
    args = {
        "strategy": strategy,
        "market": market,
        "split": "test",
        "close": close,
        "volume": vol,
        "snapshots": snaps,
        "daily_features": daily,
        "policy": AccountingPolicy(
            100000,
            "whole" if market == "IN" else "fractional",
            "pretrade_nav_fee_inclusive_budget",
        ),
        "trial_id": "fixture:" + strategy,
        "ledger": ledger,
        "provenance": {"synthetic": True},
    }
    args.update(updates)
    return build_wiki_orders(**args), args


@pytest.mark.parametrize("strategy", VERSIONS)
def test_us_entries_time_exits_and_accounting_replay(strategy):
    r, a = run(strategy)
    assert r["result"].metrics["filled_entries"] == 2
    assert r["result"].daily.cash.min() >= 0
    assert (r["result"].fills.execution_at > r["result"].fills.decision_at).all()
    assert (r["result"].trades.entry == a["close"].index[1]).all()
    duration = {VERSIONS[0]: 29, VERSIONS[1]: 20, VERSIONS[2]: 10}[strategy]
    assert (r["result"].trades.duration == duration).all()
    assert r["result"].daily.positions_value.iloc[-1] == 0
    assert a["ledger"].records[-1]["status"] == "complete"


@pytest.mark.parametrize("strategy", VERSIONS)
def test_original_india_engine_whole_shares(strategy):
    with OriginalIndiaCosts(vibe_checkout(), {}) as engine:
        r, a = run(strategy, market="IN", india_engine=engine)
        assert r["result"].metrics["filled_entries"] == 2
        assert r["result"].fills.commission.sum() > 0
        assert (r["result"].fills.quantity % 1 == 0).all()
        assert a["policy"].quantity_mode == "whole"


def test_watm_attention_scales_entire_book_not_stock_ranking():
    c, v, d, s = data()
    at = next(iter(s))
    f, b = s[at]
    base = wiki_plan(VERSIONS[0], "US", at, f, b)
    f.wiki_rz = 3.0
    hot = wiki_plan(VERSIONS[0], "US", at, f, b)
    assert hot.multiplier == 0.5
    pd.testing.assert_series_equal(base.scores, hot.scores)
    pd.testing.assert_series_equal(base.eligible, hot.eligible)
    r, _ = run(close=c, volume=v, daily_features=d, snapshots=s)
    assert set(r["result"].fills.query("buy").target_weight) == {0.25}
    assert set(r["result"].trades.ticker) == set(base.scores.nlargest(2).index)


def test_missing_attention_cash_and_zero_not_substitution():
    c, v, d, s = data()
    at = next(iter(s))
    f, b = s[at]
    f.loc[f.index[:3], ["wiki_ratio", "wiki_rz"]] = np.nan
    p = wiki_plan(VERSIONS[0], "US", at, f, b)
    assert p.status == "attention_unavailable" and p.multiplier == 0
    r, _ = run(close=c, volume=v, daily_features=d, snapshots=s)
    assert r["result"].metrics["filled_entries"] == 0
    assert f.wiki_ratio.isna().sum() == 3


@pytest.mark.parametrize(
    "strategy,field,value",
    [
        (VERSIONS[1], "volume_mean_ratio", 1.19),
        (VERSIONS[1], "wiki_ratio", 1.19),
        (VERSIONS[1], "hh20", 100.0),
        (VERSIONS[2], "prior_wiki_rz", 1.99),
        (VERSIONS[2], "wiki_ratio", 2.0),
        (VERSIONS[2], "rsi", 46.0),
        (VERSIONS[2], "return1", 0.0),
    ],
)
def test_exact_entry_boundaries(strategy, field, value):
    _, _, _, s = data()
    at = next(iter(s))
    f, b = s[at]
    assert wiki_plan(strategy, "US", at, f, b).eligible.all()
    f[field] = value
    assert not wiki_plan(strategy, "US", at, f, b).eligible.any()


def test_stops_execute_next_close_not_trigger_close():
    c, v, d, s = data()
    c.iloc[3:] = 97
    r, _ = run(close=c, volume=v, daily_features=d, snapshots=s)
    exits = r["result"].fills.query("not buy")
    assert (exits.execution_at == c.index[4]).all()
    assert (exits.decision_at == c.index[3]).all()


@pytest.mark.parametrize(
    "strategy,column,value",
    [
        (VERSIONS[1], "ll10", 101.0),
        (VERSIONS[2], "rsi", 61.0),
        (VERSIONS[2], "sma20", 99.0),
    ],
)
def test_defined_daily_exits(strategy, column, value):
    c, v, d, s = data()
    for f in d.values():
        f.loc[c.index[3], column] = value
    r, _ = run(strategy, close=c, volume=v, daily_features=d, snapshots=s)
    assert (r["result"].trades.exit == c.index[4]).all()


def test_expired_orders_missing_held_prices_and_exit_inputs():
    c, v, d, s = data()
    v.iloc[1:3] = 0
    r, _ = run(close=c, volume=v, daily_features=d, snapshots=s)
    assert r["result"].metrics["filled_entries"] == 0
    c, v, d, s = data()
    c.iloc[3] = np.nan
    with pytest.raises(ValueError, match="held"):
        run(close=c, volume=v, daily_features=d, snapshots=s)
    c, v, d, s = data()
    for f in d.values():
        f.loc[c.index[3], "ll10"] = np.nan
    with pytest.raises(ValueError, match="exit indicator"):
        run(VERSIONS[1], close=c, volume=v, daily_features=d, snapshots=s)


def test_benchmark_and_future_publication_fail_closed():
    _, _, _, s = data()
    at = next(iter(s))
    f, b = s[at]
    b["sma200"] = np.nan
    with pytest.raises(ValueError, match="benchmark"):
        wiki_plan(VERSIONS[0], "US", at, f, b)
    b["sma200"] = 100
    f["published_at"] = at + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="Noncausal"):
        wiki_plan(VERSIONS[0], "US", at, f, b)


def test_wcr_four_completed_decision_cooldown():
    c, v, d, s = data(days=75, weekly=True)
    r, _ = run(VERSIONS[2], close=c, volume=v, daily_features=d, snapshots=s)
    for _, g in r["result"].trades.groupby("ticker"):
        for old, new in zip(g.iloc[:-1].itertuples(), g.iloc[1:].itertuples()):
            decision = (
                r["result"]
                .fills.query("buy")
                .loc[
                    lambda x, current=new: x.execution_at.eq(current.entry)
                    & x.ticker.eq(current.ticker)
                ]
                .decision_at.iloc[0]
            )
            assert sum(old.exit < x < decision for x in s) >= 4


def test_all_frozen_predictive_ablations_execute():
    for strategy in VERSIONS:
        _, args = run(strategy)
        for key in ["strategy", "trial_id"]:
            args.pop(key)
        args["ledger"] = TrialLedger()
        outputs = run_wiki_ablations(
            strategy=strategy, arguments=args, trial_prefix="ablation:" + strategy
        )
        assert len(outputs) == 1 + len(COMPONENTS[strategy])
        assert all(v is not None for v in outputs.values())


def test_price_windows_use_prior_rows_and_prefix_causality():
    idx = pd.bdate_range("2020-01-01", periods=240, tz="UTC") + pd.Timedelta(hours=21)
    c = pd.Series(100 + np.arange(240) * 0.1, index=idx)
    b = pd.DataFrame({"close": c, "high": c + 1, "low": c - 1, "volume": 1000.0})
    f = wiki_price_features(b)
    assert f.hh20.iloc[30] == b.high.iloc[10:30].max()
    assert f.volume_mean_ratio.iloc[30] == 1
    changed = b.copy()
    changed.iloc[200:, changed.columns.get_indexer(["close", "high", "low"])] *= 2
    pd.testing.assert_frame_equal(f.iloc[:200], wiki_price_features(changed).iloc[:200])


def test_existing_evaluation_interface_ic_benchmark_and_missing_dsr():
    r, a = run()
    report = evaluate_wiki_run(
        r,
        benchmark=a["close"].iloc[:, 0],
        close=a["close"],
        volume=a["volume"],
        snapshots=a["snapshots"],
        market="US",
        split="test",
        policy=a["policy"],
        ledger=a["ledger"],
        trial_prefix="fixture-eval",
        vibe_root=vibe_checkout(),
    )
    assert report["ic"]["source_sha256"]
    assert report["DSR"] is None and report["random"] is None
    assert "Full trial history and explicit DSR assumptions" in report["missing"]


def raw_fixture():
    idx = pd.bdate_range("2021-01-04", "2022-02-11", tz="UTC") + pd.Timedelta(hours=21)
    bars = {}
    for n, ticker in enumerate(UNIVERSES["US"]):
        close = pd.Series(100 + np.arange(len(idx)) * (0.1 + n * 0.01), index=idx)
        bars[ticker] = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1000.0,
                "published_at": idx + pd.Timedelta(minutes=5),
            }
        )
    benchmark = bars["AAPL"].copy()
    rows = []
    for at in pd.date_range("2022-01-04", "2022-02-08", freq="7D", tz="UTC"):
        for ticker in bars:
            rows.append(
                {
                    "decision_at": at,
                    "ticker": ticker,
                    "attention_week": at - pd.Timedelta(days=8),
                    "wiki_ratio": 1.3,
                    "wiki_rz": 1.0,
                    "eligible_at_snapshot": True,
                    "wiki_published_at_guide": at - pd.Timedelta(days=1),
                }
            )
    return bars, benchmark, pd.DataFrame(rows)


def test_watm_raw_signals_through_orders_and_returns():
    bars, benchmark, wiki = raw_fixture()
    snaps, daily = prepare_wiki_snapshots("US", bars, benchmark, wiki)
    close = pd.DataFrame({t: b.close for t, b in bars.items()}).loc["2022-01-01":]
    volume = close * 0 + 1000
    r, _a = run(close=close, volume=volume, snapshots=snaps, daily_features=daily)
    assert r["result"].metrics["filled_entries"] >= 2
    assert np.isfinite(r["result"].daily.net_return).all()
    assert "snapshots" in r["settings"]["data_sha256"]
    assert (r["result"].fills.execution_at > r["result"].fills.decision_at).all()


def test_preparation_publication_lag_week_and_future_prefix():
    bars, benchmark, wiki = raw_fixture()
    snaps, _ = prepare_wiki_snapshots("US", bars, benchmark, wiki)
    at = min(snaps)
    for b in bars.values():
        b.loc[b.index > at, ["open", "high", "low", "close"]] *= 1.01
    again, _ = prepare_wiki_snapshots("US", bars, benchmark, wiki)
    pd.testing.assert_frame_equal(snaps[at][0], again[at][0])
    wiki.loc[0, "wiki_published_at_guide"] = at + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="Wikipedia unavailable"):
        prepare_wiki_snapshots("US", bars, benchmark, wiki)
    wiki.loc[0, "wiki_published_at_guide"] = at - pd.Timedelta(days=1)
    wiki.loc[0, "attention_week"] = at - pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="week does not precede"):
        prepare_wiki_snapshots("US", bars, benchmark, wiki)


def test_new_watm_run_reuses_all_200_nulls_and_dsr():
    from src.india_week3_wiki_strategies import wiki_random_candidates

    # Explicitly synthetic, tiny panel. Fixed null location preserves trade durations.
    close, volume, daily, snaps = data(days=6)
    r, a = run(close=close, volume=volume, daily_features=daily, snapshots=snaps)
    trials = pd.DataFrame(
        {
            "trial_id": ["fixture-alpha-1", "fixture-alpha-2"],
            "status": ["complete", "complete"],
            "daily_sharpe": [0.1, 0.2],
        }
    )
    # Nonconstant synthetic returns are necessary for DSR, never historical evidence.
    close, volume, daily, snaps = data(days=6)
    close.iloc[2] = 100.1
    close.iloc[3] = 100.05
    close.iloc[4] = 100.2
    close.iloc[5] = 100.15
    r, a = run(close=close, volume=volume, daily_features=daily, snapshots=snaps)
    candidates = wiki_random_candidates(r, close, volume)
    report = evaluate_wiki_run(
        r,
        benchmark=close.iloc[:, 0],
        close=close,
        volume=volume,
        snapshots=snaps,
        market="US",
        split="test",
        policy=a["policy"],
        ledger=a["ledger"],
        trial_prefix="fixture-controls",
        vibe_root=vibe_checkout(),
        random_candidates=candidates,
        max_attempts=10000,
        dsr_trials=trials,
        effective_trials=2,
        dependence_assumption="Explicit synthetic independence test only",
        ledger_complete=True,
    )
    assert len(report["random"]) == 200
    assert 0 <= report["DSR"]["probability"] <= 1
    for null in report["random"]:
        assert sorted(null.trades.duration) == sorted(r["result"].trades.duration)
        assert len(null.trades) == len(r["result"].trades)


def test_wvb_raw_breakout_and_mean_volume_are_not_old_median_rule():
    bars, benchmark, wiki = raw_fixture()
    for b in bars.values():
        at = pd.Timestamp("2022-01-03 21:00", tz="UTC")
        c = b.loc[at, "close"] * 1.02
        b.loc[at, ["open", "high", "low", "close"]] = [c, c + 0.2, c - 0.2, c]
        b.loc[at, "volume"] = 3000.0
    snaps, daily = prepare_wiki_snapshots("US", bars, benchmark, wiki)
    f, _ = snaps[min(snaps)]
    assert (f.volume_mean_ratio == 3).all()
    close = pd.DataFrame({t: b.close for t, b in bars.items()}).loc["2022-01-01":]
    volume = pd.DataFrame({t: b.volume for t, b in bars.items()}).loc[close.index]
    r, _ = run(
        VERSIONS[1], close=close, volume=volume, snapshots=snaps, daily_features=daily
    )
    assert r["result"].metrics["filled_entries"] >= 2


def test_wcr_raw_cooling_pullback_entry_uses_consecutive_weeks():
    bars, benchmark, wiki = raw_fixture()
    for b in bars.values():
        start = b.index.get_indexer([pd.Timestamp("2021-10-01 21:00", tz="UTC")])[0]
        c = b.close.copy()
        for i in range(start, len(c)):
            c.iloc[i] = c.iloc[i - 1] + (0.18 if i % 2 else -0.3)
        # Last completed Monday confirmation is positive and RSI remains 30..45.
        at = pd.Timestamp("2022-01-03 21:00", tz="UTC")
        i = c.index.get_loc(at)
        c.iloc[i] = c.iloc[i - 1] + 0.18
        for key, delta in [("open", 0), ("close", 0), ("high", 0.2), ("low", -0.2)]:
            b[key] = c + delta
    prev = pd.Timestamp("2021-12-28", tz="UTC")
    extra = wiki[wiki.decision_at.eq(wiki.decision_at.min())].copy()
    extra["decision_at"] = prev
    extra["attention_week"] = prev - pd.Timedelta(days=8)
    extra["wiki_published_at_guide"] = prev - pd.Timedelta(days=1)
    extra["wiki_ratio"] = 2.0
    extra["wiki_rz"] = 3.0
    wiki = pd.concat([extra, wiki], ignore_index=True)
    snaps, daily = prepare_wiki_snapshots("US", bars, benchmark, wiki)
    at = pd.Timestamp("2022-01-04", tz="UTC")
    f, b = snaps[at]
    assert wiki_plan(VERSIONS[2], "US", at, f, b).eligible.all()
    close = pd.DataFrame({t: b.close for t, b in bars.items()}).loc["2022-01-01":]
    volume = close * 0 + 1000
    r, _ = run(
        VERSIONS[2], close=close, volume=volume, snapshots=snaps, daily_features=daily
    )
    assert r["result"].metrics["filled_entries"] >= 2


def test_watm_missing_portfolio_attention_exits_existing_positions():
    c, v, d, s = data(weekly=True)
    _first, second = sorted(s)[:2]
    s[second][0]["wiki_ratio"] = np.nan
    s[second][0]["wiki_rz"] = np.nan
    r, _ = run(close=c, volume=v, daily_features=d, snapshots=s)
    early = r["result"].trades[r["result"].trades.entry.eq(c.index[1])]
    assert (early.exit == c.index[c.index > second][0]).all()


def test_watm_stop_cannot_be_cancelled_by_weekly_reselection():
    c, v, d, s = data(weekly=True)
    second = sorted(s)[1]
    trigger = c.index[c.index < second][-1]
    c.loc[trigger:] = 97.0
    r, _ = run(close=c, volume=v, daily_features=d, snapshots=s)
    early = r["result"].trades[r["result"].trades.entry.eq(c.index[1])]
    assert (early.exit == c.index[c.index > second][0]).all()
    assert r["result"].fills.query("buy").execution_at.value_counts().max() <= 2


def test_ic_scores_precede_risk_entry_gate():
    _, _, _, s = data()
    at = next(iter(s))
    f, b = s[at]
    f["atr"] = 6.0
    p = wiki_plan(VERSIONS[0], "US", at, f, b)
    assert p.scores.notna().all()
    assert not p.eligible.any()


def test_holdout_and_unknown_deletions_are_rejected():
    _, _, _, s = data()
    at = next(iter(s))
    f, b = s[at]
    with pytest.raises(ValueError, match="Holdout"):
        wiki_plan(VERSIONS[0], "US", pd.Timestamp("2025-10-01", tz="UTC"), f, b)
    with pytest.raises(ValueError, match="drop-one"):
        wiki_plan(VERSIONS[0], "US", at, f, b, disabled="invented")


def test_runtime_version_and_rule_hash_match_latest_frozen_revision():
    import hashlib
    import json

    from src.india_week3_wiki_strategies import FREEZE

    rules = json.loads((FREEZE / "rules.json").read_text())
    assert set(VERSIONS) == set(rules["versions"])
    r, _ = run()
    assert (
        r["settings"]["specification_sha256"]
        == hashlib.sha256((FREEZE / "rules.json").read_bytes()).hexdigest()
    )
    bars, benchmark, wiki = raw_fixture()
    snaps, daily = prepare_wiki_snapshots("US", bars, benchmark, wiki)
    close = pd.DataFrame({t: b.close for t, b in bars.items()}).loc["2022-01-01":]
    r, _ = run(
        close=close, volume=close * 0 + 1000, snapshots=snaps, daily_features=daily
    )
    assert any(e["event"] == "fee_inclusive_cash_funding" for e in r["events"])
    assert all(
        e["funded_target"] <= e["requested_target"]
        for e in r["events"]
        if e["event"] == "fee_inclusive_cash_funding"
    )
