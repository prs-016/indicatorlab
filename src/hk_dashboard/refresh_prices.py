"""Refresh one coherent Yahoo price vintage per HK stock for display only."""

from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

from src.hk_dashboard.paths import display_root, names
from src.hk_dashboard.refresh import save


def run(output, symbols=None):
    """Write new display Parquets atomically; preserve old data on provider failure.

    Adjusted and nominal prices come from the same full-history response. No
    forward fill, volume rescaling or historical-vintage concatenation occurs.
    """
    destination = output / "prices"
    destination.mkdir(parents=True, exist_ok=True)
    report = {
        "as_of": datetime.now(UTC).isoformat(),
        "display_only": True,
        "stocks": {},
    }
    chosen = symbols or list(names())
    for index, code in enumerate(chosen, 1):
        try:
            frame = yf.Ticker(code).history(
                period="max", auto_adjust=False, actions=True, raise_errors=True
            )
            required = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
            if (
                frame.empty
                or not required.issubset(frame.columns)
                or frame.index.has_duplicates
            ):
                raise ValueError("Missing or duplicate Yahoo price observations")
            frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
            # Intraday quotes are separate; daily charts end at the prior HK day.
            today = pd.Timestamp.now(tz="Asia/Hong_Kong").date()
            frame = frame[frame.index.date < today].sort_index()
            if frame.empty:
                raise ValueError("No completed daily bars")
            tmp = destination / f".{code}.tmp.parquet"
            frame.to_parquet(tmp)
            os.replace(tmp, destination / f"{code}.parquet")
            result = {
                "rows": len(frame),
                "start": str(frame.index.min().date()),
                "end": str(frame.index.max().date()),
            }
        except Exception as exc:  # noqa: BLE001 - isolate any provider failure and retain cache
            result = {"error": type(exc).__name__}
        report["stocks"][code] = result
        save(output / "prices_status.json", report)
        print(
            {"done": index, "total": len(chosen), "symbol": code, **result}, flush=True
        )
        time.sleep(0.3)
    return report


def main():
    """Refresh display prices independently from any strategy/research pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*")
    args = parser.parse_args()
    run(display_root(), args.symbols)


if __name__ == "__main__":
    main()
