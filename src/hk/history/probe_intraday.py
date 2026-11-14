#!/usr/bin/env python3
"""Probe recent Yahoo intraday bars without treating them as official live data.

This is a diagnostic helper, not a production market-data feed. Yahoo may be
delayed, incomplete, rate-limited, or unavailable, and intraday history is
retained for only a short window.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "tickers",
        nargs="*",
        default=["0700.HK", "^HSI"],
        help="Yahoo tickers to probe (default: Tencent and the HSI benchmark)",
    )
    parser.add_argument("--period", default="1d")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows: list[dict] = []
    probed_at = datetime.now(timezone.utc).replace(microsecond=0)
    for ticker in args.tickers:
        frame = yf.download(
            ticker,
            period=args.period,
            interval=args.interval,
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
            timeout=30,
            multi_level_index=False,
        )
        if frame.empty:
            rows.append({
                "ticker": ticker,
                "status": "no_intraday_data",
                "last_timestamp": "",
                "close": pd.NA,
                "volume": pd.NA,
                "probed_at_utc": probed_at.isoformat(),
            })
            continue
        last = frame.dropna(how="all", subset=[c for c in ["Open", "High", "Low", "Close"] if c in frame]).iloc[-1]
        timestamp = frame.dropna(how="all", subset=[c for c in ["Open", "High", "Low", "Close"] if c in frame]).index[-1]
        rows.append({
            "ticker": ticker,
            "status": "available_unofficial",
            "last_timestamp": timestamp.isoformat(),
            "close": last.get("Close", pd.NA),
            "volume": last.get("Volume", pd.NA),
            "probed_at_utc": probed_at.isoformat(),
        })

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
