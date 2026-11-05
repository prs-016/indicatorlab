#!/usr/bin/env python3
"""Minute poller for a complete Hong Kong cash-equity session.

Run before 09:30 HKT and leave it active through 16:05 HKT.  It records the
latest Yahoo 1-minute bar for the five Week 2 focus names and resumes safely in
the same CSV after a restart.
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo

from compare_live_sources import SYMBOLS, yahoo


HKT = ZoneInfo("Asia/Hong_Kong")
FIELDS = ["observed_at_utc", "provider", "ticker", "price_hkd", "provider_time", "request_latency_ms", "status", "note"]


def in_session(now: datetime) -> bool:
    local_time = now.astimezone(HKT).time()
    return wall_time(9, 30) <= local_time <= wall_time(16, 5)


def session_finished(now: datetime) -> bool:
    return now.astimezone(HKT).time() > wall_time(16, 5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("outputs") / "full_session_minute_poll.csv")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--allow-outside-session", action="store_true", help="Take one diagnostic sample immediately.")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    while True:
        now = datetime.now(tz=HKT)
        if in_session(now) or args.allow_outside_session:
            write_header = not args.output.exists()
            with args.output.open("a", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                if write_header:
                    writer.writeheader()
                for ticker in SYMBOLS:
                    writer.writerow(yahoo(ticker))
            if args.allow_outside_session:
                break
        elif session_finished(now):
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
