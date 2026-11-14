"""Five-second HSI quote polls with local evidence and optional AWS sinks."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import signal
import statistics
import time
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src.hk.calendar import market_state

HKT = ZoneInfo("Asia/Hong_Kong")
QUOTE_URL = "https://qt.gtimg.cn/q="
BATCH_SIZE = 100  # conservative tested request size; not a provider SLA
FIELD_PRICE, FIELD_VOLUME, FIELD_TIME, FIELD_CHANGE = 3, 6, 30, 32
LOG = logging.getLogger(__name__)


def symbol(value: str) -> str:
    """Normalize the HKD HSI equity aliases to four digits plus .HK."""
    value = str(value).strip().upper().removeprefix("HK.").removesuffix(".HK")
    if not value.isascii() or not value.isdigit() or not 0 < int(value) < 10000:
        raise ValueError("Expected an HKD HSI equity code such as 0700.HK")
    return f"{int(value):04d}.HK"


def read_symbols(path: Path) -> list[str]:
    """Read a roster CSV with yahoo_ticker, ticker or symbol column."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        column = next(
            (
                name
                for name in ("yahoo_ticker", "ticker", "symbol")
                if name in (reader.fieldnames or [])
            ),
            None,
        )
        if column is None:
            raise ValueError("Roster CSV needs yahoo_ticker, ticker or symbol")
        return list(
            dict.fromkeys(symbol(row[column]) for row in reader if row.get(column))
        )


def parse_quotes(text: str, received: datetime) -> tuple[list[dict], list[dict]]:
    """Parse r_hk fields into the team's seven-column DynamoDB contract."""
    rows, errors = [], []
    for line in text.splitlines():
        if not line.startswith("v_r_hk"):
            continue
        code = line.split("=", 1)[0].removeprefix("v_r_hk")
        try:
            values = line.split('"', 2)[1].split("~")
            if symbol(values[2]) != symbol(code):
                raise ValueError("Provider identity mismatch")
            price, volume, change = (
                float(values[FIELD_PRICE]),
                float(values[FIELD_VOLUME]),
                float(values[FIELD_CHANGE]),
            )
            if (
                not all(math.isfinite(value) for value in (price, volume, change))
                or price <= 0
                or volume < 0
            ):
                raise ValueError("Invalid numeric quote")
            stamp = (
                datetime.strptime(values[FIELD_TIME], "%Y/%m/%d %H:%M:%S")
                .replace(tzinfo=HKT)
                .astimezone(UTC)
            )
            if (stamp - received).total_seconds() > 5:
                raise ValueError("Future provider timestamp")
            rows.append(
                {
                    "symbol": symbol(code),
                    "price": price,
                    "change_pct": change,
                    "volume": volume,
                    "ts_exchange": stamp.isoformat(),
                    "ts_received": received.isoformat(),
                    "source": "tencent",
                }
            )
        except (ValueError, IndexError, TypeError) as exc:
            errors.append({"symbol": code, "error": type(exc).__name__})
    return rows, errors


def fetch_quotes(
    symbols: list[str], session: requests.Session | None = None
) -> tuple[list[dict], list[dict]]:
    """Batch r_hk quotes; a malformed name never discards other valid names."""
    session = session or requests.Session()
    expected = list(dict.fromkeys(symbol(value) for value in symbols))
    rows, errors = [], []
    for offset in range(0, len(expected), BATCH_SIZE):
        batch = expected[offset : offset + BATCH_SIZE]
        try:
            codes = ["r_hk" + value.removesuffix(".HK").zfill(5) for value in batch]
            response = session.get(QUOTE_URL + ",".join(codes), timeout=4)
            response.raise_for_status()
            response.encoding = "gbk"
            parsed, failures = parse_quotes(response.text, datetime.now(UTC))
            rows.extend(row for row in parsed if row["symbol"] in batch)
            errors.extend(failures)
        except requests.RequestException as exc:
            errors.extend(
                {"symbol": value, "error": type(exc).__name__} for value in batch
            )
    found = {row["symbol"] for row in rows}
    errors.extend(
        {"symbol": value, "error": "missing_quote"}
        for value in expected
        if value not in found
    )
    return list({row["symbol"]: row for row in rows}.values()), errors


def write_json(path: Path, value: Any) -> None:
    """Atomically replace a local JSON view so readers never see a half-write."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class AwsSink:
    """Write the shared latest table, minute Parquet snapshots and heartbeat."""

    def __init__(
        self,
        region="us-west-2",
        table=None,
        bucket=None,
    ):
        import boto3

        table = table or os.getenv("HK_QUOTE_TABLE", "indicatorlab-live-hk")
        bucket = bucket or os.getenv("HK_DATA_BUCKET", "indicatorlab-data")
        self.table = boto3.resource("dynamodb", region_name=region).Table(table)
        self.s3 = boto3.client("s3", region_name=region)
        self.metrics = boto3.client("cloudwatch", region_name=region)
        self.bucket = bucket
        self.last_minute = None

    def write(self, rows: list[dict], now: datetime) -> None:
        """Upsert latest items and persist the first successful poll of each minute."""
        with self.table.batch_writer(overwrite_by_pkeys=["symbol"]) as batch:
            for row in rows:
                batch.put_item(Item=json.loads(json.dumps(row), parse_float=Decimal))
        if rows:
            self.metrics.put_metric_data(
                Namespace="IndicatorLab",
                MetricData=[
                    {
                        "MetricName": "HKQuoteHeartbeat",
                        "Timestamp": now,
                        "Value": 1.0,
                        "Unit": "Count",
                    }
                ],
            )
        local = now.astimezone(HKT)
        minute = local.strftime("%Y-%m-%d/%H%M")
        if rows and minute != self.last_minute:
            data = pd.DataFrame(rows).to_parquet(index=False)
            key = local.strftime("raw/live/hk/date=%Y-%m-%d/%H%M.parquet")
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="application/vnd.apache.parquet",
            )
            self.last_minute = minute


def run(
    symbols: list[str],
    output: Path,
    *,
    duration_seconds=600,
    interval_seconds=5,
    aws=False,
    respect_sessions=True,
    should_stop=None,
) -> dict[str, Any]:
    """Collect latency/delay evidence, snapshots and optional shared AWS updates."""
    if interval_seconds < 5 or duration_seconds < 0:
        raise ValueError(
            "Interval must be at least five seconds; duration must be nonnegative"
        )
    symbols = list(dict.fromkeys(symbol(value) for value in symbols))
    if not symbols:
        raise ValueError("The roster is empty")
    output.mkdir(parents=True, exist_ok=True)
    if duration_seconds and (output / "observations.jsonl").exists():
        raise FileExistsError("Use a new directory for each finite delay audit")
    sink = AwsSink() if aws else None
    session = requests.Session()
    started, next_poll = time.monotonic(), time.monotonic()
    # Bounded memory for continuous operation; full observations remain on disk.
    delays, latencies = deque(maxlen=100_000), deque(maxlen=10_000)
    polls, successes, failures, last_minute = 0, 0, 0, None
    latest = {}
    while duration_seconds == 0 or time.monotonic() - started < duration_seconds:
        if should_stop and should_stop():
            break
        now = datetime.now(UTC)
        state = market_state(now)
        if respect_sessions and state != "open":
            write_json(
                output / "status.json",
                {
                    "at": now.isoformat(),
                    "market_state": state,
                    "polls": polls,
                    "requested_symbols": len(symbols),
                    "aws_enabled": aws,
                },
            )
            time.sleep(min(30, interval_seconds))
            next_poll = time.monotonic()
            if duration_seconds and time.monotonic() - started >= duration_seconds:
                break
            continue
        poll_start = time.monotonic()
        rows, errors = fetch_quotes(symbols, session)
        received = datetime.now(UTC)
        latency = (time.monotonic() - poll_start) * 1000
        polls += 1
        latencies.append(latency)
        failures = 0 if rows else min(failures + 1, 6)
        for row in rows:
            age = (
                datetime.fromisoformat(row["ts_received"])
                - datetime.fromisoformat(row["ts_exchange"])
            ).total_seconds()
            row["delay_seconds"] = max(0.0, age)
            delays.append(max(0.0, age))
            latest[row["symbol"]] = row
        # Local evidence is append-only, with the true provider and receive times.
        evidence = (
            output
            if duration_seconds
            else output / "daily" / now.astimezone(HKT).strftime("%Y-%m-%d")
        )
        evidence.mkdir(parents=True, exist_ok=True)
        with (evidence / "observations.jsonl").open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        event = {
            "at": received.isoformat(),
            "poll": polls,
            "latency_ms": round(latency, 2),
            "quotes": len(rows),
            "requested": len(symbols),
            "errors": errors,
            "market_state": state,
        }
        with (evidence / "polls.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        write_json(output / "latest.json", list(latest.values()))
        write_json(
            output / "status.json",
            event
            | {
                "aws_enabled": aws,
                "fresh_under_60s": sum(row["delay_seconds"] < 60 for row in rows),
                "latest_symbols": len(latest),
            },
        )
        minute = now.astimezone(HKT).strftime("date=%Y-%m-%d/%H%M.parquet")
        if rows and minute != last_minute:
            destination = output / "snapshots" / minute
            destination.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_parquet(destination, index=False)
            last_minute = minute
        if sink:
            try:
                sink.write(
                    [
                        {
                            key: value
                            for key, value in row.items()
                            if key != "delay_seconds"
                        }
                        for row in rows
                    ],
                    now,
                )
            except Exception as exc:
                LOG.error("AWS sink failed: %s", type(exc).__name__)
                raise  # fail visibly; the service supervisor restarts after backoff
        successes += len(rows)
        LOG.info(
            "poll=%d quotes=%d/%d latency_ms=%.1f",
            polls,
            len(rows),
            len(symbols),
            latency,
        )
        next_poll = max(next_poll + interval_seconds, time.monotonic())
        wait = (
            min(60, interval_seconds * 2**failures)
            if failures
            else max(0, next_poll - time.monotonic())
        )
        time.sleep(
            min(wait, max(0, duration_seconds - (time.monotonic() - started)))
            if duration_seconds
            else wait
        )
    summary = {
        "polls": polls,
        "requested_symbols": len(symbols),
        "observations": successes,
        "median_delay_seconds": statistics.median(delays) if delays else None,
        "p95_delay_seconds": (
            float(pd.Series(delays).quantile(0.95)) if delays else None
        ),
        "median_poll_latency_ms": statistics.median(latencies) if latencies else None,
        "wall_seconds": time.monotonic() - started,
        "aws_enabled": aws,
        "delay_statistics_window_observations": len(delays),
    }
    write_json(output / "summary.json", summary)
    write_json(output / "latest.json", list(latest.values()))
    session.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--duration-seconds", type=int, default=600, help="0 means continuous"
    )
    parser.add_argument("--interval-seconds", type=float, default=5)
    parser.add_argument(
        "--aws", action="store_true", help="Requires the team's AWS login and resources"
    )
    args = parser.parse_args()
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(
        json.dumps(
            run(
                read_symbols(args.symbols_file),
                args.output,
                duration_seconds=args.duration_seconds,
                interval_seconds=args.interval_seconds,
                aws=args.aws,
                should_stop=lambda: stopped,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
