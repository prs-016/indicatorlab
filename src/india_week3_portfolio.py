"""Explicit-order cash/position accounting for the Week 3 offline framework."""

from dataclasses import dataclass
from math import floor

import numpy as np
import pandas as pd

from src.india_week3_evaluation import SPLITS, fill_cost, net_metrics
from src.india_week3_strategies import _time


@dataclass(frozen=True)
class AccountingPolicy:
    """Required execution choices, with no implicit rounding or capital assumptions.

    initial_cash: Positive local-currency capital; quantity_mode: fractional/whole.
    sizing_basis: Must explicitly accept pretrade_nav_fee_inclusive_budget.
    Whole-share buys round down; sales to zero liquidate the exact held quantity.
    Targets allocate cash budgets including entry fees/slippage, so realized
    weights can be below targets. Insufficient cash fails; no hidden leverage.
    """

    initial_cash: float
    quantity_mode: str
    sizing_basis: str

    def __post_init__(self):
        if not np.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("Positive capital required")
        if self.quantity_mode not in {"whole", "fractional"}:
            raise ValueError("Explicit whole/fractional quantity mode required")
        if self.sizing_basis != "pretrade_nav_fee_inclusive_budget":
            raise ValueError("Explicit supported fee-inclusive sizing basis required")


@dataclass
class LedgerResult:
    """Daily accounting, fills, completed openings and split net metrics."""

    daily: pd.DataFrame
    quantities: pd.DataFrame
    fills: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict


def validate_panel(close: pd.DataFrame, volume: pd.DataFrame, split: str) -> None:
    """Validate a supplied split panel before arithmetic; no calendar is inferred.

    Args: close/volume are identically aligned UTC local-close panels; split is
        train/test. Returns None; fails on out-of-split/holdout dates or infinity.
        Callers must separately certify complete venue sessions and provenance.
    """
    if (
        close.empty
        or not close.index.is_unique
        or not close.index.is_monotonic_increasing
        or not close.columns.is_unique
    ):
        raise ValueError("Nonempty sorted unique panel required")
    if not close.index.equals(volume.index) or not close.columns.equals(volume.columns):
        raise ValueError("Close/volume alignment required")
    start, end = (pd.Timestamp(t, tz="UTC") for t in SPLITS[split])
    for timestamp in close.index:
        if not start <= _time(timestamp).normalize() <= end:
            raise ValueError("Panel crosses split boundary")
    if (
        np.isinf(close.to_numpy(dtype=float)).any()
        or np.isinf(volume.to_numpy(dtype=float)).any()
    ):
        raise ValueError("Infinite panel input")
    if (close <= 0).any().any() or (volume < 0).any().any():
        raise ValueError("Invalid prices/quantities")


class PortfolioBook:
    """Incremental form of the existing cash ledger, shared by order replay/builders.

    Args: policy, market and original India engine have account_orders semantics.
    State is local to one split; step accepts one completed close and its causal
    execution orders. A failed step aborts the study; never resume a partial fill.
    """

    def __init__(self, policy: AccountingPolicy, market: str, india_engine=None):
        if market not in {"US", "IN"} or (market == "IN" and india_engine is None):
            raise ValueError("Supported market and India engine required")
        self.last_at = None
        self.policy, self.market, self.india_engine = policy, market, india_engine
        self.cash = self.previous = policy.initial_cash
        self.held, self.openings = {}, {}
        self.fills, self.trades, self.daily, self.quantities = [], [], [], []

    def step(
        self,
        timestamp,
        prices: pd.Series,
        volumes: pd.Series,
        active: pd.DataFrame,
        *,
        i: int,
        remaining: int
    ) -> None:
        """Apply one close using prior decisions; mutate this split's cash/state.

        Prices/volumes must use the validated panel axes. i is its session index;
        remaining includes this close. Returns None; all old ledger failures apply.
        """
        at = _time(timestamp)
        if self.last_at is not None and at <= self.last_at:
            raise ValueError("Ledger closes must advance monotonically")
        for row in active.itertuples():
            if (
                row.execution_at != at
                or _time(row.decision_at) >= at
                or row.ticker not in prices.index
                or not np.isfinite(row.target_weight)
                or not 0 <= row.target_weight <= 0.5
            ):
                raise ValueError("Invalid incremental ledger order")
        policy, market, india_engine = self.policy, self.market, self.india_engine
        cash, previous = self.cash, self.previous
        held, openings = self.held, self.openings
        fills, trades, daily, quantities = (
            self.fills,
            self.trades,
            self.daily,
            self.quantities,
        )
        if any(not np.isfinite(prices[t]) for t in held):
            raise ValueError("Missing held price blocks complete accounting")
        before = cash + sum(q * prices[t] for t, q in held.items())
        deltas = []
        for r in active.itertuples():
            p = prices[r.ticker]
            if not np.isfinite(p):
                raise ValueError("Missing execution price")
            delta = r.target_weight * before - held.get(r.ticker, 0) * p
            if abs(delta) > 1e-9:
                if not np.isfinite(volumes[r.ticker]) or volumes[r.ticker] <= 0:
                    raise ValueError("Nonpositive/missing execution volume")
                deltas.append((delta, r))
        fees = 0.0
        for delta, r in sorted(deltas, key=lambda item: (item[0] > 0, item[1].ticker)):
            ticker, p = r.ticker, prices[r.ticker]
            old = held.get(ticker, 0.0)
            buy = delta > 0
            if buy:
                if old == 0 and remaining < 5:
                    raise ValueError("New entry has fewer than five sessions remaining")
                budget = delta
                if budget > cash + 1e-8:
                    raise ValueError("Insufficient cash; no hidden resizing/leverage")
                # Original cost callback is monotonic in positive trade quantity.
                lo, hi = 0.0, budget / p
                for _ in range(60):
                    q = (lo + hi) / 2
                    quote = fill_cost(
                        market, quantity=q, close=p, buy=True, india_engine=india_engine
                    )
                    if q * quote["price"] + quote["commission"] <= budget:
                        lo = q
                    else:
                        hi = q
                qty = floor(lo + 1e-10) if policy.quantity_mode == "whole" else lo
                if qty <= 1e-12:
                    raise ValueError(
                        "Target cannot purchase a positive permitted quantity"
                    )
            else:
                if market == "IN" and openings[ticker]["entry_i"] == i:
                    raise ValueError("India T+1 forbids same-session delivery exit")
                qty = old if r.target_weight == 0 else min(old, -delta / p)
                if policy.quantity_mode == "whole" and r.target_weight != 0:
                    qty = floor(qty + 1e-10)
                if qty <= 1e-12:
                    raise ValueError(
                        "Resize cannot trade a permitted positive quantity"
                    )
            quote = fill_cost(
                market, quantity=qty, close=p, buy=buy, india_engine=india_engine
            )
            fee, price = quote["commission"], quote["price"]
            cash += (-qty * price if buy else qty * price) - fee
            if cash < -1e-8:
                raise ValueError("Negative cash after original engine fees")
            fees += fee
            new = old + (qty if buy else -qty)
            if old == 0 and buy:
                openings[ticker] = {
                    "trade_id": len(fills),
                    "ticker": ticker,
                    "entry": timestamp,
                    "entry_i": i,
                    "weight": r.target_weight,
                    "resized": False,
                    "resize_path": [],
                    "net_cash": 0.0,
                    "commission_cash": 0.0,
                }
            elif new > 1e-10:
                openings[ticker]["resized"] = True
                openings[ticker]["resize_path"].append(
                    (i - openings[ticker]["entry_i"], r.target_weight)
                )
            openings[ticker]["net_cash"] += (-qty * price if buy else qty * price) - fee
            openings[ticker]["commission_cash"] += fee
            if new <= 1e-10:
                item = openings.pop(ticker)
                trades.append(
                    {**item, "exit": timestamp, "duration": i - item["entry_i"] + 1}
                )
                held.pop(ticker, None)
            else:
                held[ticker] = new
            fills.append(
                {
                    "execution_at": timestamp,
                    "decision_at": r.decision_at,
                    "ticker": ticker,
                    "buy": buy,
                    "quantity": qty,
                    "price": price,
                    "close": p,
                    "commission": fee,
                    "slippage_cash": qty * abs(price - p),
                    "reason": r.reason,
                    "target_weight": r.target_weight,
                }
            )
        if len(held) > 2:
            raise ValueError("More than two holdings")
        nav = cash + sum(q * prices[t] for t, q in held.items())
        if not np.isfinite(nav) or nav <= 0:
            raise ValueError("Invalid NAV")
        daily.append(
            {
                "cash": cash,
                "positions_value": nav - cash,
                "nav": nav,
                "commission": fees,
                "net_return": nav / previous - 1,
            }
        )
        quantities.append({t: held.get(t, 0.0) for t in prices.index})
        previous = nav
        self.cash, self.previous = cash, previous
        self.last_at = at


def account_orders(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    orders: pd.DataFrame,
    *,
    market: str,
    split: str,
    policy: AccountingPolicy,
    india_engine=None
) -> LedgerResult:
    """Account already scheduled causal target orders, sequentially without leverage.

    Args:
        close/volume: Full audited split calendar. Missing held prices fail.
        orders: execution_at, decision_at, ticker, target_weight, reason. Decisions
            must strictly precede fills, including predeclared time exits. Weights
            in [0,.5] target pretrade NAV; unspecified holdings drift. Zero exits.
        market/split/policy: Explicit market, fixed split and capital/rounding.
        india_engine: Pinned original India engine instance (required for IN).
    Returns:
        Daily cash/NAV/returns, quantities, fills, completed trade durations and
        metrics. Starts cash; requires explicit terminal liquidation orders.
        Orders are never deferred, fabricated or silently skipped. Supply the
        kernel's next-eligible-close schedule; failed fills block evaluation.
    """
    validate_panel(close, volume, split)
    if market not in {"US", "IN"} or (market == "IN" and india_engine is None):
        raise ValueError("Supported market and India engine required")
    required = ["execution_at", "decision_at", "ticker", "target_weight", "reason"]
    if not set(required) <= set(orders):
        raise ValueError("Incomplete execution order schema")
    orders = orders.copy()
    for r in orders.itertuples():
        if (
            _time(r.decision_at) >= _time(r.execution_at)
            or r.execution_at not in close.index
        ):
            raise ValueError("Order must follow its decision within the split calendar")
        if (
            r.ticker not in close
            or not np.isfinite(r.target_weight)
            or not 0 <= r.target_weight <= 0.5
        ):
            raise ValueError("Invalid order ticker/target")
    if orders.duplicated(["execution_at", "ticker"]).any():
        raise ValueError("Conflicting same-close orders")
    book = PortfolioBook(policy, market, india_engine)
    for i, timestamp in enumerate(close.index):
        book.step(
            timestamp,
            close.loc[timestamp],
            volume.loc[timestamp],
            orders[orders.execution_at == timestamp],
            i=i,
            remaining=len(close) - i,
        )
    held, daily, quantities, fills, trades = (
        book.held,
        book.daily,
        book.quantities,
        book.fills,
        book.trades,
    )
    if held:
        raise ValueError("Missing explicit split-terminal liquidation")
    daily = pd.DataFrame(daily, index=close.index)
    result = net_metrics(daily.net_return, split)
    result["filled_entries"] = len(trades)
    return LedgerResult(
        daily,
        pd.DataFrame(quantities, index=close.index),
        pd.DataFrame(fills),
        pd.DataFrame(trades),
        result,
    )


def schedule_orders(schedule: pd.DataFrame, sessions: pd.DatetimeIndex) -> pd.DataFrame:
    """Convert a matched-duration timing-null schedule to predeclared ledger orders.

    Args: schedule has trade_id/ticker/weight/entry/exit/duration from the existing
        seeded sampler. Returns entry/exit orders; no predictive signals or stops
        are applied to this conditional timing null.
    """
    rows = []
    for r in schedule.itertuples():
        rows.extend(
            [
                {
                    "execution_at": r.entry,
                    "decision_at": r.entry - pd.Timedelta(nanoseconds=1),
                    "ticker": r.ticker,
                    "target_weight": r.weight,
                    "reason": "predeclared_random_entry",
                },
                {
                    "execution_at": r.exit,
                    "decision_at": r.entry - pd.Timedelta(nanoseconds=1),
                    "ticker": r.ticker,
                    "target_weight": 0.0,
                    "reason": "predeclared_matched_duration",
                },
            ]
        )
        for offset, target in getattr(r, "resize_path", ()):
            if not 0 < offset < r.duration - 1:
                raise ValueError("Resize path must be inside its held interval")
            at = sessions[sessions.get_loc(r.entry) + int(offset)]
            rows.append(
                {
                    "execution_at": at,
                    "decision_at": r.entry - pd.Timedelta(nanoseconds=1),
                    "ticker": r.ticker,
                    "target_weight": target,
                    "reason": "predeclared_matched_resize",
                }
            )
    return pd.DataFrame(
        rows,
        columns=["execution_at", "decision_at", "ticker", "target_weight", "reason"],
    )
