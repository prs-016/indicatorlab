"""Run the real-source HSI benchmark and report annual observed-price coverage.

Use --vibe-root to point to a checkout containing the Week 4 B2 patch. Roster
validation is never bypassed. A failed benchmark writes evidence, not statistics.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vibe-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.vibe_root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / 'agent'))
    os.environ['VIBE_TRADING_HOME'] = str(output / 'runtime')
    from src.tools.alpha_bench_tool import run_alpha_bench, _load_universe_panel

    period = '2016-01-01/2026-10-31'
    result = run_alpha_bench(universe='hsi', zoo='alpha101', period=period, output_dir=str(output / 'reports'))
    evidence = {
        'attempted_at_utc': datetime.now(timezone.utc).isoformat(),
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'period': period,
        'source_policy': 'real Wikipedia request; strict published-count validation; no fallback or bypass',
        'result': result,
    }
    (output / 'benchmark_attempt.json').write_text(json.dumps(evidence, indent=2, default=str) + '\n')
    if result.get('status') != 'error':
        panel = _load_universe_panel('hsi', period)
        close = panel['close']
        rows = []
        for year in range(2016, 2027):
            observed = close.loc[close.index.year == year]
            rows.append({'year': year, 'instruments_with_observed_close': int(observed.notna().any(axis=0).sum()), 'observed_dates': len(observed), 'non_missing_close_cells': int(observed.notna().sum().sum()), 'missing_close_cells': int(observed.isna().sum().sum())})
        with (output / 'annual_coverage.csv').open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == '__main__':
    main()
