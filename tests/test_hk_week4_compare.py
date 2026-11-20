"""B5 contracts remain explicit and isolated from unavailable market results."""

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.hk.week4_compare import INDEX_SCHEMA, comparison, load_index


def fixture(tmp_path):
    index = {
        "schema_version": INDEX_SCHEMA,
        "period": {"start": "2016-01-01", "end": "2026-10-31"},
        "zoo": "fixture",
        "results": {},
    }
    for name, ic in (("sp500", 0.02), ("hsi", 0.01)):
        result = {
            "universe": name,
            "period": index["period"],
            "zoo": index["zoo"],
            "factors": [{"factor_id": "fixture_factor", "ic_mean_local": ic}],
        }
        (tmp_path / f"{name}.json").write_text(json.dumps(result))
        index["results"][name] = {"status": "ok", "path": f"{name}.json", "error": None}
    index["results"]["nifty100"] = {
        "status": "error",
        "path": None,
        "error": "fixture failure",
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index))
    return path


def test_failure_isolation_ratio_and_no_invented_sharpe(tmp_path):
    index, results = load_index(fixture(tmp_path))
    report = comparison(index, results)
    hk = next(row for row in report["rows"] if row["universe"] == "hsi")
    assert report["markets"]["nifty100"]["status"] == "error"
    assert hk["decay_ic_mean_local_vs_us"] == 0.5
    assert hk["sharpe_local"] is None and hk["dsr"] is None


def test_zero_us_denominator_is_null(tmp_path):
    index, results = load_index(fixture(tmp_path))
    results["sp500"]["factors"][0]["ic_mean_local"] = 0
    assert comparison(index, results)["rows"][0]["decay_ic_mean_local_vs_us"] is None


def test_differing_period_rejected(tmp_path):
    path = fixture(tmp_path)
    result_path = tmp_path / "hsi.json"
    result = json.loads(result_path.read_text())
    result["period"] = {"start": "2026-01-01", "end": "2026-10-31"}
    result_path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="dates"):
        load_index(path)


def test_traversal_rejected(tmp_path):
    path = fixture(tmp_path)
    index = json.loads(path.read_text())
    index["results"]["hsi"]["path"] = "../outside.json"
    path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="below"):
        load_index(path)


def test_cutoff_rejected_from_config(tmp_path):
    path = fixture(tmp_path)
    index = json.loads(path.read_text())
    index["period"]["end"] = "2026-11-01"
    path.write_text(json.dumps(index))
    with pytest.raises(ValueError, match="cutoff"):
        load_index(path)


def test_dsr_delegates_daily_returns_and_full_ledger(monkeypatch, tmp_path):
    @dataclass
    class Answer:
        deflated_sharpe_ratio: float

    dsr = Mock(return_value=Answer(0.4))
    sharpe = Mock(return_value=0.05)
    monkeypatch.setattr(
        "src.hk.week4_compare._upstream_dsr",
        lambda _: SimpleNamespace(deflated_sharpe_ratio=dsr, sharpe_ratio=sharpe),
    )
    index, results = load_index(fixture(tmp_path))
    index["trial_ledger"] = {
        "complete": True,
        "return_frequency": "daily",
        "n_trials": 3,
        "per_observation_sharpes": [0.01, 0.02, 0.03],
    }
    results["hsi"]["factors"][0]["net_daily_returns_usd"] = [0.01, -0.003, 0.002] * 20
    report = comparison(index, results, Path("unused-injected-module"))
    dsr.assert_called_once()
    assert dsr.call_args.args == (0.05,)
    assert dsr.call_args.kwargs["n_observations"] == 60
    assert dsr.call_args.kwargs["n_trials"] == 3
    assert dsr.call_args.kwargs["kurtosis"] > 0
    assert (
        next(row for row in report["rows"] if row["universe"] == "hsi")["dsr"][
            "deflated_sharpe_ratio"
        ]
        == 0.4
    )
    index["trial_ledger"]["complete"] = False
    assert all(
        row["dsr"] is None for row in comparison(index, results, Path("unused"))["rows"]
    )
