"""IC, matched-timing pricing, ablation execution and explicit-assumption DSR."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from src.india_vibe_bridge import _IC_WORKER
from src.india_week3_evaluation import random_timing_schedules
from src.india_week3_portfolio import account_orders, schedule_orders
from src.india_week3_strategies import _time


def five_session_labels(
    scores: pd.DataFrame, executions: pd.DataFrame, close: pd.DataFrame, *, split: str
) -> pd.DataFrame:
    """Build five-local-session IC labels from executable closes, censoring the end.

    Args: scores and per-name execution timestamps have identical axes; close is
        the audited split-only panel. Returns labels with NaN for missing execution,
        horizon or endpoint; no interpolation or interval crossing is permitted.
    """
    if not scores.index.equals(executions.index) or not scores.columns.equals(
        executions.columns
    ):
        raise ValueError("Scores/executions must align")
    if not close.index.is_unique or not close.index.is_monotonic_increasing:
        raise ValueError("Sorted unique close calendar required")
    from src.india_week3_evaluation import SPLITS

    start, end = (pd.Timestamp(t, tz="UTC") for t in SPLITS[split])
    for timestamp in close.index:
        if not start <= _time(timestamp).normalize() <= end:
            raise ValueError("IC price panel crosses fixed split")
    labels = pd.DataFrame(np.nan, index=scores.index, columns=scores.columns)
    for timestamp in scores.index:
        if not start <= _time(timestamp).normalize() <= end:
            raise ValueError("IC score crosses fixed split")
        for ticker in scores:
            execution = executions.at[timestamp, ticker]
            if pd.isna(execution):
                continue
            execution = _time(execution)
            if execution <= timestamp or execution not in close.index:
                raise ValueError("IC execution must follow its signal on the calendar")
            i = close.index.get_loc(execution)
            if i + 5 >= len(close):
                continue
            values = close[ticker].iloc[i : i + 6]
            if (
                values.isna().any()
                or not np.isfinite(values).all()
                or (values <= 0).any()
            ):
                continue
            labels.at[timestamp, ticker] = values.iloc[-1] / values.iloc[0] - 1
    return labels


def original_rank_ic(
    scores: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    vibe_root: Path,
    python_executable: str = sys.executable,
) -> dict:
    """Run the unchanged original IC worker for the new bounded Week 3 scope.

    Args: exactly aligned scores/labels and explicit original Vibe checkout/Python.
    Returns: Original defined IC series plus source hash; omitted intervals remain
        omitted. Legacy December-2024 bridges/archives are not modified. No factor
        imports, downloads or date-bound widening inside an old runner occurs.
    """
    if (
        not scores.index.equals(labels.index)
        or not scores.columns.equals(labels.columns)
        or not scores.index.is_unique
        or not scores.columns.is_unique
    ):
        raise ValueError("Exactly aligned unique IC axes required")
    for timestamp in scores.index:
        _time(timestamp)
    for frame in [scores, labels]:
        if np.isinf(frame.to_numpy(dtype=float)).any():
            raise ValueError("Infinite IC input")
    agent = Path(vibe_root).resolve() / "agent"
    source = agent / "src/factors/factor_analysis_core.py"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    request = {
        "dates": [t.isoformat() for t in scores.index],
        "columns": list(scores.columns),
        "scores": json.loads(scores.to_json(orient="values", date_format="iso")),
        "returns": json.loads(labels.to_json(orient="values", date_format="iso")),
    }
    child = subprocess.run(
        [str(python_executable), "-I", "-B", "-c", _IC_WORKER, str(agent)],
        input=json.dumps(request, allow_nan=False),
        capture_output=True,
        text=True,
        cwd=agent,
        timeout=60,
        check=False,
    )
    if child.returncode:
        raise RuntimeError(
            "Original Vibe IC worker failed; verify its local dependencies"
        )
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError("IC source changed during calculation")
    payload = json.loads(child.stdout)
    values = pd.Series(
        [row[0] for row in payload["data"]],
        index=pd.to_datetime(payload["index"], utc=True),
        dtype=float,
    )
    if not values.index.isin(scores.index).all():
        raise RuntimeError("Unexpected original IC dates")
    return {
        "ic": values,
        "source_sha256": digest,
        "submitted_intervals": len(scores),
        "defined_intervals": len(values),
    }


def price_random_comparisons(
    trades: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    allowed_entries: dict,
    *,
    max_attempts: int,
    accounting: dict,
    initial_entries: dict | None = None,
    mixing_sweeps: int = 64,
    cooldown_decisions: pd.DatetimeIndex | None = None,
    cooldown_steps: int = 0,
) -> dict:
    """Price all 200 count/duration matched schedules through the same cash ledger.

    Args: completed real/synthetic openings, audited split panel, independently
        prepared weekly/regime candidate indices, explicit sampler budget and
        account_orders keyword arguments. Optional initial_entries/mixing_sweeps
        enable feasible symmetric chains; finite mixing is not certified.
        Optional cooldown clock/steps retain stock-specific WCR re-entry timing.
        Resized trades retain their recorded relative-session target path,
        rather than being treated as single-weight trades. No path is chosen by performance.
    Returns: Every schedule/ledger plus Sharpes and seeds 42–241; failures raise
        without a partial/selected distribution. No source data is read.
    """
    if trades.empty:
        raise ValueError("Nonempty trades required for matched-weight null")
    if (trades.duration < 2).any():
        raise ValueError("Matched-duration pricing requires separate entry/exit closes")
    schedules = random_timing_schedules(
        trades,
        close.index,
        allowed_entries,
        max_attempts=max_attempts,
        initial_entries=initial_entries,
        mixing_sweeps=mixing_sweeps,
        cooldown_decisions=cooldown_decisions,
        cooldown_steps=cooldown_steps,
    )
    results = []
    for schedule in schedules:
        if "resize_path" in trades:
            schedule["resize_path"] = schedule.trade_id.map(trades.resize_path)
        result = price_timing_schedule(schedule, close, volume, accounting=accounting)
        results.append(result)
    return {
        "seeds": list(range(42, 242)),
        "schedules": schedules,
        "results": results,
        "sharpes": [r.metrics["net_sharpe"] for r in results],
    }


def price_timing_schedule(schedule, close, volume, *, accounting):
    """Replay one null through the existing ledger and reconcile exact lifetimes.

    Args: schedule with matched ticker/entry/exit/duration/weight and optional
        resize_path, aligned split close/volume panels and account_orders kwargs.
    Returns: LedgerResult. Missing fills, cash failures or unmatched lifetimes
        raise, never clipping trades or silently resampling based on performance.
    """
    result = account_orders(
        close, volume, schedule_orders(schedule, close.index), **accounting
    )
    actual = result.trades
    if len(actual) != len(schedule):
        raise ValueError("Random schedule failed trade-count/duration reconciliation")
    matched = schedule.merge(
        actual,
        on=["ticker", "entry", "exit"],
        how="outer",
        suffixes=("_expected", "_actual"),
        indicator=True,
        validate="one_to_one",
    )
    if (
        not (matched["_merge"] == "both").all()
        or not (matched.duration_expected == matched.duration_actual).all()
        or not np.allclose(
            matched.weight_expected, matched.weight_actual, rtol=0, atol=0
        )
    ):
        raise ValueError("Random schedule failed trade-count/duration reconciliation")
    if "resize_path" in schedule:
        for expected, actual_path in zip(
            matched.resize_path_expected, matched.resize_path_actual
        ):
            if len(expected) != len(actual_path) or not np.allclose(
                np.asarray(expected), np.asarray(actual_path), rtol=0, atol=1e-14
            ):
                raise ValueError(
                    "Random schedule failed relative resize reconciliation"
                )
    return result


def execute_ablations(
    order_builder,
    removals: dict[str, frozenset[str]],
    *,
    predictive_components: frozenset[str],
    close: pd.DataFrame,
    volume: pd.DataFrame,
    accounting: dict,
) -> dict:
    """Execute an explicit predeclared drop-one matrix via a strategy order builder.

    Args: order_builder(disabled_components) emits complete causal ledger orders;
        removals maps unique trial IDs to exactly one predictive component; the
        allowed component list must be supplied, not inferred from results.
        Shared protective risk/execution/cost components cannot be removed.
    Returns: Baseline and each variant ledger, with entry/return differences.
        Expected execution failures remain recorded as failed trials.
        Component-to-gate/ranking semantics belong in the approved builder; this
        function never edits strategy thresholds or fixed kernel source code.
    """
    if "baseline" in removals:
        raise ValueError("Reserved baseline trial ID")
    for removed in removals.values():
        if (
            len(removed) != 1
            or not removed <= predictive_components
            or removed & {"stop", "execution", "costs", "position_limit", "holdout"}
        ):
            raise ValueError("Ablations remove one declared predictive component only")
    plans = {"baseline": frozenset(), **removals}
    outputs = {}
    for trial_id, disabled in plans.items():
        try:
            orders = order_builder(disabled)
            result = account_orders(close, volume, orders, **accounting)
            outputs[trial_id] = {
                "result": result,
                "status": "complete",
                "error_type": None,
            }
        except (ValueError, RuntimeError) as exc:
            outputs[trial_id] = {
                "result": None,
                "status": "failed",
                "error_type": type(exc).__name__,
            }
    base = outputs["baseline"]["result"]
    for trial_id, item in outputs.items():
        result = item["result"]
        item["disabled"] = sorted(plans[trial_id])
        item["returns_changed"] = (
            None
            if result is None or base is None
            else not result.daily.net_return.equals(base.daily.net_return)
        )
        item["orders_changed"] = (
            None
            if result is None or base is None
            else not result.fills.equals(base.fills)
        )
    return outputs


def ablation_trial_ledger(outputs: dict, *, study_id: str) -> pd.DataFrame:
    """Create trial records including failures for merger with prior research trials.

    Args: outputs from execute_ablations; study_id uniquely identifies strategy,
        market, split, dataset and specification. Returns daily-unit SR records;
        this partial ledger is never automatically declared a full trial history.
    """
    if not study_id.strip():
        raise ValueError("Explicit unique study ID required")
    return pd.DataFrame(
        [
            {
                "trial_id": study_id + ":" + key,
                "status": item["status"],
                "daily_sharpe": (
                    np.nan
                    if item["result"] is None
                    else item["result"].metrics["net_sharpe"] / np.sqrt(252)
                ),
                "disabled": ",".join(item["disabled"]),
                "error_type": item["error_type"],
            }
            for key, item in outputs.items()
        ]
    )


def deflated_sharpe(
    returns: pd.Series,
    trials: pd.DataFrame,
    *,
    effective_trials: float,
    dependence_assumption: str,
    ledger_complete: bool,
) -> dict:
    """Calculate DSR (Bailey/Lopez de Prado 2014, equation 2) with explicit trials.

    Args:
        returns: Selected daily net series; no annualized SR enters the formula.
        trials: Unique trial_id, status and daily_sharpe fields for ALL attempted
            variants, including failures (daily_sharpe unavailable for failures).
        effective_trials: Explicit independent-equivalent count; in [1, attempts].
        dependence_assumption: Required explanation; no hidden correlation fit.
        ledger_complete: Caller attests full research-trial ledger, not just these
            three strategies. False fails; failures are counted, not erased.
    Returns:
        Probability plus daily benchmark SR, moments, counts and assumptions.
        An undefined trial SR prevents empirical variance estimation and fails;
        no zero is invented for failed trials. Serial-dependence effects on the
        selected return series are not corrected by this iid-return approximation.
    """
    if not ledger_complete or not dependence_assumption.strip():
        raise ValueError("Complete all-trial ledger and dependence assumption required")
    if (
        trials.empty
        or trials.trial_id.duplicated().any()
        or trials.trial_id.isna().any()
        or trials.status.isna().any()
    ):
        raise ValueError("Unique documented research trials required")
    if not np.isfinite(effective_trials) or not 1 <= effective_trials <= len(trials):
        raise ValueError("Invalid independent-equivalent trial count")
    values = returns.to_numpy(dtype=float)
    if len(values) < 4 or not np.isfinite(values).all() or np.std(values, ddof=1) == 0:
        raise ValueError("At least four finite nonconstant daily returns required")
    if not np.isfinite(trials.daily_sharpe).all():
        raise ValueError(
            "Unavailable attempted-trial SR: cannot estimate DSR dispersion"
        )
    sr = float(values.mean() / values.std(ddof=1))
    gamma3 = float(skew(values, bias=False))
    gamma4 = float(kurtosis(values, fisher=False, bias=False))
    benchmark = 0.0
    if effective_trials > 1:
        std = float(trials.daily_sharpe.std(ddof=1))
        g = np.euler_gamma
        benchmark = std * (
            (1 - g) * norm.ppf(1 - 1 / effective_trials)
            + g * norm.ppf(1 - 1 / (effective_trials * np.e))
        )
    variance = 1 - gamma3 * sr + (gamma4 - 1) * sr**2 / 4
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError("Undefined DSR sampling variance")
    probability = float(
        norm.cdf((sr - benchmark) * np.sqrt(len(values) - 1) / np.sqrt(variance))
    )
    return {
        "probability": probability,
        "daily_sharpe": sr,
        "daily_benchmark_sharpe": float(benchmark),
        "observations": len(values),
        "skewness": gamma3,
        "pearson_kurtosis": gamma4,
        "attempted_trials": len(trials),
        "effective_trials": effective_trials,
        "dependence_assumption": dependence_assumption,
        "formula_source": "https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf",
        "return_dependence": "iid approximation; not autocorrelation-adjusted",
    }


def evaluate_splits(panels: dict, orders: dict, *, accounting: dict) -> dict:
    """Evaluate supplied train/test orders from cash and compare their benchmarks.

    Args: panels maps train/test to close, volume, benchmark series; orders maps
        the same keys to causal execution orders. accounting provides market,
        explicit policy and optional original India engine. No data is loaded.
    Returns: Per-split ledgers, net metrics, index Sharpe/returns and equal-weight
        buy-and-hold reference. No pass decision without null/ablation/DSR inputs.
    """
    from src.india_week3_evaluation import net_metrics

    if set(panels) != {"train", "test"} or set(orders) != set(panels):
        raise ValueError("Both fixed train and test inputs required")
    outputs = {}
    for split, panel in panels.items():
        result = account_orders(
            panel["close"], panel["volume"], orders[split], split=split, **accounting
        )
        benchmark = panel["benchmark"]
        if (
            not benchmark.index.equals(panel["close"].index)
            or not np.isfinite(benchmark).all()
            or (benchmark <= 0).any()
        ):
            raise ValueError("Complete aligned benchmark required")
        index_returns = benchmark.pct_change(fill_method=None)
        index_returns.iloc[0] = 0.0
        stock = panel["close"]
        if stock.isna().any().any():
            raise ValueError("Equal-weight reference cannot fill missing stock prices")
        wealth = stock.div(stock.iloc[0]).mean(axis=1)
        reference = wealth.pct_change(fill_method=None)
        reference.iloc[0] = 0.0
        outputs[split] = {
            "result": result,
            "benchmark": net_metrics(index_returns, split),
            "benchmark_returns": index_returns,
            "equal_weight_reference": net_metrics(reference, split),
            "reference_convention": "Gross untraded price-series controls; no fictitious reference fees charged",
        }
    return outputs
