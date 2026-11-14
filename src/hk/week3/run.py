"""Freeze five strategy rules, select on train counts only, then evaluate once."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.hk.evaluation import deflated_sharpe
from src.hk.week3.features import build_bundle, make_plans
from src.hk.week3.public_data import DATA, ROOT

VIBE = ROOT.parent / "Vibe-Trading-upstream"
OUTPUT = ROOT / "results/hk/week3"


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
        for relative, expected in saved["source_hashes"].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(
                    "Preregistered source changed; record a new run rather than silently retesting"
                )
        return
    directory.mkdir(parents=True, exist_ok=False)
    paths = [
        ROOT / "src/hk/calendar.py",
        ROOT / "src/hk/evaluation.py",
        ROOT / "config/hk_week3_research.json",
        ROOT / "config.yaml",
        *sorted(Path(__file__).parent.glob("*.py")),
    ]
    record = {
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "authorization": "User requested five strategies created under the guide's seven requirements, then tested; local preregistration and sheet-ready export",
        "specification": specification,
        "source_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
        "policy": "Count-only train selection, no test outcomes before selection, no post-test tuning",
        "input_hashes": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                *sorted((DATA / "prices").glob("*.parquet")),
                DATA / "wiki_sentiment.parquet",
                ROOT / "config/hk_wiki_title_intervals.csv",
                ROOT / "config/us_wiki_title_intervals.csv",
                ROOT / "config/hk_board_lots_2026-11-12.csv",
            ]
        },
    }
    write(directory / "preregistration.json", record)
    write(OUTPUT / "five_strategy_preregistration.json", record)


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


def run(directory: Path) -> None:
    """Complete all ten market cases, their timing controls and indicator ablations."""
    specification = json.loads((ROOT / "config/hk_week3_research.json").read_text())
    freeze(directory, specification)
    if (directory / "evaluation_complete.json").exists():
        raise FileExistsError(
            "This preregistration already has a completed test; do not repeat or tune it"
        )
    bundles, requests, selections, training_rows = {}, {}, {}, []
    for market in ("HK", "US"):
        bundle = build_bundle(market, specification)
        bundles[market] = bundle
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
                        "id": f'{market}.{strategy["id"]}.v{number}.train',
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
                row for row in output["results"] if f'.{strategy["id"]}.' in row["id"]
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
    write(OUTPUT / "five_strategy_selected_variants.json", selections)
    evaluations, ic_rows = [], []
    for market, bundle in bundles.items():
        tasks = []
        for number, strategy in enumerate(specification["strategies"]):
            parameters = selections[market][strategy["id"]]["parameters"]
            for split in ("train", "test"):
                for drop in [None] + strategy["indicators"]:
                    plans, scores, bounds = make_plans(
                        bundle, strategy, parameters, tuple(specification[split]), drop
                    )
                    identifier = f'{market}.{strategy["id"]}.{split}.' + (
                        drop or "base"
                    )
                    tasks.append(
                        {
                            "id": identifier,
                            "start": bounds[0],
                            "end": bounds[1],
                            "plans": plans,
                            "random_runs": (
                                specification["random_runs"] if drop is None else 0
                            ),
                            "seed": specification["seed"]
                            + number * 10
                            + (0 if split == "train" else 1),
                        }
                    )
                    ic_rows.append({"id": identifier, **ic(bundle, scores, bounds)})
        output_path = directory / (market + "_evaluations.json")
        result = worker(requests[market] | {"tasks": tasks}, output_path)
        return_arrays = np.load(output_path.with_suffix(".npz"), allow_pickle=False)
        for row in result["results"]:
            _, strategy_id, split, ablation = row["id"].split(".")
            bounds = tuple(pd.Timestamp(value) for value in specification[split])
            frame = bundle.index.loc[bounds[0] : bounds[1]]
            benchmark = (frame.close + frame.dividend.fillna(0)) / frame.close.shift(
                1
            ) - 1
            benchmark.iloc[0] = frame.close.iloc[0] / frame.open.iloc[0] - 1
            returns = return_arrays[row["id"]]
            fx = bundle.fx.loc[bounds[0] : bounds[1]].to_numpy()
            equity = np.cumprod(1 + returns)
            usd = equity / fx
            usd_returns = np.diff(np.r_[1 / fx[0], usd]) / np.r_[1 / fx[0], usd[:-1]]
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
        legacy_count + factor_screening_trials + len(training_rows) + len(evaluations)
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
                directory / (row["market"] + "_evaluations.npz"), allow_pickle=False
            )
            values = arrays[row["id"]]
            if values.std(ddof=1) > 0:
                sample = np.asarray(trial_srs)
                # Match the documented total trial count without inventing old
                # Sharpe values: the DSR helper accepts N separately below.
                row["deflated_sharpe_probability"] = deflated_sharpe(
                    values, sample, total_trials=recorded_trials
                )
            else:
                row["deflated_sharpe_probability"] = None
    all_results = {
        "preregistration": str(directory / "preregistration.json"),
        "selections": selections,
        "legacy_recorded_trials": legacy_count,
        "recorded_total_trials": recorded_trials,
        "factor_screening_trials": factor_screening_trials,
        "dsr_scope": "Conservative count of all locally recorded strategy/variant/ablation market runs; variance estimated from current comparable per-day Sharpes. Unknown undocumented prior searches cannot be certified.",
        "train_selection": training_rows,
        "evaluations": evaluations,
    }
    write(directory / "evaluation_complete.json", all_results)
    write(OUTPUT / "five_strategy_full_results.json", all_results)
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
    pd.DataFrame(records).to_csv(OUTPUT / "five_strategy_results.csv", index=False)
    pd.DataFrame(abl).to_csv(OUTPUT / "five_strategy_ablations.csv", index=False)
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
        OUTPUT / "five_strategy_random_timing.csv", index=False
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
