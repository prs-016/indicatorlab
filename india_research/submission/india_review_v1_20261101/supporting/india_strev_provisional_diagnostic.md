> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# PROVISIONAL India academic_strev diagnostic

**Completed one user-approved diagnostic. No final Keep/Drop decision.**

Output directory: `archive:india_strev_PROVISIONAL_20261029T021955Z_21d1a038/`.
Dataset: `archive:india_session_phase4d_20261029T020413Z_05541bac/research_v3/`.
Dataset manifest SHA-256: `a99d6671002b8c15dc406d7b532556ee95cb96cb5503dd9e8555253d17e3ca42`.
Final calendar review SHA-256: `ff5ce2c688f80c71a933799d3f890f0e80866f77084dc61587bce68a989dad9d`.

## Method and authorization

The current user explicitly authorized one provisional diagnostic; the Vibe + Jack combination and portfolio parameters are developer-approved, not represented as explicit PM portfolio approvals. `src/india_diagnostic.py` invokes the original Vibe `agent/src/factors/zoo/academic/strev.py::compute` and `factor_analysis_core.py::compute_ic_series` through the existing isolated bridge. Portfolio accounting uses the existing `simulate_portfolio` adapted from Jack. No factor or accounting formula was changed.

The diagnostic runner accepts only the pinned dataset/review hashes, academic_strev and exact approved baseline. It reruns calendar/data/21-session checks and waives only exhaustive amendment-inventory certainty after explicit approval. Wrong dataset, review, strategy, configuration, missing sessions, unresolved date classifications and lag mismatches remain failures. Existing manifests and `calendar_certified=false` / `amendment_coverage_confirmed=false` are unchanged. This is an auditable diagnostic-only exception, not global certification.

Signals use the original inverse trailing 21-session return with cross-sectional z-scoring. The eight assigned NSE equities are ranked descending; the top two receive 50% targets, with ticker ordering for ties. The separate benchmark is ^NSEI. Signals occur at each W-FRI period's final session; execution is at a strictly subsequent eligible close. Weights drift between executions. Costs are 10 bps times absolute traded NAV, including initial entry. Risk-free and cash interest are zero; Sharpe uses sqrt(252) and sample daily standard deviation. No terminal liquidation, factor optimization or parameter search occurs.

Inputs are restricted to 1,011 sessions from December 3, 2020 through December 31, 2024: 21 warm-up sessions plus 990 evaluation sessions January 4, 2021 onward. January 1, 2021 is warm-up. No post-2024 observation or holdout data enters the run. Valid special sessions remain, including the January 20 recovery; no raw or derived source file was altered.

## Actual results — PROVISIONAL

| Metric | STREV portfolio | Nifty 50 benchmark |
|---|---:|---:|
| Cumulative return | 75.5389% net | 67.3032% |
| Annualized daily Sharpe | 0.843175 net | 0.978960 |
| Maximum drawdown | -16.6617% net | See daily benchmark NAV |

Gross strategy cumulative return before modeled turnover costs was **107.6286%**. The net portfolio exceeded benchmark cumulative return by **8.2357 percentage points**, while its daily Sharpe was lower. Neither comparison establishes a final strategy conclusion.

**Mean execution-aligned Spearman rank IC: 0.07338394**, from **207 valid completed execution intervals**, with zero undefined intervals. Each observation correlates all eight stocks' signal-date scores with their subsequent return from that target's actual execution close to the next execution close. It is a predictive cross-sectional metric, not portfolio return, and is not Sharpe or IC information ratio. The final execution has no completed subsequent rebalance interval and is excluded from IC. The separately saved auxiliary next-session IC is not the headline approved horizon.

| Accounting / sample | Count or value |
|---|---:|
| Evaluation daily observations | 990 |
| Input sessions including warm-up | 1,011 |
| Input stock closing observations | 8,088 |
| Rebalance executions | 208 |
| Nonzero-turnover executions | 208 |
| Stock trade legs (buys/sells/weight trims) | 581 |
| Total absolute NAV turnover | 167.780013 |
| Sum of daily cost fractions | 0.167780013 |
| First / last execution | 2021-01-11 / 2024-12-30 |

A trade leg is a nonzero stock weight adjustment, not a round trip or whole rebalance. The cost-fraction sum is 16.7780% across changing daily NAV bases; it is **not** a direct percentage-point deduction from terminal return. Net returns apply costs multiplicatively each day. The portfolio begins in cash; initial cash sessions enter daily Sharpe. The benchmark begins at the first evaluation close, with its initial daily return set to zero, matching the documented reporting convention.

No order was deferred or cancelled. The sole order-log entry is the terminal December 31 signal skipped because no later permitted execution exists. No post-cutoff terminal label or trade was manufactured.

## Quality and limitations

The analysis slice has **12 repeated-close flags**, all retained:

- ICICIBANK.NS: 2021-12-30 (1).
- SBIN.NS: 2021-10-22, 2022-03-08, 2022-12-20, 2022-12-22, 2023-05-17, 2023-06-05 (6).
- KOTAKBANK.NS: 2021-06-30, 2023-03-06, 2024-09-04, 2024-12-11 (4).
- AXISBANK.NS: 2022-11-22 (1).

These are observed repetitions, not proven bad prices. No missing-close, missing-volume, zero-volume or >20% adjusted daily-move flags occur in the required slice. The older full-history anomalies/reports remain preserved; restricting the approved input window is not repair or silent anomaly exclusion. No validity exclusion was needed inside this slice (`exclusion_ledger.json` is empty).

The reconstructed calendar matches all nine required histories exactly and all 7,920 stock/date lag checks passed. Exhaustive historical amendment/publication retrieval remains unproven; the reviewed residual uncertainty is accepted only for this diagnostic. A new concrete session contradiction would require review of affected results.

The **frozen Yahoo-adjustment vintage is not historically point-in-time**. Later corporate-action effects and inherited vendor normalization remain documented limitations, not a calendar failure. Benchmark comparison is also imperfect: Nifty 50 is a price index, while equity histories carry dividend adjustments. The fixed eight-stock assignment has selection/survivorship limitations; positive volume and a published close do not guarantee executable fills, particularly during short special sessions. Fractional holdings, flat turnover fees and no spread/impact/tax model are provisional assumptions. No significance claim or final retention decision is made.

## Tests and post-run checks

Before execution, the complete project-.venv suite passed **136 tests in 9.87 seconds**, with no failures or skips, including 16 new diagnostic-override regressions. Existing timing, original Vibe factor/IC integration, causal invariance, turnover, missing-data, calendar and adjustment regressions passed. No packages were installed.

After execution, an independent saved-artifact audit verified all original/evidence/source/output hashes, exact session counts and cutoff, all 207 execution-interval labels, all 208 strictly subsequent executions and top-two score selections, 581 trade legs with turnover/cost reconciliation, and recomputed net-return, cumulative-return and Sharpe identities. Strict certification flags and original dataset hashes remained unchanged. These checks did not rerun the strategy.

Exact executed commands:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m src.india_diagnostic --approved-diagnostic
```

The runner produces a unique directory each time; a repeat strategy experiment needs renewed authorization, since the present approval covered one run. The existing diagnostic has completed. `verify_saved_run.py` verifies its saved outputs without another backtest.

Saved artifacts include exact configuration, authorization/override, frozen dataset manifest and readiness review, calendar audits, used input closes/volumes/benchmark, factor scores, IC inputs/labels and IC series, daily returns/NAV, holdings, executions, stock trade legs, order log, exclusion ledger, quality flags, metrics, warnings, test/console logs, package/runtime/Git provenance, working source snapshots (including original Vibe factor/IC/base files), and SHA-256 artifact inventory. Reproduction depends on retained source evidence paths; the used input matrices and code snapshots are independently preserved with this run.

No other factors, final Keep/Drop decision, source-data alteration, commit, push or publication. Stop for user review.
