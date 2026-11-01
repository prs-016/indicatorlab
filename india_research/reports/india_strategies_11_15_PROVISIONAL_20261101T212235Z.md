# PROVISIONAL — India strategies 11–15

All five approved Qlib158 factors passed readiness and completed exactly one diagnostic each on unchanged research_v4. Each original Vibe implementation was invoked once on real data; its saved score cache fed both readiness and the existing portfolio simulator. No convention, direction or parameter was selected from returns. No final Keep/Drop decision is made.

| # | Registry ID | Mean rank IC | Net Sharpe | Net cumulative return | Minus Nifty 50 (pp) | Cost-fraction sum | Trade legs |
|---|---|---:|---:|---:|---:|---:|---:|
| 11 | `qlib158_std20` | 0.008742 | 0.501045 | 38.2745% | -29.0287 | 0.166326 | 580 |
| 12 | `qlib158_rsv20` | -0.055441 | -0.236678 | -23.6375% | -90.9408 | 0.216736 | 631 |
| 13 | `qlib158_sump20` | -0.061997 | -0.033481 | -9.9512% | -77.2544 | 0.151167 | 565 |
| 14 | `qlib158_wvma20` | -0.008857 | 0.596890 | 45.4276% | -21.8756 | 0.144001 | 557 |
| 15 | `qlib158_cord10` | -0.088912 | -0.052153 | -11.5646% | -78.8678 | 0.234068 | 648 |


The saved Nifty 50 price-index benchmark returned **67.303244%**, with daily annualized Sharpe **0.978960345**. All five net returns and Sharpes are below it. Benchmark differences are cumulative-return percentage points, not annualized alpha. Cost-fraction sums aggregate fees over changing NAV bases; they are not percentage-point return deductions or cash fees.

## Readiness and timing

Every factor has **7,920/7,920 finite evaluation scores**, zero evaluation NaNs/infinities, **209/209 all-eight eligible and uniquely identified top-two candidates**, zero daily exact ties, and zero weekly boundary or near-boundary ties at 1e-10. There are 208 nonterminal targets/executions and 207 defined execution-aligned IC intervals per factor. No target was skipped for missing signals; the last candidate lacks a subsequent pre-cutoff execution session.

The only NaNs are initial warm-up cells: STD/RSV 152 each, SUMP/WVMA 160 each, CORD 80. STD/RSV require 20 input rows; SUMP/WVMA require 21; CORD requires 11. Upstream declared warm-ups remain 20/20/20/20/10. The common 25 prior sessions cover all five, with no evaluation warm-up shortfall. Original computations emitted no numerical warnings; saved outputs satisfy their mathematical ranges. Parent CSV parsing emitted five deprecation warnings about `float_precision`; the round-trip cache checks were exact and results were unaffected.

Evaluation contains 990 sessions, January 4, 2021–December 31, 2024, plus 25 prior sessions starting November 26, 2020. First execution is January 11, 2021; last is December 30, 2024. All signals, inputs, executions and IC labels end by December 31, 2024. The October 1, 2025 onward holdout was not accessed.

## Unchanged methodology

Eight assigned NSE stocks, separate `^NSEI` benchmark; final session of each W-FRI period, descending original scores, top two 50% targets, ascending-ticker exact-tie rule, long-only fractional weights that drift. Execute strictly at the subsequent eligible close, with positive volume for changed holdings. Cost is 10 bps times absolute traded NAV including entry/drift rebalancing; daily net return is `(1+gross)*(1-cost_fraction)-1`. Initial cash earns zero and remains in Sharpe; no terminal forced liquidation.

IC is the original Vibe cross-sectional Spearman rank IC over all eight stocks, using signal scores against actual execution-close to next successful execution-close returns. The unfinished final label is excluded. Sharpe is daily net mean divided by sample standard deviation times sqrt(252), zero risk-free; cumulative return is compounded net wealth minus one. No additional Qlib installation, downloads, parallel infrastructure or alternate real-data factor scoring was needed.

## Material limitations and interpretation

- All five are interpretable under this baseline, but financial predictive validity is unproven. STD has a small positive IC; the other four have negative IC. WVMA's positive return alongside negative IC does not establish alpha. Original directions remain unchanged.
- Frozen Yahoo adjusted OHLC is a retrieval-time vintage, **not historically point-in-time**. Cash-dividend and other time-varying adjustments can affect rolling signals; no new alternative-basis selection counts were computed. Previously reported ILLIQ/Alpha101 sensitivity counts must not be transferred to these factors.
- The existing verifier reconfirmed all **12 volume conversions and 24 exact quantity anchors**, preserving every other CSV token. Study inputs have no missing/zero required fields. This supports the declared v4 volume basis without certifying the full daily tape. Reliance's pre-July-2023 non-split normalization and the small Kotak quantity discrepancy remain unresolved research limitations accepted for these provisional runs; no new material input failure was identified by the scoped checks.
- A constant per-stock volume scale largely cancels from WVMA, but a scale change inside a rolling window does not. CORD's original `volume+1` makes unit invariance inexact. Synthetic unit-change tests verify this distinction. WVMA uses zero volume as zero product; CORD uses its original +1; neither applies ILLIQ's zero-turnover rule. These inputs contain no zero volumes.
- Material calendar/clock checks passed again. Strict dataset certification flags remain false; the dataset/review-bound diagnostic exception waives only exhaustive amendment-inventory certainty. It does not waive missing sessions, price integrity or cutoff checks.
- The benchmark is a price index while stocks have dividend-adjusted histories. A fixed eight-stock basket and two-stock concentration, frozen volume vintage, close-fill proxies and flat costs omit survivorship/membership verification, spread, impact, taxes and capacity. No out-of-sample inference or multiple-testing adjustment is established.

## Evidence and verification

The [Strategy Log](india_strategy_log_11_15_PROVISIONAL_20261101T212235Z.md) contains exact formulas, dependencies, registry/source evidence and per-run inventory hashes; [CSV](india_strategy_log_11_15_PROVISIONAL_20261101T212235Z.csv) preserves full precision and unit definitions. The [batch directory](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/README.md) links separate immutable factor directories, [comparison](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/comparison.csv), [shared provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/provenance.json), [calendar/volume preflight](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/shared_preflight.json), [saved-output checks](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/verification.json) and [complete test log](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/complete_test_suite.log).

The complete automated suite passed **388 tests in 64.79 seconds** (353 prior + 35 new); no failures/skips. Focused development regressions passed 35 cases. Saved score caches, execution timing, IC boundaries/rank calculations, NAV, costs, net Sharpe and benchmark identities reconcile without re-scoring factors or rerunning portfolios. All **1,293 pre-existing protected files**—datasets, prior results/reports, submission package and prior source/tests—remain byte-for-byte unchanged. Changes are two new source modules, one test module, three documentation updates and these new reports/artifacts. AGENTS.md records the new workflow; no dependency changed.

Prior findings remain eight original PROVISIONAL backtests plus two non-evaluable factors, preserved in the [ten-strategy comparison](india_ten_strategy_provisional_comparison.md). With these five additions, the research scope is fifteen investigated factors, thirteen provisional portfolios and two non-evaluable cases. Review the new results and limitations before deciding next research; no further run, final label, commit/push or publication is authorized.
