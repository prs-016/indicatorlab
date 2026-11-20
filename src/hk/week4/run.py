"""Freeze three strategy rules, select on train counts only, then evaluate once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.hk.week4.features import build_bundle, make_plans
from src.hk.week4.public_data import CUTOFF, DATA, ROOT

VIBE = Path(os.environ.get("HK_VIBE_ROOT", ROOT.parent / "Vibe-Trading-upstream"))
OUTPUT = ROOT / "results/hk/week4"


def encode(value):
    """Serialize numpy scalars and UTC timestamps without nonstandard NaN JSON."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def write(path: Path, value) -> None:
    """Write one locally auditable JSON artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=encode, allow_nan=False) + "\n")


def freeze(directory: Path, specification: dict) -> None:
    """Record immutable rules and source hashes before any strategy performance run."""
    if (directory / "preregistration.json").exists():
        saved = json.loads((directory / "preregistration.json").read_text())
        if saved["specification"] != specification:
            raise ValueError("Preregistered rules changed; start and log a new trial")
        for relative, expected in (
            saved["source_hashes"] | saved["input_hashes"]
        ).items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(
                    "Preregistered source changed; record a new run rather than silently retesting"
                )
        for relative, expected in saved["upstream_source_hashes"].items():
            if hashlib.sha256((VIBE / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("Frozen Vibe engine source changed: " + relative)
        return
    directory.mkdir(parents=True, exist_ok=False)
    paths = [
        ROOT / "src/hk/calendar.py",
        ROOT / "src/hk/ic_diagnostic.py",
        ROOT / "config/hk_week4_research.json",
        ROOT / "config/hk_week3_research.json",
        ROOT / "results/hk/week3/FIVE_STRATEGY_REPORT.md",
        ROOT / "results/hk/week4/STRATEGY_RULES_BEFORE_TEST.md",
        ROOT / "config.yaml",
        ROOT / "src/config.py",
        ROOT / "src/sentiment/__init__.py",
        ROOT / "src/sentiment/finbert_scorer.py",
        ROOT / "src/storage.py",
        *sorted(Path(__file__).parent.glob("*.py")),
    ]
    record = {
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "authorization": "User requested local Week 4 tasks including mandated extended evaluation; AWS and publishing excluded",
        "prior_test_exposure": "Earlier test interval 2022-01-01 through 2025-09-30 has already been observed. This is a mandated extension, not a new untouched holdout. No strategy formulas or thresholds were selected from extended-test results.",
        "shared_sheet_preregistration": False,
        "specification": specification,
        "source_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
        "policy": "Count-only train threshold selection; finish both markets train nulls/ablations, freeze train-only nominee; then one unchanged extended test; no post-test tuning",
        "upstream_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=VIBE, text=True
        ).strip(),
        "upstream_source_hashes": {
            relative: hashlib.sha256((VIBE / relative).read_bytes()).hexdigest()
            for relative in [
                "agent/backtest/engines/base.py",
                "agent/backtest/engines/global_equity.py",
                "agent/backtest/runner.py",
                "agent/src/quantlib/multipletesting.py",
            ]
        },
        "input_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                *sorted((DATA / "prices").glob("*.parquet")),
                DATA / "wiki_sentiment.parquet",
                DATA / "wiki_sentiment_method.json",
                *sorted((DATA / "attention").glob("*.parquet")),
                *sorted((DATA / "wikipedia").glob("*.json")),
                ROOT / "config/hk_wiki_title_intervals.csv",
                ROOT / "config/us_wiki_title_intervals.csv",
                ROOT / "config/hk_board_lots_2026-11-12.csv",
            ]
        },
    }
    write(directory / "preregistration.json", record)
    write(OUTPUT / "three_strategy_preregistration.json", record)


def worker(request: dict, destination: Path) -> dict:
    """Execute the actual Vibe equity engine in a package-isolated child process."""
    request_path = destination.with_suffix(".request.json")
    write(request_path, request)
    command = [
        sys.executable,
        "-B",
        str(Path(__file__).with_name("vibe_worker.py")),
        str(request_path),
        str(destination),
        "--vibe-root",
        str(VIBE),
    ]
    subprocess.run(command, cwd=VIBE, check=True)
    return json.loads(destination.read_text())


def base_request(bundle, specification, directory: Path) -> dict:
    """Persist only pre-cutoff arrays and the dated lot reference for the worker."""
    destination = directory / (bundle.market + ".npz")
    np.savez_compressed(
        destination,
        dates=bundle.dates.values.astype("datetime64[ns]"),
        codes=np.array(bundle.codes),
        **{key: value.to_numpy() for key, value in bundle.prices.items()},
    )
    lots_frame = pd.read_csv(ROOT / "config/hk_board_lots_2026-11-12.csv")
    lots = dict(zip(lots_frame.symbol, lots_frame.board_lot.astype(int)))
    if bundle.market == "HK" and set(bundle.codes) - set(lots):
        raise ValueError("Missing official board-lot reference")
    return {
        "market": bundle.market,
        "research_cutoff": str(
            __import__("src.config", fromlist=["holdout_start"]).holdout_start()
        ),
        "data": str(destination),
        "initial_cash": specification["markets"][bundle.market]["initial_cash"],
        "lots": lots if bundle.market == "HK" else {},
    }


def ic(bundle, scores: dict, bounds) -> dict:
    """Mean weekly cross-sectional Spearman IC against next-open five-session labels."""
    values = []
    start, end = bounds
    for entry, signal in scores.items():
        exit_ = entry + 5
        if not start <= entry < exit_ <= end:
            continue
        a, b = bundle.prices["open"].iloc[entry], bundle.prices["open"].iloc[exit_]
        dividends = bundle.prices["dividend"].iloc[entry + 1 : exit_ + 1].sum()
        returns = (b + dividends) / a - 1
        signal = pd.Series(signal)
        valid = signal.notna() & returns.notna() & a.gt(0) & b.gt(0)
        if (
            valid.sum() >= 2
            and signal[valid].nunique() > 1
            and returns[valid].nunique() > 1
        ):
            values.append(float(signal[valid].rank().corr(returns[valid].rank())))
    return {"ic": float(np.mean(values)) if values else None, "ic_weeks": len(values)}


def sharpe(values) -> float:
    """Annualized daily net Sharpe at zero risk-free rate; flat cash convention is zero."""
    values = np.asarray(values)
    return (
        float(values.mean() / values.std(ddof=1) * np.sqrt(252))
        if values.std(ddof=1) > 0
        else 0.0
    )


def upstream_dsr(returns, trial_sharpes, total_trials, directory):
    """Use upstream's existing DSR implementation in its isolated src namespace."""
    payload = {
        "returns": np.asarray(returns).tolist(),
        "trial_sharpes": np.asarray(trial_sharpes).tolist(),
        "total_trials": total_trials,
    }
    source = directory / "dsr_request.json"
    source.write_text(json.dumps(payload))
    command = [
        sys.executable,
        "-B",
        str(Path(__file__).with_name("statistics_worker.py")),
        str(source),
        str(VIBE),
    ]
    result = subprocess.run(
        command, cwd=VIBE, check=True, capture_output=True, text=True
    )
    value = json.loads(result.stdout)
    return value["deflated_sharpe_ratio"]


def validate_specification(specification):
    """Reject mismatched config/split/cutoff before any portfolio execution."""
    expected_end = str((CUTOFF - pd.Timedelta(days=1)).date())
    if specification["end"] != expected_end or specification["test"][1] != expected_end:
        raise ValueError("Research end must be derived from config holdout_start")
    shared = config.load()["strategy"]["split"]
    for name in ("train", "test"):
        if [str(value) for value in shared[name]] != specification[name]:
            raise ValueError("Week4 split differs from active shared config")
    old = json.loads((ROOT / "config/hk_week3_research.json").read_text())
    if specification["strategies"] != old["strategies"][:3]:
        raise ValueError(
            "Week4 must preserve the first three registered hypotheses unchanged"
        )
    if (
        specification["random_runs"] < 200
        or specification["prior_recorded_trials"] < 268
    ):
        raise ValueError("Missing timing controls or prior search history")


def nominate_train_candidate(training_rows, selections, train_eligibility=None):
    """Choose highest mean selected TRAIN Sharpe across markets; lexical tie break."""
    rows = []
    for strategy in sorted(next(iter(selections.values()))):
        observations = []
        for market, selected in selections.items():
            choice = selected[strategy]
            key = f"{market}.{strategy}.v{choice['variant']}.train"
            match = next(row for row in training_rows if row["id"] == key)
            observations.append(
                {
                    "market": market,
                    "sharpe": match["sharpe"],
                    "entries": match["entries"],
                }
            )
        rows.append(
            {
                "strategy": strategy,
                "mean_train_sharpe": float(
                    np.mean([row["sharpe"] for row in observations])
                ),
                "market_train": observations,
                "eligible_in_both_train_markets": bool(train_eligibility)
                and all(
                    train_eligibility.get(f"{market}.{strategy}", {}).get(
                        "eligible", False
                    )
                    for market in selections
                ),
            }
        )
    ranked = sorted(
        rows,
        key=lambda row: (
            not row["eligible_in_both_train_markets"],
            -row["mean_train_sharpe"],
            row["strategy"],
        ),
    )
    return {
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "strategy": ranked[0]["strategy"],
        "rule": "Prefer candidates eligible in both train markets (entries >=30, timing percentile >=90, no unchanged train ablation). Within that group, highest mean selected-variant TRAIN daily net Sharpe, lexical ID tie break. If none eligible, report highest mean as INELIGIBLE research nominee. No test metrics used",
        "train_eligible": ranked[0]["eligible_in_both_train_markets"],
        "ranked_train_candidates": ranked,
        "nomination_is_keep": False,
    }


def assess_train_eligibility(evaluations, directory):
    """No-op training indicators make a fixed strategy ineligible, never tune test."""
    status = {}
    bases = [
        r for r in evaluations if r["period"] == "train" and r["ablation"] == "base"
    ]
    for base in bases:
        key = f"{base['market']}.{base['strategy']}"
        arrays = np.load(
            directory / f"{base['market']}_train_evaluations.npz", allow_pickle=False
        )
        unchanged = []
        for row in evaluations:
            if (
                row["period"] != "train"
                or row["market"] != base["market"]
                or row["strategy"] != base["strategy"]
                or row["ablation"] == "base"
            ):
                continue
            if row["entries"] == base["entries"] and np.allclose(
                arrays[row["id"]], arrays[base["id"]], rtol=0, atol=1e-12
            ):
                unchanged.append(row["ablation"])
        reasons = []
        if base["entries"] < 30:
            reasons.append("fewer than 30 train entries")
        if base["random_percentile"] < 90:
            reasons.append("train timing percentile below 90")
        if unchanged:
            reasons.append("unchanged train ablation: " + ", ".join(unchanged))
        status[key] = {
            "eligible": not reasons,
            "unchanged_indicators": unchanged,
            "reasons": reasons,
            "policy": "Prior formulas retained; any unchanged training indicator makes case ineligible, with no post-test tuning",
        }
    return status


def run(directory: Path) -> None:
    """Complete all six market cases, their timing controls and indicator ablations."""
    # Workers execute with cwd=VIBE, so every persisted request path must be
    # absolute even when the CLI was given a repository-relative run directory.
    directory = directory.expanduser().resolve()
    specification = json.loads((ROOT / "config/hk_week4_research.json").read_text())
    validate_specification(specification)
    if (directory / "test_started.json").exists() or (
        directory / "evaluation_complete.json"
    ).exists():
        raise FileExistsError(
            "This preregistration already has a completed test; do not repeat or tune it"
        )
    bundles = {market: build_bundle(market, specification) for market in ("HK", "US")}
    freeze(directory, specification)
    requests, selections, training_rows = {}, {}, []
    for market in ("HK", "US"):
        bundle = bundles[market]
        request = base_request(bundle, specification, directory)
        requests[market] = request
        tasks = []
        for strategy in specification["strategies"]:
            for number, variant in enumerate(strategy["variants"]):
                plans, _scores, bounds = make_plans(
                    bundle, strategy, variant, tuple(specification["train"])
                )
                tasks.append(
                    {
                        "id": f"{market}.{strategy['id']}.v{number}.train",
                        "selection_group": strategy["id"],
                        "start": bounds[0],
                        "end": bounds[1],
                        "plans": plans,
                    }
                )
        output = worker(
            request | {"tasks": tasks}, directory / (market + "_train_selection.json")
        )
        training_rows.extend(
            row | {"market": market, "phase": "train_selection"}
            for row in output["results"]
        )
        chosen = {}
        for strategy in specification["strategies"]:
            candidates = [
                row for row in output["results"] if f".{strategy['id']}." in row["id"]
            ]
            selected = next(
                (row for row in candidates if row["entries"] >= 30), candidates[-1]
            )
            number = int(selected["id"].split(".v")[1].split(".")[0])
            chosen[strategy["id"]] = {
                "variant": number,
                "parameters": strategy["variants"][number],
                "train_entries": selected["entries"],
            }
        selections[market] = chosen
        write(directory / (market + "_quality.json"), bundle.quality)
    # Both market selections are frozen before any test performance is computed.
    write(
        directory / "selected_before_test.json",
        {"frozen_at_utc": datetime.now(UTC).isoformat(), "selections": selections},
    )
    write(OUTPUT / "three_strategy_selected_variants.json", selections)
    evaluations, ic_rows = [], []
    for split in ("train", "test"):
        if split == "test":
            train_eligibility = assess_train_eligibility(evaluations, directory)
            write(directory / "train_eligibility.json", train_eligibility)
            candidate = nominate_train_candidate(
                training_rows, selections, train_eligibility
            )
            write(directory / "candidate_before_test.json", candidate)
            write(OUTPUT / "candidate_before_test.json", candidate)
            # All train timing controls and ablations finish before opening test.
            with (directory / "test_started.json").open("x") as handle:
                json.dump(
                    {
                        "started_at_utc": datetime.now(UTC).isoformat(),
                        "candidate": candidate["strategy"],
                        "policy": "One unchanged extended test after completed TRAIN diagnostics",
                    },
                    handle,
                )
        for market, bundle in bundles.items():
            tasks = []
            for number, strategy in enumerate(specification["strategies"]):
                parameters = selections[market][strategy["id"]]["parameters"]
                for drop in [None] + strategy["indicators"]:
                    plans, scores, bounds = make_plans(
                        bundle, strategy, parameters, tuple(specification[split]), drop
                    )
                    identifier = f"{market}.{strategy['id']}.{split}." + (
                        drop or "base"
                    )
                    tasks.append(
                        {
                            "id": identifier,
                            "start": bounds[0],
                            "end": bounds[1],
                            "plans": plans,
                            "random_runs": specification["random_runs"]
                            if drop is None
                            else 0,
                            "seed": specification["seed"]
                            + number * 10
                            + (0 if split == "train" else 1),
                        }
                    )
                    ic_rows.append({"id": identifier, **ic(bundle, scores, bounds)})
            output_path = directory / f"{market}_{split}_evaluations.json"
            result = worker(requests[market] | {"tasks": tasks}, output_path)
            return_arrays = np.load(output_path.with_suffix(".npz"), allow_pickle=False)
            for row in result["results"]:
                _, strategy_id, _, ablation = row["id"].split(".")
                bounds = tuple(pd.Timestamp(value) for value in specification[split])
                frame = bundle.index.loc[bounds[0] : bounds[1]]
                benchmark = (
                    frame.close + frame.dividend.fillna(0)
                ) / frame.close.shift(1) - 1
                benchmark.iloc[0] = frame.close.iloc[0] / frame.open.iloc[0] - 1
                returns = return_arrays[row["id"]]
                fx = bundle.fx.loc[bounds[0] : bounds[1]].to_numpy()
                equity = np.cumprod(1 + returns)
                usd = equity / fx
                usd_returns = (
                    np.diff(np.r_[1 / fx[0], usd]) / np.r_[1 / fx[0], usd[:-1]]
                )
                evaluations.append(
                    row
                    | {
                        "market": market,
                        "strategy": strategy_id,
                        "period": split,
                        "ablation": ablation,
                        "benchmark_sharpe": sharpe(benchmark.to_numpy()),
                        "usd_sharpe": sharpe(usd_returns),
                        "total_return": float(equity[-1] - 1),
                        "usd_total_return": float(usd[-1] / (1 / fx[0]) - 1),
                    }
                )
    ic_map = {row["id"]: row for row in ic_rows}
    for row in evaluations:
        row.update(ic_map[row["id"]])
    # Reconstruct the known pre-session search count from the existing saved logs.
    legacy_count = 0
    for path in [
        ROOT / "results/hk/week1/strategy_results.csv",
        *sorted((ROOT / "results/hk/week2").glob("*strategy_results.csv")),
    ]:
        frame = pd.read_csv(path)
        name = next((key for key in ("strategy", "Strategy") if key in frame), None)
        legacy_count += int(frame[name].nunique()) if name else len(frame)
    factor_screening_trials = (
        101  # required Alpha101 HSI benchmark attempted all 101 factors
    )
    recorded_trials = (
        int(specification["prior_recorded_trials"])
        + len(training_rows)
        + len(evaluations)
    )
    for period in ("train", "test"):
        trial_srs = [
            row["sharpe"] / np.sqrt(252)
            for row in evaluations
            if row["period"] == period
        ]
        if period == "train":
            trial_srs += [row["sharpe"] / np.sqrt(252) for row in training_rows]
        # The probability uses every documented trial count, with variance
        # estimated from comparable, actually observed current-period trials.
        for row in evaluations:
            if row["period"] != period:
                continue
            arrays = np.load(
                directory / (row["market"] + "_" + row["period"] + "_evaluations.npz"),
                allow_pickle=False,
            )
            values = arrays[row["id"]]
            if values.std(ddof=1) > 0:
                sample = np.asarray(trial_srs)
                # Match the documented total trial count without inventing old
                # Sharpe values: the DSR helper accepts N separately below.
                row["deflated_sharpe_probability"] = upstream_dsr(
                    values, sample, recorded_trials, directory
                )
            else:
                row["deflated_sharpe_probability"] = None
    all_results = {
        "preregistration": str(directory / "preregistration.json"),
        "selections": selections,
        "candidate_before_test": candidate,
        "train_eligibility": train_eligibility,
        "legacy_recorded_trials": legacy_count,
        "prior_recorded_trials": specification["prior_recorded_trials"],
        "prior_trial_breakdown": {
            "legacy_strategies": 21,
            "hsi_factor_attempts": 101,
            "train_variants": 22,
            "base_and_ablation_evaluations": 124,
        },
        "recorded_total_trials": recorded_trials,
        "factor_screening_trials": factor_screening_trials,
        "dsr_scope": "Conservative count of all locally recorded strategy/variant/ablation market runs; variance estimated from current comparable per-day Sharpes. Unknown undocumented prior searches cannot be certified.",
        "train_selection": training_rows,
        "evaluations": evaluations,
    }
    write(directory / "evaluation_complete.json", all_results)
    write(OUTPUT / "three_strategy_full_results.json", all_results)
    records, abl = [], []
    for market in ("HK", "US"):
        for strategy in specification["strategies"]:
            pair = {
                row["period"]: row
                for row in evaluations
                if row["market"] == market
                and row["strategy"] == strategy["id"]
                and row["ablation"] == "base"
            }
            train, test = pair["train"], pair["test"]
            failures = []
            train_case = train_eligibility[f"{market}.{strategy['id']}"]
            if train_case["unchanged_indicators"]:
                failures.append(
                    "redundant train indicator(s): "
                    + ", ".join(train_case["unchanged_indicators"])
                )
            if train["entries"] < 30:
                failures.append("fewer than 30 train entries")
            if test["sharpe"] <= test["benchmark_sharpe"]:
                failures.append("test Sharpe does not beat index")
            if train["random_percentile"] < 90:
                failures.append("train below 90th-percentile timing control")
            if test["random_percentile"] < 90:
                failures.append("test below 90th-percentile timing control")
            records.append(
                {
                    "market": market,
                    "strategy": strategy["id"],
                    "what_it_does": strategy["description"],
                    "train_entries": train["entries"],
                    "test_entries": test["entries"],
                    "ic_train": train["ic"],
                    "ic_test": test["ic"],
                    "sharpe_train": train["sharpe"],
                    "sharpe_test": test["sharpe"],
                    "max_drawdown_train": train["max_drawdown"],
                    "max_drawdown_test": test["max_drawdown"],
                    "benchmark_test_sharpe": test["benchmark_sharpe"],
                    "random_percentile_train": train["random_percentile"],
                    "random_percentile_test": test["random_percentile"],
                    "dsr_probability": test["deflated_sharpe_probability"],
                    "usd_sharpe_train": train["usd_sharpe"],
                    "usd_sharpe_test": test["usd_sharpe"],
                    "decision": "DROP" if failures else "KEEP",
                    "reason": (
                        "; ".join(failures)
                        if failures
                        else "Passes train entries, test-index and both timing-null gates; candidate for further research only"
                    ),
                }
            )
            for row in evaluations:
                if (
                    row["market"] == market
                    and row["strategy"] == strategy["id"]
                    and row["ablation"] != "base"
                ):
                    abl.append(
                        {
                            "market": market,
                            "strategy": strategy["id"],
                            "period": row["period"],
                            "removed_indicator": row["ablation"],
                            "sharpe": row["sharpe"],
                            "sharpe_change": row["sharpe"]
                            - pair[row["period"]]["sharpe"],
                            "entries": row["entries"],
                            "ic": row["ic"],
                        }
                    )
    pd.DataFrame(records).to_csv(OUTPUT / "three_strategy_results.csv", index=False)
    pd.DataFrame(abl).to_csv(OUTPUT / "three_strategy_ablations.csv", index=False)
    random_rows = [
        {
            "market": row["market"],
            "strategy": row["strategy"],
            "period": row["period"],
            "run": number + 1,
            "sharpe": value,
        }
        for row in evaluations
        if row["ablation"] == "base"
        for number, value in enumerate(row["random_sharpes"])
    ]
    pd.DataFrame(random_rows).to_csv(
        OUTPUT / "three_strategy_random_timing.csv", index=False
    )
    print(
        pd.DataFrame(records)[
            [
                "market",
                "strategy",
                "train_entries",
                "ic_test",
                "sharpe_train",
                "sharpe_test",
                "decision",
            ]
        ].to_string(index=False)
    )


def main() -> None:
    """Run once under an immutable local preregistration; never auto-tune test results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.run_dir)


if __name__ == "__main__":
    main()
