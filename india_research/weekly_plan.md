# IndicatorLab — India Weekly Research Plan

## 1. Current scope and authority

**Week starting:** October 26, 2026
**Market:** India (NSE)
**Working branch:** `india`
**Methodology:** Original Vibe-Trading factors/IC + Jack-inspired portfolio simulation. The PM-approved replacement is Vibe-Trading; the combined portfolio baseline is developer-approved.
**Current task:** Strategy-expansion Phase 2—record the separately approved ILLIQ diagnostic and ten-strategy comparison: eight provisional backtests and two non-evaluable factors. This is distinct from the earlier Phase 2 data-ingestion work.

**Objective:** Maintain a ten-strategy research scope: preserve the five assessed originals, integrate five additional factors selected using mathematics and available data, and prepare one reviewed weekly research report. Ten investigated strategies does not imply ten valid portfolio backtests. The new candidates have developer approval for integration, not PM endorsement; real-data signal-only auditing was subsequently approved, and the four separately approved provisional portfolio diagnostics are now complete; all five approved additions have now completed one provisional diagnostic each; repeats remain unauthorized.

## 2. Ten-strategy tracker

IC and Sharpe below are transcribed from existing saved metrics solely to preserve findings; they did not determine the new shortlist. Every reported backtest remains PROVISIONAL. Dashes mean not calculated, not zero.

| # | Exact strategy ID | Assessment status | Portfolio backtest status | Execution-aligned mean rank IC | Daily net annualized Sharpe |
|---|---|---|---|---:|---:|
| 1 | `academic_strev` | Investigated; provisional findings preserved | Completed, original research_v3 | 0.073384 | 0.843175 |
| 2 | `alpha101_001` | Investigated; material tie dependence disclosed | Completed, original research_v3 | -0.023759 | 0.076889 |
| 3 | `alpha101_002` | Investigated; 12 volume-unit conversions verified | Completed, research_v4 | 0.018146 | 0.498502 |
| 4 | `alpha101_003` | Investigated; non-evaluable with current eight-name eligibility | Not run; 1,073/7,920 finite scores and no eligible weekly dates | — | — |
| 5 | `alpha101_004` | Investigated; unsuitable under current eight-stock top-two setup | Not run; 193/209 memberships tie-dependent, only 16 unique | — | — |
| 6 | `alpha101_033` | Signal/readiness and saved accounting audits passed; limitations retained | Completed PROVISIONAL, research_v4 | 0.059466 | 0.823290 |
| 7 | `alpha101_101` | Signal/readiness and saved accounting audits passed; limitations retained | Completed PROVISIONAL, research_v4 | -0.037382 | -0.151835 |
| 8 | `alpha101_054` | Signal/readiness and saved accounting audits passed; limitations retained | Completed PROVISIONAL, research_v4 | 0.056246 | 0.776599 |
| 9 | `alpha101_014` | Signal/readiness and saved accounting audits passed; limitations retained | Completed PROVISIONAL, research_v4 | 0.048654 | 0.382497 |
| 10 | `academic_illiq` | Separately approved frozen-proxy diagnostic; 51/209 and 31/209 sensitivity warnings retained | Completed PROVISIONAL, research_v4; developer India metadata exception | -0.003106 | 0.748968 |

**Progress:** 5 original strategies investigated; 3 provisional portfolio backtests completed; 2 documented non-evaluable/unsuitable assessments; 5 additional factors integrated, signal-audited and provisionally backtested. There are eight completed real-data provisional portfolio backtests and two non-evaluable factors in total. No final Keep/Drop decisions have been made.

Preserved findings:

- [STREV diagnostic](reports/india_strev_provisional_diagnostic.md).
- [Alpha101_001 diagnostic](reports/india_alpha101_001_provisional_diagnostic.md).
- [Alpha101_002 diagnostic](reports/india_alpha101_002_provisional_diagnostic.md).
- [Alpha101_003 investigation](reports/india_alpha101_003_investigation.md).
- [Alpha101_004 decision](reports/india_alpha101_004_readiness_decision.md).

The [Phase 2 selection proposal](reports/india_phase2_strategy_selection.md) contains exact registry paths, formulas, dependencies, warm-ups, expected discrimination, limitations and selection evidence. All five approved candidates fit the existing 25 prior-session preparation; the subsequent signal-only audit found complete evaluation coverage and no ties for all five; see the [readiness review](reports/india_phase2_signal_readiness_review.md). `academic_illiq` now has explicit developer approval for India research despite its missing `equity_in` registry tag. No upstream endorsement is claimed and no tag or formula changed. See the [integration review](reports/india_phase2_integration_review.md) for the INR turnover-proxy evidence and unresolved vintage limitations.

## 3. Fixed study configuration

- **Universe:** Eight assigned NSE equities, with `^NSEI` kept separate as benchmark.
- **Evaluation:** January 4, 2021–December 31, 2024 inclusive; do not extend the original December 31, 2024 cutoff.
- **Holdout:** October 1, 2025 onward; never use it for candidate selection, tuning or evaluation.
- **Prospective input for 6–10:** Existing verified research_v4, subject to review; no source-data modification or earlier-result migration.
- **Warm-up:** Existing 25 prior sessions from November 26, 2020 through January 1, 2021 cover all five integrations. Preserve original factor windows and missing-value behavior.
- **Portfolio baseline if separately authorized:** Weekly W-FRI top-two long-only 50/50 targets, descending score/ticker tie break, subsequent eligible-close execution, 10-bps absolute-NAV turnover costs, execution-aligned original Vibe IC and daily net-return sqrt(252) Sharpe with zero risk-free.
- **Limitations:** Frozen vendor histories are not historically point-in-time. Reliance normalization, the small Kotak quantity discrepancy, calendar-inventory limits and price/volume conventions remain documented; no silent repairs or reinterpretation of actual nominal shares.

Use `docs/india_backtesting_methodology.md`. No changed factor definition, universe, execution, ranking, cost or price basis follows from this plan. Previous single-factor diagnostic approvals have been used and do not cover new factors/repeats.

## 4. Deliverables and next review gate

Completed integration deliverables:

1. Five original Vibe modules invoked through isolated imports; legacy implementations unchanged.
2. Dependency/cutoff validation, original NaNs, input flags and coverage/tie diagnostics.
3. Identical portfolio/IC composition verified with explicitly synthetic fixtures only.
4. `academic_illiq` developer exception and dataset-bound adjusted-INR turnover-proxy evidence: 256 official-record checks across 32 dates, no failures. Sampling does not certify every daily input or actual traded value.
5. Integration suite: 287 passed, including 37 new Phase 2 cases. Existing datasets, reports and saved results verified unchanged by hashes.

Subsequent signal-only audit deliverables:

- All five: 7,920/7,920 finite evaluation scores, zero NaNs/infinities/ties, 209 unique eight-name weekly candidates (208 nonterminal).
- #014: five weekly pair changes on Yahoo Close basis. ILLIQ: 51 without dividend adjustment and 31 on fixed terminal normalization removal; conditional frozen-INR-proxy recommendation.
- Reparsed official proxy evidence: 256 checks passed; twenty real-data causal/window checks passed.
- Complete suite: 300 passed, including thirteen new audit cases. All prior results, original inputs and earlier reports preserved.

**Stop for review.** All five additions have completed their separately approved single diagnostics. ILLIQ has 208 executions, 207 IC intervals and 491 trade legs; its INR closing-price × vendor-volume proxy is not actual exchange turnover. The full suite passed 353 tests and 1,036 earlier files remained unchanged. The current [ten-strategy comparison](reports/india_ten_strategy_provisional_comparison.md) separates eight PROVISIONAL backtests from the two non-evaluable factors. The [earlier seven-strategy report](reports/india_phase2_provisional_backtests.md) is preserved. No repeats, alternative conventions or final Keep/Drop decisions are authorized.

For any subsequently authorized experiment, retain definition/parameters, data/configuration/source hashes, signal coverage/NaNs/ties, metrics with exact conventions, warnings, execution/trade logs and reproducibility evidence. Keep/Drop recommendations remain a reviewed deliverable when requested; none is made by candidate selection. Save new uniquely named outputs without overwriting historical results.

## 5. Weekly research report and future weeks

Prepare one reviewed weekly report distinguishing investigated, eligible, backtested and non-evaluable strategies. Report limitations and pending decisions alongside results; never invent an IC/Sharpe for an unrun strategy or treat an execution count as proof of validity.

Preserve the current ten-strategy tracker, reports and versioned outputs when a new week begins. Add newly assigned scope and dates explicitly rather than replacing completed findings. Do not repeat completed experiments unless requested or required for validation. No task scheduling, commits, pushes, PRs or publication is authorized by this plan.
