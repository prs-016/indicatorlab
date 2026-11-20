"""Verify the frozen candidate through Vibe's actual native CLI on sealed inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.hk.week4.features import build_bundle, make_plans
from src.hk.week4.public_data import DATA, ROOT


def signal_source(decision_weights: pd.DataFrame) -> str:
    """Embed decision-date weights; Vibe applies its own single execution shift."""
    csv = decision_weights.to_csv(index_label="date")
    return (
        "from io import StringIO\nimport pandas as pd\n\n"
        "WEIGHTS_CSV = " + repr(csv) + "\n\n"
        "class SignalEngine:\n"
        "    def generate(self, data_map):\n"
        "        weights = pd.read_csv(StringIO(WEIGHTS_CSV), index_col=0, parse_dates=True)\n"
        "        return {code: weights[code].reindex(frame.index).fillna(0.0)\n"
        "                for code, frame in data_map.items() if code in weights.columns}\n"
    )


def prepare_native(
    run_directory: Path, study: Path, market: str, vibe_root: Path
) -> dict:
    """Export only frozen decisions and hash-verified original Yahoo OHLCV."""
    spec = json.loads((ROOT / "config/hk_week4_research.json").read_text())
    candidate = json.loads((study / "candidate_before_test.json").read_text())
    selected = json.loads((study / "selected_before_test.json").read_text())[
        "selections"
    ]
    strategy = next(s for s in spec["strategies"] if s["id"] == candidate["strategy"])
    bundle = build_bundle(market, spec)
    plans, _, bounds = make_plans(
        bundle,
        strategy,
        selected[market][strategy["id"]]["parameters"],
        tuple(spec["test"]),
    )
    targets = pd.DataFrame(0.0, index=bundle.dates, columns=bundle.codes)
    execution_dates = set()
    for plan in plans:
        targets.iloc[
            plan["entry"] : plan["exit"], targets.columns.get_loc(plan["symbol"])
        ] = plan["weight"]
        execution_dates.update(
            [
                str(bundle.dates[plan["entry"]].date()),
                str(bundle.dates[plan["exit"]].date()),
            ]
        )
    # These rows are decision-date targets. Returning a second shifted series
    # from SignalEngine would delay execution twice; the generated code does not.
    decisions = targets.shift(-1).fillna(0.0)
    run_directory.mkdir(parents=True, exist_ok=False)
    (run_directory / "code").mkdir()
    (run_directory / "prices").mkdir()
    (run_directory / "code/signal_engine.py").write_text(signal_source(decisions))
    manifest = {
        "schema_version": 1,
        "interval": "1D",
        "sources": ["Yahoo frozen research snapshot"],
        "frames": {},
    }
    codes = list(bundle.codes)
    # SPY is another US equity, so including its frozen frame preserves native
    # US routing and permits benchmark resolution. ^HSI is an index market;
    # adding it as a tradable code would incorrectly select CompositeEngine.
    if market == "US":
        codes.append(spec["markets"][market]["benchmark"])
    start = bundle.dates[max(0, bounds[0] - 2)]
    for code in codes:
        raw = pd.read_parquet(
            DATA / "prices" / (code.replace("^", "INDEX_") + ".parquet")
        )
        frame = raw.loc[
            start : spec["test"][1], ["open", "high", "low", "close", "volume"]
        ].dropna(subset=["open", "high", "low", "close"])
        dest = run_directory / "prices" / (code + ".csv")
        frame.to_csv(dest, index_label="date")
        manifest["frames"][code] = {
            "path": str(dest.relative_to(run_directory)),
            "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "attrs": {
                "price_basis": "Yahoo split-adjusted OHLC; dividends separate in original input",
                "currency": "HKD" if market == "HK" else "USD",
            },
        }
    (run_directory / "frozen_data_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    lots_frame = pd.read_csv(ROOT / "config/hk_board_lots_2026-11-12.csv")
    config = {
        "codes": codes,
        "start_date": str(start.date()),
        "end_date": spec["test"][1],
        "evaluation_start_date": spec["test"][0],
        "source": "yfinance",
        "interval": "1D",
        "position_adjustment": "rebalance",
        "rebalance_mask": sorted(execution_dates),
        "initial_cash": spec["markets"][market]["initial_cash"],
        "slippage_us": 0.001,
        "benchmark": spec["markets"][market]["benchmark"],
        "frozen_data_manifest": str(run_directory / "frozen_data_manifest.json"),
    }
    if market == "HK":
        config["hk_lot_sizes"] = dict(
            zip(lots_frame.symbol, lots_frame.board_lot.astype(int))
        )
    (run_directory / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    record = {
        "prepared_at_utc": datetime.now(UTC).isoformat(),
        "candidate": candidate["strategy"],
        "market": market,
        "study_preregistration_sha256": hashlib.sha256(
            (study / "preregistration.json").read_bytes()
        ).hexdigest(),
        "native_upstream_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=vibe_root, text=True
        ).strip(),
        "comparison_policy": "Verification of fixed candidate; no strategy tuning. Research closes/reopens weekly even in same name; native target rebalancing may retain it. Native engine omits separate dividend credits and uses constant HK duty; research uses separate dividends and dated rounded duty. These differences must be reconciled, not hidden.",
        "hsi_native_benchmark_limit": market == "HK",
        "planned_entries": len(plans),
    }
    (run_directory / "verification_protocol.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--vibe-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DATA / "native")
    args = parser.parse_args()
    if not (args.study / "evaluation_complete.json").exists():
        raise ValueError("Complete the frozen strategy evaluation first")
    results = json.loads((args.study / "evaluation_complete.json").read_text())
    if (args.output / "native_verification_summary.json").exists():
        raise FileExistsError("Native verification already completed")
    rows = []
    for market in ["HK", "US"]:
        directory = args.output / market
        protocol = prepare_native(directory, args.study, market, args.vibe_root)
        env = os.environ.copy()
        env["VIBE_TRADING_ALLOWED_RUN_ROOTS"] = str(args.output.resolve())
        command = [
            sys.executable,
            "-B",
            "-m",
            "backtest.runner",
            str(directory.resolve()),
        ]
        executed = subprocess.run(
            command,
            cwd=args.vibe_root / "agent",
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        (directory / "runner.stdout.txt").write_text(executed.stdout)
        (directory / "runner.stderr.txt").write_text(executed.stderr)
        row = protocol | {"command": command, "exit_code": executed.returncode}
        metrics = directory / "artifacts/metrics.csv"
        if executed.returncode == 0 and metrics.exists():
            frame = pd.read_csv(metrics)
            m = frame.iloc[0].to_dict()
            own = next(
                r
                for r in results["evaluations"]
                if r["market"] == market
                and r["strategy"] == protocol["candidate"]
                and r["period"] == "test"
                and r["ablation"] == "base"
            )
            row.update(
                native_sharpe=float(m["sharpe"]),
                research_sharpe=own["sharpe"],
                sharpe_difference=float(m["sharpe"]) - own["sharpe"],
                native_metrics_path=str(metrics),
            )
            row["within_point_one"] = abs(row["sharpe_difference"]) <= 0.1
        else:
            row["error"] = (executed.stderr or executed.stdout)[-2000:]
        rows.append(row)
        print(json.dumps(row), flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    summary = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "rows": rows,
        "confirmation": "Only comparisons with abs(Sharpe difference)<=0.1 pass direct numerical agreement; larger differences need quantified cost/timing/dividend reconciliation before nomination.",
    }
    (args.output / "native_verification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    (ROOT / "results/hk/week4/native_verification_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
