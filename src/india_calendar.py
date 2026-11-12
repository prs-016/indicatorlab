"""Evidence-aware NSE calendar reconstruction and STREV readiness checks.

An observed vendor calendar never defines exchange sessions. This module does
not fetch data, fill prices, infer closures from 404 responses, or run portfolios.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from src.india_data import BACKTEST_END, BENCHMARK, NSE_STOCKS, _validate_dates


def _source(evidence: dict) -> bool:
    return (
        evidence.get("confirmed") is True
        and urlparse(evidence.get("source_url", "")).hostname in {
            "nsearchives.nseindia.com", "archives.nseindia.com", "www.nseindia.com"}
        and bool(evidence.get("source_date"))
        and bool(evidence.get("source_sha256"))
    )


def reconstruct_calendar(
    start: str, end: str, *, annual_rules: dict[int, dict],
    overrides: list[dict],
) -> pd.DataFrame:
    """Return every civil date's session/closure/unverifiable classification.

    Parameters: start/end bound the pre-cutoff audit; annual_rules maps each
    year to holidays plus source URL/date/hash/confirmed status. Weekdays are
    regular sessions and weekends closures only within evidenced annual rules.
    Overrides explicitly reopen Muhurat/weekend sessions or amend holidays;
    unconfirmed/missing evidence becomes unverifiable, never an assumed closure.
    Returns a date-indexed calendar with reason and provenance. Caller must
    audit the completeness of amendments; this function cannot prove absence
    of undiscovered circulars from a list of sources.
    """
    dates = pd.date_range(start, end)
    _validate_dates(dates)
    if dates.empty or dates[-1] > BACKTEST_END:
        raise ValueError("Calendar range must be nonempty and end by 2024-12-31")
    rows = []
    for date in dates:
        rule = annual_rules.get(date.year, {})
        if not _source(rule):
            status, reason = "unverifiable", "annual_rule_evidence_missing"
        elif date.strftime("%Y-%m-%d") in rule.get("holidays", []):
            status, reason = "closure", "annual_trading_holiday"
        elif date.day_of_week >= 5:
            status, reason = "closure", "regular_weekend"
        else:
            status, reason = "session", "regular_weekday"
        rows.append({"date": date, "status": status, "reason": reason,
                     "source_url": rule.get("source_url"),
                     "source_date": rule.get("source_date"),
                     "source_sha256": rule.get("source_sha256")})
    calendar = pd.DataFrame(rows).set_index("date")
    seen = set()
    for override in overrides:
        date = pd.Timestamp(override["date"])
        if date in seen:
            raise ValueError("Conflicting duplicate calendar overrides")
        seen.add(date)
        if date not in calendar.index:
            raise ValueError("Override lies outside audit range")
        if override["status"] not in {"session", "closure", "unverifiable"}:
            raise ValueError("Invalid override classification")
        status = override["status"] if _source(override) else "unverifiable"
        for key in ("source_url", "source_date", "source_sha256", "reason"):
            calendar.loc[date, key] = override.get(key)
        calendar.loc[date, "status"] = status
    return calendar


@dataclass(frozen=True)
class CalendarAudit:
    """Comparison outputs; readiness includes evidence and complete stock data."""

    discrepancies: pd.DataFrame
    lookbacks: pd.DataFrame
    schedule: pd.DataFrame
    summary: dict


def audit_calendar(
    calendar: pd.DataFrame, histories: dict[str, pd.DataFrame], *,
    evaluation_start: str = "2021-01-04", lookback: int = 21,
    amendment_coverage_confirmed: bool = False,
) -> CalendarAudit:
    """Compare expected sessions with nine histories and audit timing, not returns.

    Parameters: calendar is the complete civil-date reconstruction; histories
    contains exactly the eight NSE equities and ^NSEI, with lowercase close and
    stock volume. evaluation_start fixes warm-up selection; lookback is 21 for
    original STREV (other values are rejected). amendment_coverage_confirmed
    is an explicit externally reviewed evidence-completeness gate, not inferred
    from agreement with vendor data. Returns discrepancies, exact lag endpoints,
    W-FRI signal/next-session candidates, and an explicit readiness decision.
    """
    _validate_dates(calendar.index)
    if (calendar.empty or calendar.index.max() > BACKTEST_END
            or not calendar.index.equals(pd.date_range(calendar.index.min(), calendar.index.max()))):
        raise ValueError("Require a contiguous, pre-cutoff civil-date calendar")
    if lookback != 21:
        raise ValueError("Original academic_strev uses 21 sessions")
    if set(histories) != {*NSE_STOCKS, BENCHMARK}:
        raise ValueError("Expected exactly eight NSE stocks and ^NSEI")
    if not calendar.status.isin(["session", "closure", "unverifiable"]).all():
        raise ValueError("Unknown calendar status")
    start = pd.Timestamp(evaluation_start)
    if start not in calendar.index or calendar.loc[start, "status"] != "session":
        raise ValueError("Evaluation start must be a verified expected session")
    sessions = calendar.index[calendar.status.eq("session")]
    prior = sessions[sessions < start]
    warmup = prior[-lookback:]
    required = warmup.append(sessions[sessions >= start])
    records = []
    for day in calendar.index[calendar.status.eq("unverifiable")]:
        records.append({"date": day, "symbol": "ALL", "issue": "unverifiable_calendar_date"})
    for symbol, frame in histories.items():
        _validate_dates(frame.index)
        if len(frame) and frame.index.max() > BACKTEST_END:
            raise ValueError("Input history exceeds the cutoff")
        if "close" not in frame or (symbol != BENCHMARK and "volume" not in frame):
            raise ValueError("Missing required price/volume field")
        for day in required:
            if day not in frame.index:
                records.append({"date": day, "symbol": symbol, "issue": "missing_session_record"})
                continue
            value = frame.loc[day, "close"]
            if not np.isfinite(value) or value <= 0:
                records.append({"date": day, "symbol": symbol, "issue": "invalid_or_missing_close"})
            if symbol != BENCHMARK:
                volume = frame.loc[day, "volume"]
                if not np.isfinite(volume) or volume < 0:
                    records.append({"date": day, "symbol": symbol, "issue": "invalid_or_missing_volume"})
        # Ignore earlier history outside the required warm-up, but never silently
        # remove supplied rows on confirmed closures within the audited range.
        if len(required):
            scope = frame.loc[required.min():calendar.index.max()]
            for day in scope.index.intersection(calendar.index[calendar.status.eq("closure")]):
                records.append({"date": day, "symbol": symbol, "issue": "record_on_confirmed_closure"})
    discrepancy = pd.DataFrame(records, columns=["date", "symbol", "issue"])
    lag_rows = []
    for day in sessions[sessions >= start]:
        position = sessions.get_loc(day)
        lag = sessions[position - lookback] if position >= lookback else pd.NaT
        for symbol in NSE_STOCKS:
            frame = histories[symbol]
            supplied = frame.index[frame.index <= day]
            supplied_lag = supplied[-(lookback + 1)] if day in frame.index and len(supplied) > lookback else pd.NaT
            lag_rows.append({"date": day, "symbol": symbol,
                             "expected_lag_date": lag, "supplied_lag_date": supplied_lag,
                             "clock_matches": pd.notna(lag) and lag == supplied_lag,
                             "endpoint_records_present": day in frame.index and lag in frame.index})
    eval_dates = sessions[sessions >= start]
    signals = pd.Series(eval_dates, index=eval_dates).groupby(eval_dates.to_period("W-FRI")).last()
    schedule = []
    for signal in signals:
        later = eval_dates[eval_dates > signal]
        next_date = later[0] if len(later) else pd.NaT
        complete = pd.notna(next_date)
        if complete:
            for symbol in NSE_STOCKS:
                frame = histories[symbol]
                complete = bool(complete and next_date in frame.index)
                if complete:
                    complete = bool(pd.notna(frame.loc[next_date, "close"])
                                    and frame.loc[next_date, "close"] > 0
                                    and pd.notna(frame.loc[next_date, "volume"])
                                    and frame.loc[next_date, "volume"] > 0)
        schedule.append({"signal_date": signal, "next_expected_session": next_date,
                         "all_eight_records_positive_volume": complete,
                         "status": "terminal_no_execution" if pd.isna(next_date) else "candidate_only_not_a_trade"})
    lookbacks = pd.DataFrame(lag_rows)
    warmup_ok = len(warmup) == lookback
    passed = bool(amendment_coverage_confirmed and warmup_ok and discrepancy.empty
                  and not calendar.status.eq("unverifiable").any()
                  and lookbacks.clock_matches.all())
    summary = {
        "backtest_ready": passed, "calendar_certified": passed,
        "amendment_coverage_confirmed": amendment_coverage_confirmed,
        "warmup_sessions": len(warmup), "warmup_complete": warmup_ok,
        "warmup_start": str(warmup.min().date()) if len(warmup) else None,
        "warmup_end": str(warmup.max().date()) if len(warmup) else None,
        "evaluation_start": str(start.date()),
        "expected_evaluation_sessions": len(eval_dates),
        "expected_sessions_by_year": {str(y): int((eval_dates.year == y).sum()) for y in sorted(set(eval_dates.year))},
        "discrepancy_count": len(discrepancy),
        "unverifiable_calendar_dates": int(calendar.status.eq("unverifiable").sum()),
        "lookback_clock_mismatches": int((~lookbacks.clock_matches).sum()),
        "no_portfolio_backtest_executed": True,
    }
    return CalendarAudit(discrepancy, lookbacks, pd.DataFrame(schedule), summary)


def write_certified_dataset(
    calendar: pd.DataFrame, histories: dict[str, pd.DataFrame], destination: str | Path,
    *, parent_manifest: str | Path, evaluation_start: str = "2021-01-04",
    amendment_coverage_confirmed: bool = False,
) -> Path:
    """Write a new bounded research version only if all calendar/data checks pass.

    Parameters: calendar/histories are audited again; destination must be new;
    parent_manifest supplies immutable provenance; evaluation_start and the
    explicit amendment evidence gate control readiness. Returns new manifest
    path. Any failed check raises before a dataset directory is created.
    """
    audit = audit_calendar(calendar, histories, evaluation_start=evaluation_start,
                           amendment_coverage_confirmed=amendment_coverage_confirmed)
    if not audit.summary["calendar_certified"]:
        raise ValueError("Calendar/data certification failed; no certified dataset written")
    parent_manifest = Path(parent_manifest)
    parent_sha = hashlib.sha256(parent_manifest.read_bytes()).hexdigest()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "derived").mkdir()
    sessions = calendar.index[calendar.status.eq("session")]
    start = pd.Timestamp(audit.summary["warmup_start"])
    dates = sessions[sessions >= start]
    for symbol, frame in histories.items():
        frame.loc[dates].to_csv(destination / f"derived/{symbol}.csv", index_label="Date")
    calendar.to_csv(destination / "calendar.csv", index_label="Date")
    manifest = {**audit.summary, "parent_manifest": str(parent_manifest.resolve()),
                "parent_manifest_sha256": parent_sha,
                "selection": "Exactly 21 verified warm-up sessions plus evaluation sessions; parent preserved",
                "files_sha256": {str(f.relative_to(destination)): hashlib.sha256(f.read_bytes()).hexdigest()
                                 for f in destination.rglob("*.csv")}}
    path = destination / "research_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path
