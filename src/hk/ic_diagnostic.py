"""Audit-only IC orientation correction; never execute or change a portfolio."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.hk.week3.features import build_bundle, strategy_week
from src.hk.week3.public_data import ROOT

OUTPUT = ROOT / "results/hk/week3"


def oriented_score(mask, priority, observed):
    """Rank eligible names above ineligible names, preserving within-name priority.

    Ineligible observed names score zero. Eligible names score one plus their
    within-eligible percentile rank. Missing lookback remains missing. This
    changes no selection, size, stop, trade or portfolio return.
    """
    selected = priority.where(mask).dropna()
    result = pd.Series(0.0, index=priority.index).where(observed)
    result.loc[selected.index] = 1.0 + selected.rank(pct=True)
    return result


def rank_ic(bundle, scores, bounds):
    """Evaluate the original five-session labels with a corrected selection score."""
    values = []
    for entry, signal in scores.items():
        exit_ = entry + 5
        if not bounds[0] <= entry < exit_ <= bounds[1]:
            continue
        a, b = bundle.prices["open"].iloc[entry], bundle.prices["open"].iloc[exit_]
        dividends = bundle.prices["dividend"].iloc[entry + 1 : exit_ + 1].sum()
        returns = (b + dividends) / a - 1
        valid = signal.notna() & returns.notna() & a.gt(0) & b.gt(0)
        if (
            valid.sum() >= 2
            and signal[valid].nunique() > 1
            and returns[valid].nunique() > 1
        ):
            values.append(float(signal[valid].rank().corr(returns[valid].rank())))
    return (float(np.mean(values)) if values else None), len(values)


def main():
    """Freeze the correction protocol, recompute IC only, and preserve old exports."""
    destination = OUTPUT / "ic_orientation_review_summary.json"
    if destination.exists():
        raise FileExistsError("This IC audit is complete; do not overwrite it")
    original = json.loads((OUTPUT / "five_strategy_full_results.json").read_text())
    frozen = json.loads((OUTPUT / "five_strategy_preregistration.json").read_text())
    verification = json.loads(
        (OUTPUT / "research_verification_summary.json").read_text()
    )
    for relative, expected in verification["hashes"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen input/source changed: " + relative)
    # All attention files must exist: the review cannot fetch or replace inputs.
    for market in frozen["specification"]["markets"].values():
        for code in market["symbols"]:
            if not (ROOT / "data/hk_week3/attention" / (code + ".parquet")).exists():
                raise FileNotFoundError(code)
    protocol = {
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "reason": "Review found selected negative-priority stocks ranked below rejected zero-score stocks in two base strategies; zero-priority ablations also lost their eligibility signal.",
        "method": "Observed ineligible score=0; eligible score=1+within-eligible percentile rank of the unchanged original priority. Missing lookback stays missing. Original five-session open-to-open plus dividend labels, splits, selected variants and IC averaging unchanged.",
        "portfolio_runs": 0,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "no_tuning": "Deterministic reporting correction for all 124 saved evaluations. No candidate, parameter, portfolio, Sharpe, timing-null, DSR or KEEP gate changes.",
    }
    (OUTPUT / "ic_orientation_review_protocol.json").write_text(
        json.dumps(protocol, indent=2) + "\n"
    )
    spec = frozen["specification"]
    rows = []
    for market in ("HK", "US"):
        bundle = build_bundle(market, spec)
        for strategy in spec["strategies"]:
            parameters = original["selections"][market][strategy["id"]]["parameters"]
            for period in ("train", "test"):
                first = int(bundle.dates.searchsorted(pd.Timestamp(spec[period][0])))
                last = int(
                    bundle.dates.searchsorted(
                        pd.Timestamp(spec[period][1]), side="right"
                    )
                    - 1
                )
                for drop in [None] + strategy["indicators"]:
                    scores = {}
                    for week in bundle.weekly["rv63"].index:
                        entry_day = week + pd.Timedelta(days=7)
                        entry = int(bundle.dates.searchsorted(entry_day))
                        next_week = int(
                            bundle.dates.searchsorted(entry_day + pd.Timedelta(days=7))
                        )
                        planned_exit = min(entry + 5, next_week)
                        if (
                            entry < first
                            or entry >= last
                            or planned_exit > last
                            or planned_exit <= entry
                        ):
                            continue
                        mask, priority, _scale = strategy_week(
                            bundle, strategy, parameters, week, drop
                        )
                        observed = bundle.weekly["rv63"].loc[week].notna()
                        scores[entry] = oriented_score(mask, priority, observed)
                    value, count = rank_ic(bundle, scores, (first, last))
                    identifier = f"{market}.{strategy['id']}.{period}.{drop or 'base'}"
                    saved = next(
                        r for r in original["evaluations"] if r["id"] == identifier
                    )
                    rows.append(
                        {
                            "id": identifier,
                            "market": market,
                            "strategy": strategy["id"],
                            "period": period,
                            "ablation": drop or "base",
                            "original_ic": saved["ic"],
                            "reviewed_ic": value,
                            "original_ic_weeks": saved["ic_weeks"],
                            "reviewed_ic_weeks": count,
                        }
                    )
    frame = pd.DataFrame(rows)
    frame.to_csv(OUTPUT / "five_strategy_ic_reviewed.csv", index=False)
    corrected = pd.read_csv(OUTPUT / "five_strategy_results.csv")
    for index, row in corrected.iterrows():
        for period in ("train", "test"):
            match = frame[
                (frame.market == row.market)
                & (frame.strategy == row.strategy)
                & (frame.period == period)
                & (frame.ablation == "base")
            ].iloc[0]
            corrected.loc[index, "ic_" + period] = match.reviewed_ic
    corrected["ic_method"] = (
        "selection-oriented rank IC; review v1; portfolio unchanged"
    )
    corrected.to_csv(OUTPUT / "five_strategy_results_reviewed.csv", index=False)
    summary = protocol | {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "evaluations": len(frame),
        "changed_ic_values": int(
            (~np.isclose(frame.original_ic, frame.reviewed_ic, equal_nan=True)).sum()
        ),
        "all_original_source_input_hashes_match": True,
        "original_results_preserved": True,
    }
    destination.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        corrected[
            ["market", "strategy", "ic_test", "sharpe_test", "decision"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
