#!/usr/bin/env python3
"""Audit the latest completed Yahoo 1-minute session for the five focus names."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from compare_live_sources import HEADERS, SYMBOLS


HKT = ZoneInfo("Asia/Hong_Kong")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("outputs"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    bars = []
    for ticker in SYMBOLS:
        payload = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"interval": "1m", "range": "5d", "includePrePost": "false"},
            headers=HEADERS,
            timeout=20,
        ).json()["chart"]["result"][0]
        quote = payload["indicators"]["quote"][0]
        frame = pd.DataFrame({
            "timestamp": pd.to_datetime(payload["timestamp"], unit="s", utc=True),
            "open": quote["open"], "high": quote["high"], "low": quote["low"],
            "close": quote["close"], "volume": quote["volume"],
        }).dropna(subset=["close"])
        frame["local_time"] = frame["timestamp"].dt.tz_convert(HKT)
        frame["session_date"] = frame["local_time"].dt.date
        session_date = frame["session_date"].max()
        latest = frame.loc[frame["session_date"].eq(session_date)].copy()
        latest.insert(0, "ticker", ticker)
        bars.append(latest)
        minutes = latest["local_time"].dt.floor("min")
        gaps = int(minutes.sort_values().diff().gt(pd.Timedelta(minutes=1)).sum())
        summaries.append({
            "ticker": ticker,
            "session_date": str(session_date),
            "first_bar_hkt": latest["local_time"].min().isoformat(),
            "last_bar_hkt": latest["local_time"].max().isoformat(),
            "bar_count": len(latest),
            "non_one_minute_gaps_including_lunch": gaps,
            "first_price": float(latest.iloc[0]["close"]),
            "last_price": float(latest.iloc[-1]["close"]),
            "source": "Yahoo Finance chart API",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        })
    pd.concat(bars, ignore_index=True).to_csv(args.output_dir / "latest_session_1m_bars.csv", index=False)
    pd.DataFrame(summaries).to_csv(args.output_dir / "latest_session_1m_summary.csv", index=False)
    (args.output_dir / "latest_session_1m_summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
