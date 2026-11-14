"""Isolated Vibe transaction-engine worker; JSON in/out and no network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    """Execute frozen training selections, evaluations and timing nulls locally."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vibe-root", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.vibe_root / "agent"))
    from engine_adapter import random_schedule, simulate

    request = json.loads(args.request.read_text())
    storage = np.load(request["data"], allow_pickle=False)
    data = {key: storage[key] for key in storage.files}
    data["codes"] = data["codes"].tolist()
    data["dates"] = pd.DatetimeIndex(data["dates"])
    if data["dates"].max() >= pd.Timestamp("2025-10-01"):
        raise ValueError("Post-cutoff data reached the engine")
    data["frames"] = {
        code: pd.DataFrame(
            {key: data[key][:, col] for key in ("open", "close", "volume")},
            index=data["dates"],
        )
        for col, code in enumerate(data["codes"])
    }
    results, series = [], {}
    completed_groups = set()
    for task in request["tasks"]:
        group = task.get("selection_group")
        if group in completed_groups:
            continue
        kwargs = {
            "market": request["market"],
            "initial_cash": request["initial_cash"],
            "lots": request["lots"],
            "start": task["start"],
            "end": task["end"],
        }
        base = simulate(data, task["plans"], **kwargs, detail=True)
        values = base.pop("returns")
        base.pop("equity")
        deviation = float(np.std(values, ddof=1))
        sharpe = (
            float(np.mean(values) / deviation * np.sqrt(252)) if deviation > 0 else 0.0
        )
        row = {"id": task["id"], "sharpe": sharpe, **base}
        series[task["id"]] = values
        if group and base["entries"] >= 30:
            completed_groups.add(group)
        count = task.get("random_runs", 0)
        null = []
        rng = np.random.default_rng(task.get("seed", 42))
        for run in range(count):
            frozen = (
                random_schedule(task["plans"], data, task["start"], task["end"], rng)
                if task["plans"]
                else []
            )
            trial = simulate(data, frozen, **kwargs)
            sample = trial["returns"]
            std = sample.std(ddof=1)
            null.append(float(sample.mean() / std * np.sqrt(252)) if std > 0 else 0.0)
            if run % 50 == 0:
                print(f"{task['id']} random={run+1}/{count}", flush=True)
        row["random_sharpes"] = null
        row["random_percentile"] = (
            float(np.mean(np.array(null) < sharpe) * 100) if null else None
        )
        results.append(row)
        print(f"{task['id']} entries={row['entries']} Sharpe={sharpe:.4f}", flush=True)
    output = {
        "results": results,
        "engine_hashes": {
            str(path.relative_to(args.vibe_root)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in [
                args.vibe_root / "agent/backtest/engines/base.py",
                args.vibe_root / "agent/backtest/engines/global_equity.py",
            ]
        },
    }
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    np.savez_compressed(args.output.with_suffix(".npz"), **series)


if __name__ == "__main__":
    main()
