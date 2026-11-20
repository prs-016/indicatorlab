"""Offline boundaries, selected-score orientation and train-only nomination."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import config
from src.hk.week4 import features, public_data, run
from src.sentiment import finbert_scorer

ROOT = Path(__file__).resolve().parents[1]


def test_config_and_spec_share_week4_boundary():
    spec = json.loads((ROOT / "config/hk_week4_research.json").read_text())
    run.validate_specification(spec)
    assert str(config.holdout_start()) == "2026-11-01"
    assert spec["test"] == ["2022-01-01", "2026-10-31"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("end", "2026-11-01"),
        ("test", ["2022-01-01", "2025-09-30"]),
        ("random_runs", 199),
        ("prior_recorded_trials", 267),
    ],
)
def test_mismatched_rules_rejected(field, value):
    spec = json.loads((ROOT / "config/hk_week4_research.json").read_text())
    spec[field] = value
    with pytest.raises(ValueError):
        run.validate_specification(spec)


def test_three_hypotheses_preserved_without_post_test_tuning():
    old = json.loads((ROOT / "config/hk_week3_research.json").read_text())
    new = json.loads((ROOT / "config/hk_week4_research.json").read_text())
    assert new["strategies"] == old["strategies"][:3]
    assert any(
        "market_attention_risk_gate" in item["indicators"] for item in new["strategies"]
    )


def test_research_download_rejects_future_before_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Future research attempted a network call")

    monkeypatch.setattr(public_data.requests, "get", forbidden)
    with pytest.raises(ValueError, match="holdout"):
        public_data.download_prices("0700.HK", "2015-01-01", "2026-11-01")


def test_stale_price_cache_is_not_claimed_as_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(public_data, "DATA", tmp_path)
    (tmp_path / "prices").mkdir()
    pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2025-09-30"])).to_parquet(
        tmp_path / "prices/0700.HK.parquet"
    )
    with pytest.raises(ValueError, match="snapshot"):
        public_data.download_prices("0700.HK", "2015-01-01", "2026-10-31")


def test_negative_selected_scores_rank_above_rejected_names():
    priority = pd.Series(
        {"selected_low": -0.2, "selected_high": -0.1, "rejected": 0, "missing": np.nan}
    )
    mask = pd.Series(
        {
            "selected_low": True,
            "selected_high": True,
            "rejected": False,
            "missing": False,
        }
    )
    observed = priority.notna()
    score = features.oriented_score(mask, priority, observed)
    assert score.selected_high > score.selected_low > score.rejected
    assert np.isnan(score["missing"])


def test_zero_priority_ablation_retains_eligibility_information():
    p = pd.Series([0.0, 0.0, 0.0])
    s = features.oriented_score(pd.Series([True, True, False]), p, p.notna())
    assert s.iloc[0] == s.iloc[1] > s.iloc[2]


def test_nomination_uses_both_train_markets_only():
    selections = {
        market: {name: {"variant": 0} for name in ["a", "b"]} for market in ["HK", "US"]
    }
    rows = [
        {"id": f"{market}.{name}.v0.train", "sharpe": sr, "entries": 40}
        for market, name, sr in [
            ("HK", "a", 0),
            ("US", "a", 2),
            ("HK", "b", 1.5),
            ("US", "b", 1.5),
        ]
    ]
    # An irrelevant test row cannot affect selection.
    rows.append({"id": "HK.a.v0.test", "sharpe": 1000, "entries": 40})
    candidate = run.nominate_train_candidate(rows, selections)
    assert candidate["strategy"] == "b"
    assert candidate["nomination_is_keep"] is False


def test_started_test_cannot_be_repeated(tmp_path):
    (tmp_path / "test_started.json").write_text("{}")
    with pytest.raises(FileExistsError, match="completed test"):
        run.run(tmp_path)


def test_shared_scorer_batched_probability_schema_without_network(monkeypatch):
    calls = []

    def factory(model, revision, device):
        def classify(texts, **kwargs):
            calls.append((texts, kwargs))
            return [
                [
                    {"label": "positive", "score": 0.7},
                    {"label": "negative", "score": 0.2},
                    {"label": "neutral", "score": 0.1},
                ]
                for _ in texts
            ]

        return classify

    monkeypatch.setattr(finbert_scorer, "_classifier", factory)
    scorer = finbert_scorer.FinbertScorer("local", "pinned", 8, 512, "cpu")
    out = scorer.score(["profits grew", "", "profits grew"])
    assert len(calls[0][0]) == 1
    assert calls[0][1] == {"batch_size": 8, "truncation": True, "max_length": 512}
    assert out.loc[0, "sentiment_pos"] == 0.7
    assert out.loc[0, "sentiment_neg"] == 0.2
    assert np.isnan(out.loc[1, "sentiment_neu"])
    assert (
        finbert_scorer.prepare_text("  Report ", " profits\n grew ")
        == "Report profits grew"
    )


def test_shared_scorer_source_attribution_matches_exact_team_copy():
    # Exact file from ca3d391; don't require that sibling branch's Git objects
    # in a fresh Jack checkout to run offline tests.
    expected = "8663385349511360891a2a4524aa7ca98a4cce61e197284c5b532bc86b5d373b"
    actual = (ROOT / "src/sentiment/finbert_scorer.py").read_bytes()
    assert hashlib.sha256(actual).hexdigest() == expected


def test_fx_uses_only_previous_observed_close_and_rejects_stale():
    raw = pd.Series([7.8, 7.9], index=pd.to_datetime(["2026-10-23", "2026-10-26"]))
    dates = pd.to_datetime(["2026-10-26", "2026-10-27"])
    rates, ages = features.previous_close_fx(raw, dates, 7)
    assert rates.tolist() == [7.8, 7.9]
    assert ages.tolist() == [3, 1]
    with pytest.raises(ValueError, match="stale"):
        features.previous_close_fx(raw.iloc[:1], pd.to_datetime(["2026-11-02"]), 7)


def test_week4_weather_closure_removed_without_fabricating_sessions():
    from src.hk.week4.market_calendar import sessions

    actual = sessions("2023-07-14", "2023-07-18")
    assert pd.Timestamp("2023-07-17") not in actual
    assert pd.Timestamp("2023-07-18") in actual


def test_delayed_exit_overlap_is_rejected():
    with pytest.raises(ValueError, match="overlaps"):
        features.validate_plan_overlap(
            [
                {"symbol": "0700.HK", "entry": 1, "exit": 9},
                {"symbol": "0700.HK", "entry": 8, "exit": 12},
            ]
        )
    features.validate_plan_overlap(
        [
            {"symbol": "0700.HK", "entry": 1, "exit": 9},
            {"symbol": "0700.HK", "entry": 9, "exit": 12},
        ]
    )


def test_all_train_diagnostics_precede_test_and_noop_is_ineligible(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    trace = []
    days = pd.to_datetime(["2021-12-30", "2021-12-31", "2022-01-03", "2022-01-04"])
    bundle = SimpleNamespace(
        index=pd.DataFrame(
            {"close": [100, 101, 100, 101], "open": [100] * 4, "dividend": [0.0] * 4},
            index=days,
        ),
        fx=pd.Series(1.0, index=days),
        quality={},
    )
    monkeypatch.setattr(run, "build_bundle", lambda market, spec: bundle)
    monkeypatch.setattr(
        run, "freeze", lambda directory, spec: directory.mkdir(parents=True)
    )
    monkeypatch.setattr(run, "base_request", lambda bundle, spec, directory: {})
    monkeypatch.setattr(run, "make_plans", lambda *args: ([], {}, (0, 1)))
    monkeypatch.setattr(run, "OUTPUT", tmp_path / "out")
    monkeypatch.setattr(run, "upstream_dsr", lambda *args: 0.5)
    directory = tmp_path / "run"

    def worker(request, destination):
        ids = [task["id"] for task in request["tasks"]]
        is_test = any(".test." in key for key in ids)
        if is_test:
            assert (directory / "candidate_before_test.json").exists()
            assert (directory / "train_eligibility.json").exists()
            assert (
                "HK_train_evaluations.json" in trace
                and "US_train_evaluations.json" in trace
            )
        trace.append(destination.name)
        results = []
        arrays = {}
        for task in request["tasks"]:
            arrays[task["id"]] = np.array([0.01, -0.005])
            results.append(
                {
                    "id": task["id"],
                    "entries": 30,
                    "sharpe": 1.0,
                    "max_drawdown": -0.005,
                    "trades": [],
                    "random_percentile": 95.0,
                    "random_sharpes": [0.0] * 200,
                }
            )
        np.savez_compressed(destination.with_suffix(".npz"), **arrays)
        return {"results": results}

    monkeypatch.setattr(run, "worker", worker)
    run.run(directory)
    saved = json.loads((directory / "candidate_before_test.json").read_text())
    assert saved["train_eligible"] is False
    cases = json.loads((directory / "train_eligibility.json").read_text())
    assert all(
        not case["eligible"] and case["unchanged_indicators"] for case in cases.values()
    )
    assert trace.index("US_train_evaluations.json") < trace.index(
        "HK_test_evaluations.json"
    )


def test_relative_run_directory_resolved_before_worker_changes_cwd(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, "build_bundle", lambda market, spec: None)
    seen = []

    class BeforePortfolio(Exception):
        pass

    def freeze(directory, spec):
        seen.append(directory)
        raise BeforePortfolio

    monkeypatch.setattr(run, "freeze", freeze)
    with pytest.raises(BeforePortfolio):
        run.run(Path("relative-study"))
    assert seen == [(tmp_path / "relative-study").resolve()]
    assert seen[0].is_absolute()
