> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# India ten-strategy research comparison and provisional ILLIQ diagnostic

**PROVISIONAL — eight completed portfolio diagnostics, two non-evaluable applicability studies. No final Keep/Drop decisions.** This version adds the separately user-approved single `academic_illiq` diagnostic. The earlier seven-strategy comparison and all previous reports/results remain unchanged. No alternative price/volume convention was selected using portfolio returns.

## Ten-strategy comparison

Assignment order is preserved. IC means average execution-aligned cross-sectional Spearman correlation; net Sharpe means daily cost-adjusted portfolio mean / sample standard deviation × sqrt(252), zero risk-free. Cumulative returns span January 4, 2021–December 31, 2024 and are not annualized. Dashes mean no portfolio evaluation, not zero performance.

| # | Strategy | Research status | Mean rank IC | Net daily Sharpe | Net cumulative return | Executions / stock legs |
|---|---|---|---:|---:|---:|---:|
| 1 | `academic_strev` | PROVISIONAL backtest | 0.073384 | 0.843175 | 75.5389% | 208 / 581 |
| 2 | `alpha101_001` | PROVISIONAL backtest | -0.023759 | 0.076889 | -1.5932% | 208 / 698 |
| 3 | `alpha101_002` | PROVISIONAL backtest | 0.018146 | 0.498502 | 38.0712% | 207 / 689 |
| 4 | `alpha101_003` | Non-evaluable under current methodology | — | — | — | — |
| 5 | `alpha101_004` | Non-evaluable under current methodology | — | — | — | — |
| 6 | `alpha101_033` | PROVISIONAL backtest | 0.059466 | 0.823290 | 78.4805% | 208 / 725 |
| 7 | `alpha101_101` | PROVISIONAL backtest | -0.037382 | -0.151835 | -17.9156% | 208 / 725 |
| 8 | `alpha101_054` | PROVISIONAL backtest | 0.056246 | 0.776599 | 69.6519% | 208 / 724 |
| 9 | `alpha101_014` | PROVISIONAL backtest | 0.048654 | 0.382497 | 24.3375% | 208 / 708 |
| 10 | `academic_illiq` | PROVISIONAL backtest | -0.003106 | 0.748968 | 70.4904% | 208 / 491 |

**Nifty 50 price-index benchmark:** cumulative return **67.3032%**, daily annualized Sharpe **0.978960**. All eight archives use that benchmark convention; adjusted stock prices include dividend adjustments whereas the index is not total-return.

The two non-evaluable cases remain separate from the eight completed portfolios: #003 has 1,073/7,920 finite scores and no all-eight-eligible weekly dates; #004 has 193/209 ticker-tie-dependent weekly memberships and only 16 unique pairs. These are assignment-specific applicability findings, not final economic Keep/Drop decisions. The previous source reports remain authoritative and unchanged.

Original STREV and #001 use research_v3; STREV has its approved 21-session warm-up. The other six completed diagnostics use research_v4 and 25 prior sessions. No prior strategy was rerun for this table. #001 retains material tie dependence/one undefined IC; #002 retains four score NaNs, a skipped target and an extended IC horizon. Thus this is an archival comparison with explicit version/eligibility caveats, not a newly standardized rerun or significance ranking.

## Newly completed academic_illiq diagnostic

- Mean execution-aligned rank IC: **-0.003105590**, **207** valid intervals; none undefined.
- Annualized daily net Sharpe: **0.748968037**; benchmark **0.978960345**.
- Net cumulative return: **70.490427%**; gross **84.376576%**; benchmark **67.303244%**.
- Net maximum drawdown: **-21.612232%**.
- **990** daily observations, **208** executions, **491** stock trade legs; first execution **2021-01-11**, last **2024-12-30**.
- Absolute NAV turnover sum **78.259626674**; sum of per-execution cost fractions **0.078259627** at 10 bps per unit absolute NAV turnover.

The sum of cost fractions is a sum relative to each execution-day NAV, not total cash fees or a loss percentage of initial capital; it does not equal the gross-to-net compounded return difference. Near-zero negative cross-sectional rank IC can coexist with a positive long-only return: IC is not portfolio Sharpe or absolute market exposure. No profitability, statistical significance or final selection inference follows from these provisional observations.

Immutable output: `archive:india_academic_illiq_PROVISIONAL_20261029T053314Z_128ef15c/`.
Comparison/evidence directory: `archive:india_ten_strategy_comparison_PROVISIONAL_20261029T053021Z/`.
Each has an artifact inventory. The ILLIQ directory records configuration/approval, dataset/readiness copies, original metadata and source hashes/snapshots, proxy evidence and official checks, sensitivity disclosures, scores/NaNs, IC scores/forward labels/intervals, daily gross/net/benchmark NAV, holdings, executions, trade legs/costs, order log, quality flags, warnings and completed status. The comparison directory contains full tests, actual invocation, independent reconciliation and CSV/JSON records for all ten slots.

## Unchanged definition, declared India convention and provenance

Original code: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/academic/illiq.py`, SHA-256 `a2bab2dce9549f1db7274d8699d41b8fa306c392f3c96fd1e46ac0bba0b6edc6`; Vibe HEAD `7f6908b7e1b95d971f4151bfaf2382e2ce9485cf`. Its original safe division, 21-complete-ratio rolling mean and cross-sectional sample-standard-deviation z-score are unchanged. Higher scores still mean less liquid; the top two original scores are bought. No sign inversion or replacement score was introduced.

**Adjusted-INR closing price × frozen vendor-unit volume is a closing-price turnover proxy, not actual NSE exchange turnover, USD traded value, or nominal historical traded value.** Actual exchange traded value sums trades at their individual prices and is recorded separately in the official evidence. Cash-dividend scaling remains in this proxy. Split/bonus price and quantity normalization should offset in products under the declared units, but all historical quantities are not independently certified.

**India use is a developer-approved research metadata exception**, explicitly accepted by the current user instruction. The country-agnostic computation is reused despite the unchanged upstream metadata lacking `equity_in`. This is not upstream endorsement or explicit PM approval of the factor. `india_metadata_exception.json`, approval and provenance retain that distinction; upstream country tags and original dollar-volume terminology are not rewritten.

Dataset: `archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/research_manifest.json`, SHA-256 `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`.
Readiness review: `india_research/reports/india_phase2_signal_readiness_review.md`, SHA-256 `055cebcac8f176f2ad31bcf80bb29a3d019fd516ad9deb085e41391f8b82f1f3`.
Readiness inventory: `archive:india_phase2_signal_readiness_20261029T050613Z/artifact_hashes.json`, SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`.
Proxy basis review: `archive:india_phase2_integration_20261029T045327Z/turnover_basis_review.json`, SHA-256 `ec86d435e80810798df23c1158f2d522424a4e7b1ea5bfd0e7f16f113276b4c7`.

The runner binds this evidence to actual close/volume matrices and verifies all nine history hashes, original factor/helper/IC sources, current structural calendar, twelve volume corrections and 24 quantity anchors. It verifies all 256 current sampled price × volume products against the saved official-record expectations across 32 dates and the 32 original archive hashes. All pass, maximum relative discrepancy **2.656182248594874e-7** at `8 * float32 epsilon` tolerance. This reuses the previously independently parsed official records; no new exchange retrieval or action reconstruction was claimed. No downloaded data or source dataset was modified.

## Timing, warm-up and accounting audit

- Exact eight assigned NSE stocks; `^NSEI` separate. The input contains 1,015 sessions, including 25 prior sessions from November 26, 2020 through January 1, 2021. Evaluation has 990 sessions through December 31, 2024.
- Original ILLIQ requires 22 bars (one return predecessor plus 21 ratios). Its 168 warm-up NaNs occur before evaluation; all 7,920 evaluation scores are finite, no infinities or score filling. There are no study-input zero volumes or zero denominators. Synthetic tests preserve 21-session NaN propagation after hypothetical zero volume and preserve NaNs at zero cross-sectional dispersion.
- All 209 weekly W-FRI candidate rows are eight-score eligible with unique top-two membership. The terminal candidate is unexecutable, leaving 208 executions. No executed membership depends on ticker tie breaking.
- Saved prefix/minimum-window checks pass and current scores reproduce all readiness scores. Every execution was independently checked against the next input session, with 50/50 target weights matching the unique audited pair and positive volume.
- Every one of 207 IC labels matches the all-eight adjusted-close ratio from the actual execution close to the next actual execution close. Signal date precedes entry, which precedes exit; no unfinished final label, post-2024 observation or October 2025 onward holdout is used.
- Daily net returns reconcile to `(1+gross)*(1-cost)-1`; cost fractions to turnover × 0.001; NAV to daily compounding; Sharpe to saved net mean/sample standard deviation × sqrt(252). Signed trade legs reconcile to aggregate turnover/costs.
- Twelve repeated-close flags are preserved as observed quality flags, not automatically classified as bad prices or silently excluded. Original raw/snapshot artifacts are untouched.

All saved timing/accounting checks passed in `saved_illiq_reconciliation.json`. The diagnostic waives only exhaustive historical calendar-inventory certainty, within the same approved provisional scope; all material session, lookback, units and cutoff gates remain active. Strict manifest certification flags remain false and unchanged.

## Explicit limitations accepted for this diagnostic

- **51/209 dividend-sensitive** candidate memberships when the saved dividend factor is removed, and **31/209 normalization-sensitive** memberships when fixed terminal cash normalization is removed. Those are pre-existing signal-only diagnostics; no alternative-convention portfolio or return-based convention choice was run.
- Frozen Yahoo history is a retrieval-time adjustment vintage, **not historically point-in-time data**. Causal factor timing does not establish that future-adjusted inputs were available historically.
- Unresolved pre-July-2023 Reliance non-split normalization remains; cancellation in sampled price × volume products does not settle the adjusted-return numerator. The small March 1, 2024 Kotak quantity discrepancy remains untouched. Sampled official checks do not certify every historical daily quantity.
- The two-name illiquidity exposure can be concentrated. The signal audit counted Kotak in 127/209 candidate pairs and no Reliance/HDFC appearances. Fractional closes and 10-bps flat costs do not model spreads, capacity, impact or taxes, which may matter for an illiquidity-oriented factor.
- The benchmark is a price index while adjusted stocks include dividend adjustments. Initial cash days are included, cash interest/risk-free are zero and there is no terminal liquidation.

## Verification, changed files and next review gate

Complete suite executed before evaluation:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

**353 passed in 50.10 seconds, no failures/skips/warnings**, including 24 new offline synthetic ILLIQ scope/proxy tests. They verify explicit single-factor permission, exact settings/hashes/warm-up, unsupported currency or turnover interpretation, sensitivity disclosures, material validation failures, repeat prevention and current-product/source checks. Existing formula, causality, missingness and portfolio tests all remain passing.

**1,036 earlier files verified unchanged**, including all seven prior portfolio outputs, prior comparisons/readiness reports, original data/evidence and existing source/tests. All eight completed portfolio artifact inventories verify. No previous strategy was rerun.

New reusable source/test: `src/india_illiq_diagnostic.py`, `tests/test_india_illiq_diagnostic.py`. The runner reuses original factor/IC and portfolio composition plus the tested trade ledger/evidence helpers; it does not broaden the consumed four-factor approval. Documentation updates: AGENTS.md, India context, methodology and weekly tracker. This new ten-strategy report supersedes the earlier comparison for current tracking while preserving that historical report unchanged.

The single ILLIQ approval is consumed. Stop for review; no repeats, new convention, final Keep/Drop, commit, push or publication are authorized.
