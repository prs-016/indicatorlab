"""Acquire bounded attention inputs separately from preregistration and backtesting."""

import argparse
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from src.hk.week4.features import attention
from src.hk.week4.public_data import DATA, ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=["attention"], default="attention")
    p.parse_args()
    spec = json.loads((ROOT / "config/hk_week4_research.json").read_text())
    intervals = pd.concat(
        [
            pd.read_csv(ROOT / "config/hk_wiki_title_intervals.csv"),
            pd.read_csv(ROOT / "config/us_wiki_title_intervals.csv"),
        ],
        ignore_index=True,
    )
    rows = []
    for market in spec["markets"].values():
        for ticker in market["symbols"]:
            f = attention(ticker, intervals)
            row = {
                "ticker": ticker,
                "weeks": len(f),
                "first": str(f.index.min().date()),
                "last": str(f.index.max().date()),
                "missing_views": int(f.views.isna().sum()),
                "sha256": hashlib.sha256(
                    (DATA / "attention" / (ticker + ".parquet")).read_bytes()
                ).hexdigest(),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
    (DATA / "attention_acquisition.json").write_text(
        json.dumps(
            {"completed_at_utc": datetime.now(UTC).isoformat(), "records": rows},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
