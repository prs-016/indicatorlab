#!/usr/bin/env python3
"""Build the Hong Kong Week 2 evidence tables from the local HSI archive.

The script is deliberately offline: it reads the date-stamped Yahoo files in
``research/hk_market_history`` and writes reviewable CSV/JSON artifacts beside
this file.  Refresh the archive first when a newer market date is required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
MARKET_DIR = ROOT / "data" / "hk_market_history"
OUTPUT_DIR = ROOT / "results" / "hk" / "week2"
OFFICIAL_2024_URL = (
    "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/"
    "20241122T174500.pdf"
)
OFFICIAL_2026_URL = (
    "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/"
    "20260821T174500.pdf"
)
HISTORY_URL = (
    "https://github.com/AndyLongest/HistoricalIndexPrices/tree/"
    "bdb5c01084b314a94edfad155547d9373d0d8191"
)

FOCUS = ["0700.HK", "0005.HK", "1299.HK", "0941.HK", "0388.HK", "^HSI"]

# Exact roster in Appendix 1 of the 13-Nov-2020 review release, effective
# 7-Dec-2020.  This is the anchor requested by the assignment.
HSI_2020_12_07 = {
    "1299.HK", "0005.HK", "0939.HK", "2318.HK", "0388.HK", "1398.HK",
    "3988.HK", "2628.HK", "0011.HK", "2388.HK", "3328.HK", "0002.HK",
    "0003.HK", "0006.HK", "1038.HK", "0823.HK", "0016.HK", "1109.HK",
    "1113.HK", "2007.HK", "0688.HK", "1997.HK", "0017.HK", "0012.HK",
    "0101.HK", "0700.HK", "9988.HK", "3690.HK", "1810.HK", "0941.HK",
    "2269.HK", "0883.HK", "0669.HK", "0001.HK", "0027.HK", "0175.HK",
    "2319.HK", "2313.HK", "2020.HK", "2382.HK", "1928.HK", "1177.HK",
    "0386.HK", "1093.HK", "0066.HK", "0288.HK", "0857.HK", "1876.HK",
    "0267.HK", "1044.HK", "0762.HK", "2018.HK",
}

# Counts after each review, as stated in the official HSI review releases.
REVIEW_COUNTS = {
    "2020-12-07": 52,
    "2021-03-15": 55,
    "2021-06-07": 58,
    "2021-09-06": 60,
    "2021-12-06": 64,
    "2022-03-07": 66,
    "2022-06-13": 69,
    "2022-09-05": 73,
    "2022-12-05": 76,
    "2023-03-13": 76,
    "2023-06-05": 80,
    "2023-09-04": 80,
    "2023-12-04": 82,
    "2024-03-04": 82,
    "2024-06-11": 82,
    "2024-09-09": 82,
    "2024-12-09": 83,
    "2025-06-09": 85,
    "2025-09-08": 88,
}

REVIEW_RELEASES = {
    "2020-12-07": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20201113T000000.pdf",
    "2021-03-15": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20210226T000000.pdf",
    "2021-12-06": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20211119T000000.pdf",
    "2022-03-07": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20220218T000000.pdf",
    "2022-09-05": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20220819T000000.pdf",
    "2022-12-05": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20221118T000000.pdf",
    "2023-06-05": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20230512T175000.pdf",
    "2024-12-09": OFFICIAL_2024_URL,
    "2025-06-09": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20250516T174501.pdf",
    "2025-09-08": "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20250822T174500.pdf",
}

BOARD_LOTS = {
    "0700.HK": 100,
    "0005.HK": 400,
    "1299.HK": 200,
    "0941.HK": 500,
    "0388.HK": 100,
}


def _file_for_ticker(coverage: pd.DataFrame, ticker: str) -> Path:
    row = coverage.loc[coverage["ticker"].eq(ticker)]
    if row.empty or not row.iloc[0]["file"]:
        raise FileNotFoundError(f"No local price file for {ticker}")
    return MARKET_DIR / str(row.iloc[0]["file"])


def _load_price(coverage: pd.DataFrame, ticker: str) -> pd.DataFrame:
    frame = pd.read_csv(_file_for_ticker(coverage, ticker), parse_dates=["Date"])
    return frame.sort_values("Date").drop_duplicates("Date").set_index("Date")


def build_membership(universe: pd.DataFrame) -> pd.DataFrame:
    """Create effective-dated HSI intervals from the pinned reconstruction.

    The pinned source stores each security only while it is an HSI member, so
    its first/last observations are membership bounds.  Two official-roster
    corrections are explicit: 0011 (no free price file after delisting) and
    0823 (omitted by the secondary reconstruction).  The September 2025 review
    is added from the official release so the prescribed test can end in Sep-25.
    """
    rows: list[dict[str, object]] = []
    anchor = pd.Timestamp("2020-12-07")
    for row in universe.itertuples(index=False):
        start = pd.to_datetime(row.historical_membership_first_observation, errors="coerce")
        end = pd.to_datetime(row.historical_membership_last_observation, errors="coerce")
        if pd.isna(start) or pd.isna(end):
            continue
        # The secondary reconstruction has six stale intervals that overlap the
        # official 7-Dec-2020 roster but are not in it.  Use the published roster
        # as the control and exclude those intervals instead of forcing the total.
        if start <= anchor <= end and row.yahoo_ticker not in HSI_2020_12_07:
            continue
        # The secondary archive's shared cutoff is 22-Aug-2025. No HSI removals
        # took effect at the 8-Sep-2025 review, so continuing members extend to
        # the requested test cutoff.
        if end == pd.Timestamp("2025-08-22"):
            end = pd.Timestamp("2025-09-30")
        rows.append({
            "ticker": row.yahoo_ticker,
            "company_name": row.company_name,
            "member_from": start.date().isoformat(),
            "member_to": end.date().isoformat(),
            "source": HISTORY_URL,
            "source_note": "pinned reconstruction from official HSI review notices",
        })

    by_ticker = {item["ticker"]: item for item in rows}
    by_ticker["0011.HK"] = {
        "ticker": "0011.HK",
        "company_name": "Hang Seng Bank",
        "member_from": "2014-10-31",
        "member_to": "2025-09-30",
        "source": OFFICIAL_2024_URL,
        "source_note": "official roster correction; free original-listing price history unavailable",
    }
    by_ticker["0823.HK"] = {
        "ticker": "0823.HK",
        "company_name": "Link REIT",
        "member_from": "2014-10-31",
        "member_to": "2025-09-30",
        "source": OFFICIAL_2024_URL,
        "source_note": "official roster correction",
    }
    # The secondary archive joins repeated constituent spells into a stale
    # interval.  The effective dates below are the official HSI re-admissions;
    # without them the 2021-24 point-in-time counts are understated.
    for ticker, name, effective_date, release_date in [
        ("0291.HK", "China Resources Beer", "2021-12-06", "2021-12-06"),
        ("0992.HK", "Lenovo Group", "2022-03-07", "2022-03-07"),
        ("1088.HK", "China Shenhua Energy", "2022-09-05", "2022-09-05"),
        ("0322.HK", "Tingyi", "2022-12-05", "2022-12-05"),
        ("0836.HK", "China Resources Power", "2023-06-05", "2023-06-05"),
    ]:
        item = by_ticker.get(ticker, {
            "ticker": ticker,
            "company_name": name,
            "member_to": "2025-09-30",
        })
        item.update({
            "company_name": name,
            "member_from": effective_date,
            "source": REVIEW_RELEASES[release_date],
            "source_note": "official HSI re-admission date; stale secondary interval corrected",
        })
        by_ticker[ticker] = item
    for ticker, name in {
        "0300.HK": "Midea Group",
        "2057.HK": "ZTO Express",
    }.items():
        by_ticker[ticker] = {
            "ticker": ticker,
            "company_name": name,
            "member_from": "2025-06-09",
            "member_to": "2025-09-30",
            "source": REVIEW_RELEASES["2025-06-09"],
            "source_note": "official June 2025 HSI addition",
        }
    for ticker, name in {
        "0728.HK": "China Telecom",
        "2618.HK": "JD Logistics",
        "9992.HK": "Pop Mart",
    }.items():
        by_ticker[ticker] = {
            "ticker": ticker,
            "company_name": name,
            "member_from": "2025-09-08",
            "member_to": "2025-09-30",
            "source": REVIEW_RELEASES["2025-09-08"],
            "source_note": "official September 2025 HSI addition",
        }

    result = pd.DataFrame(by_ticker.values())
    result["member_from"] = pd.to_datetime(result["member_from"])
    result["member_to"] = pd.to_datetime(result["member_to"])
    return result.sort_values(["ticker", "member_from"]).reset_index(drop=True)


def review_count_checks(membership: pd.DataFrame) -> pd.DataFrame:
    rows = []
    release_dates = sorted((pd.Timestamp(key), value) for key, value in REVIEW_RELEASES.items())
    for raw_date, expected in REVIEW_COUNTS.items():
        date = pd.Timestamp(raw_date)
        actual = int(((membership["member_from"] <= date) & (membership["member_to"] >= date)).sum())
        applicable = [url for source_date, url in release_dates if source_date <= date]
        source = applicable[-1] if applicable else HISTORY_URL
        rows.append({
            "effective_date": date,
            "published_constituent_count": expected,
            "reconstructed_constituent_count": actual,
            "difference": actual - expected,
            "status": "pass" if actual == expected else "review",
            "official_release": REVIEW_RELEASES.get(raw_date, source),
        })
    return pd.DataFrame(rows)


def max_history_checks(coverage: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    benchmark = _load_price(coverage, "^HSI")
    benchmark_dates = benchmark.index
    summary_rows: list[dict[str, object]] = []
    split_rows: list[dict[str, object]] = []
    all_rows: list[dict[str, object]] = []

    for row in coverage.loc[coverage["status"].eq("downloaded")].itertuples(index=False):
        frame = _load_price(coverage, row.ticker)
        ohlc = frame[["Open", "High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce")
        impossible = (
            ohlc["High"].lt(ohlc[["Open", "Low", "Close"]].max(axis=1) - 1e-8)
            | ohlc["Low"].gt(ohlc[["Open", "High", "Close"]].min(axis=1) + 1e-8)
            | ohlc.le(0).any(axis=1)
        )
        volume = pd.to_numeric(frame["Volume"], errors="coerce")
        zero_volume = volume.eq(0)
        in_range_benchmark = benchmark_dates[(benchmark_dates >= frame.index.min()) & (benchmark_dates <= frame.index.max())]
        missing_dates = in_range_benchmark.difference(frame.index)
        pre_2021 = frame.index < pd.Timestamp("2021-01-01")
        item = {
            "ticker": row.ticker,
            "company_name": getattr(row, "company_name", ""),
            "first_date": frame.index.min(),
            "last_date": frame.index.max(),
            "rows": len(frame),
            "gaps_vs_hsi": len(missing_dates),
            "zero_volume_rows": int(zero_volume.sum()),
            "impossible_price_rows": int(impossible.sum()),
            "pre_2021_zero_volume_rows": int((zero_volume & pre_2021).sum()),
            "pre_2021_impossible_price_rows": int((impossible & pre_2021).sum()),
            "price_source": "Yahoo Finance chart API",
        }
        all_rows.append(item)
        if row.ticker in FOCUS:
            events = pd.to_numeric(frame.get("Stock Splits", pd.Series(index=frame.index, dtype=float)), errors="coerce").fillna(0)
            event_rows = events.loc[events.ne(0)]
            if event_rows.empty:
                split_rows.append({
                    "ticker": row.ticker,
                    "event_date": pd.NaT,
                    "split_ratio": np.nan,
                    "bonus_issue_check": "No separate bonus-issue field is exposed by Yahoo; verify against issuer filings for execution-price work.",
                    "source": "Yahoo Finance corporate actions",
                })
            else:
                for event_date, ratio in event_rows.items():
                    split_rows.append({
                        "ticker": row.ticker,
                        "event_date": event_date,
                        "split_ratio": float(ratio),
                        "bonus_issue_check": "Yahoo classifies this as a split; bonus issues are not separately identified.",
                        "source": "Yahoo Finance corporate actions",
                    })
            summary_rows.append({
                **item,
                "board_lot_shares": BOARD_LOTS.get(row.ticker, np.nan),
                "split_event_count": len(event_rows),
            })

    return pd.DataFrame(summary_rows), pd.DataFrame(split_rows), pd.DataFrame(all_rows)


def current_constituents(universe: pd.DataFrame) -> pd.DataFrame:
    result = universe.loc[universe["is_hsi_2026_09_07"].eq(True), [
        "hk_code", "yahoo_ticker", "company_name", "current_membership_source"
    ]].copy()
    result.insert(0, "as_of", pd.Timestamp("2026-11-04"))
    result = result.rename(columns={"current_membership_source": "source"})
    return result.sort_values("hk_code").reset_index(drop=True)


def main() -> None:
    global MARKET_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-dir", type=Path, default=MARKET_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    MARKET_DIR = args.market_dir
    args.output_dir.mkdir(parents=True, exist_ok=True)

    universe = pd.read_csv(MARKET_DIR / "hsi_universe.csv")
    coverage = pd.read_csv(MARKET_DIR / "coverage.csv")

    membership = build_membership(universe)
    counts = review_count_checks(membership)
    max_summary, splits, all_checks = max_history_checks(coverage)
    current = current_constituents(universe)

    membership.to_csv(args.output_dir / "hsi_membership_intervals.csv", index=False, date_format="%Y-%m-%d")
    counts.to_csv(args.output_dir / "hsi_review_count_checks.csv", index=False, date_format="%Y-%m-%d")
    max_summary.to_csv(args.output_dir / "max_history_splits_summary.csv", index=False, date_format="%Y-%m-%d")
    splits.to_csv(args.output_dir / "split_events.csv", index=False, date_format="%Y-%m-%d")
    all_checks.to_csv(args.output_dir / "all_hsi_history_checks.csv", index=False, date_format="%Y-%m-%d")
    current.to_csv(args.output_dir / "hsi_current_constituents.csv", index=False, date_format="%Y-%m-%d")

    summary = {
        "current_constituents": int(len(current)),
        "membership_intervals": int(len(membership)),
        "review_count_checks_passed": int(counts["status"].eq("pass").sum()),
        "review_count_checks_total": int(len(counts)),
        "latest_market_date": str(pd.to_datetime(coverage["last_date"], errors="coerce").max().date()),
        "downloaded_price_files_including_benchmark": int(coverage["status"].eq("downloaded").sum()),
        "symbols_with_ohlc_consistency_warnings": int((all_checks["impossible_price_rows"] > 0).sum()),
        "source_warning": "Yahoo contains OHLC consistency warnings; preserved and counted rather than repaired.",
    }
    (args.output_dir / "week2_evidence_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
