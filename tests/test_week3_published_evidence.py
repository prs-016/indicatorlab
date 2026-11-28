"""Offline frozen-rule and actual-result package integrity; no backtesting."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "india_research/submission/week3_complex_v1_2_20261123"
FREEZE = ROOT / "india_research/reports/week3_wiki_frozen_20261117_v1_2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_original_rule_freeze_is_verified_without_rewriting_historical_hashes():
    frozen = json.loads((FREEZE / "checksums.json").read_text())
    for name, expected in frozen["rules_files"].items():
        assert digest(FREEZE / name) == expected
    assert digest(FREEZE / "rules.json") == (
        "c44d9adf372c069a064fdcbec25ee5fce35640b99b390cd03ed58dab9f273c33"
    )


def test_current_publication_and_legacy_parameter_dependencies_are_hash_verified():
    manifest = json.loads((PACKAGE / "publication_manifest.json").read_text())
    for name, expected in manifest["files_sha256"].items():
        path = (PACKAGE / name).resolve()
        assert path.is_relative_to(PACKAGE) and digest(path) == expected
    for name, expected in manifest["source_files"].items():
        assert digest(ROOT / name) == expected
    legacy = ROOT / "india_research/reports/week3_v2_registration_frozen_20261115"
    assert digest(legacy / "parameters.json") == (
        "b8050ee0f1411cb8bc5b54d04ed20b6c938c364eec5e18d071be0164d8eec72e"
    )


@pytest.mark.parametrize("strategy", ["WATM_v1_2", "WVB_v1_2", "WCR_v1_2"])
@pytest.mark.parametrize("split", ["train", "test"])
def test_actual_null_metrics_match_counts_and_reported_percentiles(strategy, split):
    summary = json.loads((PACKAGE / "results_summary.json").read_text())[strategy][
        split
    ]
    with (PACKAGE / strategy / f"{split}_random_metrics.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == summary["random_comparisons"] == 200
    assert {int(row["seed"]) for row in rows} == set(range(42, 242))
    assert {int(row["entries"]) for row in rows} == {summary["entries"]}
    beaten = sum(float(row["net_sharpe"]) < summary["net_sharpe"] for row in rows)
    assert 100 * beaten / len(rows) == summary["random_percentile"]
    if strategy != "WATM_v1_2":
        original = json.loads((PACKAGE / strategy / "evaluation.json").read_text())
        recorded = original["splits"][split]
        assert summary["net_sharpe"] == recorded["net_sharpe"]
        assert summary["mean_rank_IC"] == recorded["mean_rank_IC"]
    assert summary["DSR"] is None


def test_log_rows_and_india_gaps_do_not_claim_registration_or_results():
    with (PACKAGE / "strategy_log_import.tsv").open() as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        assert len(reader.fieldnames) == 7
        rows = list(reader)
    assert len(rows) == 3
    assert all("India N/A" in row["Sharpe"] for row in rows)
    assert rows[0]["Keep or drop"] == "DROP"
    assert all(row["Keep or drop"] == "INSUFFICIENT TRADES" for row in rows[1:])
    statuses = json.loads((PACKAGE / "registration_status.json").read_text())
    assert statuses["WATM_v1_2"]["registered_at"] is None
    assert "NOT VERIFIED REGISTERED" in statuses["WVB_v1_2"]["status"]
    decision = json.loads((PACKAGE / "india_2025_decision.json").read_text())
    assert decision["accepted"] == 0 and decision["quarantined"] == 1496
    with (PACKAGE / "market_results.csv").open() as stream:
        markets = list(csv.DictReader(stream))
    assert len(markets) == 12
    assert all(row["net_sharpe"] == "N/A" for row in markets if row["market"] == "IN")


def test_trial_projection_preserves_successes_and_original_failed_attempts():
    with (PACKAGE / "trial_ledger.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1653
    assert (
        sum(
            row["status"] == "complete"
            and row["kind"] in {"random", "random_timing_comparison"}
            for row in rows
        )
        == 1200
    )
    assert (
        sum(row["status"] == "not_run" and row["kind"] == "random" for row in rows)
        == 400
    )
    assert sum(row["status"] == "failed" for row in rows) == 2
