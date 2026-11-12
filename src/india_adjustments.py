"""Audit official-price conversions into a frozen Yahoo adjustment vintage.

No downloads, price filling, portfolio calculations, or factor changes. The
terminal Yahoo ratio defines the chosen vendor vintage; NSE cash actions and
official pre-dividend closes independently reconstruct its earlier changes.
"""

import re

import numpy as np
import pandas as pd

from src.india_data import BACKTEST_END


FACTOR_RTOL = 8 * np.finfo(np.float32).eps  # Yahoo snapshot prices have float32 precision.


def parse_action(subject: str) -> tuple[str, float]:
    """Return (type, cash amount or share multiplier) for an NSE action subject.

    Parameters: subject is the verbatim NSE corporate-action description.
    Returns dividend (including combined special/ordinary amounts), bonus/split
    share multiplier, or nonadjusting buyback. Unknown descriptions raise rather
    than silently treating their effect as zero.
    """
    if "dividend" in subject.lower():
        cash = re.findall(r"\bR(?:s|e)\.?\s*(\d+(?:\.\d+)?)\s*Per\s+Sh", subject, re.I)
        if not cash:
            raise ValueError(f"Unparsed cash distribution: {subject}")
        return "dividend", sum(float(value) for value in cash)
    if "bonus" in subject.lower():
        ratio = re.search(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", subject)
        if not ratio or float(ratio[2]) <= 0:
            raise ValueError(f"Unparsed bonus: {subject}")
        return "shares", 1 + float(ratio[1]) / float(ratio[2])
    if "split" in subject.lower() or "sub-division" in subject.lower():
        amounts = re.findall(r"\bR(?:s|e)\.?\s*(\d+(?:\.\d+)?)", subject, re.I)
        if len(amounts) != 2 or min(map(float, amounts)) <= 0:
            raise ValueError(f"Unparsed subdivision: {subject}")
        return "shares", float(amounts[0]) / float(amounts[1])
    if subject.lower().strip() == "buy back":
        return "nonadjusting_buyback", 1.0
    raise ValueError(f"Unclassified corporate action: {subject}")


def audit_conversion(
    session: str, nominal_close: float, *, terminal_date: str,
    terminal_close: float, terminal_adjusted_close: float,
    events: list[dict], previous_nominal_closes: dict[str, float],
    anchors: list[dict],
) -> dict:
    """Derive one conversion and independently check both sides of a missing day.

    Parameters: session/nominal_close identify the recovered NSE record;
    terminal_date/close/adjusted_close define the frozen Yahoo vintage at a
    pre-cutoff date. events are complete official action metadata through that
    vintage's retrieval date (date/subject). previous_nominal_closes maps each
    relevant pre-cutoff dividend ex-date to its verified NSE previous close.
    anchors contains exactly one verified NSE/Yahoo pair before and after the
    session (date, nominal_close, yahoo_close, yahoo_adjusted_close).
    Returns a ledger entry; adjusted_close is populated only on all checks.
    Missing evidence produces unresolved status, never an estimated replacement.
    Source/hash validation and record extraction are the caller's responsibility.
    """
    result = {"date": session, "nominal_close": nominal_close,
              "verified": False, "adjusted_close": None, "tolerance_rtol": FACTOR_RTOL}
    try:
        day, terminal = pd.Timestamp(session), pd.Timestamp(terminal_date)
        if not day <= terminal <= BACKTEST_END:
            raise ValueError("Conversion/terminal dates exceed the historical cutoff")
        numbers = [nominal_close, terminal_close, terminal_adjusted_close]
        if not np.isfinite(numbers).all() or min(numbers) <= 0:
            raise ValueError("Nonpositive/nonfinite input price")
        if len(anchors) != 2:
            raise ValueError("Two independent NSE/Yahoo anchor dates are required")
        anchors = sorted(anchors, key=lambda a: a["date"])
        left, right = map(lambda a: pd.Timestamp(a["date"]), anchors)
        if not left < day < right <= BACKTEST_END:
            raise ValueError("Anchors must bracket the session within cutoff")
        split_multiplier = 1.0
        dividend_product = 1.0
        checks = []
        seen = set()
        for event in events:
            date = pd.Timestamp(event["date"])
            key = (event["date"], event["subject"])
            if key in seen:
                raise ValueError("Duplicate corporate action")
            seen.add(key)
            kind, value = parse_action(event["subject"])
            if left < date <= right and kind != "nonadjusting_buyback":
                raise ValueError("Action inside anchor bracket; cannot use constant factor")
            if date > day and kind == "shares":
                split_multiplier *= value
            if day < date <= terminal and kind == "dividend":
                previous = previous_nominal_closes.get(str(date.date()))
                if previous is None:
                    raise ValueError(f"Missing independent pre-dividend close: {date.date()}")
                if not np.isfinite(previous) or not 0 < value < previous:
                    raise ValueError("Invalid cash amount or pre-dividend price")
                step = 1 - value / previous
                dividend_product *= step
                checks.append({"ex_date": str(date.date()), "cash_nominal": value,
                               "previous_nominal_close": previous, "step_factor": step})
        terminal_dividend_factor = terminal_adjusted_close / terminal_close
        dividend_factor = terminal_dividend_factor * dividend_product
        total_factor = dividend_factor / split_multiplier
        result.update(
            split_share_multiplier=split_multiplier,
            nominal_to_yahoo_close_factor=1 / split_multiplier,
            terminal_dividend_factor=terminal_dividend_factor,
            preterminal_dividend_product=dividend_product,
            reconstructed_dividend_factor=dividend_factor,
            total_conversion_factor=total_factor, dividend_steps=checks,
            after_terminal_dividend_treatment="Inherited frozen Yahoo terminal ratio; not independently reconstructed from holdout prices",
        )
        anchor_checks = []
        for anchor in anchors:
            n, y, a = [float(anchor[k]) for k in (
                "nominal_close", "yahoo_close", "yahoo_adjusted_close")]
            if not np.isfinite([n, y, a]).all() or min(n, y, a) <= 0:
                raise ValueError("Invalid anchor price")
            split_ok = bool(np.isclose(y / n, 1 / split_multiplier, rtol=FACTOR_RTOL, atol=0))
            dividend_ok = bool(np.isclose(a / y, dividend_factor, rtol=FACTOR_RTOL, atol=0))
            total_ok = bool(np.isclose(a / n, total_factor, rtol=FACTOR_RTOL, atol=0))
            anchor_checks.append({**anchor, "observed_split_factor": y / n,
                                  "observed_dividend_factor": a / y,
                                  "observed_total_factor": a / n,
                                  "split_pass": split_ok, "dividend_pass": dividend_ok,
                                  "total_pass": total_ok})
        result["anchor_checks"] = anchor_checks
        if not all(c[k] for c in anchor_checks for k in ("split_pass", "dividend_pass", "total_pass")):
            raise ValueError("Independent reconstruction disagrees with one or both anchors")
        result.update(verified=True, adjusted_close=nominal_close * total_factor,
                      verification_scope="NSE-action reconstruction and two official anchor checks against frozen Yahoo vintage, within float32 tolerance; not point-in-time or an independent reconstruction of post-terminal Yahoo adjustments")
    except (ValueError, TypeError, OverflowError) as exc:
        result["unresolved_reason"] = str(exc)
    return result
