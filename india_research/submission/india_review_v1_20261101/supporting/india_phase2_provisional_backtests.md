> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# India Phase 2 provisional portfolio diagnostics and seven-strategy comparison

**PROVISIONAL — no final Keep/Drop decision.** The four specifically approved diagnostics completed once each: `alpha101_033`, `alpha101_101`, `alpha101_054`, `alpha101_014`. `academic_illiq` remains unrun. No earlier strategy was rerun or migrated to a new dataset.

## Consolidated saved results

The table preserves assignment/approval order rather than ranking by realized performance. IC is mean execution-aligned cross-sectional Spearman correlation across eight names; Sharpe is daily cost-adjusted portfolio mean / sample standard deviation × sqrt(252), zero risk-free. They measure different things. Returns are cumulative over January 4, 2021–December 31, 2024, not annualized.

| Strategy | Dataset / prior sessions | Mean rank IC | Valid IC intervals | Net daily Sharpe | Net cumulative return | Executions | Stock trade legs |
|---|---|---:|---:|---:|---:|---:|---:|
| `academic_strev` | research_v3 / 21 | 0.073384 | 207 | 0.843175 | 75.5389% | 208 | 581 |
| `alpha101_001` | research_v3 / 25 | -0.023759 | 206 | 0.076889 | -1.5932% | 208 | 698 |
| `alpha101_002` | research_v4 / 25 | 0.018146 | 206 | 0.498502 | 38.0712% | 207 | 689 |
| `alpha101_033` | research_v4 / 25 | 0.059466 | 207 | 0.823290 | 78.4805% | 208 | 725 |
| `alpha101_101` | research_v4 / 25 | -0.037382 | 207 | -0.151835 | -17.9156% | 208 | 725 |
| `alpha101_054` | research_v4 / 25 | 0.056246 | 207 | 0.776599 | 69.6519% | 208 | 724 |
| `alpha101_014` | research_v4 / 25 | 0.048654 | 207 | 0.382497 | 24.3375% | 208 | 708 |

**Common Nifty 50 price-index benchmark:** cumulative return **67.3032%**, daily annualized Sharpe **0.978960**. Benchmark returns start at zero on the first evaluation date, matching the established baseline. No benchmark costs are imposed. Adjusted equities include dividend adjustments; this benchmark is not a total-return index.

All four new runs contain 990 daily observations and 1,015 input sessions, including 25 prior sessions beginning November 26, 2020. Each has 209 all-eight-finite, uniquely selected weekly candidates, 208 executions and 207 defined IC intervals. First execution is January 11, 2021; last is December 30, 2024. The terminal December 31 candidate is not executed; no post-cutoff label is invented. Holdings are marked through December 31 without forced liquidation. No executed membership depends on ticker tie breaking.

## Gross returns, costs and drawdowns

| New factor | Gross cumulative return | Net cumulative return | Net maximum drawdown | Absolute NAV turnover sum | Sum of cost fractions |
|---|---:|---:|---:|---:|---:|
| `alpha101_033` | 143.6637% | 78.4805% | -26.3874% | 311.037535 | 0.311038 |
| `alpha101_101` | 11.9828% | -17.9156% | -36.9498% | 310.330179 | 0.310330 |
| `alpha101_054` | 131.3530% | 69.6519% | -26.4314% | 309.930496 | 0.309930 |
| `alpha101_014` | 66.8837% | 24.3375% | -26.2193% | 294.055054 | 0.294055 |

Costs equal absolute traded NAV weight × 0.001 at each execution. The last column sums fractions of each execution day’s NAV; it is neither a cash amount nor a percentage loss of initial capital. Gross-to-net compounded return differences therefore do not equal this simple sum. Small rebalancing trades caused by weight drift are included; trade legs are individual buys/sells, distinct from weekly executions.

## Approved methodology and exact input evidence

- Original Vibe factor definitions and rank-IC implementation; existing Jack-inspired sequential portfolio accounting. No factor, cost, ranking or fill rule changed.
- Eight assigned NSE equities, separate `^NSEI`; 2021–2024 evaluation, 25 common prior sessions; no post-2024 market observations or holdout.
- Weekly W-FRI final-session signal, descending score/ticker tie rule, top-two 50/50 long-only targets; execution at the strictly subsequent eligible close. New holdings earn returns only after execution.
- Ten-basis-point absolute-NAV turnover costs, fractional targets, zero cash interest/risk-free and no terminal liquidation.
- IC labels run from an actual execution close to the next actual execution close, using the earlier signal score and all eight stock returns. No last unfinished IC interval is manufactured.

Input manifest: `archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/research_manifest.json`.
SHA-256: `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`.
Signal readiness: `india_research/reports/india_phase2_signal_readiness_review.md`, SHA-256 `055cebcac8f176f2ad31bcf80bb29a3d019fd516ad9deb085e41391f8b82f1f3`.
Readiness artifact inventory: `archive:india_phase2_signal_readiness_20261029T050613Z/artifact_hashes.json`, SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`.

Before each run, `src/india_phase2_diagnostic.py` verifies those hashes, all readiness/package artifacts, the original Vibe factor/helper/IC hashes, exact baseline settings and nine data histories. It reparses research_v4 quantity evidence (12 verified corrections, 24 anchors), reconstructs the 1,015-session calendar and checks zero material calendar/clock discrepancies. Each factor’s three saved causal prefix checks and minimum-window check must pass. Newly calculated scores match its saved readiness scores across all 1,015 input rows; the complete regression suite also verifies causal perturbations. No-look-ahead checks support algorithmic timing, not historical point-in-time availability of the frozen adjustments.

The runner records a factor/dataset/review-bound provisional exception only for exhaustive historical calendar-inventory certainty, consistent with the explicit diagnostic approval. It does not change manifest certification flags or waive missing-session/clock checks. ILLIQ, changed settings and reuse after any factor invocation are rejected. A documented preflight failure before any invocation may be resumed without consuming an additional portfolio evaluation.

## Separate immutable experiment directories

- `alpha101_033`: `archive:india_alpha101_033_PROVISIONAL_20261029T052028Z_88f535b9/`.
- `alpha101_101`: `archive:india_alpha101_101_PROVISIONAL_20261029T052033Z_92cb90a5/`.
- `alpha101_054`: `archive:india_alpha101_054_PROVISIONAL_20261029T052039Z_b9fa136d/`.
- `alpha101_014`: `archive:india_alpha101_014_PROVISIONAL_20261029T052044Z_76d8ca9d/`.

Each completed directory has its own artifact inventory, exact configuration and approval record, readiness/calendar preflight, copied dataset/reviews, original factor metadata/hashes and source snapshots, input OHLCV/benchmark, scores and missingness, weekly candidates, IC scores/labels/intervals, daily gross/net/benchmark NAV, holdings, executions, signed trade legs/costs, order log, quality flags, warnings and metrics. Status is completed/PROVISIONAL. No existing experiment directory was overwritten.

Batch evidence and CSV/JSON comparison: `archive:india_phase2_comparison_PROVISIONAL_20261029T051458Z/`. The full test log precedes the four evaluations; per-run inventories are pinned in `verified_run_inventories.json`. `saved_result_reconciliation.json` independently checks every saved execution, target, return label, daily accounting identity, cost, NAV and Sharpe. All checks passed.

## Limitations and per-factor interpretation

- **#033:** all-eight signal coverage and unique weekly selection; no membership changes in the tested adjustment sensitivities. Its positive IC and measured returns are provisional observations, not evidence of future profitability.
- **#101:** original `(high-low+0.001)` denominator remains unchanged. The fixed 0.001 is price-unit dependent; tested scales changed magnitudes but no selections. Negative observed IC/return/Sharpe are preserved without a Keep/Drop label.
- **#054:** original fifth powers and denominator are unchanged; no invalid/zero denominator occurred in this evaluation. Flat bars would retain original NaNs. No price-basis membership changes were measured in the readiness diagnostics.
- **#014:** dividend adjustment convention changed 5/209 weekly memberships in the saved signal audit. This run retains the predeclared adjusted basis and verified volume corrections; no convention was selected by portfolio returns. Correlation uses raw open/volume windows, not the degenerate rank inputs of #003.
- **Common data:** frozen Yahoo-adjustment vintage is not historically point-in-time. Unresolved pre-July-2023 Reliance normalization and the small Kotak quantity discrepancy remain disclosed. The 12 repeated-close flags in each new input are retained; they are observations, not automatically confirmed bad prices. No anomaly was repaired or silently excluded.
- **Common modeling:** fixed eight-stock basket, fractional holdings, positive-volume/closing-price fill proxy, flat turnover costs; no spread, impact, tax or market-capacity model. Exhaustive calendar-amendment inventory is not certified.
- **Comparison limits:** older STREV/#001 use research_v3; STREV has its original 21-session warm-up. #002 and the new four use research_v4 with 25 prior sessions. Price histories and study period are preserved, but this is an archival comparison, not a newly standardized rerun. #001 retains material ticker-tie dependence and one undefined IC interval; #002 retains four signal NaNs, one skipped target and an extended IC interval. All seven metrics remain provisional; no significance/multiple-testing claim is made.
- **Excluded from portfolio evaluation:** #003 and #004 retain their documented non-evaluable/unsuitable findings; ILLIQ retains conditional signal readiness and lacks portfolio approval. No new factor or ILLIQ evaluation ran.

## Verification and interrupted preflight evidence

Final complete command:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

**329 passed in 49.59 seconds; no failures, skips or warnings.** Twenty-nine new offline synthetic cases in `tests/test_india_phase2_diagnostic.py` cover the four-factor approval boundary, exact scope/evidence/settings, calendar/readiness/causality gates, volume anchors, repeat prevention, drift/cost reconciliation, execution cutoffs and optional CSV-field serialization.

The first #033 attempt stopped during strict preflight JSON serialization because optional causality CSV fields contained NaN. It invoked neither factor compute nor portfolio accounting. Its approval/configuration files, stack trace, source version and `preflight_failed_factor_not_invoked` status remain preserved in a separate uniquely named directory. The helper now records optional fields as JSON null. The 327-test initial suite, 328-test fix suite and final 329-test suite are preserved; only the final suite preceded successful evaluations. This was one completed evaluation per approved factor, not a performance-driven rerun.

**773 prior files verified unchanged**, including all previous datasets, reports, source/tests, saved strategy results and archived evidence. The four new successful inventories also verify independently. No original data, formula or prior performance result changed. Source additions are only the scoped runner and its tests; AGENTS.md, project context, methodology and weekly tracker are updated with the completed status.

Stop for user review. The four single-run approvals are consumed; no repeats, ILLIQ run, final Keep/Drop, commit, push or publication are authorized.
