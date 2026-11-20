"""Tencent HSI stock source for the shared live service (opt-in CLI only)."""

from __future__ import annotations

import argparse
import logging
import signal
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
import yaml

from src.hk.calendar import (
    FULL_DAY_CLOSURES,
    HKT,
    LATE_OPENS_HKT,
    calendar,
    market_state,
)
from src.hk.live import parse_quotes, read_symbols
from src.live.base import AwsSink, LocalSink, PollLoop

# Observed r_hk wire format, cross-check evidence: results/hk/week3/quote_comparison_summary.json.
# Field 6 is retained as provider quantity; no unverified lot/share conversion.
FIELD_NAME, FIELD_CODE, FIELD_LAST, FIELD_VOLUME, FIELD_TIME, FIELD_CHANGE_PCT = (
    1,
    2,
    3,
    6,
    30,
    32,
)
MAX_SYMBOLS_PER_REQUEST = (
    100  # Tested conservative batch, not a claimed provider maximum.
)
QUOTE_URL = "https://qt.gtimg.cn/q="
# The earlier local calendar omitted this evidenced full closure. Keep the
# running Week 3 collector untouched; apply the correction only in this module.
WEATHER_CLOSURES = set(FULL_DAY_CLOSURES) | {
    "2016-08-02",  # https://www.hkex.com.hk/News/Market-Communications/2016/1608022news?sc_lang=en
    "2016-10-21",  # https://www.hkex.com.hk/News/Market-Communications/2016/1610212news?sc_lang=en
    "2017-08-23",  # https://www.hkex.com.hk/News/Market-Communications/2017/1708232news?sc_lang=en
    "2023-07-17",  # https://www.hkex.com.hk/News/Market-Communications/2023/2307172news?sc_lang=en
}


class TencentSource:
    """Fetch conservative batches with a three-second request timeout."""

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def fetch(self, symbols: list[str]) -> tuple[list[dict], list[dict]]:
        """Keep good symbols when another request or wire record fails."""
        rows, errors = [], []
        for offset in range(0, len(symbols), MAX_SYMBOLS_PER_REQUEST):
            batch = symbols[offset : offset + MAX_SYMBOLS_PER_REQUEST]
            codes = ["r_hk" + value.removesuffix(".HK").zfill(5) for value in batch]
            try:
                response = self.session.get(QUOTE_URL + ",".join(codes), timeout=3)
                response.raise_for_status()
                response.encoding = "gbk"
                parsed, bad = parse_quotes(response.text, datetime.now(UTC))
                rows.extend(row for row in parsed if row["symbol"] in batch)
                errors.extend(bad)
            except requests.RequestException:
                errors.extend(
                    {"symbol": value, "error": "request failed"} for value in batch
                )
        found = {row["symbol"] for row in rows}
        errors.extend(
            {"symbol": value, "error": "missing quote"}
            for value in symbols
            if value not in found
        )
        return rows, errors


def session_gate(now: datetime) -> tuple[str, datetime]:
    """Return session state and the next tradable continuous-session instant."""
    state = market_state(now)
    if str(now.astimezone(HKT).date()) in WEATHER_CLOSURES:
        state = "closed"
    if state == "open":
        return state, now
    local_day = pd.Timestamp(now.astimezone(HKT).date())
    schedule = calendar().schedule.loc[local_day : local_day + pd.Timedelta(days=20)]
    for day, row in schedule.iterrows():
        label = str(day.date())
        if label in WEATHER_CLOSURES:
            continue
        opens = [row["open"]]
        if pd.notna(row["break_end"]):
            opens.append(row["break_end"])
        delayed = LATE_OPENS_HKT.get(label)
        if delayed:
            late = pd.Timestamp(
                datetime.combine(day.date(), datetime.min.time()), tz=HKT
            ) + pd.Timedelta(hours=delayed[0], minutes=delayed[1])
            opens = [max(value, late.tz_convert("UTC")) for value in opens]
        for opening in opens:
            if opening > pd.Timestamp(now) and opening < row["close"]:
                return state, opening.to_pydatetime()
    raise ValueError("No supported session found in the next twenty days")


def main() -> None:
    """Start only when explicitly invoked; AWS is an explicit command-line option."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/live_hk_week4"))
    parser.add_argument("--aws", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text())
    settings = config["live"]["hk"]
    roster = args.config.resolve().parent / settings["symbols_file"]
    symbols = read_symbols(roster)
    if args.aws:
        import boto3

        region = config["live"]["region"]
        sink = AwsSink(
            "hk",
            boto3.resource("dynamodb", region_name=region).Table(settings["table"]),
            boto3.client("s3", region_name=region),
            boto3.client("cloudwatch", region_name=region),
            config["live"]["bucket"],
            expected_symbols=set(symbols),
        )
    else:
        sink = LocalSink(args.output)
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.basicConfig(level=logging.INFO)
    PollLoop(
        symbols, TencentSource(), sink, session_gate, settings["interval_seconds"]
    ).run(lambda: stopped)


if __name__ == "__main__":
    main()
