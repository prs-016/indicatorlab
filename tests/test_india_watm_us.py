"""Offline technical integration; fixture results are never historical results."""

import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from india_week3_test_support import vibe_checkout

import src.india_watm_us as watm
from src.india_week3_portfolio import AccountingPolicy
from src.india_week3_runner import TrialLedger
from src.india_week3_wiki_strategies import FREEZE, build_wiki_orders


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("No acquisition/network allowed")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def fixture_inputs():
    # Reuse the existing fixture builder, without modifying a frozen test/module.
    spec = importlib.util.spec_from_file_location(
        "wiki_fixture_helpers",
        Path(__file__).with_name("test_india_week3_wiki_strategies.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bars, benchmark, wiki = module.raw_fixture()
    labels = benchmark.index.normalize().tz_localize(None)
    prices = {
        t: b[["open", "high", "low", "close", "volume"]].set_axis(labels).copy()
        for t, b in bars.items()
    }
    prices["SPY"] = (
        benchmark[["open", "high", "low", "close", "volume"]].set_axis(labels).copy()
    )
    schedule = pd.DataFrame({"close": benchmark.index}, index=labels)
    # Extend the synthetic attention table into a training segment as well.
    base = wiki[wiki.decision_at.eq(wiki.decision_at.min())]
    rows = []
    for at in pd.date_range("2021-11-16", "2022-02-08", freq="7D", tz="UTC"):
        f = base.copy()
        f["decision_at"] = at
        f["attention_week"] = at - pd.Timedelta(days=8)
        f["wiki_published_at_guide"] = at - pd.Timedelta(days=1)
        rows.append(f)
    return watm.USInputs(
        prices,
        schedule,
        pd.concat(rows, ignore_index=True),
        {
            "synthetic": True,
            "rules_sha256": hashlib.sha256(
                (FREEZE / "rules.json").read_bytes()
            ).hexdigest(),
        },
    )


def registration(inputs):
    return {
        "strategy": watm.STRATEGY,
        "rules_sha256": inputs.provenance["rules_sha256"],
        "registered_at": "2026-11-17T20:00:00Z",
        "confirmed_by": "synthetic fixture user",
        "confirmation_reference": "SYNTHETIC ONLY: not real shared registration",
    }


def test_real_verified_input_join_without_strategy_execution():
    if not watm.TIINGO.exists() or not watm.WIKI.exists():
        pytest.skip("Private historical source packages unavailable")
    inputs = watm.load_us_inputs()
    report = watm.preflight(inputs)
    assert report["stock_and_benchmark_rows"] == 28358
    assert report["aligned_sessions"] == 2578
    assert report["weekly_decisions"] == 487
    assert report["wiki_portfolio_coverage_pass"] == 487
    assert len(report["blockers"]) == 1 and "registration" in report["blockers"][0]
    assert not report["baseline_run_ready"]
    assert not report["timing"]["provider_publication_observed"]


def test_closed_session_mapping_retains_unknown_provider_publication():
    inputs = fixture_inputs()
    prepared = watm.prepare_us(inputs)
    for ticker, bars in prepared["bars"].items():
        assert bars.provider_publication_at.isna().all()
        assert list(bars.session_date) == list(inputs.prices[ticker].index)
        assert bars.index.equals(pd.DatetimeIndex(inputs.schedule["close"]))
        assert (pd.DatetimeIndex(bars.published_at) == bars.index).all()
    assert not prepared["provenance"]["availability"]["provider_publication_observed"]
    assert (
        prepared["panels"]["train"]["close"].index.max()
        < prepared["panels"]["test"]["close"].index.min()
    )
    for split, p in prepared["panels"].items():
        assert (
            p["close"].index.year == int("2021" if split == "train" else "2022")
        ).all()
        for at, (frame, _) in p["snapshots"].items():
            assert (frame.close_at < at).all()
            assert (frame.published_at <= at).all()


def test_no_new_lag_convention_is_invented():
    inputs = fixture_inputs()
    with pytest.raises(ValueError, match="No arbitrary"):
        watm.price_availability(
            inputs,
            {"mode": "calendar_lag", "lag_minutes": 0, "reference": "unapproved"},
        )


def test_preflight_capital_default_and_user_registration_confirmation():
    inputs = fixture_inputs()
    assert watm.preflight(inputs, registration=registration(inputs))[
        "baseline_run_ready"
    ]
    with pytest.raises(ValueError, match="Positive capital"):
        watm.preflight(inputs, initial_cash=0, registration=registration(inputs))
    record = registration(inputs)
    record["rules_sha256"] = "incorrect"
    assert not watm.preflight(inputs, registration=record)["baseline_run_ready"]


def test_observed_evidence_remains_separate_and_hash_bound(tmp_path):
    inputs = fixture_inputs()
    rows = []
    for ticker in inputs.prices:
        for date, close in inputs.schedule["close"].items():
            rows.append(
                {
                    "Date": str(date.date()),
                    "ticker": ticker,
                    "published_at": (close + pd.Timedelta(minutes=5)).isoformat(),
                }
            )
    path = tmp_path / "observed.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    policy = {
        "mode": "observed",
        "reference": "explicit synthetic receipts",
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    times, meta = watm.price_availability(inputs, policy)
    assert meta["provider_publication_observed"]
    assert (times["SPY"] > inputs.schedule["close"]).all()
    policy["sha256"] = "wrong"
    with pytest.raises(ValueError, match="hash mismatch"):
        watm.price_availability(inputs, policy)


def test_future_prices_do_not_change_earlier_snapshots():
    inputs = fixture_inputs()
    old = watm.prepare_us(inputs)
    at = pd.Timestamp("2021-12-07", tz="UTC")
    for frame in inputs.prices.values():
        frame.loc[
            frame.index > at.tz_localize(None), ["open", "high", "low", "close"]
        ] *= 2
    changed = watm.prepare_us(inputs)
    for stamp, (frame, b) in old["panels"]["train"]["snapshots"].items():
        if stamp < at:
            other = changed["panels"]["train"]["snapshots"][stamp]
            pd.testing.assert_frame_equal(frame, other[0])
            assert b == other[1]


def _fixture_run(prepared, split):
    p = prepared["panels"][split]
    return build_wiki_orders(
        strategy=watm.STRATEGY,
        market="US",
        split=split,
        **{k: p[k] for k in ["close", "volume", "snapshots", "daily_features"]},
        policy=AccountingPolicy(
            100000, "fractional", "pretrade_nav_fee_inclusive_budget"
        ),
        trial_id="synthetic-only",
        ledger=TrialLedger(),
        provenance={"synthetic": True}
    )


def test_terminal_adjustment_scaling_cannot_choose_watm_names_or_weights():
    inputs = fixture_inputs()
    base = watm.prepare_us(inputs)
    for i, (ticker, frame) in enumerate(inputs.prices.items()):
        # Models a future split/dividend factor constant over the observed prefix.
        frame[["open", "high", "low", "close"]] *= 2.0 ** (i % 3 - 1)
    scaled = watm.prepare_us(inputs)
    for split in ["train", "test"]:
        a = _fixture_run(base, split)
        b = _fixture_run(scaled, split)
        pd.testing.assert_series_equal(
            a["result"].daily.net_return,
            b["result"].daily.net_return,
            atol=1e-12,
            rtol=1e-10,
        )
        assert a["result"].trades.ticker.tolist() == b["result"].trades.ticker.tolist()
        assert a["result"].trades.entry.tolist() == b["result"].trades.entry.tolist()
        assert a["result"].trades.exit.tolist() == b["result"].trades.exit.tolist()
        for at, plan in a["plans"].items():
            other = b["plans"][at]
            pd.testing.assert_series_equal(
                plan.scores, other.scores, atol=1e-12, rtol=1e-10
            )
            pd.testing.assert_series_equal(plan.eligible, other.eligible)
            assert plan.regime == other.regime and plan.multiplier == other.multiplier


def test_controlled_fixture_execution_runs_existing_controls_and_defers_test(
    tmp_path, monkeypatch
):
    inputs = fixture_inputs()
    prepared = watm.prepare_us(inputs)
    monkeypatch.setattr(watm, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()
    output = tmp_path / "results" / "synthetic-only"
    result = watm.run_us_study(
        prepared,
        registration=registration(inputs),
        output=output,
        vibe_root=vibe_checkout(),
    )
    assert result["decision"] == "INSUFFICIENT TRAINING ENTRIES"
    assert set(result["performance"]) == {"train"}
    assert not (output / "test").exists()
    assert len(list((output / "train").glob("drop_*"))) == 4
    assert len(list((output / "train").glob("random_*"))) == 201  # includes summary CSV
    ledger = json.loads((output / "trial_ledger.json").read_text())
    assert len([r for r in ledger["records"] if r["kind"] == "random"]) == 200
    assert result["performance"]["train"]["DSR"] is None
    assert result["initial_cash"] == 100000
    assert (output / "train/metrics.json").exists()
    with pytest.raises(FileExistsError):
        watm.run_us_study(
            prepared,
            registration=registration(inputs),
            output=output,
            vibe_root=vibe_checkout(),
        )


def test_registration_is_checked_before_any_execution_or_output(tmp_path, monkeypatch):
    prepared = watm.prepare_us(fixture_inputs())
    monkeypatch.setattr(watm, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()
    output = tmp_path / "results" / "must-not-exist"
    with pytest.raises(ValueError, match="registration"):
        watm.run_us_study(
            prepared, registration=None, output=output, vibe_root=Path("/not-used")
        )
    assert not output.exists()


def test_manifest_path_escape_and_hash_tampering_fail_before_loading(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files_sha256": {"../private": "0" * 64}})
    )
    with pytest.raises(ValueError, match="path/hash mismatch"):
        watm._verify_inventory(tmp_path)
    (tmp_path / "data.csv").write_text("original")
    digest = hashlib.sha256((tmp_path / "data.csv").read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files_sha256": {"data.csv": digest}})
    )
    watm._verify_inventory(tmp_path)
    (tmp_path / "data.csv").write_text("tampered")
    with pytest.raises(ValueError, match="path/hash mismatch"):
        watm._verify_inventory(tmp_path)


def test_missing_held_price_fails_and_preserves_failure_ledger(tmp_path, monkeypatch):
    inputs = fixture_inputs()
    prepared = watm.prepare_us(inputs)
    p = prepared["panels"]["train"]
    p["close"].iloc[-6] = np.nan
    monkeypatch.setattr(watm, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()
    output = tmp_path / "results" / "synthetic-failure"
    with pytest.raises(ValueError, match="held"):
        watm.run_us_study(
            prepared,
            registration=registration(inputs),
            output=output,
            vibe_root=Path("/not-used"),
        )
    assert (output / "execution_failure.json").exists()
    ledger = json.loads((output / "trial_ledger.json").read_text())
    assert ledger["records"][0]["status"] == "failed"


def test_holdout_cannot_enter_clock_boundary():
    inputs = fixture_inputs()
    inputs.schedule.iloc[-1, inputs.schedule.columns.get_loc("close")] = pd.Timestamp(
        "2025-10-01", tz="UTC"
    )
    with pytest.raises(ValueError, match="Holdout"):
        watm.price_availability(inputs)


def test_registration_row_is_complete_and_never_claims_results():
    inputs = fixture_inputs()
    row = watm.registration_row(inputs)
    assert len(row) == 7 and row[:2] == ["Jamaal", "WATM_v1_2"]
    assert row[3:6] == [
        "NOT EVALUATED",
        "NOT EVALUATED / NOT EVALUATED",
        "NOT EVALUATED",
    ]
    assert "USD100000" in row[6]
    assert inputs.provenance["rules_sha256"] in row[6]
    assert "NOT REGISTERED" in row[6]
    assert "historical Tiingo publication receipt" in row[6]


def test_dsr_merges_all_recorded_alpha_trials_without_assuming_three():
    from types import SimpleNamespace

    ledger = TrialLedger()
    for i in range(5):
        ledger.record(
            "synthetic-current-" + str(i),
            kind="strategy" if i == 0 else "ablation",
            settings={},
            status="complete",
            metrics={"net_sharpe": float(i + 1) / 10},
        )
    returns = pd.Series([0.001, -0.002, 0.003, 0.001, -0.001, 0.002, -0.0005, 0.0015])
    runs = {
        "train": {
            "trial_id": "synthetic-run",
            "result": SimpleNamespace(daily=pd.DataFrame({"net_return": returns})),
        }
    }
    reports = {
        "train": {
            "DSR": None,
            "missing": ["Full trial history and explicit DSR assumptions"],
        }
    }
    prior = pd.DataFrame(
        {
            "trial_id": ["synthetic-prior-1", "synthetic-prior-2"],
            "status": ["complete", "complete"],
            "daily_sharpe": [0.1, 0.2],
        }
    )
    watm._finish_dsr(
        runs,
        reports,
        {},
        prior,
        3.0,
        "Explicit synthetic fixture dependence assumption only",
        True,
        ledger,
    )
    assert reports["train"]["DSR"]["attempted_trials"] == 7
    assert reports["train"]["missing"] == []
    assert (
        ledger.records[-1]["kind"] == "DSR"
        and ledger.records[-1]["status"] == "complete"
    )


def test_incomplete_dsr_history_never_becomes_probability_or_keep():
    ledger = TrialLedger()
    reports = {
        "train": {
            "DSR": None,
            "missing": ["Full trial history and explicit DSR assumptions"],
        }
    }
    watm._finish_dsr({}, reports, {}, None, None, None, False, ledger)
    assert reports["train"]["DSR"] is None and reports["train"]["missing"]
    assert ledger.records == []


def test_train_pass_gate_routes_test_without_claiming_mocked_performance(
    tmp_path, monkeypatch
):
    # Orchestration boundary unit test only. Metrics are mocked, never readiness evidence.
    from types import SimpleNamespace

    inputs = fixture_inputs()
    prepared = watm.prepare_us(inputs)
    monkeypatch.setattr(watm, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()
    calls = []

    def build(**kwargs):
        calls.append((kwargs["split"], kwargs.get("disabled")))
        result = SimpleNamespace(
            metrics={
                "filled_entries": 30,
                "net_sharpe": 0.2,
                "net_cumulative_return": 0.1,
            },
            trades=pd.DataFrame(),
            daily=pd.DataFrame(),
        )
        return {"trial_id": kwargs["trial_id"], "result": result, "plans": {}}

    def save(directory, run):
        directory.mkdir()

    def evaluate(run, **kwargs):
        return {
            "benchmark": {"net_sharpe": 0.1},
            "ic": {"ic": pd.Series([0.1])},
            "random": None,
            "DSR": None,
            "missing": ["Mocked control result; not historical evidence"],
        }

    monkeypatch.setattr(watm, "build_wiki_orders", build)
    monkeypatch.setattr(watm, "_save_run", save)
    monkeypatch.setattr(watm, "evaluate_wiki_run", evaluate)
    output = tmp_path / "results" / "mocked-orchestration-only"
    result = watm.run_us_study(
        prepared,
        registration=registration(inputs),
        output=output,
        vibe_root=Path("/not-used"),
    )
    assert set(result["performance"]) == {"train", "test"}
    assert len(calls) == 10
    assert result["decision"] == "NOT EVALUATED"
    assert len([s for s, component in calls if component is None]) == 2


def test_user_confirmation_time_does_not_invent_shared_entry_time():
    inputs = fixture_inputs()
    record = registration(inputs)
    record["confirmed_at"] = record.pop("registered_at")
    record["registered_at"] = None
    assert watm.preflight(inputs, registration=record)["baseline_run_ready"]
