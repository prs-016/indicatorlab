"""Offline Tiingo/Wikipedia integration for the frozen first WATM US study.

No acquisition, credential access, strategy changes or implicit registration.
The user-approved closed-session information boundary is explicit and is never
represented as a provider publication receipt. Existing strategy/accounting/
evaluation functions remain authoritative.
"""

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.india_week3_evaluation import SPLITS, guide_decision
from src.india_week3_market_adapter import _read_prices
from src.india_week3_portfolio import AccountingPolicy
from src.india_week3_runner import TrialLedger, _audit_value
from src.india_week3_strategies import UNIVERSES, _time
from src.india_week3_wiki_strategies import (
    COMPONENTS,
    FREEZE,
    build_wiki_orders,
    evaluate_wiki_run,
    prepare_wiki_snapshots,
    wiki_random_candidates,
)

STRATEGY = "WATM_v1_2"
ROOT = Path(__file__).resolve().parents[1]
TIINGO = ROOT / "results/week3_tiingo_20261117T195551Z"
WIKI = ROOT / "data/processed/wikipedia/week3_v2_20261116"
START = pd.Timestamp("2015-07-01")
END = pd.Timestamp("2025-09-30")


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_inventory(directory, manifest_name="manifest.json"):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / manifest_name).read_text())
    for name, expected in manifest["files_sha256"].items():
        path = (directory / name).resolve()
        if (
            not path.is_relative_to(directory)
            or not path.is_file()
            or _hash(path) != expected
        ):
            raise ValueError("Input inventory path/hash mismatch")
    return manifest


@dataclass
class USInputs:
    """Hash-verified source frames, scheduled times, wiki rows and provenance."""

    prices: dict
    schedule: pd.DataFrame
    wiki: pd.DataFrame
    provenance: dict


def load_us_inputs(tiingo=TIINGO, wiki=WIKI):
    """Load existing validated files only; never acquire data or approve timing.

    Args: Tiingo and Wikipedia package directories with inventories. Returns
    USInputs with all ten names/SPY and original guide-lag Wikipedia features.
    Source hash checks, exact historical bounds, clock alignment and duplicate
    checks fail before execution preparation. Missing attention remains missing.
    """
    tiingo, wiki = Path(tiingo).resolve(), Path(wiki).resolve()
    market_manifest = _verify_inventory(tiingo)
    _verify_inventory(wiki)
    frozen = json.loads((FREEZE / "checksums.json").read_text())
    for name, expected in frozen["rules_files"].items():
        if _hash(FREEZE / name) != expected:
            raise ValueError("Frozen rules changed")
    prices = {}
    for ticker in [*UNIVERSES["US"], "SPY"]:
        name = f"derived/{ticker}.csv"
        frame = _read_prices(tiingo / name, market_manifest["files_sha256"][name])
        if frame.index.min() != START or frame.index.max() != END:
            raise ValueError("Full authorized warm-up/evaluation span required")
        if not np.isfinite(frame).all().all() or frame.volume.le(0).any():
            raise ValueError("Unresolved price/volume observations")
        prices[ticker] = frame
    schedule = pd.read_csv(
        tiingo / "derived/us_xnys_schedule.csv", index_col=0, parse_dates=True
    )
    if (
        not schedule.index.is_unique
        or not schedule.index.is_monotonic_increasing
        or schedule.index.min() != START
        or schedule.index.max() != END
    ):
        raise ValueError("Invalid bounded session calendar")
    schedule["close"] = [_time(t) for t in schedule["close"]]
    for ticker, frame in prices.items():
        if not frame.index.equals(schedule.index):
            raise ValueError("Stock/benchmark/calendar session mismatch")
    w = pd.read_csv(wiki / "wiki_strategy_features.csv")
    for key in ["attention_week", "decision_at", "wiki_published_at_guide"]:
        w[key] = pd.to_datetime(w[key], utc=True)
    if (
        w.decision_at.isna().any()
        or (w.decision_at >= pd.Timestamp("2025-10-01", tz="UTC")).any()
    ):
        raise ValueError("Wikipedia decision reaches holdout or is missing")
    w = w[w.market.eq("US")].copy()
    if (
        set(w.ticker) != set(UNIVERSES["US"])
        or w.duplicated(["ticker", "decision_at"]).any()
    ):
        raise ValueError("Exact unique US company-week inputs required")
    w = w[w.decision_at.ge(pd.Timestamp(SPLITS["train"][0], tz="UTC"))].copy()
    expected = pd.date_range("2016-06-07", "2025-09-30", freq="7D", tz="UTC")
    for ticker in UNIVERSES["US"]:
        if not pd.DatetimeIndex(w.loc[w.ticker.eq(ticker), "decision_at"]).equals(
            expected
        ):
            raise ValueError("Missing or unexpected company-week rows")
    provenance = {
        "tiingo_manifest_sha256": _hash(tiingo / "manifest.json"),
        "wiki_manifest_sha256": _hash(wiki / "manifest.json"),
        "rules_sha256": _hash(FREEZE / "rules.json"),
        "scheduled_closes_are_not_publication_receipts": True,
        "benchmark_basis": "Existing Tiingo derived adjusted SPY close; raw fields separately preserved",
        "warmup_excluded_from_metrics": True,
    }
    return USInputs(prices, schedule, w, provenance)


def price_availability(inputs, policy=None):
    """Resolve closed-session information boundaries without inventing receipts.

    Args: verified inputs; optional observed evidence CSV with explicit reference.
    Default completed_session is the user's rule, not a numeric publication lag:
    signals require close < decision, orders require a subsequent eligible session.
    Returns boundaries and provenance. The frozen interface's published_at field
    carries that model boundary; observed provider publication remains unknown.
    """
    if policy is None:
        policy = {
            "mode": "completed_session",
            "reference": "User Task6 integration clarification: daily OHLCV only after the corresponding trading session has closed",
        }
    if (
        not isinstance(policy, dict)
        or not isinstance(policy.get("reference"), str)
        or not policy["reference"].strip()
    ):
        raise ValueError("Explicit information-boundary reference required")
    symbols = [*UNIVERSES["US"], "SPY"]
    if policy.get("mode") == "completed_session":
        result = {ticker: inputs.schedule["close"].copy() for ticker in symbols}
        label = "COMPLETED-SESSION INFORMATION BOUNDARY; NOT TIINGO PUBLICATION"
    elif policy.get("mode") == "observed":
        path = Path(policy["path"])
        if _hash(path) != policy.get("sha256"):
            raise ValueError("Publication evidence hash mismatch")
        frame = pd.read_csv(path)
        if (
            set(frame) != {"Date", "ticker", "published_at"}
            or frame.duplicated(["Date", "ticker"]).any()
            or set(frame.ticker) != set(symbols)
        ):
            raise ValueError("Exact publication evidence schema/basket required")
        frame["Date"] = pd.to_datetime(frame.Date)
        frame["published_at"] = [_time(t) for t in frame.published_at]
        result = {}
        for ticker in symbols:
            values = frame[frame.ticker.eq(ticker)].set_index("Date").published_at
            if not values.index.equals(inputs.schedule.index):
                raise ValueError("Incomplete/unsorted publication evidence")
            result[ticker] = values
        label = "SUPPLIED HASH-BOUND HISTORICAL PUBLICATION EVIDENCE"
    else:
        raise ValueError("No arbitrary publication-lag convention is approved")
    for values in result.values():
        if values.isna().any() or (values < inputs.schedule["close"]).any():
            raise ValueError("Information boundary missing or precedes session close")
        for at in values:
            _time(at)
    return result, {
        "policy": policy,
        "label": label,
        "provider_publication_observed": policy["mode"] == "observed",
        "sha256": hashlib.sha256(
            json.dumps(policy, sort_keys=True).encode()
        ).hexdigest(),
    }


def prepare_us(inputs, availability_policy=None):
    """Connect validated prices/wiki to the unchanged frozen snapshot builder.

    Args: USInputs and optional observed timing evidence; the default is the
    user-approved completed-session information boundary. Returns full warm-up
    bars, causal snapshots/features and exact train/test accounting panels.
    No orders or historical performance are calculated by preparation.
    """
    availability, timing = price_availability(inputs, availability_policy)
    bars = {}
    for ticker, frame in inputs.prices.items():
        b = frame.copy(deep=True)
        b["session_date"] = b.index
        # Compatibility name in the frozen runner: information boundary only,
        # not a historical provider publication assertion.
        b["published_at"] = availability[ticker].to_numpy()
        b["provider_publication_at"] = pd.NaT
        b["information_boundary_basis"] = timing["label"]
        b.index = pd.DatetimeIndex(inputs.schedule["close"])
        bars[ticker] = b
    benchmark = bars.pop("SPY")
    snapshots, daily = prepare_wiki_snapshots("US", bars, benchmark, inputs.wiki)
    close = pd.DataFrame({t: bars[t].close for t in UNIVERSES["US"]})
    volume = pd.DataFrame({t: bars[t].volume for t in UNIVERSES["US"]})
    panels = {}
    for split, (start, end) in SPLITS.items():
        mask = (close.index.normalize() >= pd.Timestamp(start, tz="UTC")) & (
            close.index.normalize() <= pd.Timestamp(end, tz="UTC")
        )
        c = close.loc[mask]
        s = {
            at: pair
            for at, pair in snapshots.items()
            if pd.Timestamp(start, tz="UTC") <= at <= pd.Timestamp(end, tz="UTC")
        }
        panels[split] = {
            "close": c,
            "volume": volume.loc[c.index],
            "benchmark": benchmark.close.loc[c.index],
            "snapshots": s,
            "daily_features": daily,
        }
    return {
        "panels": panels,
        "bars": bars,
        "benchmark_bars": benchmark,
        "provenance": {**inputs.provenance, "availability": timing},
    }


def preflight(
    inputs, *, availability_policy=None, initial_cash=100000, registration=None
):
    """Assess concrete run inputs without executing a strategy or claiming approval.

    Args: verified inputs and optional explicit runtime evidence. Returns counts,
    blockers and timing policy status; registration is separately user-verified.
    Full prior-trial history is required for a complete DSR, not data preparation.
    """
    blockers = []
    try:
        _, timing = price_availability(inputs, availability_policy)
    except (ValueError, KeyError, OSError) as error:
        timing = None
        blockers.append(str(error))
    if initial_cash is None:
        blockers.append("Explicit initial US research capital required")
    else:
        AccountingPolicy(
            initial_cash, "fractional", "pretrade_nav_fee_inclusive_budget"
        )
    try:
        _registration(registration, inputs.provenance["rules_sha256"])
    except (ValueError, KeyError, OSError) as error:
        blockers.append(str(error))
    covered = (
        inputs.wiki.assign(
            valid=inputs.wiki.eligible_at_snapshot
            & inputs.wiki.wiki_ratio.notna()
            & inputs.wiki.wiki_rz.notna()
        )
        .groupby("decision_at")
        .valid.sum()
    )
    return {
        "strategy": STRATEGY,
        "stock_count": 10,
        "stock_and_benchmark_rows": sum(len(f) for f in inputs.prices.values()),
        "aligned_sessions": len(inputs.schedule),
        "weekly_decisions": len(covered),
        "wiki_portfolio_coverage_pass": int(covered.ge(8).sum()),
        "timing": timing,
        "blockers": blockers,
        "baseline_run_ready": not blockers,
        "full_evaluation_additional_input": "Complete prior research-trial history plus explicit DSR dependence/effective-trial assumptions",
        "provenance": inputs.provenance,
    }


def _registration(record, rules_hash):
    if (
        not isinstance(record, dict)
        or record.get("rules_sha256") != rules_hash
        or record.get("strategy") != STRATEGY
    ):
        raise ValueError(
            "Verified actual shared registration bound to frozen rules required"
        )
    if not all(record.get(k) for k in ["confirmed_by", "confirmation_reference"]):
        raise ValueError(
            "User confirmation of actual shared Strategy Log registration required"
        )
    if record.get("evidence_path") and _hash(record["evidence_path"]) != record.get(
        "evidence_sha256"
    ):
        raise ValueError("Registration evidence hash mismatch")
    confirmation_time = record.get("confirmed_at") or record.get("registered_at")
    if not confirmation_time:
        raise ValueError("Timezone-aware registration confirmation time required")
    _aware_registration(confirmation_time)


def _aware_registration(value):
    # Registration is current audit metadata, not a historical research observation.
    if pd.Timestamp(value).tzinfo is None:
        raise ValueError("Timezone-aware registration timestamp required")


def _save_run(directory, run):
    directory.mkdir()
    run["orders"].to_csv(directory / "orders.csv", index=False)
    result = run["result"]
    pd.DataFrame({at: plan.scores for at, plan in run["plans"].items()}).T.to_csv(
        directory / "signal_scores.csv"
    )
    for name in ["daily", "quantities", "fills", "trades"]:
        getattr(result, name).to_csv(directory / (name + ".csv"))
    (directory / "metrics.json").write_text(
        json.dumps(_audit_value(result.metrics), indent=2, allow_nan=False) + "\n"
    )


def run_us_study(
    prepared,
    *,
    initial_cash=100000,
    registration,
    output,
    vibe_root,
    prior_trials=None,
    effective_trials=None,
    dependence_assumption=None,
    ledger_complete=False,
):
    """Execute the already implemented train-first study only with explicit inputs.

    Args: prepared verified data/timing; actual shared-registration evidence;
    explicit initial cash, never-existing local results path and Vibe IC checkout.
    DSR accepts a complete prior-trial ledger/effective count/assumption; without
    it DSR and final KEEP/DROP stay NOT EVALUATED. Returns saved artifact metadata.
    No source access/strategy tuning occurs. Insufficient train entries defer test.
    """
    _registration(registration, prepared["provenance"]["rules_sha256"])
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "results"):
        raise ValueError("Study artifacts must stay in local ignored results")
    output.mkdir(exist_ok=False)
    policy = AccountingPolicy(
        initial_cash, "fractional", "pretrade_nav_fee_inclusive_budget"
    )
    prefix = STRATEGY + ":US:" + output.name
    ledger = TrialLedger()
    runs = {}
    reports = {}
    ablations = {}
    errors = []
    provenance = {
        **prepared["provenance"],
        "registration": registration,
        "orchestrator_sha256": _hash(Path(__file__)),
    }
    try:
        for split in ["train", "test"]:
            if (
                split == "test"
                and runs["train"]["result"].metrics["filled_entries"] < 30
            ):
                errors.append(
                    "Fewer than30 training entries; test not examined; new version required for any threshold adjustment"
                )
                break
            p = prepared["panels"][split]
            common = {
                k: p[k] for k in ["close", "volume", "snapshots", "daily_features"]
            }
            args = dict(
                market="US",
                split=split,
                policy=policy,
                ledger=ledger,
                provenance=provenance,
                **common,
            )
            run = build_wiki_orders(
                strategy=STRATEGY, trial_id=f"{prefix}:{split}:baseline", **args
            )
            runs[split] = run
            _save_run(output / split, run)
            ablations[split] = {}
            for component in COMPONENTS[STRATEGY]:
                try:
                    variant = build_wiki_orders(
                        strategy=STRATEGY,
                        disabled=component,
                        trial_id=f"{prefix}:{split}:drop:{component}",
                        **args,
                    )
                    ablations[split][component] = variant
                    _save_run(output / split / ("drop_" + component), variant)
                except (ValueError, RuntimeError) as error:
                    ablations[split][component] = None
                    errors.append(
                        f"{split} ablation {component}: {type(error).__name__}"
                    )
            candidates = (
                wiki_random_candidates(run, p["close"], p["volume"])
                if not run["result"].trades.empty
                else None
            )
            report = evaluate_wiki_run(
                run,
                benchmark=p["benchmark"],
                close=p["close"],
                volume=p["volume"],
                snapshots=p["snapshots"],
                market="US",
                split=split,
                policy=policy,
                ledger=ledger,
                trial_prefix=f"{prefix}:{split}:evaluation",
                vibe_root=Path(vibe_root),
                random_candidates=candidates,
                max_attempts=10000,
            )
            reports[split] = report
            report["ic"]["ic"].to_csv(output / split / "ic.csv")
            (output / split / "ic_metadata.json").write_text(
                json.dumps(
                    {k: v for k, v in report["ic"].items() if k != "ic"}, indent=2
                )
                + "\n"
            )
            if report["random"] is not None:
                pd.DataFrame(
                    {
                        "seed": range(42, 242),
                        "net_sharpe": [
                            r.metrics["net_sharpe"] for r in report["random"]
                        ],
                    }
                ).to_csv(output / split / "random_sharpes.csv", index=False)
                for seed, null in zip(range(42, 242), report["random"], strict=True):
                    directory = output / split / ("random_" + str(seed))
                    directory.mkdir()
                    null.daily.to_csv(directory / "daily.csv")
                    null.trades.to_csv(directory / "trades.csv")
                    null.fills.to_csv(directory / "fills.csv")
        _finish_dsr(
            runs,
            reports,
            ablations,
            prior_trials,
            effective_trials,
            dependence_assumption,
            ledger_complete,
            ledger,
        )
        decision = _decision(runs, reports, ablations)
        result = {
            "strategy": STRATEGY,
            "market": "US",
            "decision": decision,
            "errors": errors,
            "provenance": provenance,
            "initial_cash": initial_cash,
            "performance": {
                s: {
                    "strategy": r["result"].metrics,
                    "benchmark": reports[s]["benchmark"],
                    "ic_mean": float(reports[s]["ic"]["ic"].mean()),
                    "DSR": reports[s]["DSR"],
                    "missing": reports[s]["missing"],
                }
                for s, r in runs.items()
            },
        }
        (output / "evaluation.json").write_text(
            json.dumps(_audit_value(result), indent=2, allow_nan=False, default=str)
            + "\n"
        )
        return result
    except Exception as error:
        (output / "execution_failure.json").write_text(
            json.dumps(
                {
                    "status": "FAILED; no complete evaluation claim",
                    "error_type": type(error).__name__,
                    "completed_splits": list(runs),
                    "provenance": _audit_value(provenance),
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
        raise
    finally:
        ledger.save(output / "trial_ledger.json")


def _finish_dsr(
    runs,
    reports,
    ablations,
    prior_trials,
    effective_trials,
    assumption,
    complete,
    ledger,
):
    from src.india_week3_research import deflated_sharpe

    if prior_trials is None or not complete:
        return
    current = []
    for record in ledger.records:
        if record["kind"] in {"strategy", "ablation"}:
            sr = record["metrics"].get("net_sharpe", np.nan)
            current.append(
                {
                    "trial_id": record["trial_id"],
                    "status": record["status"],
                    "daily_sharpe": sr / np.sqrt(252) if sr is not None else np.nan,
                }
            )
    trials = pd.concat([prior_trials, pd.DataFrame(current)], ignore_index=True)
    for split, run in runs.items():
        try:
            dsr = deflated_sharpe(
                run["result"].daily.net_return,
                trials,
                effective_trials=effective_trials,
                dependence_assumption=assumption or "",
                ledger_complete=complete,
            )
            reports[split]["DSR"] = dsr
            reports[split]["missing"] = [
                m
                for m in reports[split]["missing"]
                if m != "Full trial history and explicit DSR assumptions"
            ]
            ledger.record(
                run["trial_id"] + ":DSR",
                kind="DSR",
                settings={
                    "effective_trials": effective_trials,
                    "assumption": assumption,
                    "trial_ids": trials.trial_id.tolist(),
                },
                status="complete",
                metrics=dsr,
            )
        except (ValueError, TypeError) as error:
            reports[split]["missing"].append("DSR: " + str(error))
            ledger.record(
                run["trial_id"] + ":DSR",
                kind="DSR",
                settings={"ledger_complete": complete},
                status="failed",
                error=type(error).__name__,
            )


def _decision(runs, reports, ablations):
    train = runs["train"]["result"].metrics
    if train["filled_entries"] < 30:
        return "INSUFFICIENT TRAINING ENTRIES"

    def nulls(split):
        return (
            []
            if reports[split]["random"] is None
            else [r.metrics["net_sharpe"] for r in reports[split]["random"]]
        )

    complete = all(
        reports[s]["DSR"] is not None
        and not reports[s]["missing"]
        and set(ablations[s]) == set(COMPONENTS[STRATEGY])
        and all(v is not None for v in ablations[s].values())
        for s in ["train", "test"]
    )
    return guide_decision(
        training_entries=train["filled_entries"],
        train_sharpe=train["net_sharpe"],
        test_sharpe=runs["test"]["result"].metrics["net_sharpe"],
        index_test_sharpe=reports["test"]["benchmark"]["net_sharpe"],
        random_train=nulls("train"),
        random_test=nulls("test"),
        reports_complete=complete,
    )


def main():
    """Run a read-only real-data preflight; historical execution is an explicit API.

    CLI accepts optional policy/capital/registration records and prints only counts
    and blockers. It never performs trades or accesses a provider/credential.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiingo", type=Path, default=TIINGO)
    parser.add_argument("--wiki", type=Path, default=WIKI)
    parser.add_argument("--availability", type=Path)
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--initial-cash", type=float, default=100000)
    args = parser.parse_args()
    inputs = load_us_inputs(args.tiingo, args.wiki)
    availability = (
        json.loads(args.availability.read_text()) if args.availability else None
    )
    registration = (
        json.loads(args.registration.read_text()) if args.registration else None
    )
    print(
        json.dumps(
            preflight(
                inputs,
                availability_policy=availability,
                initial_cash=args.initial_cash,
                registration=registration,
            ),
            indent=2,
            default=str,
        )
    )


def registration_row(inputs, *, initial_cash=100000):
    """Return the exact seven-column US registration row, without registering it.

    Args: verified USInputs and approved capital override or user-default100000.
    Returns owner/version/description/IC/Sharpe/decision/notes with unrun results,
    fixed rule hash, data hashes and closed-session timing explicitly recorded.
    """
    AccountingPolicy(initial_cash, "fractional", "pretrade_nav_fee_inclusive_budget")
    description = (
        "US; sources Tiingo OHLCV + Wikimedia attention. Regime SPY close>SMA200; "
        "stock close>SMA50 and momentum=close[t-21]/close[t-126]-1>0; weekly top2 "
        "descending momentum, ascending ticker ties. At least8/10 valid Wikipedia "
        "ratio/z inputs; median robust z>=2 halves portfolio targets, otherwise full; "
        "insufficient coverage targets cash. Wiki baseline8 prior weeks,26 prior valid "
        "abnormal values,MAD1.4826,one-day guide lag. d=max(.02,2*ATR20/close),reject d>.10; "
        "weight=min(.50,.01/d) times portfolio multiplier; maximum2 positions,no leverage. "
        "Initial stop=fill*(1-d); trail=max(previous stop,highest completed close-2*entry ATR). "
        "Weekly remove lost eligibility/top2; protective exits execute later. "
        "Tuesday00:00UTC decisions from closed bars; first subsequent eligible close; "
        "new entries expire after2 sessions,require5 remaining. Fractional shares,US10bps "
        "per side turnover,fee-inclusive cash funding,split-end liquidation; no missing fills."
    )
    notes = (
        f"US starting capital USD{initial_cash:g}; train2016-06-01..2021-12-31; "
        "test2022-01-01..2025-09-30; warmup2015-07-01. "
        f"Frozen rules SHA256={inputs.provenance['rules_sha256']}; "
        f"Tiingo manifest SHA256={inputs.provenance.get('tiingo_manifest_sha256','SYNTHETIC')}; "
        f"Wiki manifest SHA256={inputs.provenance.get('wiki_manifest_sha256','SYNTHETIC')}. "
        "Closed-session information boundary is not a historical Tiingo publication receipt. "
        "At least30 training entries; original Vibe IC,five-session labels; net train/test "
        "Sharpe vs SPY;200 matched timing nulls,seeds42-241;four frozen predictive "
        "ablations;DSR includes prior trials with explicit dependence assumptions. "
        "NOT REGISTERED until actual shared-log entry is confirmed; NOT EVALUATED."
    )
    return [
        "Jamaal",
        STRATEGY,
        description,
        "NOT EVALUATED",
        "NOT EVALUATED / NOT EVALUATED",
        "NOT EVALUATED",
        notes,
    ]


if __name__ == "__main__":
    main()
