# India Week 3 research — offline execution interface

The [review package](../india_research/submission/week3_complex_v1_2_20261123/README.md)
contains actual US metrics, frozen specifications, ablations, 1,200 completed null
metrics, a complete current-trial audit projection and Strategy Log import rows.
It includes no licensed source prices or attention corpus. India is not evaluated.

Use the project virtual environment and existing requirements. IndicatorLab and
Vibe-Trading both use a package named src: preserve the subprocess isolation.
Configure an existing Vibe checkout explicitly; do not install a second strategy
framework or Microsoft Qlib. Example (replace the path with your checkout):

```bash
VIBE_TRADING_ROOT=/path/to/Vibe-Trading python -B -m pytest \
  tests/test_india_week3_strategies.py tests/test_india_week3_evaluation.py \
  tests/test_india_week3_framework.py tests/test_india_week3_integration.py \
  tests/test_india_week3_wiki_strategies.py tests/test_india_week3_randomization.py \
  tests/test_india_week3_wcr_nulls.py tests/test_india_watm_us.py \
  tests/test_india_week3_market_adapter.py tests/test_week3_published_evidence.py \
  -q -p no:cacheprovider
```

Without VIBE_TRADING_ROOT, only original-Vibe integration cases skip explicitly.
The private-input join also skips when licensed source packages are absent; this
is not a historical coverage or performance test. Synthetic unit fixtures are
never reported as strategy returns. Source-level frozen rule checks run offline.

`prepare_wiki_snapshots` joins verified closed-session OHLCV, benchmark bars and
existing lagged Wikipedia features. `build_wiki_orders(strategy=...)` handles all
three frozen versions; `evaluate_wiki_run` uses the existing accounting, original
Vibe IC, matched null replays, ablations and trial ledger. Callers provide the
explicit Vibe root/interpreter, approved input provenance and initial cash. India
fees are bound through OriginalIndiaCosts, not guessed turnover rates.

For authorized private Tiingo/Wikipedia packages, the existing CLI performs
**preflight only**, with no provider calls or historical trades:

```bash
python -B -m src.india_watm_us --tiingo /path/to/tiingo-snapshot \
  --wiki /path/to/wiki-snapshot --initial-cash 100000
```

Use `--help` for existing availability/registration-record arguments. A run
requires explicit accepted timing/provenance and execution authorization. Do not
interpret this old preflight's registration blocker as proof that WATM was never
registered: the published status file records the later user confirmation.

Frozen Week 3 train/test/holdout boundaries remain 2016-06-01..2021-12-31,
2022-01-01..2025-09-30, and exclusion from 2025-10-01. Shared main's newer global
configuration is untouched. Never extend these studies to the newer cutoff,
load post-cutoff source observations and then filter them, or run incomplete
India series as if missing dates had zero returns.
