"""Offline Week 3 evaluation primitives; not a historical backtest runner."""

import numpy as np
import pandas as pd

from src.india_backtest import annualized_sharpe
from src.india_week3_strategies import _time

SPLITS = {
    "train": ("2016-06-01", "2021-12-31"),
    "test": ("2022-01-01", "2025-09-30"),
}


def net_metrics(returns: pd.Series, split: str) -> dict:
    """Reuse daily sample-standard-deviation Sharpe for supplied net returns.

    Args:
        returns: Full audited daily net-return series including cash days; aware
            timestamp index bounded by the selected fixed split. No data is read.
        split: train or test.
    Returns:
        Sharpe and compounded net return. Does not certify calendar completeness,
        costs or provenance; missing/infinite returns fail in the shared helper.
    """
    start, end = (pd.Timestamp(t, tz="UTC") for t in SPLITS[split])
    if not returns.index.is_unique or not returns.index.is_monotonic_increasing:
        raise ValueError("Sorted unique daily returns required")
    for t in returns.index:
        stamp = _time(t).normalize()
        if not start <= stamp <= end:
            raise ValueError("Returns cross fixed split boundary")
    if (returns <= -1).any():
        raise ValueError("Invalid long-only NAV return")
    sharpe = annualized_sharpe(returns)
    return {
        "net_sharpe": sharpe,
        "net_cumulative_return": float((1 + returns).prod() - 1),
    }


def guide_decision(
    *,
    training_entries: int,
    train_sharpe: float,
    test_sharpe: float,
    index_test_sharpe: float,
    random_train: list[float],
    random_test: list[float],
    reports_complete: bool,
) -> str:
    """Apply guide pass marks only after a complete evaluated evidence package.

    Args:
        training_entries: Filled openings in this market's training split.
        train_sharpe/test_sharpe/index_test_sharpe: Audited comparable metrics.
        random_train/random_test: Exactly 200 valid matched-timing null Sharpes.
        reports_complete: IC, ablation and all-trial DSR evidence available.
    Returns:
        NOT EVALUATED, INSUFFICIENT TRAINING ENTRIES, KEEP CANDIDATE or DROP.
        A candidate is not final PM approval; missing evidence never earns KEEP.
    """
    if not isinstance(training_entries, int) or training_entries < 0:
        raise ValueError("Invalid entry count")
    if training_entries < 30:
        return "INSUFFICIENT TRAINING ENTRIES"
    values = [train_sharpe, test_sharpe, index_test_sharpe, *random_train, *random_test]
    if (
        not reports_complete
        or len(random_train) != 200
        or len(random_test) != 200
        or not np.isfinite(values).all()
    ):
        return "NOT EVALUATED"
    passes = (
        test_sharpe > index_test_sharpe
        and sum(train_sharpe > x for x in random_train) >= 180
        and sum(test_sharpe > x for x in random_test) >= 180
    )
    return "KEEP CANDIDATE" if passes else "DROP"


def random_timing_schedules(
    trades: pd.DataFrame,
    sessions: pd.DatetimeIndex,
    allowed_entries: dict,
    *,
    max_attempts: int,
    initial_entries: dict | None = None,
    mixing_sweeps: int = 64,
    cooldown_decisions: pd.DatetimeIndex | None = None,
    cooldown_steps: int = 0,
) -> list[pd.DataFrame]:
    """Generate 200 offline timing nulls preserving filled counts and durations.

    Args:
        trades: Unique trade_id index and ticker, duration (entry counts as 1),
            weight columns. Caller must provide audited within-split real trades.
        sessions: Complete local close calendar for one fixed split, no holdout.
        allowed_entries: trade_id -> permissible session indices, already filtered
            for the original regime stratum, weekly clock and valid input coverage.
            These lists must be defined without inspecting realized returns.
        max_attempts: Explicit rejection budget when no initial schedule is given.
        initial_entries: Optional audited feasible trade_id -> session index.
            Enables independently seeded constraint-preserving Markov chains.
        mixing_sweeps: Fixed relocation/swap sweeps per independent chain. No
            convergence or uniform finite-sample claim follows from this count.
        cooldown_decisions/cooldown_steps: Optional actual decision clock and
            number of strictly earlier decisions required after a ticker exit.
            Requires the anchored sampler; preserves WCR's frozen cooldown.
    Returns:
        Exactly 200 schedules using seeds 42–241, without pricing/returns. Same-name
        order conflicts and more than two post-close slots are rejected. Exits occur at
        the matched duration, not from dynamic strategy stops. No partial result
        or performance-based selection is returned on failure. Anchored chains
        have a uniform invariant measure, but finite mixing is not certified.
    """
    if not sessions.is_unique or not sessions.is_monotonic_increasing:
        raise ValueError("Sorted unique sessions required")
    for t in sessions:
        _time(t)
    if not trades.index.is_unique or max_attempts < 1:
        raise ValueError("Unique trade IDs and positive attempt budget required")
    if set(allowed_entries) != set(trades.index):
        raise ValueError("Candidate entries required for every trade")
    for trade_id, row in trades.iterrows():
        if (
            not np.isfinite(row["duration"])
            or int(row["duration"]) != row["duration"]
            or row["duration"] < 1
            or not 0 < row["weight"] <= 0.5
        ):
            raise ValueError("Invalid duration or weight")
        candidates = allowed_entries[trade_id]
        if not candidates or any(
            not isinstance(i, (int, np.integer))
            or i < 0
            or i + row["duration"] > len(sessions)
            for i in candidates
        ):
            raise ValueError("Invalid candidate session indices")
    if not isinstance(cooldown_steps, int) or cooldown_steps < 0:
        raise ValueError("Nonnegative integer cooldown required")
    if cooldown_steps and (
        initial_entries is None
        or cooldown_decisions is None
        or not cooldown_decisions.is_unique
        or not cooldown_decisions.is_monotonic_increasing
    ):
        raise ValueError(
            "Cooldown requires anchored sampling and a sorted decision clock"
        )
    if initial_entries is not None:
        return _conditioned_timing_schedules(
            trades,
            sessions,
            allowed_entries,
            initial_entries,
            mixing_sweeps,
            cooldown_decisions,
            cooldown_steps,
        )
    results = []
    for seed in range(42, 242):
        rng = np.random.default_rng(seed)
        for _ in range(max_attempts):
            occupied = np.zeros(len(sessions), dtype=int)
            tickers = {}
            rows = []
            valid = True
            for trade_id, row in trades.iterrows():
                start = int(rng.choice(allowed_entries[trade_id]))
                end = start + int(row["duration"])
                own = tickers.setdefault(
                    row["ticker"], np.zeros(len(sessions), dtype=bool)
                )
                # Exits release their portfolio slot before replacement buys.
                # Same-ticker execution endpoints remain exclusive: the ledger
                # rejects two orders for one ticker at the same close.
                if (occupied[start : end - 1] >= 2).any() or own[start:end].any():
                    valid = False
                    break
                occupied[start : end - 1] += 1
                own[start:end] = True
                rows.append(
                    {
                        "trade_id": trade_id,
                        "ticker": row["ticker"],
                        "weight": row["weight"],
                        "duration": int(row["duration"]),
                        "entry": sessions[start],
                        "exit": sessions[end - 1],
                    }
                )
            if valid:
                results.append(pd.DataFrame(rows))
                break
        else:
            raise ValueError(
                f"Infeasible or rejection budget exhausted at seed {seed}; "
                "no partial baseline; exhaustion does not prove infeasibility"
            )
    return results


def _conditioned_timing_schedules(
    trades,
    sessions,
    allowed,
    initial,
    sweeps,
    cooldown_decisions=None,
    cooldown_steps=0,
):
    """Randomize a feasible placement using symmetric moves without return inputs.

    Args: validated trades/calendar/candidates, initial index mapping and positive
        fixed sweeps, optional frozen cooldown and original decision clock.
        Returns 200 schedules with movement diagnostics in attrs.
        Single-site uniform proposals and symmetric pair-start swaps satisfy
        detailed balance for the uniform feasible-schedule measure. Independent
        chains share a starting state; disconnected components/finite mixing can
        limit exploration. Neither returns nor a Sharpe target select moves.
    """
    if set(initial) != set(trades.index) or not isinstance(sweeps, int) or sweeps < 1:
        raise ValueError("Complete initial placement and positive sweeps required")
    ids = list(trades.index)
    durations = trades.duration.to_numpy(dtype=int)
    tickers = trades.ticker.tolist()
    choices = [np.array(sorted(set(allowed[t])), dtype=int) for t in ids]
    support = [set(c) for c in choices]
    starts = np.array([initial[t] for t in ids])
    if any(not isinstance(x, (int, np.integer)) for x in starts):
        raise ValueError("Initial entries must be integer indices")
    if any(d < 2 for d in durations) or any(
        s not in c for s, c in zip(starts, support)
    ):
        raise ValueError("Invalid initial placement or matched duration")
    occupancy = np.zeros(len(sessions), dtype=int)
    own = {t: np.zeros(len(sessions), dtype=int) for t in set(tickers)}
    tails = {}
    if cooldown_steps:
        for at in cooldown_decisions:
            _time(at)
        for i, candidates in enumerate(choices):
            for start in candidates:
                exit_at = sessions[start + durations[i] - 1]
                next_decision = cooldown_decisions.searchsorted(exit_at, side="right")
                eligible = int(next_decision) + cooldown_steps
                stop = (
                    len(sessions)
                    if eligible >= len(cooldown_decisions)
                    else int(
                        sessions.searchsorted(
                            cooldown_decisions[eligible], side="right"
                        )
                    )
                )
                tails[i, int(start)] = max(start + durations[i], stop)

    def own_end(i, start):
        return tails[i, int(start)] if cooldown_steps else start + durations[i]

    def mark(i, start, delta):
        end = start + durations[i]
        occupancy[start : end - 1] += delta
        own[tickers[i]][start : own_end(i, start)] += delta

    def fits(i, start):
        end = start + durations[i]
        return not (
            (occupancy[start : end - 1] >= 2).any()
            or own[tickers[i]][start : own_end(i, start)].any()
        )

    for i, start in enumerate(starts):
        if not fits(i, start):
            raise ValueError("Initial schedule violates slot/ticker constraints")
        mark(i, start, 1)
    initial_occupancy = occupancy.copy()
    initial_own = {t: v.copy() for t, v in own.items()}
    results = []
    for seed in range(42, 242):
        rng = np.random.default_rng(seed)
        current = starts.copy()
        occupancy[:] = initial_occupancy
        for ticker, own_occupancy in own.items():
            own_occupancy[:] = initial_own[ticker]
        moved_single = moved_pair = 0
        for _ in range(sweeps):
            for i in rng.permutation(len(ids)):
                old = current[i]
                proposed = int(rng.choice(choices[i]))
                mark(i, old, -1)
                if fits(i, proposed):
                    current[i] = proposed
                    moved_single += int(proposed != old)
                mark(i, current[i], 1)
            order = rng.permutation(len(ids))
            for i, j in zip(order[::2], order[1::2]):
                a, b = current[i], current[j]
                if a == b or b not in support[i] or a not in support[j]:
                    continue
                mark(i, a, -1)
                mark(j, b, -1)
                accepted = fits(i, b)
                if accepted:
                    mark(i, b, 1)
                    accepted = fits(j, a)
                    mark(i, b, -1)
                if accepted:
                    current[i], current[j] = b, a
                    moved_pair += 1
                mark(i, current[i], 1)
                mark(j, current[j], 1)
        result = pd.DataFrame(
            [
                {
                    "trade_id": trade_id,
                    "ticker": tickers[i],
                    "weight": trades.loc[trade_id, "weight"],
                    "duration": int(durations[i]),
                    "entry": sessions[current[i]],
                    "exit": sessions[current[i] + durations[i] - 1],
                }
                for i, trade_id in enumerate(ids)
            ]
        )
        result.attrs["sampler"] = {
            "method": "feasible_symmetric_relocation_and_pair_swap",
            "seed": seed,
            "sweeps": sweeps,
            "single_moves": moved_single,
            "pair_swaps": moved_pair,
            "changed_entries": int((current != starts).sum()),
            "mean_absolute_session_shift": float(np.abs(current - starts).mean()),
            "uniform_invariant_not_certified_finite_mixing": True,
        }
        if cooldown_steps:
            result.attrs["sampler"]["strict_prior_decision_cooldown"] = cooldown_steps
        results.append(result)
    return results


def fill_cost(
    market: str, *, quantity: float, close: float, buy: bool, india_engine=None
) -> dict:
    """Quote execution/cash fees using US guide costs or an injected Vibe engine.

    Args:
        market: US or IN; quantity: positive already-approved execution quantity;
        close: valid execution close; buy: actual cash side.
        india_engine: Caller-supplied pinned original IndiaEquityEngine for IN.
            No engine/model download or duplicate Indian fee formula is provided.
    Returns:
        Fill price and cash commission, with slippage reflected only in price.
        Does not decide lot rounding, cash availability or venue executability.
    """
    if not np.isfinite([quantity, close]).all() or quantity <= 0 or close <= 0:
        raise ValueError("Positive finite fill quantity/price required")
    if market == "US":
        return {"price": close, "commission": quantity * close * 0.001}
    if market != "IN" or india_engine is None:
        raise ValueError("IN requires the pinned original IndiaEquityEngine")
    price = float(india_engine.apply_slippage(close, 1 if buy else -1))
    fee = float(india_engine.calc_commission(quantity, price, 1, is_open=buy))
    if not np.isfinite([price, fee]).all() or price <= 0 or fee < 0:
        raise ValueError("Invalid original engine execution costs")
    return {"price": price, "commission": fee}
