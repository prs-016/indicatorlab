# Actual HSI Alpha101 benchmark

Local completion: 2026-11-12T08:06:38Z. Period 2016-06-01 through 2025-09-30.
100 factors tested, one skipped (alpha101_097: >95% NaN). All 85 Wikipedia
constituents loaded through the shared HK chain; zero missing names.
Wikipedia revision 1377881667, source date 2026-10-01. Sector coverage 100%.
Top reported mean IC: alpha101_054, 0.0408; IC IR 0.2668 (rounded report values).

This is an exploratory factor-IC benchmark, not a costed strategy Sharpe/KEEP
test. Current Wikipedia membership is survivorship biased and lags the separate
official 95-name operational snapshot. Tencent/Eastmoney/Yahoo data was observed;
mixed price/volume adjustment basis is disclosed in panel metadata.

Working command from repository root, with the project's dependencies installed:

```python
from cli.main import main
raise SystemExit(main(["alpha", "bench", "--zoo", "alpha101", "--universe", "hsi",
                      "--period", "2016-06-01/2025-09-30", "--top", "20", "--yes"]))
```

Use `PYTHONPATH=agent` and optionally set VIBE_TRADING_HOME to an isolated runtime
directory. The argparse main entry worked on Python 3.14; the separate Typer
module entry encountered an existing unresolved `typer` annotation error.
No raw prices, model files or generated benchmark HTML are in this package.
