"""Draft B5 consumer for a proposed B4 index; never invent portfolio metrics."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from src import config

INDEX_SCHEMA = "indicatorlab.cross-market-index/v0-draft"
REPORT_SCHEMA = "indicatorlab.cross-market-report/v0-draft"
METRICS = (
    "ic_mean_local",
    "ic_ir_local",
    "sharpe_local",
    "ic_mean_usd",
    "ic_ir_usd",
    "sharpe_usd",
)


def _number(value):
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("Metrics must be finite numbers or null")
    return float(value)


def load_index(path: Path) -> tuple[dict, dict]:
    """Load contained per-market JSON files and preserve independently failed markets."""
    index = json.loads(path.read_text())
    if index.get("schema_version") != INDEX_SCHEMA:
        raise ValueError("Unsupported B4 index schema; team agreement is still pending")
    if set(index.get("period", {})) != {"start", "end"} or not index.get("zoo"):
        raise ValueError("Index needs a common period and zoo")
    start, end = [date.fromisoformat(index["period"][key]) for key in ("start", "end")]
    if start > end or end >= config.holdout_start():
        raise ValueError(
            "Comparison period must precede the configured research cutoff"
        )
    results = {}
    for universe, item in index["results"].items():
        if item["status"] == "error":
            results[universe] = {
                "status": "error",
                "error": item.get("error", "unspecified"),
            }
            continue
        if item["status"] != "ok":
            raise ValueError("Market status must be ok or error")
        result_path = (path.parent / item["path"]).resolve()
        if not result_path.is_relative_to(path.parent.resolve()):
            raise ValueError("Result paths must remain below the index directory")
        result = json.loads(result_path.read_text())
        if (
            result.get("universe") != universe
            or result.get("period") != index["period"]
            or result.get("zoo") != index["zoo"]
        ):
            raise ValueError("Result universe, dates and zoo must match the index")
        for factor in result["factors"]:
            if not factor.get("factor_id"):
                raise ValueError("Factor identity is required")
            for metric in METRICS:
                _number(factor.get(metric))
        results[universe] = dict(result, status="ok")
    return index, results


def _upstream_dsr(agent: Path):
    target = agent / "src/quantlib/multipletesting.py"
    spec = importlib.util.spec_from_file_location(
        "week4_upstream_multipletesting", target
    )
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load upstream multiple-testing module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def comparison(index: dict, results: dict, agent: Path | None = None) -> dict:
    """Compute paired metric ratios and upstream DSR only with a complete trial ledger."""
    by_id = {}
    for universe, result in results.items():
        if result["status"] == "ok":
            for factor in result["factors"]:
                identity = factor["factor_id"]
                if (identity, universe) in by_id:
                    raise ValueError("Duplicate factor/market row")
                by_id[identity, universe] = factor
    rows = []
    ledger = index.get("trial_ledger", {})
    trial_sharpes = ledger.get("per_observation_sharpes", [])
    usable_dsr = (
        agent is not None
        and ledger.get("complete") is True
        and ledger.get("return_frequency") == "daily"
        and ledger.get("n_trials") == len(trial_sharpes)
        and len(trial_sharpes) > 1
    )
    module = _upstream_dsr(agent) if usable_dsr else None
    for (identity, universe), factor in sorted(by_id.items()):
        row = {"factor_id": identity, "universe": universe}
        us = by_id.get((identity, "sp500"), {})
        for metric in METRICS:
            row[metric] = _number(factor.get(metric))
            denominator = _number(us.get(metric))
            row[f"decay_{metric}_vs_us"] = (
                row[metric] / denominator
                if universe != "sp500"
                and row[metric] is not None
                and denominator is not None
                and abs(denominator) > 1e-12
                else None
            )
        row["dsr"] = None
        row["dsr_status"] = (
            "unavailable: requires net daily portfolio returns and complete cross-market trial ledger"
        )
        portfolio = factor.get("net_daily_returns_usd")
        if module is not None and portfolio is not None:
            import numpy as np
            from scipy.stats import kurtosis, skew

            values = np.asarray([_number(value) for value in portfolio], dtype=float)
            trials = np.asarray(
                [_number(value) for value in trial_sharpes], dtype=float
            )
            if (
                not np.isfinite(values).all()
                or not np.isfinite(trials).all()
                or len(values) < 30
                or np.std(values, ddof=1) <= 0
            ):
                raise ValueError(
                    "DSR needs at least thirty finite, varying net daily returns"
                )
            row["dsr"] = asdict(
                module.deflated_sharpe_ratio(
                    module.sharpe_ratio(values),
                    n_observations=len(values),
                    n_trials=len(trials),
                    trial_sharpe_std=float(np.std(trials, ddof=1)),
                    skew=float(skew(values, bias=False)),
                    kurtosis=float(kurtosis(values, fisher=False, bias=False)),
                )
            )
            row["dsr_status"] = (
                "computed with upstream function; input ledger completeness is caller-attested"
            )
        rows.append(row)
    return {
        "schema_version": REPORT_SCHEMA,
        "proposal_only": True,
        "period": index["period"],
        "zoo": index["zoo"],
        "markets": {
            market: {"status": value["status"], "error": value.get("error")}
            for market, value in results.items()
        },
        "rows": rows,
        "limits": [
            "Schema awaits Joshua/Jamal/Jack agreement",
            "Ratios with a near-zero or missing US denominator are null",
            "Negative-denominator ratios need contextual interpretation",
            "IC does not imply a tradable portfolio or Sharpe",
        ],
    }


def markdown(report: dict) -> str:
    """Render an inspection table while keeping machine-readable nulls explicit."""
    lines = [
        "# B5 comparison (draft schema)",
        "",
        "| Factor | Market | IC local | IC IR local | Sharpe local | Sharpe USD |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        cells = [
            (
                str(row[key]).replace("|", "\\|").replace("\n", " ")
                if row.get(key) is not None
                else "N/A"
            )
            for key in (
                "factor_id",
                "universe",
                "ic_mean_local",
                "ic_ir_local",
                "sharpe_local",
                "sharpe_usd",
            )
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Read the proposed B4 index and write B5 JSON/Markdown beside an explicit prefix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vibe-agent", type=Path)
    args = parser.parse_args()
    index, results = load_index(args.index)
    report = comparison(index, results, args.vibe_agent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    args.output.with_suffix(".md").write_text(markdown(report))


if __name__ == "__main__":
    main()
