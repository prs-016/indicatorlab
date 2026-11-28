"""Offline v2 signals -> persistent orders -> cash/returns integration."""

import socket

import numpy as np
import pandas as pd
import pytest
from india_week3_test_support import vibe_checkout

from src.india_week3_costs import OriginalIndiaCosts
from src.india_week3_portfolio import AccountingPolicy
from src.india_week3_runner import TrialLedger, build_and_account, prepare_snapshots
from src.india_week3_strategies import UNIVERSES, price_features


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No network permitted")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def fixture(market="US"):
    dates = pd.bdate_range("2022-01-03", periods=30, tz="UTC") + pd.Timedelta(hours=16)
    close = pd.DataFrame(
        {t: 100 + np.arange(len(dates)) * 0.05 for t in UNIVERSES[market]}, index=dates
    )
    volume = close * 0 + 1000
    daily = {
        t: pd.DataFrame({"sma50": 90.0, "sma20": 120.0, "ll20": 80.0}, index=dates)
        for t in close
    }
    at = pd.Timestamp("2022-01-04", tz="UTC")
    f = pd.DataFrame(index=close.columns)
    fields = {
        "close": 100.0,
        "atr": 2.0,
        "momentum": 0.2,
        "sma50": 90.0,
        "hh55": 99.0,
        "volume": 1000.0,
        "vr": 2.0,
        "reddit_ratio": 2.0,
        "wiki_ratio": 2.0,
        "reddit_rz": 3.0,
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
        "prior_close": 70.0,
        "prior_sma20": 90.0,
        "prior_atr": 4.0,
        "prior_rsi": 25.0,
        "prior_posts": 100.0,
        "posts": 70.0,
        "rsi": 40.0,
        "previous_high": 99.0,
    }
    for key, value in fields.items():
        f[key] = value
    f["close_at"] = dates[0]
    f["published_at"] = dates[0] + pd.Timedelta(seconds=1)
    f["attention_week"] = at - pd.Timedelta(days=8)
    f["prior_snapshot"] = at - pd.Timedelta(days=7)
    f["prior_published_at"] = at - pd.Timedelta(days=7, hours=1)
    b = {
        "close": 110.0,
        "sma200": 100.0,
        "sma200_previous20": 99.0,
        "rv20": 0.2,
        "close_at": dates[0],
        "published_at": dates[0],
    }
    f["momentum"] = np.linspace(0.1, 0.3, len(f))
    return close, volume, daily, {at: (f, b)}


def run(strategy="AGM_v2", market="US", **updates):
    close, volume, daily, snapshots = fixture(market)
    ledger = TrialLedger()
    args = {
        "strategy": strategy,
        "market": market,
        "split": "test",
        "close": close,
        "volume": volume,
        "snapshots": snapshots,
        "daily_features": daily,
        "policy": AccountingPolicy(
            100000,
            "whole" if market == "IN" else "fractional",
            "pretrade_nav_fee_inclusive_budget",
        ),
        "pending_update": "replace_on_snapshot",
        "trial_id": "synthetic:" + strategy,
        "ledger": ledger,
        "provenance": {"dataset": "synthetic fixture only"},
    }
    args.update(updates)
    result = build_and_account(**args)
    return result, ledger


@pytest.mark.parametrize("strategy", ["AGM_v2", "SCB_v2", "AER_v2"])
def test_all_three_persist_signals_to_fills_and_returns(strategy):
    result, ledger = run(strategy)
    assert result["result"].metrics["filled_entries"] == 2
    assert len(result["result"].fills) == 4
    assert result["result"].daily.iloc[-1].positions_value == 0
    assert np.isfinite(result["result"].metrics["net_sharpe"])
    assert all(result["orders"].execution_at > result["orders"].decision_at)
    assert ledger.records[0]["status"] == "complete"
    assert ledger.records[0]["settings"]["strategy"] == strategy
    assert len(ledger.records[0]["settings_sha256"]) == 64


def test_agm_defined_ablation_changes_risk_not_selection():
    full, _ = run()
    none, _ = run(variant="no_attention")
    reddit, _ = run(variant="reddit_only")
    p = next(iter(full["plans"].values()))
    q = next(iter(none["plans"].values()))
    assert p.ungated == q.ungated and set(p.targets) == set(q.targets)
    assert q.targets == {t: 2 * w for t, w in p.targets.items()}
    assert (
        reddit["orders"].target_weight.tolist() == full["orders"].target_weight.tolist()
    )
    with pytest.raises(ValueError, match="Only AGM"):
        run("SCB_v2", variant="no_attention")


def test_protective_exit_cannot_fill_its_trigger_or_be_cancelled():
    close, vol, daily, snaps = fixture()
    close.iloc[3:] = 90
    at = next(iter(snaps))
    later = at + pd.Timedelta(days=7)
    f, b = snaps[at]
    f = f.copy()
    f["close_at"] = close.index[5]
    f["published_at"] = close.index[5]
    f["attention_week"] = later - pd.Timedelta(days=8)
    snaps[later] = (f, b)
    result, _ = run(close=close, volume=vol, daily_features=daily, snapshots=snaps)
    exits = result["orders"][result["orders"].reason == "stop"]
    assert len(exits) == 2 and (exits.execution_at == close.index[4]).all()
    assert (exits.decision_at == close.index[3]).all()


def test_entry_expiry_and_missing_holdings_fail_closed():
    close, vol, daily, snaps = fixture()
    vol.iloc[1:3] = 0
    result, _ = run(close=close, volume=vol, daily_features=daily, snapshots=snaps)
    assert result["result"].metrics["filled_entries"] == 0
    assert any("expired" in e["event"] for e in result["events"])
    close, vol, daily, snaps = fixture()
    close.iloc[3] = np.nan
    ledger = TrialLedger()
    with pytest.raises(ValueError, match="held"):
        run(
            close=close,
            volume=vol,
            daily_features=daily,
            snapshots=snaps,
            ledger=ledger,
        )
    assert ledger.records[0]["status"] == "failed"


@pytest.mark.parametrize("strategy", ["AGM_v2", "SCB_v2", "AER_v2"])
def test_actual_isolated_india_engine_binding_and_end_to_end(strategy):
    with OriginalIndiaCosts(vibe_checkout(), {}) as engine:
        assert engine.calc_commission(10, 100, 1, True) == pytest.approx(1.186226)
        result, ledger = run(strategy, market="IN", india_engine=engine)
        assert result["result"].daily.commission.sum() > 0
        assert (
            result["result"].fills.iloc[0].price
            > result["result"].fills.iloc[0]["close"]
        )
        assert ledger.records[0]["settings"]["engine"]["source_sha256"]
    assert engine.child.poll() is not None


def test_prepare_price_indicators_and_publication_without_data_fetch():
    history = pd.bdate_range("2020-01-01", "2022-01-14", tz="UTC") + pd.Timedelta(
        hours=16
    )
    c = pd.Series(100 + np.arange(len(history)) * 0.5, index=history)
    bar = pd.DataFrame(
        {
            "close": c,
            "high": c + 0.2,
            "low": c - 0.2,
            "volume": 1000.0,
            "published_at": history + pd.Timedelta(seconds=1),
        }
    )
    at = pd.Timestamp("2022-01-04", tz="UTC")
    _, _, _, snap = fixture()
    attention = snap[at][0][
        [
            "reddit_ratio",
            "reddit_rz",
            "wiki_ratio",
            "wiki_rz",
            "published_at",
            "attention_week",
        ]
    ]
    bars = {t: bar.copy() for t in UNIVERSES["US"]}
    snapshots, daily = prepare_snapshots("AGM_v2", "US", bars, bar, {at: attention})
    features, _ = snapshots[at]
    assert features.iloc[0].momentum == pytest.approx(
        price_features(bar).loc[features.iloc[0].close_at, "momentum"]
    )
    closes = pd.DataFrame({t: bars[t]["close"] for t in bars}).loc["2022-01-03":]
    volume = closes * 0 + 1000
    # A tiny supplied calendar can still test integration; it is not historical completeness.
    result, _ = run(
        close=closes, volume=volume, daily_features=daily, snapshots=snapshots
    )
    assert result["result"].metrics["filled_entries"] == 2


def test_signal_to_original_ic_null_returns_dsr_and_full_trial_audit(tmp_path):
    import json

    from src.india_week3_runner import evaluate_recorded_run

    result, ledger = run()
    close, volume, _, snapshots = fixture()
    trade_ids = result["result"].trades.trade_id.tolist()
    dsr_trials = pd.DataFrame(
        {
            "trial_id": ["synthetic-old", "synthetic-new", "synthetic-variant"],
            "status": ["complete"] * 3,
            "daily_sharpe": [-0.1, 0.05, 0.1],
        }
    )
    report = evaluate_recorded_run(
        result,
        benchmark=close.iloc[:, 0],
        close=close,
        volume=volume,
        snapshots=snapshots,
        market="US",
        split="test",
        policy=AccountingPolicy(
            100000, "fractional", "pretrade_nav_fee_inclusive_budget"
        ),
        ledger=ledger,
        trial_prefix="synthetic-eval",
        vibe_root=vibe_checkout(),
        random_candidates={key: [1] for key in trade_ids},
        max_attempts=2,
        dsr_trials=dsr_trials,
        effective_trials=3,
        dependence_assumption="synthetic independent sensitivity only",
        ledger_complete=True,
    )
    assert len(report["random"]) == 200
    assert report["ic"]["submitted_intervals"] == 1
    assert 0 <= report["DSR"]["probability"] <= 1
    assert len([r for r in ledger.records if r["kind"] == "random"]) == 200
    assert {r["kind"] for r in ledger.records} == {"strategy", "random", "IC", "DSR"}
    json.dumps(ledger.records, allow_nan=False)
    path = tmp_path / "synthetic_trials.json"
    assert len(ledger.save(path)) == 64
    assert len(json.loads(path.read_text())["records"]) == len(ledger.records)
    with pytest.raises(FileExistsError):
        ledger.save(path)


def test_defined_agm_batch_retains_all_variant_parameters():
    from src.india_week3_runner import run_defined_ablations

    close, volume, daily, snapshots = fixture()
    ledger = TrialLedger()
    args = {
        "market": "US",
        "split": "test",
        "close": close,
        "volume": volume,
        "snapshots": snapshots,
        "daily_features": daily,
        "policy": AccountingPolicy(
            100000, "fractional", "pretrade_nav_fee_inclusive_budget"
        ),
        "pending_update": "replace_on_snapshot",
        "ledger": ledger,
        "provenance": {"dataset": "synthetic"},
    }
    results = run_defined_ablations(
        "AGM_v2", run_arguments=args, trial_prefix="synthetic-ablation"
    )
    assert len(results) == len(ledger.records) == 4
    assert all(value is not None for value in results.values())
    assert {r["settings"]["variant"] for r in ledger.records} == set(results)


def test_past_fills_unchanged_by_future_prices_and_invalid_publication_rejected():
    close, volume, daily, snaps = fixture()
    first, _ = run(close=close, volume=volume, daily_features=daily, snapshots=snaps)
    changed = close.copy()
    changed.iloc[20:] = changed.iloc[20:] * 1.01
    second, _ = run(close=changed, volume=volume, daily_features=daily, snapshots=snaps)
    pd.testing.assert_frame_equal(
        first["result"].daily.iloc[:20], second["result"].daily.iloc[:20]
    )
    at = next(iter(snaps))
    f, b = snaps[at]
    f = f.copy()
    f["published_at"] = at + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="unpublished"):
        run(snapshots={at: (f, b)})


def test_aer_cooldown_and_event_consumption_persist_between_weekly_snapshots():
    close, volume, daily, snapshots = fixture()
    for frame in daily.values():
        frame["sma20"] = 90.0
    first = next(iter(snapshots))
    template, b = snapshots[first]
    for at in [first + pd.Timedelta(days=7), first + pd.Timedelta(days=21)]:
        f = template.copy()
        previous = close.index[close.index < at][-1]
        f["close_at"] = previous
        f["published_at"] = previous
        f["attention_week"] = at - pd.Timedelta(days=8)
        f["prior_snapshot"] = at - pd.Timedelta(days=7)
        f["prior_published_at"] = at - pd.Timedelta(days=8)
        snapshots[at] = (f, b)
    result, _ = run(
        "AER_v2", close=close, volume=volume, daily_features=daily, snapshots=snapshots
    )
    entries = result["result"].fills[result["result"].fills.buy]
    assert len(entries) == 6
    first_names = set(
        entries.loc[
            entries.execution_at == pd.Timestamp("2022-01-04T16:00:00Z"), "ticker"
        ]
    )
    cooling_names = set(
        entries.loc[
            entries.execution_at == pd.Timestamp("2022-01-11T16:00:00Z"), "ticker"
        ]
    )
    assert first_names.isdisjoint(cooling_names)
    assert len(result["consumed_events"]) == 6


def test_original_fee_binding_rejects_unrelated_configuration_and_no_new_fees():
    with pytest.raises(ValueError, match="fee"):
        OriginalIndiaCosts(
            vibe_checkout(),
            {"access_token": "never-exposed-synthetic-marker"},
        )


def test_train_run_starts_cash_independently_and_evaluation_rejects_changed_inputs():
    from src.india_week3_runner import evaluate_recorded_run

    close, volume, daily, snapshots = fixture()
    shift = pd.Timedelta(days=364)
    shifted = {}
    for at, (f, b) in snapshots.items():
        f = f.copy()
        b = dict(b)
        for key in [
            "close_at",
            "published_at",
            "attention_week",
            "prior_snapshot",
            "prior_published_at",
        ]:
            f[key] = f[key] - shift
        for key in ["close_at", "published_at"]:
            b[key] = b[key] - shift
        shifted[at - shift] = (f, b)
    train, _ = run(
        split="train",
        close=close.set_axis(close.index - shift),
        volume=volume.set_axis(volume.index - shift),
        daily_features={t: f.set_axis(f.index - shift) for t, f in daily.items()},
        snapshots=shifted,
    )
    assert train["result"].daily.iloc[0]["cash"] == 100000
    test, ledger = run()
    changed = close.copy()
    changed.iloc[-1, 0] += 1
    with pytest.raises(ValueError, match="differs"):
        evaluate_recorded_run(
            test,
            benchmark=close.iloc[:, 0],
            close=changed,
            volume=volume,
            snapshots=snapshots,
            market="US",
            split="test",
            policy=AccountingPolicy(
                100000, "fractional", "pretrade_nav_fee_inclusive_budget"
            ),
            ledger=ledger,
            trial_prefix="tampered",
            vibe_root=vibe_checkout(),
        )


def test_aer_time_exit_is_predeclared_and_counts_entry_as_session_one():
    result, _ = run("AER_v2")
    assert result["result"].trades.duration.tolist() == [20, 20]
    exits = result["orders"][result["orders"].reason == "time"]
    assert len(exits) == 2
    assert set(exits.decision_at) == set(result["result"].trades.entry)


def test_infeasible_null_keeps_batch_failure_and_all_unrun_seeds():
    from src.india_week3_runner import evaluate_recorded_run

    result, ledger = run()
    close, volume, _, snapshots = fixture()
    with pytest.raises(ValueError):
        evaluate_recorded_run(
            result,
            benchmark=close.iloc[:, 0],
            close=close,
            volume=volume,
            snapshots=snapshots,
            market="US",
            split="test",
            policy=AccountingPolicy(
                100000, "fractional", "pretrade_nav_fee_inclusive_budget"
            ),
            ledger=ledger,
            trial_prefix="infeasible",
            vibe_root=vibe_checkout(),
            random_candidates={},
            max_attempts=1,
        )
    seeds = [r for r in ledger.records if r["kind"] == "random"]
    assert len(seeds) == 200 and all(r["status"] == "not_run" for r in seeds)
    assert any(
        r["kind"] == "random_schedule" and r["status"] == "failed"
        for r in ledger.records
    )


@pytest.mark.parametrize("strategy", ["AGM_v2", "SCB_v2", "AER_v2"])
def test_every_frozen_indicator_deletion_executes_and_is_audited(strategy):
    from src.india_week3_ablation import COMPONENTS
    from src.india_week3_runner import run_all_drop_one

    close, volume, daily, snapshots = fixture()
    ledger = TrialLedger()
    args = {
        "market": "US",
        "split": "test",
        "close": close,
        "volume": volume,
        "snapshots": snapshots,
        "daily_features": daily,
        "policy": AccountingPolicy(
            100000, "fractional", "pretrade_nav_fee_inclusive_budget"
        ),
        "pending_update": "replace_on_snapshot",
        "ledger": ledger,
        "provenance": {"dataset": "synthetic"},
    }
    results = run_all_drop_one(
        strategy, run_arguments=args, trial_prefix="frozen:" + strategy
    )
    assert len(results) == len(COMPONENTS[strategy]) + 1
    assert all(r is not None for r in results.values())
    assert len(ledger.records) == len(results)
    assert all(r["status"] == "complete" for r in ledger.records)
    for name in COMPONENTS[strategy]:
        assert (
            ledger.records[list(results).index("drop:" + name)]["settings"][
                "disabled_indicator"
            ]
            == name
        )


def test_drop_one_removes_gate_and_score_without_changing_baseline():
    from src.india_week3_ablation import drop_one_plan
    from src.india_week3_strategies import weekly_plan

    _, _, _, snapshots = fixture()
    at = next(iter(snapshots))
    frame, b = snapshots[at]
    changed = frame.copy()
    changed["sentiment_delta"] = -0.1
    assert not weekly_plan("AER_v2", "US", at, changed, b).targets
    dropped = drop_one_plan(
        "AER_v2", "US", at, changed, b, component="sentiment_change"
    )
    assert len(dropped.targets) == 2
    assert dropped.scores.iloc[0] == pytest.approx(0.1 / 0.03)
    assert not weekly_plan("AER_v2", "US", at, changed, b).targets
    changed = frame.copy()
    changed["hh55"] = 110.0
    assert not weekly_plan("SCB_v2", "US", at, changed, b).targets
    assert (
        len(drop_one_plan("SCB_v2", "US", at, changed, b, component="breakout").targets)
        == 2
    )
    with pytest.raises(ValueError):
        drop_one_plan("SCB_v2", "US", at, frame, b, component="stop")


def test_sentiment_indicator_deletion_removes_its_exit_but_keeps_price_risk():
    close, volume, daily, snapshots = fixture()
    first = next(iter(snapshots))
    frame, b = snapshots[first]
    later = first + pd.Timedelta(days=7)
    changed = frame.copy()
    previous = close.index[close.index < later][-1]
    changed["close_at"] = previous
    changed["published_at"] = previous
    changed["attention_week"] = later - pd.Timedelta(days=8)
    changed["sentiment"] = -0.1
    snapshots[later] = (changed, b)
    base, _ = run(
        "SCB_v2", close=close, volume=volume, daily_features=daily, snapshots=snapshots
    )
    dropped, _ = run(
        "SCB_v2",
        close=close,
        volume=volume,
        daily_features=daily,
        snapshots=snapshots,
        variant="drop:sentiment_level",
    )
    assert (base["orders"].reason == "sentiment").sum() == 2
    assert not (dropped["orders"].reason == "sentiment").any()
    assert (dropped["orders"].reason == "terminal").sum() == 2
