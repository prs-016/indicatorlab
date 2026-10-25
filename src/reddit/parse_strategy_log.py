"""Parse the JSON block printed by `vibe-trading alpha compare` into a comparison table.

Only metrics the tool actually printed are reported. `alpha compare` scores each
alpha by its daily cross-sectional Spearman rank IC against next-day close-to-close
returns (Vibe-Trading src/tools/alpha_bench_tool.py::_compute_forward_returns and
src/factors/factor_analysis_core.py). It does not produce Sharpe ratio, cumulative
return, or drawdown.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

from src.reddit import settings

DESCRIPTIONS = {
    "alpha101_002": "-corr(rank(delta(log(volume),2)), rank((close-open)/open), 6)",
    "alpha101_003": "-corr(rank(open), rank(volume), 10)",
    "alpha101_006": "-corr(open, volume, 10)",
    "alpha101_012": "sign(delta(volume,1)) * -delta(close,1)",
    "alpha101_013": "-rank(cov(rank(close), rank(volume), 5))",
}


def parse(log_path: Path) -> pd.DataFrame:
    text = log_path.read_text()
    m = re.search(r"^\{.*?^\}", text, re.S | re.M)
    if not m:
        raise SystemExit(f"no JSON result block in {log_path}")
    res = json.loads(m.group(0))
    df = pd.DataFrame(res["ranking"])
    df["formula (Kakushadze 2015)"] = df["id"].map(DESCRIPTIONS)
    df["universe"] = res["universe"]
    df["period"] = res["period"]
    df["status"] = res["status"]
    df["failed_ticker_downloads"] = len(re.findall(r"^yahoo failed for", text, re.M))
    df["source_log"] = log_path.name
    return df


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else (settings.STRATEGY_LOGS / "alpha_compare_latest.log").resolve()
    out = parse(path)
    out.to_csv(settings.STRATEGY_LOGS / "alpha101_comparison.csv", index=False)
    print(out[["rank", "id", "ic_mean", "ic_std", "ir", "ic_positive_ratio", "ic_count"]].to_string(index=False))
