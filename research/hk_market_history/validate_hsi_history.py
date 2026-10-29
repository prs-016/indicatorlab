#!/usr/bin/env python3
"""Validate the HSI universe, coverage manifest, and downloaded price files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


EXPECTED_UNAVAILABLE = {
    "0011.HK": "no_reliable_original_history",
    "0013.HK": "no_reliable_original_history",
    "0494.HK": "no_reliable_original_history",
    "1880.HK": "no_reliable_original_history",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()

    universe = pd.read_csv(args.data_dir / "hsi_universe.csv")
    coverage = pd.read_csv(args.data_dir / "coverage.csv")
    file_index = pd.read_csv(args.data_dir / "price_file_index.csv")
    equity_coverage = coverage.loc[coverage["is_benchmark"].eq(False)].copy()
    downloaded = equity_coverage.loc[equity_coverage["status"].eq("downloaded")]

    price_checks = []
    for row in downloaded.itertuples(index=False):
        path = args.data_dir / row.file
        frame = pd.read_csv(path, parse_dates=["Date"])
        ohlc = frame[["Open", "High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce")
        high_violation = (ohlc["High"] + 1e-9 < ohlc[["Open", "Low", "Close"]].max(axis=1)).sum()
        low_violation = (ohlc["Low"] - 1e-9 > ohlc[["Open", "High", "Close"]].min(axis=1)).sum()
        negative_volume = (pd.to_numeric(frame["Volume"], errors="coerce") < 0).sum()
        duplicate_dates = int(frame["Date"].duplicated().sum())
        missing_adj_close = int(frame["Adj Close"].isna().sum())
        critical_issue = any([duplicate_dates, negative_volume, missing_adj_close])
        ohlc_warning = any([high_violation, low_violation])
        price_checks.append({
            "ticker": row.ticker,
            "rows": len(frame),
            "first_date": frame["Date"].min().date().isoformat(),
            "last_date": frame["Date"].max().date().isoformat(),
            "duplicate_dates": duplicate_dates,
            "high_violations": int(high_violation),
            "low_violations": int(low_violation),
            "negative_volume": int(negative_volume),
            "missing_adj_close": missing_adj_close,
            "status": "fail" if critical_issue else ("warning" if ohlc_warning else "pass"),
        })
    checks = pd.DataFrame(price_checks)
    checks.to_csv(args.data_dir / "validation_checks.csv", index=False)

    unavailable = dict(
        equity_coverage.loc[equity_coverage["status"].ne("downloaded"), ["ticker", "status"]].itertuples(index=False, name=None)
    )
    end_2024 = equity_coverage.loc[equity_coverage["is_hsi_2024_12_31"].eq(True)]
    current = equity_coverage.loc[equity_coverage["is_hsi_2026_09_07"].eq(True)]
    benchmark = coverage.loc[coverage["ticker"].eq("^HSI")].iloc[0]
    requested_through = pd.to_datetime(
        universe["price_data_requested_through"].dropna().iloc[0]
    )
    benchmark_last = pd.to_datetime(benchmark.last_date)
    date_stamped_files = downloaded.apply(
        lambda row: (
            f"__daily__{row.first_date}_to_{row.last_date}.csv" in str(row.file)
        ),
        axis=1,
    )
    benchmark_name_is_clear = (
        "Hang_Seng_Index__HSI__daily__" in str(benchmark.file)
        and f"_to_{benchmark.last_date}.csv" in str(benchmark.file)
    )
    index_columns = [
        "ticker", "company_name", "is_benchmark", "bar_interval", "first_date",
        "last_date", "row_count", "status", "file", "retrieved_at_utc",
    ]
    assertions = {
        "unique_equities_114": universe["hk_code"].nunique() == 114,
        "historical_members_100": int(universe["historical_member_2014_2024"].sum()) == 100,
        "end_2024_members_83": int(universe["is_hsi_2024_12_31"].sum()) == 83,
        "current_2026_members_95": int(universe["is_hsi_2026_09_07"].sum()) == 95,
        "downloaded_equities_110": len(downloaded) == 110,
        "unavailable_set_expected": unavailable == EXPECTED_UNAVAILABLE,
        "all_end_2024_members_downloaded": end_2024["status"].eq("downloaded").all(),
        "all_current_members_downloaded": current["status"].eq("downloaded").all(),
        "benchmark_starts_1986_12_31": benchmark.first_date == "1986-12-31",
        "benchmark_within_7_calendar_days_of_request": (
            0 <= (requested_through - benchmark_last).days <= 7
        ),
        "all_equity_files_have_date_ranges_in_names": bool(date_stamped_files.all()),
        "benchmark_file_name_identifies_hsi_and_date_range": benchmark_name_is_clear,
        "price_file_index_matches_coverage": file_index.fillna("").equals(
            coverage[index_columns].fillna("")
        ),
        "no_critical_price_file_failures": checks["status"].ne("fail").all(),
        "manifest_has_no_duplicate_dates": int(coverage["duplicate_dates"].sum()) == 0,
        "manifest_has_no_nonpositive_close": int(coverage["nonpositive_close"].sum()) == 0,
        "manifest_has_no_missing_adj_close": int(coverage["missing_adj_close"].sum()) == 0,
    }
    assertions = {name: bool(value) for name, value in assertions.items()}
    all_assertions_pass = all(assertions.values())
    warning_rows = int(checks["high_violations"].sum() + checks["low_violations"].sum())
    current_reaching_benchmark_latest = int(current["last_date"].eq(benchmark.last_date).sum())
    result = {
        "status": "pass_with_source_warnings" if all_assertions_pass and warning_rows else ("pass" if all_assertions_pass else "fail"),
        "assertions": assertions,
        "equity_price_rows": int(downloaded["row_count"].sum()),
        "benchmark_rows": int(benchmark.row_count),
        "price_files_checked": int(len(checks)),
        "requested_through_inclusive": requested_through.date().isoformat(),
        "benchmark_latest_date": benchmark.last_date,
        "current_members_reaching_benchmark_latest_date": current_reaching_benchmark_latest,
        "current_members_downloaded": int(current["status"].eq("downloaded").sum()),
        "ohlc_consistency_warning_rows": warning_rows,
        "ohlc_warning_note": "Yahoo contains a small number of rows where open/close falls outside reported high-low. Values are preserved and flagged rather than altered.",
    }
    (args.data_dir / "validation_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
