"""OFFLINE SYNTHETIC calendar evidence and histories; no real-data backtests."""

import json

import numpy as np
import pandas as pd
import pytest

from src.india_calendar import audit_calendar, reconstruct_calendar, write_certified_dataset
from src.india_data import BENCHMARK, NSE_STOCKS
from src.india_reconciliation import verify_equities


def source(**extra):
    return {"source_url": "https://nsearchives.nseindia.com/content/circulars/SYNTHETIC.pdf",
            "source_date": "2023-12-01", "source_sha256": "0" * 64,
            "confirmed": True, **extra}


@pytest.fixture
def synthetic():
    rules = {2023: source(holidays=["2023-12-25"]),
             2024: source(holidays=["2024-01-22", "2024-01-26"])}
    overrides = [source(date="2024-01-20", status="session", reason="synthetic_live_saturday")]
    calendar = reconstruct_calendar("2023-12-01", "2024-02-29", annual_rules=rules, overrides=overrides)
    sessions = calendar.index[calendar.status.eq("session")]
    frames = {s: pd.DataFrame({"close": 100., "volume": 1000.}, index=sessions)
              for s in (*NSE_STOCKS, BENCHMARK)}
    return calendar, frames


def test_weekend_special_and_holiday_closure_are_distinct(synthetic):
    calendar, frames = synthetic
    assert calendar.loc["2024-01-20", "status"] == "session"
    assert calendar.loc["2024-01-21", "status"] == "closure"
    assert calendar.loc["2024-01-22", "status"] == "closure"
    audit = audit_calendar(calendar, frames, evaluation_start="2024-01-04",
                           amendment_coverage_confirmed=True)
    assert audit.summary["calendar_certified"]
    assert audit.summary["warmup_sessions"] == 21
    assert audit.lookbacks.clock_matches.all()


def test_missing_real_session_blocks_even_with_no_missing_existing_cells(synthetic):
    calendar, frames = synthetic
    for symbol in frames:
        frames[symbol] = frames[symbol].drop(pd.Timestamp("2024-01-20"))
        assert frames[symbol].close.notna().all()
    audit = audit_calendar(calendar, frames, evaluation_start="2024-01-04",
                           amendment_coverage_confirmed=True)
    assert not audit.summary["backtest_ready"]
    gaps = audit.discrepancies[audit.discrepancies.issue.eq("missing_session_record")]
    assert len(gaps) == 9
    assert audit.summary["lookback_clock_mismatches"] > 0
    schedule = audit.schedule.set_index("signal_date")
    row = schedule.loc["2024-01-19"]
    assert row.next_expected_session == pd.Timestamp("2024-01-20")
    assert not row.all_eight_records_positive_volume


def test_muhurat_reopens_a_listed_holiday():
    calendar = reconstruct_calendar("2024-11-01", "2024-11-03",
        annual_rules={2024: source(holidays=["2024-11-01"])},
        overrides=[source(date="2024-11-01", status="session", reason="synthetic_muhurat")])
    assert calendar.loc["2024-11-01", "status"] == "session"
    assert calendar.loc["2024-11-02", "status"] == "closure"


def test_amended_holiday_reopens_old_date_and_closes_new_date():
    calendar = reconstruct_calendar("2023-06-28", "2023-06-29",
        annual_rules={2023: source(holidays=["2023-06-28"])}, overrides=[
            source(date="2023-06-28", status="session", reason="holiday_rescheduled"),
            source(date="2023-06-29", status="closure", reason="new_holiday")])
    assert calendar.status.tolist() == ["session", "closure"]


def test_missing_evidence_is_unverifiable_not_an_inferred_closure():
    calendar = reconstruct_calendar("2024-01-05", "2024-01-06", annual_rules={}, overrides=[])
    assert calendar.status.eq("unverifiable").all()
    calendar = reconstruct_calendar("2024-01-05", "2024-01-06",
        annual_rules={2024: source(holidays=[])}, overrides=[
            source(date="2024-01-06", status="session", confirmed=False)])
    assert calendar.loc["2024-01-06", "status"] == "unverifiable"


def test_evidence_completeness_is_not_inferred_from_vendor_agreement(synthetic):
    calendar, frames = synthetic
    audit = audit_calendar(calendar, frames, evaluation_start="2024-01-04")
    assert audit.discrepancies.empty
    assert not audit.summary["calendar_certified"]


def test_missing_close_benchmark_and_volume_are_reported(synthetic):
    calendar, frames = synthetic
    frames[NSE_STOCKS[0]].loc["2024-01-10", "close"] = np.nan
    frames[NSE_STOCKS[1]].loc["2024-01-10", "volume"] = np.nan
    frames[BENCHMARK].loc["2024-01-10", "close"] = np.nan
    audit = audit_calendar(calendar, frames, evaluation_start="2024-01-04",
                           amendment_coverage_confirmed=True)
    assert len(audit.discrepancies) == 3
    assert not audit.summary["backtest_ready"]


def test_prices_on_confirmed_closure_are_not_silently_removed(synthetic):
    calendar, frames = synthetic
    frames[NSE_STOCKS[0]].loc[pd.Timestamp("2024-01-22")] = [100., 1000.]
    frames[NSE_STOCKS[0]] = frames[NSE_STOCKS[0]].sort_index()
    audit = audit_calendar(calendar, frames, evaluation_start="2024-01-04",
                           amendment_coverage_confirmed=True)
    assert "record_on_confirmed_closure" in audit.discrepancies.issue.tolist()
    assert pd.Timestamp("2024-01-22") in frames[NSE_STOCKS[0]].index


def test_lookback_warmup_and_execution_have_no_off_by_one(synthetic):
    calendar, frames = synthetic
    audit = audit_calendar(calendar, frames, evaluation_start="2024-01-04",
                           amendment_coverage_confirmed=True)
    expected = calendar.index[calendar.status.eq("session")]
    day = pd.Timestamp("2024-01-04")
    lag = expected[expected.get_loc(day) - 21]
    row = audit.lookbacks.iloc[0]
    assert row.expected_lag_date == lag
    assert audit.summary["warmup_start"] == str(lag.date())
    assert (audit.schedule.next_expected_session.dropna().to_numpy()
            > audit.schedule.signal_date.iloc[:-1].to_numpy()).all()


def test_certified_version_written_only_after_all_checks_pass(synthetic, tmp_path):
    calendar, frames = synthetic
    parent = tmp_path / "parent.json"
    parent.write_text("{}")
    with pytest.raises(ValueError, match="no certified dataset"):
        write_certified_dataset(calendar, frames, tmp_path / "blocked", parent_manifest=parent,
                                evaluation_start="2024-01-04")
    assert not (tmp_path / "blocked").exists()
    path = write_certified_dataset(calendar, frames, tmp_path / "passed", parent_manifest=parent,
                                   evaluation_start="2024-01-04", amendment_coverage_confirmed=True)
    manifest = json.loads(path.read_text())
    assert manifest["calendar_certified"]
    assert len(manifest["files_sha256"]) == 10
    with pytest.raises(FileExistsError):
        write_certified_dataset(calendar, frames, tmp_path / "passed", parent_manifest=parent,
                                evaluation_start="2024-01-04", amendment_coverage_confirmed=True)


def test_insufficient_warmup_cannot_certify(synthetic):
    calendar, frames = synthetic
    audit = audit_calendar(calendar.loc["2024-01-01":], frames,
                           evaluation_start="2024-01-04", amendment_coverage_confirmed=True)
    assert not audit.summary["warmup_complete"]
    assert not audit.summary["calendar_certified"]


def test_calendar_refuses_holdout_or_changed_factor_lookback(synthetic):
    with pytest.raises(ValueError):
        reconstruct_calendar("2024-12-31", "2025-10-01", annual_rules={}, overrides=[])
    calendar, frames = synthetic
    with pytest.raises(ValueError, match="21 sessions"):
        audit_calendar(calendar, frames, evaluation_start="2024-01-04", lookback=20)


def test_explicit_new_record_date_still_cannot_override_price_cutoff():
    with pytest.raises(ValueError, match="cutoff"):
        verify_equities(pd.DataFrame(), "2025-10-01", allowed_sessions=("2025-10-01",))


def test_filling_january20_repairs_clock_without_certifying_amendments(synthetic):
    calendar, frames = synthetic
    originals = {s:f.copy() for s,f in frames.items()}
    for s in frames:
        frames[s] = frames[s].drop(pd.Timestamp('2024-01-20'))
    before = audit_calendar(calendar,frames,evaluation_start='2024-01-04')
    assert len(before.discrepancies) == 9
    for s in frames:
        frames[s] = originals[s]
    after = audit_calendar(calendar,frames,evaluation_start='2024-01-04')
    assert after.discrepancies.empty
    assert after.lookbacks.clock_matches.all()
    assert not after.summary['backtest_ready']
    row = after.schedule.set_index('signal_date').loc['2024-01-19']
    assert row.next_expected_session == pd.Timestamp('2024-01-20')
    assert row.all_eight_records_positive_volume
