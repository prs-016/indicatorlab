#!/usr/bin/env python3
"""Build a reproducible Hang Seng Index research universe and price archive.

By default the archive refreshes through the latest daily bar available from
Yahoo Finance. A fixed exclusive --end date can still be supplied when a
research cutoff is needed. The archive combines:
  * official HSI membership snapshots (end-2024 count and Sep-2026 list),
  * a public historical-member reconstruction for 2014-2024, and
  * freshly downloaded Yahoo Finance daily OHLCV histories.

No missing price is filled or silently replaced with a successor security.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


OFFICIAL_HSI_2026 = [
    (5, "HSBC HOLDINGS"), (939, "CCB"), (1299, "AIA"), (1398, "ICBC"),
    (388, "HKEX"), (3988, "BANK OF CHINA"), (2318, "PING AN"),
    (2628, "CHINA LIFE"), (3968, "CM BANK"), (2388, "BOC HONG KONG"),
    (9988, "BABA"), (3690, "MEITUAN"), (1211, "BYD COMPANY"),
    (669, "TECHTRONIC IND"), (9618, "JD.COM"), (9888, "BAIDU"),
    (9961, "TRIP.COM"), (175, "GEELY AUTO"), (1024, "KUAISHOU"),
    (9992, "POP MART"), (2020, "ANTA SPORTS"), (9633, "NONGFU SPRING"),
    (27, "GALAXY ENT"), (288, "WH GROUP"), (2015, "LI AUTO"),
    (66, "MTR CORPORATION"), (300, "MIDEA GROUP"), (2319, "MENGNIU DAIRY"),
    (6690, "HAIER SMARTHOME"), (9901, "NEW ORIENTAL"),
    (1928, "SANDS CHINA"), (291, "CHINA RES BEER"),
    (2313, "SHENZHOU INTL"), (2331, "LI NING"), (322, "TINGYI"),
    (1929, "CHOW TAI FOOK"), (6862, "HAIDILAO"), (6181, "LAOPU GOLD"),
    (1044, "HENGAN INT'L"), (1876, "BUD APAC"), (700, "TENCENT"),
    (1810, "XIAOMI"), (9999, "NETEASE"), (981, "SMIC"),
    (992, "LENOVO GROUP"), (1347, "HUA HONG SEMICONDUCTOR"),
    (2382, "SUNNY OPTICAL"), (285, "BYD ELECTRONIC"), (883, "CNOOC"),
    (857, "PETROCHINA"), (2899, "ZIJIN MINING"), (1, "CKH HOLDINGS"),
    (1088, "CHINA SHENHUA"), (3750, "CATL"), (386, "SINOPEC CORP"),
    (1378, "CHINA HONGQIAO"), (267, "CITIC"), (1519, "J&T EXPRESS"),
    (2057, "ZTO EXPRESS"), (2338, "WEICHAI POWER"), (3993, "CMOC"),
    (2600, "CHALCO"), (2618, "JD LOGISTICS"), (316, "OOIL"),
    (868, "XINYI GLASS"), (968, "XINYI SOLAR"), (941, "CHINA MOBILE"),
    (2, "CLP HOLDINGS"), (6, "POWER ASSETS"), (3, "HK & CHINA GAS"),
    (728, "CHINA TELECOM"), (1038, "CKI HOLDINGS"), (2688, "ENN ENERGY"),
    (836, "CHINA RES POWER"), (762, "CHINA UNICOM"),
    (6160, "BEONE MEDICINES"), (2269, "WUXI BIO"), (1801, "INNOVENT BIO"),
    (2359, "WUXI APPTEC"), (1093, "CSPC PHARMA"), (3692, "HANSOH PHARMA"),
    (1177, "SINO BIOPHARM"), (6618, "JD HEALTH"), (1099, "SINOPHARM"),
    (241, "ALI HEALTH"), (16, "SHK PPT"), (1109, "CHINA RES LAND"),
    (823, "LINK REIT"), (1113, "CK ASSET"), (1997, "WHARF REIC"),
    (688, "CHINA OVERSEAS"), (12, "HENDERSON LAND"),
    (1209, "CHINA RES MIXC"), (960, "LONGFOR GROUP"),
    (101, "HANG LUNG PPT"),
]

MANUAL_HISTORICAL = {
    "HK0011": "Hang Seng Bank",
    "HK0013": "Hutchison Whampoa",
    "HK0494": "Li & Fung",
    "HK1880": "Belle International",
}
UNRELIABLE_ORIGINAL_HISTORY = set(MANUAL_HISTORICAL)

OFFICIAL_2026_URL = (
    "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/"
    "20260821T174500.pdf"
)
OFFICIAL_2024_URL = (
    "https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/"
    "20241122T174500.pdf"
)
SECONDARY_HISTORY_URL = (
    "https://github.com/AndyLongest/HistoricalIndexPrices/tree/"
    "bdb5c01084b314a94edfad155547d9373d0d8191"
)
YAHOO_URL = "https://finance.yahoo.com/"
BAR_INTERVAL = "1d"
HONG_KONG_TZ = ZoneInfo("Asia/Hong_Kong")


def code_to_ticker(hk_code: str) -> str:
    return f"{int(hk_code[2:]):04d}.HK"


def build_universe(reference_map: Path, requested_through: str) -> pd.DataFrame:
    mapping = pd.read_csv(reference_map)
    mapping = mapping.loc[mapping["index_folder"].eq("hsi")].copy()
    mapping["price_start"] = pd.to_datetime(mapping["price_start"], errors="coerce")
    mapping["price_end"] = pd.to_datetime(mapping["price_end"], errors="coerce")

    records: dict[str, dict] = {}
    cutoff = pd.Timestamp("2024-12-31")
    for row in mapping.itertuples(index=False):
        code = row.folder_symbol
        if row.price_start > cutoff:
            continue
        records[code] = {
            "hk_code": code,
            "company_name": row.company_name,
            "historical_member_2014_2024": True,
            "is_hsi_2024_12_31": bool(row.price_start <= cutoff <= row.price_end),
            "historical_membership_first_observation": (
                row.price_start.date().isoformat() if pd.notna(row.price_start) else ""
            ),
            "historical_membership_last_observation": (
                row.price_end.date().isoformat() if pd.notna(row.price_end) else ""
            ),
            "historical_membership_source": SECONDARY_HISTORY_URL,
        }

    for code, name in MANUAL_HISTORICAL.items():
        records.setdefault(code, {})
        records[code].update({
            "hk_code": code,
            "company_name": name,
            "historical_member_2014_2024": True,
            "is_hsi_2024_12_31": False,
            "historical_membership_first_observation": "",
            "historical_membership_last_observation": "",
            "historical_membership_source": SECONDARY_HISTORY_URL,
        })

    # LINK REIT is present in the official end-2024 and 2026 HSI lists but was
    # omitted from the secondary reconstruction. Keeping it here makes the
    # official end-2024 count reconcile to 83.
    records.setdefault("HK0823", {})
    records["HK0823"].update({
        "hk_code": "HK0823",
        "company_name": "Link REIT",
        "historical_member_2014_2024": True,
        "is_hsi_2024_12_31": True,
        "historical_membership_first_observation": "",
        "historical_membership_last_observation": "",
        "historical_membership_source": OFFICIAL_2024_URL,
    })

    current = {f"HK{code:04d}": name for code, name in OFFICIAL_HSI_2026}
    for code, name in current.items():
        row = records.setdefault(code, {
            "hk_code": code,
            "company_name": name,
            "historical_member_2014_2024": False,
            "is_hsi_2024_12_31": False,
            "historical_membership_first_observation": "",
            "historical_membership_last_observation": "",
            "historical_membership_source": "",
        })
        if not row.get("company_name"):
            row["company_name"] = name
        row["is_hsi_2026_09_07"] = True
        row["current_membership_source"] = OFFICIAL_2026_URL

    for row in records.values():
        row.setdefault("is_hsi_2026_09_07", False)
        row.setdefault("current_membership_source", "")
        row["yahoo_ticker"] = code_to_ticker(row["hk_code"])

    result = pd.DataFrame(records.values()).sort_values("hk_code").reset_index(drop=True)
    result.insert(0, "security_id", result["hk_code"])
    result["price_data_requested_through"] = requested_through
    result["price_source"] = YAHOO_URL

    assert result["is_hsi_2024_12_31"].sum() == 83, "End-2024 HSI list must contain 83 names"
    assert result["is_hsi_2026_09_07"].sum() == 95, "Current official HSI list must contain 95 names"
    return result


def extract_ticker(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = raw.columns.get_level_values(0)
        level1 = raw.columns.get_level_values(1)
        if ticker in level0:
            frame = raw[ticker].copy()
        elif ticker in level1:
            frame = raw.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        frame = raw.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame.index.name = "Date"
    frame.columns = [str(c) for c in frame.columns]
    # Require an actual price observation. Yahoo can emit a future
    # dividend-only row with zero volume and no OHLC values; that is a corporate
    # action event, not a completed daily price bar.
    key_cols = [c for c in ["Open", "High", "Low", "Close", "Adj Close"] if c in frame]
    if not key_cols:
        return pd.DataFrame()
    return frame.dropna(how="all", subset=key_cols).sort_index()


def download_batch(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    return yf.download(
        tickers=tickers,
        start=start,
        end=end,
        interval=BAR_INTERVAL,
        auto_adjust=False,
        actions=True,
        repair=True,
        group_by="ticker",
        threads=True,
        progress=False,
        timeout=30,
    )


def save_prices(
    universe: pd.DataFrame,
    output_dir: Path,
    start: str,
    end: str,
    batch_size: int,
) -> pd.DataFrame:
    price_dir = output_dir / "prices"
    benchmark_dir = output_dir / "benchmark"
    price_dir.mkdir(parents=True, exist_ok=True)
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    all_tickers = universe["yahoo_ticker"].drop_duplicates().tolist()
    blocked_tickers = {code_to_ticker(code) for code in UNRELIABLE_ORIGINAL_HISTORY}
    tickers = [ticker for ticker in all_tickers if ticker not in blocked_tickers]
    tickers.append("^HSI")
    frames: dict[str, pd.DataFrame] = {}

    for batch_no, start_i in enumerate(range(0, len(tickers), batch_size), start=1):
        batch = tickers[start_i:start_i + batch_size]
        print(f"Downloading batch {batch_no}: {len(batch)} symbols", flush=True)
        try:
            raw = download_batch(batch, start, end)
        except Exception as exc:  # keep the manifest complete even if a batch fails
            print(f"Batch error: {exc}", flush=True)
            raw = pd.DataFrame()
        for ticker in batch:
            frame = extract_ticker(raw, ticker)
            if not frame.empty:
                frames[ticker] = frame
        time.sleep(1)

    missing = [ticker for ticker in tickers if ticker not in frames]
    for idx, ticker in enumerate(missing, start=1):
        print(f"Retrying {idx}/{len(missing)}: {ticker}", flush=True)
        try:
            raw = yf.download(
                tickers=ticker,
                start=start,
                end=end,
                interval=BAR_INTERVAL,
                auto_adjust=False,
                actions=True,
                repair=True,
                progress=False,
                threads=False,
                timeout=30,
            )
            frame = extract_ticker(raw, ticker)
            if not frame.empty:
                frames[ticker] = frame
        except Exception as exc:
            print(f"Retry error for {ticker}: {exc}", flush=True)
        time.sleep(0.5)

    coverage = []
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    generated_files: set[Path] = set()
    for ticker in [*all_tickers, "^HSI"]:
        frame = frames.get(ticker, pd.DataFrame())
        is_benchmark = ticker == "^HSI"
        destination: Path | None = None
        if ticker in blocked_tickers:
            duplicate_dates = 0
            nonpositive_close = 0
            missing_adj_close = 0
            first_date = ""
            last_date = ""
            row_count = 0
            status = "no_reliable_original_history"
        elif not frame.empty:
            standard = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits", "Capital Gains"]
            for col in standard:
                if col not in frame:
                    frame[col] = pd.NA
            frame = frame[standard]
            duplicate_dates = int(frame.index.duplicated().sum())
            nonpositive_close = int((pd.to_numeric(frame["Close"], errors="coerce") <= 0).sum())
            missing_adj_close = int(frame["Adj Close"].isna().sum())
            first_date = frame.index.min().date().isoformat()
            last_date = frame.index.max().date().isoformat()
            prefix = "Hang_Seng_Index__HSI" if is_benchmark else ticker
            destination = (benchmark_dir if is_benchmark else price_dir) / (
                f"{prefix}__daily__{first_date}_to_{last_date}.csv"
            )
            frame.to_csv(destination, date_format="%Y-%m-%d", float_format="%.8f")
            generated_files.add(destination)
            row_count = len(frame)
            status = "downloaded"
        else:
            duplicate_dates = 0
            nonpositive_close = 0
            missing_adj_close = 0
            first_date = ""
            last_date = ""
            row_count = 0
            status = "no_yahoo_history"
        coverage.append({
            "ticker": ticker,
            "is_benchmark": is_benchmark,
            "bar_interval": BAR_INTERVAL,
            "status": status,
            "first_date": first_date,
            "last_date": last_date,
            "row_count": row_count,
            "duplicate_dates": duplicate_dates,
            "nonpositive_close": nonpositive_close,
            "missing_adj_close": missing_adj_close,
            "source": YAHOO_URL,
            "retrieved_at_utc": retrieved_at,
            "file": str(destination.relative_to(output_dir)) if destination else "",
        })

    # Remove superseded date-stamped files only after the replacement archive
    # has been written successfully. This keeps every ticker unambiguous while
    # avoiding duplicate snapshots from older refreshes.
    for directory in (price_dir, benchmark_dir):
        for old_file in directory.glob("*.csv"):
            if old_file not in generated_files:
                old_file.unlink()
    return pd.DataFrame(coverage)


def resolve_download_window(exclusive_end: str | None) -> tuple[str, str]:
    """Return Yahoo's exclusive end date and the requested inclusive date."""
    if exclusive_end:
        end_date = pd.Timestamp(exclusive_end).date()
    else:
        end_date = datetime.now(HONG_KONG_TZ).date() + timedelta(days=1)
    if end_date <= pd.Timestamp("1900-01-01").date():
        raise ValueError("--end must be later than 1900-01-01")
    return end_date.isoformat(), (end_date - timedelta(days=1)).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start", default="1900-01-01")
    parser.add_argument(
        "--end",
        default=None,
        help=(
            "Exclusive Yahoo end date. Omit it to request data through the "
            "current Hong Kong calendar date."
        ),
    )
    parser.add_argument("--batch-size", type=int, default=12)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    exclusive_end, requested_through = resolve_download_window(args.end)
    print(
        f"Requesting daily bars through {requested_through} "
        f"(exclusive Yahoo end {exclusive_end})",
        flush=True,
    )
    universe = build_universe(args.reference_map, requested_through)
    universe.to_csv(args.output_dir / "hsi_universe.csv", index=False)
    coverage = save_prices(universe, args.output_dir, args.start, exclusive_end, args.batch_size)
    coverage = coverage.merge(
        universe[["yahoo_ticker", "hk_code", "company_name", "historical_member_2014_2024", "is_hsi_2024_12_31", "is_hsi_2026_09_07"]],
        how="left",
        left_on="ticker",
        right_on="yahoo_ticker",
    ).drop(columns=["yahoo_ticker"])
    coverage.to_csv(args.output_dir / "coverage.csv", index=False)
    coverage[[
        "ticker", "company_name", "is_benchmark", "bar_interval", "first_date",
        "last_date", "row_count", "status", "file", "retrieved_at_utc",
    ]].to_csv(args.output_dir / "price_file_index.csv", index=False)

    downloaded_equities = coverage.loc[
        coverage["is_benchmark"].eq(False) & coverage["status"].eq("downloaded")
    ]
    current_members = coverage.loc[coverage["is_hsi_2026_09_07"].eq(True)]
    benchmark = coverage.loc[coverage["ticker"].eq("^HSI")].iloc[0]
    latest_equity_date = downloaded_equities["last_date"].max()

    summary = {
        "unique_equities": int(len(universe)),
        "historical_members_2014_2024": int(universe["historical_member_2014_2024"].sum()),
        "hsi_members_2024_12_31": int(universe["is_hsi_2024_12_31"].sum()),
        "hsi_members_2026_09_07": int(universe["is_hsi_2026_09_07"].sum()),
        "equities_downloaded": int(len(downloaded_equities)),
        "equities_without_usable_history": int(
            (coverage["is_benchmark"].eq(False) & coverage["status"].ne("downloaded")).sum()
        ),
        "current_hsi_members_downloaded": int(current_members["status"].eq("downloaded").sum()),
        "benchmark_first_date": benchmark.first_date,
        "benchmark_last_date": benchmark.last_date,
        "latest_equity_date": latest_equity_date,
        "requested_through_inclusive": requested_through,
        "yahoo_exclusive_end": exclusive_end,
        "bar_interval": BAR_INTERVAL,
        "retrieved_at_utc": coverage["retrieved_at_utc"].iloc[0],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
