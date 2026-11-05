#!/usr/bin/env python3
"""Take repeatable cross-source HK quote snapshots for the five focus stocks.

Free public feeds are compared on price, provider timestamp and request latency.
Futu is probed only when a local OpenD is running; HKEX is represented as the
authoritative exchange source and explicitly marked manual/licensed because it
does not offer an anonymous public quote API.
"""

from __future__ import annotations

import argparse
import csv
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


SYMBOLS = {
    "0700.HK": {"tencent": "hk00700", "eastmoney": "116.00700"},
    "0005.HK": {"tencent": "hk00005", "eastmoney": "116.00005"},
    "1299.HK": {"tencent": "hk01299", "eastmoney": "116.01299"},
    "0941.HK": {"tencent": "hk00941", "eastmoney": "116.00941"},
    "0388.HK": {"tencent": "hk00388", "eastmoney": "116.00388"},
}
HEADERS = {"User-Agent": "indicatorlab-week2/1.0 (educational research)"}


def _row(provider: str, ticker: str, started: float, **values: Any) -> dict[str, Any]:
    return {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "provider": provider,
        "ticker": ticker,
        "price_hkd": values.get("price_hkd"),
        "provider_time": values.get("provider_time"),
        "request_latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "status": values.get("status", "ok"),
        "note": values.get("note", ""),
    }


def yahoo(ticker: str) -> dict[str, Any]:
    started = time.perf_counter()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        result = requests.get(url, params={"interval": "1m", "range": "1d"}, headers=HEADERS, timeout=5).json()["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        closes = result["indicators"]["quote"][0].get("close") or []
        valid = [(ts, px) for ts, px in zip(timestamps, closes) if px is not None]
        ts, px = valid[-1]
        return _row("Yahoo chart 1m", ticker, started, price_hkd=float(px), provider_time=datetime.fromtimestamp(ts, timezone.utc).isoformat())
    except Exception as exc:  # noqa: BLE001
        return _row("Yahoo chart 1m", ticker, started, status="error", note=type(exc).__name__)


def tencent(ticker: str, code: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.get("https://qt.gtimg.cn/q=" + code, headers=HEADERS, timeout=5)
        response.encoding = "gbk"
        parts = response.text.split('="', 1)[1].rsplit('"', 1)[0].split("~")
        provider_time = parts[30] if len(parts) > 30 else None
        return _row("Tencent quote", ticker, started, price_hkd=float(parts[3]), provider_time=provider_time)
    except Exception as exc:  # noqa: BLE001
        return _row("Tencent quote", ticker, started, status="error", note=type(exc).__name__)


def eastmoney(ticker: str, secid: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": secid, "fields": "f43,f57,f58,f59,f86"},
            headers=HEADERS,
            timeout=5,
        ).json()["data"]
        scale = 10 ** int(payload.get("f59", 3))
        ts = int(payload["f86"])
        return _row("Eastmoney", ticker, started, price_hkd=float(payload["f43"]) / scale, provider_time=datetime.fromtimestamp(ts, timezone.utc).isoformat())
    except Exception as exc:  # noqa: BLE001
        return _row("Eastmoney", ticker, started, status="error", note=type(exc).__name__)


def futu_probe(ticker: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection(("127.0.0.1", 11111), timeout=0.25):
            status, note = "available", "Futu OpenD detected; use futu-api get_market_snapshot for licensed quotes."
    except OSError:
        status, note = "unavailable", "Futu OpenD is not running on localhost:11111."
    return _row("Futu OpenD", ticker, started, status=status, note=note)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readings", type=int, default=5)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("outputs"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for reading in range(1, args.readings + 1):
        jobs = []
        with ThreadPoolExecutor(max_workers=15) as pool:
            for ticker, ids in SYMBOLS.items():
                jobs.extend([
                    pool.submit(yahoo, ticker),
                    pool.submit(tencent, ticker, ids["tencent"]),
                    pool.submit(eastmoney, ticker, ids["eastmoney"]),
                ])
            for future in as_completed(jobs):
                item = future.result()
                item["reading"] = reading
                rows.append(item)
        for ticker in SYMBOLS:
            futu = futu_probe(ticker)
            futu["reading"] = reading
            rows.append(futu)
            rows.append({
                **_row("HKEX official", ticker, time.perf_counter(), status="manual_or_licensed", note="Authoritative exchange source; no anonymous public real-time quote API."),
                "reading": reading,
            })
        if reading < args.readings:
            time.sleep(args.delay_seconds)

    columns = ["reading", "observed_at_utc", "provider", "ticker", "price_hkd", "provider_time", "request_latency_ms", "status", "note"]
    with (args.output_dir / "live_source_readings.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir / "live_source_readings.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"readings": args.readings, "rows": len(rows), "output": str(args.output_dir)}, indent=2))


if __name__ == "__main__":
    main()
