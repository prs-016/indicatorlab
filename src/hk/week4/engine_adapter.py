"""Fast event scheduling around Vibe's actual equity engine transaction methods.

Import only inside an isolated Vibe process: both projects own a src package.
No broker module or order API is used. Positions, fees, slippage, lot rounding,
fills, cash and completed trade records are Vibe backtest objects.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from decimal import ROUND_CEILING, Decimal

import numpy as np
import pandas as pd
from backtest.engines.global_equity import GlobalEquityEngine


class ResearchEquityEngine(GlobalEquityEngine):
    """Reuse Vibe costs with dated HK duty and statutory whole-dollar rounding."""

    def calc_commission(self, size, price, direction, is_open):
        """Return original engine fees with HK duty date and rounding corrections."""
        if self.market != "hk":
            return super().calc_commission(size, price, direction, is_open)
        day = str(self._bar_ts.date())
        self.hk_stamp_tax = 0.0013 if "2021-08-01" <= day <= "2023-11-16" else 0.001
        total = super().calc_commission(size, price, direction, is_open)
        duty = (
            Decimal(str(size)) * Decimal(str(price)) * Decimal(str(self.hk_stamp_tax))
        )
        return (
            total - float(duty) + float(duty.to_integral_value(rounding=ROUND_CEILING))
        )


def simulate(
    data: dict,
    plans: list[dict],
    market: str,
    initial_cash: float,
    lots: dict[str, int],
    start: int,
    end: int,
    *,
    detail=False,
) -> dict:
    """Execute a frozen schedule with original Vibe fills and no silent rejections.

    Open/close orders use this bar's observable open. Cash dividends accrue only
    to holdings carried into their ex-date. Daily marks are the identical
    long-only, unlevered cash-plus-shares identity used by the engine.
    """
    config = {
        "initial_cash": initial_cash,
        "leverage": 1.0,
        "position_adjustment": "hold",
        "slippage_us": 0.001,
        "hk_lot_sizes": lots,
    }
    engine = ResearchEquityEngine(config, market="hk" if market == "HK" else "us")
    codes, dates = data["codes"], data["dates"]
    opens, closes, volumes, dividends = (
        data[key] for key in ("open", "close", "volume", "dividend")
    )
    frames = data["frames"]
    col = {code: index for index, code in enumerate(codes)}
    entries, exits = {}, {}
    for plan in plans:
        if (
            not start <= plan["entry"] < plan["exit"] <= end
            or plan["symbol"] not in col
        ):
            raise ValueError("Schedule crosses a split or has an invalid instrument")
        entries.setdefault(plan["entry"], []).append(plan)
        exits.setdefault(plan["exit"], []).append(plan)
    equity = np.full(end - start + 1, initial_cash, dtype=float)
    exposure = np.zeros_like(equity)
    dividend_cash = 0.0
    marks = np.full(len(codes), np.nan)
    for index in range(start, end + 1):
        stamp = dates[index]
        engine._bar_idx, engine._bar_ts = index, stamp
        for code, position in list(engine.positions.items()):
            cash = float(dividends[index, col[code]]) * position.size
            engine.capital += cash
            dividend_cash += cash
        # All sizing uses prices observed at this open, never today's close.
        opening_equity = engine.capital
        for code, position in engine.positions.items():
            price = opens[index, col[code]]
            if not np.isfinite(price) or price <= 0:
                price = marks[col[code]]
            opening_equity += position.size * price
        for plan in sorted(exits.get(index, []), key=lambda item: item["symbol"]):
            code, column = plan["symbol"], col[plan["symbol"]]
            if code not in engine.positions:
                raise ValueError("Scheduled exit has no corresponding executed entry")
            if not (
                math.isfinite(opens[index, column])
                and opens[index, column] > 0
                and volumes[index, column] > 0
            ):
                raise ValueError("Scheduled exit is not executable")
            engine._active_symbol = code
            fill = engine._execution_price(float(opens[index, column]), -1)
            engine._close_position(code, fill, stamp, plan.get("reason", "scheduled"))
        for plan in sorted(entries.get(index, []), key=lambda item: item["symbol"]):
            code, column = plan["symbol"], col[plan["symbol"]]
            if not (
                math.isfinite(opens[index, column])
                and opens[index, column] > 0
                and volumes[index, column] > 0
            ):
                raise ValueError("Scheduled entry is not executable")
            order = engine._plan_open_order(
                code, float(plan["weight"]), frames[code], stamp, opening_equity
            )
            if order is None or order.cost > engine.capital + 1e-7:
                raise ValueError(
                    "A baseline/strategy trade could not execute at its declared size"
                )
            engine._execute_open_order(order, stamp)
        finite = np.isfinite(closes[index]) & (closes[index] > 0)
        marks[finite] = closes[index, finite]
        invested = sum(
            position.size * marks[col[code]]
            for code, position in engine.positions.items()
        )
        value = engine.capital + invested
        if not math.isfinite(value) or value <= 0 or engine.capital < -1e-6:
            raise ValueError("Invalid portfolio accounting")
        equity[index - start] = value
        exposure[index - start] = invested / value
    if engine.positions or len(engine.trades) != len(plans):
        raise ValueError(
            "Executed trade count/holding duration differs from the frozen schedule"
        )
    expected = sorted(
        (plan["symbol"], plan["entry"], plan["exit"] - plan["entry"]) for plan in plans
    )
    actual = sorted(
        (
            trade.symbol,
            int(dates.get_loc(trade.entry_time)),
            int(dates.get_loc(trade.exit_time) - dates.get_loc(trade.entry_time)),
        )
        for trade in engine.trades
    )
    if expected != actual:
        raise ValueError("Realized trade timing failed its invariant")
    returns = np.diff(np.r_[initial_cash, equity]) / np.r_[initial_cash, equity[:-1]]
    result = {
        "returns": returns,
        "equity": equity,
        "entries": len(engine.trades),
        "mean_exposure": float(exposure.mean()),
        "commission": float(sum(trade.commission for trade in engine.trades)),
        "dividend_cash": dividend_cash,
        "lot_assumptions": engine.lot_assumptions,
        "rejections": dict(engine.plan_rejections),
    }
    if detail:
        result["trades"] = [
            {
                key: str(value) if isinstance(value, pd.Timestamp) else value
                for key, value in asdict(trade).items()
            }
            for trade in engine.trades
        ]
    return result


def random_schedule(
    plans: list[dict], data: dict, start: int, end: int, rng
) -> list[dict]:
    """Construct nonoverlapping random timing with exactly preserved trade durations.

    Uniform stars-and-bars gaps avoid rejection failure for dense schedules.
    Listing and actual execution availability bound each symbol's sampling space.
    """
    result = []
    for column, code in enumerate(data["codes"]):
        original = [plan for plan in plans if plan["symbol"] == code]
        if not original:
            continue
        valid = (
            np.isfinite(data["open"][:, column])
            & (data["open"][:, column] > 0)
            & (data["volume"][:, column] > 0)
        )
        possible = np.flatnonzero(valid[start : end + 1]) + start
        lower, upper = int(possible[0]), int(possible[-1])
        durations = [plan["exit"] - plan["entry"] for plan in original]
        free = upper - lower - sum(durations)
        if free < 0:
            raise ValueError(
                "Cannot preserve all holding durations in this instrument's trading history"
            )
        for _attempt in range(1000):
            ordered = [original[int(item)] for item in rng.permutation(len(original))]
            separators = np.sort(
                rng.choice(free + len(original), size=len(original), replace=False)
            )
            gaps = np.diff(np.r_[-1, separators, free + len(original)]) - 1
            cursor, candidate = lower, []
            for offset, plan in enumerate(ordered):
                entry = cursor + int(gaps[offset])
                exit_ = entry + plan["exit"] - plan["entry"]
                if not valid[entry] or not valid[exit_]:
                    break
                candidate.append(
                    plan | {"entry": entry, "exit": exit_, "reason": "random_timing"}
                )
                cursor = exit_
            else:
                result.extend(candidate)
                break
        else:
            raise ValueError("No executable timing schedule after 1000 attempts")
    return result
