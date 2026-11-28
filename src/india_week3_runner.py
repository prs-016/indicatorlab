"""Causal persistent v2 order building on supplied, already verified observations."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.india_week3_portfolio import PortfolioBook, account_orders, validate_panel
from src.india_week3_strategies import (
    STRATEGIES,
    UNIVERSES,
    _time,
    aer_event_eligible,
    daily_risk,
    open_holding,
    price_features,
    weekly_exit,
    weekly_plan,
)

AGM_VARIANTS = {
    "baseline": ("reddit", "wiki"),
    "no_attention": (),
    "reddit_only": ("reddit",),
    "wiki_only": ("wiki",),
}
ORDER_COLUMNS = ["execution_at", "decision_at", "ticker", "target_weight", "reason"]


def _audit_value(value):
    if isinstance(value, dict):
        return {str(k): _audit_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_audit_value(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


class TrialLedger:
    """In-memory append-only audit of all attempted studies and null comparisons.

    Args: No inputs. record requires a unique trial ID and explicit settings.
    Entries include failures, versions, parameter/settings hashes and metrics.
    This ledger does not assert it contains the researcher's earlier trials.
    """

    def __init__(self):
        self.records = []

    def record(
        self,
        trial_id: str,
        *,
        kind: str,
        settings: dict,
        status: str,
        metrics: dict | None = None,
        error: str | None = None
    ) -> None:
        """Append a unique completed/failed/not-run trial; return None."""
        if any(r["trial_id"] == trial_id for r in self.records):
            raise ValueError("Duplicate trial ID")
        payload = json.dumps(
            _audit_value(settings), sort_keys=True, default=str, allow_nan=False
        )
        self.records.append(
            {
                "trial_id": trial_id,
                "kind": kind,
                "settings": json.loads(payload),
                "settings_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "status": status,
                "metrics": _audit_value(dict(metrics or {})),
                "error_type": error,
            }
        )

    def save(self, path: Path) -> str:
        """Save an immutable JSON audit snapshot to a new caller-selected file.

        Args: path must not already exist. Returns the written SHA-256. This
        records all attempts in this ledger but never claims earlier research
        history is complete; callers must merge that evidence for DSR.
        """
        payload = (
            json.dumps(
                {
                    "scope": "recorded attempts only; prior research history not automatically complete",
                    "records": self.records,
                },
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        with Path(path).open("x", encoding="utf-8") as stream:
            stream.write(payload)
        return hashlib.sha256(payload.encode()).hexdigest()


def prepare_snapshots(
    strategy: str, market: str, bars: dict, benchmark_bars: pd.DataFrame, weekly: dict
) -> tuple[dict, dict]:
    """Combine causal price indicators with supplied complete weekly attention rows.

    Args: bars maps the fixed basket to timezone-aware OHLCV local-close frames;
        benchmark_bars follows the same schema. weekly maps Tuesday snapshot to
        ticker-indexed attention/sentiment/publication rows from upstream adapters.
        No sentiment/attention count is invented; prior AER rows require an actual
        previous weekly snapshot. Warm-up bars are not evaluation observations.
    Returns: Snapshot dict (features, benchmark) and full daily feature dict.
        AER's first weekly row supplies history only, without a prior event.
    """
    if set(bars) != set(UNIVERSES[market]):
        raise ValueError("Exact strategy basket required")
    daily = {t: price_features(frame) for t, frame in bars.items()}
    if "published_at" not in benchmark_bars or any(
        "published_at" not in b for b in bars.values()
    ):
        raise ValueError("Actual price publication timestamps required")
    benchmark = price_features(benchmark_bars)
    snapshots, prior = {}, {}
    for at, attention in sorted(weekly.items()):
        at = _time(at)
        rows = []
        for ticker in UNIVERSES[market]:
            history = daily[ticker].loc[daily[ticker].index < at]
            if history.empty:
                raise ValueError("No preceding price bar")
            row = {
                **history.iloc[-1].to_dict(),
                **attention.loc[ticker].to_dict(),
                "close_at": history.index[-1],
            }
            # Prices are authoritative: weekly columns cannot replace price indicators.
            row.update(history.iloc[-1].to_dict())
            row["published_at"] = max(
                _time(row["published_at"]),
                max(
                    _time(t)
                    for t in bars[ticker].loc[: history.index[-1], "published_at"]
                ),
            )
            if strategy == "AER_v2":
                previous = prior.get(at - pd.Timedelta(days=7))
                if previous is not None:
                    old = previous.loc[ticker]
                    for field in [
                        "return5",
                        "close",
                        "sma20",
                        "atr",
                        "rsi",
                        "reddit_ratio",
                        "reddit_rz",
                        "wiki_ratio",
                        "wiki_rz",
                        "sentiment",
                        "posts",
                    ]:
                        row["prior_" + field] = old[field]
                    row["prior_atr_pct"] = old["atr"] / old["close"]
                    row["prior_snapshot"] = at - pd.Timedelta(days=7)
                    row["prior_published_at"] = old["published_at"]
            rows.append(row)
        frame = pd.DataFrame(rows, index=UNIVERSES[market])
        prior[at] = frame
        if strategy == "AER_v2" and at - pd.Timedelta(days=7) not in prior:
            continue
        history = benchmark.loc[benchmark.index < at]
        if history.empty:
            raise ValueError("No preceding benchmark bar")
        b = {
            **history.iloc[-1].to_dict(),
            "close_at": history.index[-1],
            "published_at": max(
                _time(t)
                for t in benchmark_bars.loc[: history.index[-1], "published_at"]
            ),
        }
        snapshots[at] = (frame, b)
    return snapshots, daily


def build_and_account(
    strategy: str,
    market: str,
    split: str,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    snapshots: dict,
    daily_features: dict,
    *,
    policy,
    pending_update: str,
    trial_id: str,
    ledger: TrialLedger,
    provenance: dict,
    india_engine=None,
    variant: str = "baseline"
) -> dict:
    """Run persistent decisions -> actual ledger fills -> risk state on one split.

    Args: snapshots/daily_features come from prepare_snapshots (or audited prepared
        inputs); close/volume contain evaluation sessions only. policy fixes cash
        rounding/budget convention; pending_update must explicitly accept
        replace_on_snapshot for unfilled entry/resize targets (never exits).
        trial_id/ledger/provenance record every attempt and declared dataset IDs.
        variant selects defined AGM controls or a frozen drop:<indicator> deletion.
    Returns: Accounting result, exact orders, plans and event log. Failures are
        recorded and raised, never returned as successful partial portfolios.
        No model/data access, fee assumptions, registration or file writes occur.
    """
    if any(r["trial_id"] == trial_id for r in ledger.records):
        raise ValueError("Duplicate trial ID")
    from src.india_week3_ablation import COMPONENTS

    component = variant.removeprefix("drop:") if variant.startswith("drop:") else None
    if component is not None and component not in COMPONENTS[strategy]:
        raise ValueError("Unknown frozen drop-one indicator")
    sources = (
        AGM_VARIANTS["baseline"] if component is not None else AGM_VARIANTS[variant]
    )
    if strategy != "AGM_v2" and variant != "baseline" and component is None:
        raise ValueError("Only AGM accepts combined/source-only attention controls")
    settings = {
        "strategy": strategy,
        "frozen_registration_sha256": hashlib.sha256(
            Path(__file__)
            .resolve()
            .parents[1]
            .joinpath(
                "india_research/reports/week3_v2_registration_frozen_20261115/parameters.json"
            )
            .read_bytes()
        ).hexdigest(),
        "specification_sha256": hashlib.sha256(
            Path(__file__)
            .resolve()
            .parents[1]
            .joinpath(
                "india_research/reports/india_week3_strategy_registration_v2_PROPOSED_20261115.md"
            )
            .read_bytes()
        ).hexdigest(),
        "market": market,
        "split": split,
        "variant": variant,
        "disabled_indicator": component,
        "attention_sources": sources,
        "policy": asdict(policy),
        "pending_update": pending_update,
        "provenance": provenance,
        "engine": getattr(india_engine, "provenance", None),
        "integration_source_sha256": {
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in [
                "india_week3_runner.py",
                "india_week3_portfolio.py",
                "india_week3_costs.py",
                "india_week3_research.py",
                "india_week3_ablation.py",
            ]
        },
        "kernel_sha256": hashlib.sha256(
            Path(__file__).with_name("india_week3_strategies.py").read_bytes()
        ).hexdigest(),
    }
    try:
        return _run(
            strategy,
            market,
            split,
            close,
            volume,
            snapshots,
            daily_features,
            policy,
            pending_update,
            trial_id,
            ledger,
            settings,
            india_engine,
            sources,
        )
    except Exception as exc:
        if not any(r["trial_id"] == trial_id for r in ledger.records):
            ledger.record(
                trial_id,
                kind="strategy" if variant == "baseline" else "ablation",
                settings=settings,
                status="failed",
                error=type(exc).__name__,
            )
        raise


def _run(
    strategy,
    market,
    split,
    close,
    volume,
    snapshots,
    daily_features,
    policy,
    pending_update,
    trial_id,
    ledger,
    settings,
    engine,
    sources,
):
    STRATEGIES[strategy]
    validate_panel(close, volume, split)
    if set(close) != set(UNIVERSES[market]) or pending_update != "replace_on_snapshot":
        raise ValueError("Exact basket and explicit pending-order policy required")
    if market == "IN" and (engine is None or policy.quantity_mode != "whole"):
        raise ValueError("India requires original engine and whole-share policy")
    for frame in daily_features.values():
        for timestamp in frame.index:
            _time(timestamp)
    settings["data_sha256"] = {
        "close": hashlib.sha256(close.to_csv().encode()).hexdigest(),
        "volume": hashlib.sha256(volume.to_csv().encode()).hexdigest(),
        "daily_features": {
            t: hashlib.sha256(f.to_csv().encode()).hexdigest()
            for t, f in daily_features.items()
        },
        "snapshots": {
            str(at): hashlib.sha256(
                (f.to_csv() + json.dumps(b, sort_keys=True, default=str)).encode()
            ).hexdigest()
            for at, (f, b) in snapshots.items()
        },
    }
    dates = close.index
    decisions = {
        at: pair
        for at, pair in snapshots.items()
        if dates[0].normalize() <= _time(at) <= dates[-1]
    }
    if set(decisions) & set(dates):
        raise ValueError("Snapshot and execution close must be distinct")
    book = PortfolioBook(policy, market, engine)
    pending, risks, last_exit, consumed = {}, {}, {}, set()
    orders, events, plans = [], [], {}
    for at in sorted(set(dates) | set(decisions)):
        if at in decisions:
            frame, b = decisions[at]
            # A weekly decision never cancels an already triggered protective exit.
            for t in list(pending):
                if pending[t]["target_weight"] > 0:
                    events.append(
                        {"at": at, "ticker": t, "event": "replaced_unfilled_target"}
                    )
                    pending.pop(t)
            disabled = settings.get("disabled_indicator")
            if disabled:
                from src.india_week3_ablation import drop_one_plan

                plan = drop_one_plan(
                    strategy,
                    market,
                    at,
                    frame,
                    b,
                    component=disabled,
                    held=tuple(book.held),
                )
            else:
                plan = weekly_plan(
                    strategy,
                    market,
                    at,
                    frame,
                    b,
                    held=tuple(book.held),
                    attention_sources=sources,
                )
            plans[at] = plan
            for t in list(book.held):
                r = frame.loc[t]
                selected = t in plan.ungated if np.isfinite(plan.scores[t]) else True
                reason = weekly_exit(
                    strategy,
                    regime=plan.regime,
                    selected=selected,
                    momentum=(
                        np.nan if disabled == "momentum" else r.get("momentum", np.nan)
                    ),
                    sentiment=(
                        np.nan
                        if disabled == "sentiment_level"
                        else r.get("sentiment", np.nan)
                    ),
                )
                if reason and (t not in pending or pending[t]["target_weight"] > 0):
                    pending[t] = {
                        "decision_at": at,
                        "target_weight": 0.0,
                        "reason": reason,
                    }
            if plan.status != "ready" or not plan.regime:
                continue
            exiting = {t for t, p in pending.items() if p["target_weight"] == 0}
            occupied = set(book.held) - exiting
            if strategy == "AGM_v2":
                targets = plan.targets
            else:
                eligible = plan.eligible.copy()
                eligible.loc[list(book.held)] = False
                if strategy == "AER_v2":
                    i = dates.searchsorted(at)
                    for t in eligible.index:
                        event = str(frame.loc[t, "prior_snapshot"])
                        elapsed = None if t not in last_exit else i - last_exit[t]
                        if not aer_event_eligible(
                            t + event, consumed, sessions_since_exit=elapsed
                        ):
                            eligible[t] = False
                names = sorted(
                    eligible[eligible].index, key=lambda t: (-plan.scores[t], t)
                )[: max(0, 2 - len(occupied))]
                targets = {
                    t: min(
                        0.5,
                        0.01
                        / max(0.02, 2 * frame.loc[t, "atr"] / frame.loc[t, "close"]),
                    )
                    for t in names
                }
            for t, w in targets.items():
                if t in exiting:
                    continue
                pending[t] = {
                    "decision_at": at,
                    "target_weight": w,
                    "reason": "weekly_target",
                    "atr": frame.loc[t, "atr"],
                    "distance": max(
                        0.02, 2 * frame.loc[t, "atr"] / frame.loc[t, "close"]
                    ),
                    "attempts": 0,
                    "event": t + str(frame.loc[t].get("prior_snapshot", "")),
                }
            continue
        i = dates.get_loc(at)
        # Time and split exits are known from entry/calendar, before this bar.
        for t, h in list(risks.items()):
            if i == len(dates) - 1 or h.held_sessions + 1 >= STRATEGIES[strategy]:
                pending[t] = {
                    "decision_at": book.openings[t]["entry"],
                    "target_weight": 0.0,
                    "reason": "terminal" if i == len(dates) - 1 else "time",
                }
        if i == len(dates) - 1:
            pending = {t: p for t, p in pending.items() if p["target_weight"] == 0}
        active, metadata = [], {}
        exiting_now = {
            t
            for t, p in pending.items()
            if p["target_weight"] == 0
            and p["decision_at"] < at
            and np.isfinite(volume.at[at, t])
            and volume.at[at, t] > 0
        }
        slots = 2 - len(set(book.held) - exiting_now)
        for t, p in sorted(
            pending.items(),
            key=lambda item: (item[1]["target_weight"] > 0, item[0]),
        ):
            if p["decision_at"] >= at:
                continue
            entry = p["target_weight"] > 0
            if entry:
                if strategy == "AER_v2" and t in last_exit and i - last_exit[t] < 10:
                    continue
                p["attempts"] += 1
                if (t not in book.held and p["attempts"] > 2) or (
                    t not in book.held and len(dates) - i < 5
                ):
                    events.append(
                        {
                            "at": at,
                            "ticker": t,
                            "event": "entry_expired_or_terminal_boundary",
                        }
                    )
                    pending.pop(t)
                    continue
                if t not in book.held and slots <= 0:
                    continue
            if (
                not np.isfinite(volume.at[at, t])
                or volume.at[at, t] <= 0
                or not np.isfinite(close.at[at, t])
            ):
                continue
            active.append(
                {
                    "execution_at": at,
                    "ticker": t,
                    **{k: p[k] for k in ["decision_at", "target_weight", "reason"]},
                }
            )
            metadata[t] = dict(p)
            if entry and t not in book.held:
                slots -= 1
        before = set(book.held)
        book.step(
            at,
            close.loc[at],
            volume.loc[at],
            pd.DataFrame(active, columns=ORDER_COLUMNS),
            i=i,
            remaining=len(dates) - i,
        )
        orders.extend(active)
        after = set(book.held)
        for t in before - after:
            risks.pop(t)
            last_exit[t] = i
        for t in metadata:
            pending.pop(t, None)
        for t in after - before:
            p = metadata[t]
            fill = next(
                f
                for f in reversed(book.fills)
                if f["ticker"] == t and f["execution_at"] == at
            )
            risks[t] = open_holding(strategy, fill["price"], p["atr"], p["distance"])
            if strategy == "AER_v2":
                consumed.add(p["event"])
        for t in before & after:
            row = daily_features[t].loc[at]
            risks[t], reason = daily_risk(
                risks[t],
                close.at[at, t],
                sma=(
                    np.nan
                    if settings.get("disabled_indicator") in {"sma50", "sma20"}
                    else (row["sma50"] if strategy == "AGM_v2" else row["sma20"])
                ),
                low20=(
                    np.nan
                    if settings.get("disabled_indicator") == "low20_exit"
                    else row["ll20"]
                ),
            )
            if reason and t not in pending:
                pending[t] = {"decision_at": at, "target_weight": 0.0, "reason": reason}
    if book.held:
        raise ValueError("Unfilled terminal liquidation; no complete result")
    order_frame = pd.DataFrame(orders, columns=ORDER_COLUMNS)
    result = account_orders(
        close,
        volume,
        order_frame,
        market=market,
        split=split,
        policy=policy,
        india_engine=engine,
    )
    replay = pd.DataFrame(book.daily, index=dates)
    pd.testing.assert_frame_equal(result.daily, replay)
    ledger.record(
        trial_id,
        kind="strategy" if settings["variant"] == "baseline" else "ablation",
        settings=settings,
        status="complete",
        metrics=result.metrics,
    )
    return {
        "trial_id": trial_id,
        "settings": settings,
        "orders": order_frame,
        "result": result,
        "plans": plans,
        "events": events,
        "consumed_events": sorted(consumed),
    }


def run_defined_ablations(
    strategy: str, *, run_arguments: dict, trial_prefix: str
) -> dict:
    """Execute only the explicitly specified AGM source-filter variants.

    Args: strategy must be AGM_v2; run_arguments supplies all build_and_account
        inputs except strategy/variant/trial_id; trial_prefix makes unique IDs.
    Returns: Baseline/no-attention/Reddit-only/Wikipedia-only results. Expected
        failures remain in the shared trial ledger; no replacement trial chosen.
        SCB/AER drop-one ranking/gate semantics are intentionally not guessed.
    """
    if strategy != "AGM_v2":
        raise ValueError("Only AGM ablation semantics are specified")
    results = {}
    for variant in AGM_VARIANTS:
        try:
            results[variant] = build_and_account(
                strategy=strategy,
                variant=variant,
                trial_id=trial_prefix + ":" + variant,
                **run_arguments
            )
        except (ValueError, RuntimeError):
            results[variant] = None
    return results


def evaluate_recorded_run(
    run: dict,
    *,
    benchmark: pd.Series,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    snapshots: dict,
    market: str,
    split: str,
    policy,
    ledger: TrialLedger,
    trial_prefix: str,
    vibe_root: Path,
    india_engine=None,
    random_candidates: dict | None = None,
    max_attempts: int | None = None,
    random_initial_entries: dict | None = None,
    random_mixing_sweeps: int = 64,
    random_cooldown_decisions: pd.DatetimeIndex | None = None,
    random_cooldown_steps: int = 0,
    dsr_trials: pd.DataFrame | None = None,
    effective_trials: float | None = None,
    dependence_assumption: str | None = None,
    ledger_complete: bool = False
) -> dict:
    """Connect a completed order builder to original IC, benchmarks, nulls and DSR.

    Args: supplied inputs must match the completed run. random_candidates must be
        predeclared weekly/regime/coverage calendar indices for every actual trade;
        random_initial_entries selects the corrected feasible anchored sampler;
        random_mixing_sweeps fixes its move budget before pricing, without a
        finite-mixing guarantee. DSR needs full prior history/dependence settings.
        Optional random_cooldown_decisions/steps preserve WCR's re-entry clock.
    Returns: Metrics/IC/benchmark plus optional full 200 null results and DSR.
        Missing optional evidence is NOT EVALUATED, never an implicit success.
        Each IC/null/DSR evaluation attempt is recorded with full source/settings.
    """
    from src.india_week3_evaluation import net_metrics, random_timing_schedules
    from src.india_week3_research import (
        deflated_sharpe,
        five_session_labels,
        original_rank_ic,
        price_timing_schedule,
    )
    from src.india_week3_strategies import entry_close

    if (
        not benchmark.index.equals(close.index)
        or not np.isfinite(benchmark).all()
        or (benchmark <= 0).any()
    ):
        raise ValueError("Complete aligned benchmark required")
    result = run["result"]
    if not result.daily.index.equals(close.index):
        raise ValueError("Run/panel mismatch")
    source_settings = run["settings"]
    if (
        source_settings["market"] != market
        or source_settings["split"] != split
        or source_settings["policy"] != asdict(policy)
    ):
        raise ValueError("Evaluation settings differ from source run")
    for name, frame in [("close", close), ("volume", volume)]:
        if (
            hashlib.sha256(frame.to_csv().encode()).hexdigest()
            != source_settings["data_sha256"][name]
        ):
            raise ValueError("Evaluation panel differs from source run")
    if source_settings["engine"] != getattr(india_engine, "provenance", None):
        raise ValueError("Evaluation engine differs from source run")
    returns = benchmark.pct_change(fill_method=None)
    returns.iloc[0] = 0.0
    report = {
        "metrics": result.metrics,
        "benchmark": net_metrics(returns, split),
        "ic": None,
        "random": None,
        "DSR": None,
        "missing": [],
    }
    scores = pd.DataFrame({at: plan.scores for at, plan in run["plans"].items()}).T
    executions = pd.DataFrame(
        pd.NaT, index=scores.index, columns=scores.columns, dtype="datetime64[ns, UTC]"
    )
    for at in scores.index:
        for t in scores:
            executions.at[at, t] = entry_close(
                at,
                close.index,
                volume[t],
                split_end=close.index[-1],
                remaining_sessions=int((close.index > at).sum()),
            )
    settings = {
        "market": market,
        "split": split,
        "source_run": run["trial_id"],
        "benchmark_sha256": hashlib.sha256(benchmark.to_csv().encode()).hexdigest(),
        "policy": asdict(policy),
    }
    try:
        labels = five_session_labels(scores, executions, close, split=split)
        ic = original_rank_ic(scores, labels, vibe_root=vibe_root)
        report["ic"] = ic
        ledger.record(
            trial_prefix + ":IC",
            kind="IC",
            settings={**settings, "source_sha256": ic["source_sha256"]},
            status="complete",
            metrics={"defined_intervals": ic["defined_intervals"]},
        )
    except Exception as exc:
        ledger.record(
            trial_prefix + ":IC",
            kind="IC",
            settings=settings,
            status="failed",
            error=type(exc).__name__,
        )
        raise
    if random_candidates is not None:
        if max_attempts is None:
            raise ValueError("Explicit timing-null feasibility budget required")
        trades = result.trades.set_index("trade_id")
        if trades.empty or (trades.duration < 2).any():
            raise ValueError("Matched null requires completed multi-close trades")
        try:
            schedules = random_timing_schedules(
                trades,
                close.index,
                random_candidates,
                max_attempts=max_attempts,
                initial_entries=random_initial_entries,
                mixing_sweeps=random_mixing_sweeps,
                cooldown_decisions=random_cooldown_decisions,
                cooldown_steps=random_cooldown_steps,
            )
        except (ValueError, RuntimeError) as exc:
            ledger.record(
                trial_prefix + ":random_batch",
                kind="random_schedule",
                settings={
                    **settings,
                    "candidate_indices": random_candidates,
                    "max_attempts": max_attempts,
                    "initial_entries": random_initial_entries,
                    "mixing_sweeps": random_mixing_sweeps,
                    "cooldown_steps": random_cooldown_steps,
                    "cooldown_decisions": (
                        list(random_cooldown_decisions)
                        if random_cooldown_decisions is not None
                        else None
                    ),
                    "seeds": list(range(42, 242)),
                },
                status="failed",
                error=type(exc).__name__,
            )
            for seed in range(42, 242):
                ledger.record(
                    trial_prefix + ":random:" + str(seed),
                    kind="random",
                    settings={
                        **settings,
                        "seed": seed,
                        "batch": trial_prefix + ":random_batch",
                    },
                    status="not_run",
                )
            raise
        nulls = []
        for seed, schedule in zip(range(42, 242), schedules):
            if "resize_path" in trades:
                schedule["resize_path"] = schedule.trade_id.map(trades.resize_path)
            trial = trial_prefix + ":random:" + str(seed)
            config = {
                **settings,
                "seed": seed,
                "max_attempts": max_attempts,
                "candidate_indices": random_candidates,
                "sampler": schedule.attrs.get("sampler", {"method": "rejection"}),
                "initial_entries": random_initial_entries,
                "cooldown_steps": random_cooldown_steps,
                "cooldown_decisions": (
                    list(random_cooldown_decisions)
                    if random_cooldown_decisions is not None
                    else None
                ),
                "schedule_sha256": hashlib.sha256(
                    schedule.to_csv().encode()
                ).hexdigest(),
            }
            try:
                null = price_timing_schedule(
                    schedule,
                    close,
                    volume,
                    accounting={
                        "market": market,
                        "split": split,
                        "policy": policy,
                        "india_engine": india_engine,
                    },
                )
                ledger.record(
                    trial,
                    kind="random",
                    settings=config,
                    status="complete",
                    metrics=null.metrics,
                )
                nulls.append(null)
            except (ValueError, RuntimeError) as exc:
                ledger.record(
                    trial,
                    kind="random",
                    settings=config,
                    status="failed",
                    error=type(exc).__name__,
                )
                nulls.append(None)
        if all(n is not None for n in nulls):
            report["random"] = nulls
        else:
            report["missing"].append("Incomplete 200-run random distribution")
    else:
        report["missing"].append("Predeclared timing-null candidates")
    if dsr_trials is not None:
        config = {
            **settings,
            "effective_trials": effective_trials,
            "dependence_assumption": dependence_assumption,
            "ledger_complete": ledger_complete,
            "trial_history": dsr_trials.to_dict(orient="records"),
        }
        try:
            dsr = deflated_sharpe(
                result.daily.net_return,
                dsr_trials,
                effective_trials=effective_trials,
                dependence_assumption=dependence_assumption or "",
                ledger_complete=ledger_complete,
            )
            report["DSR"] = dsr
            ledger.record(
                trial_prefix + ":DSR",
                kind="DSR",
                settings=config,
                status="complete",
                metrics=dsr,
            )
        except (ValueError, TypeError) as exc:
            # Do not serialize invented NaN trial results into the audit settings.
            config["trial_history_sha256"] = hashlib.sha256(
                dsr_trials.to_csv().encode()
            ).hexdigest()
            config.pop("trial_history")
            ledger.record(
                trial_prefix + ":DSR",
                kind="DSR",
                settings=config,
                status="failed",
                error=type(exc).__name__,
            )
            raise
    else:
        report["missing"].append("Full trial history and explicit DSR assumptions")
    return report


def run_all_drop_one(strategy: str, *, run_arguments: dict, trial_prefix: str) -> dict:
    """Run frozen baseline plus every predictive-indicator deletion, without tuning.

    Args: strategy is the fixed v2 ID; run_arguments has build_and_account inputs
        except strategy/variant/trial_id. Returns every variant or None on failure;
        the shared ledger preserves all failures. Stops/costs/sizing remain fixed.
    """
    from src.india_week3_ablation import COMPONENTS

    outputs = {}
    for variant in ["baseline", *("drop:" + name for name in COMPONENTS[strategy])]:
        try:
            outputs[variant] = build_and_account(
                strategy=strategy,
                variant=variant,
                trial_id=trial_prefix + ":" + variant,
                **run_arguments
            )
        except (ValueError, RuntimeError):
            outputs[variant] = None
    return outputs
