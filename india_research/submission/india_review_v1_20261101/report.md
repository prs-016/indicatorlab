> Portable submission copy packaged 2026-11-01. Original reports and all backtest archives remain unchanged.

# India ten-strategy research review

**For PM review · prepared 2026-10-29 06:10 UTC · all portfolio results PROVISIONAL**

**Decision requested:** review the preliminary priorities, accept or revise the treatment of two non-evaluable original factors, and agree the next validation work. No final PM Keep/Drop decisions are recorded. Detailed formulas, source versions and hashes are in the [Strategy Log](strategy_log.md) ([CSV](strategy_log.csv)). Earlier drafts remain unchanged in the original workspace; their identity is recorded in REVIEW_HISTORY.json.

## Findings and preliminary priorities

Ten factors have been investigated: **eight completed portfolio diagnostics and two non-evaluable factors** under the fixed eight-stock baseline. Retain STREV, #033 and #054 for further research; investigate #001, #002, #014 and ILLIQ. Deprioritize #101 for observed performance. Remove #003/#004 from this baseline’s evaluation queue because their signals cannot support meaningful selection here—not because of measured portfolio losses.

| Exact registry ID | Evaluation | Mean rank IC | Net Sharpe | Net return | Preliminary priority |
|---|---|---:|---:|---:|---|
| `academic_strev` | PROVISIONAL backtest | 0.073384 | 0.843175 | 75.5389% | Keep |
| `alpha101_001` | PROVISIONAL backtest | -0.023759 | 0.076889 | -1.5932% | Investigate |
| `alpha101_002` | PROVISIONAL backtest | 0.018146 | 0.498502 | 38.0712% | Investigate |
| `alpha101_003` | Non-evaluable | N/A | N/A | N/A | Drop — non-evaluable in this baseline |
| `alpha101_004` | Non-evaluable | N/A | N/A | N/A | Drop — non-evaluable in this baseline |
| `alpha101_033` | PROVISIONAL backtest | 0.059466 | 0.823290 | 78.4805% | Keep |
| `alpha101_101` | PROVISIONAL backtest | -0.037382 | -0.151835 | -17.9156% | Drop — observed baseline performance |
| `alpha101_054` | PROVISIONAL backtest | 0.056246 | 0.776599 | 69.6519% | Keep |
| `alpha101_014` | PROVISIONAL backtest | 0.048654 | 0.382497 | 24.3375% | Investigate |
| `academic_illiq` | PROVISIONAL backtest | -0.003106 | 0.748968 | 70.4904% | Investigate |

**Benchmark:** Nifty 50 price index (`^NSEI`): **67.3032%** cumulative return and **0.978960** daily annualized Sharpe. All eight strategies have lower net Sharpe than this benchmark. Stock histories include dividend adjustments; the benchmark is a price index, so this comparison is not matched on total-return basis. N/A means no portfolio was run, not zero performance.

**Keep** means retain for independent research, not deploy. **Drop** means deprioritize this exact baseline, not reject a factor universally. **Investigate** means material interpretation or implementation questions remain. These are qualitative analyst judgments, not PM-approved thresholds or an out-of-sample selection rule. Positive returns and positive IC do not establish predictive alpha.

## Signal findings that drive the review

- **STREV / #033 / #054:** positive IC and above-benchmark cumulative returns support research retention, tempered by lower Sharpe, costs and unmeasured overlap. No diversification claim is made.
- **#001:** all scores are available, but 162/208 executed selections depend on ticker tie breaking. One all-score tie makes IC undefined; its performance cannot be uniquely attributed to factor rankings.
- **#002:** four original correlation NaNs remain; one weekly target was skipped, extending one IC interval to ten sessions. Twelve independently verified recovered-volume corrections were used; costs and broader volume-vintage limits remain important.
- **#003 / #004:** #003 has only 1,073/7,920 finite scores and no all-eight-eligible weekly signals. #004 has finite scores but 193/209 weekly selections depend on ties, leaving only 16 unique pairs. Neither has portfolio metrics.
- **#101:** negative IC, net Sharpe and net return motivate deprioritization. Its original price-unit-dependent `0.001` constant is unchanged; no score inversion or retuning is proposed.
- **#014:** positive IC accompanies weak net performance and high turnover. Dividend-adjustment choice changes 5/209 candidate selections; the predeclared basis remains unchanged.
- **ILLIQ:** near-zero negative IC accompanies a positive long-only return and concentrated exposure. Adjusted-INR close × vendor volume is a **closing-price turnover proxy, not actual exchange turnover or USD traded value**. India use despite missing `equity_in` is a **developer-approved metadata exception**, not upstream endorsement or an explicitly recorded PM factor approval. Prior signal diagnostics found **51/209 dividend-sensitive** and **31/209 normalization-sensitive** selections. No alternative convention was chosen using portfolio returns.

## Methodology and limits

Evaluation is **January 4, 2021–December 31, 2024**, 990 sessions, on RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, KOTAKBANK and AXISBANK (all `.NS`); `^NSEI` is separate. Weekly Friday-ending signals require eight finite scores; targets hold the top two equally, long-only, with a fixed ticker tie rule. Trades execute at a strictly subsequent eligible close with positive volume. Costs are **10 bps per absolute traded NAV**, including entry and drift rebalancing; there is no terminal liquidation.

Headline IC is mean cross-sectional Spearman correlation between signal scores and returns from actual execution close to the next successful execution close. Net Sharpe uses daily net mean/sample standard deviation × √252, zero risk-free; initial cash days are included. Net return is cumulative, not annualized. STREV and the five additions have 207 valid IC intervals; #001 and #002 have 206, with the tie/skipped-signal qualifications above.

These archives use a frozen Yahoo-adjustment vintage, **not historically point-in-time prices**. Reliance’s pre-July-2023 normalization and the small Kotak quantity discrepancy remain unresolved. Twelve repeated-close flags are retained; the study inputs have no missing-close, zero-volume or >20% adjusted-close-move flags. Sampled official checks do not certify every historical quantity. Material calendar checks passed, but exhaustive amendment-inventory certainty was waived only for the approved provisional diagnostics; strict certification flags are unchanged.

The comparison preserves original versions: STREV/#001 use research_v3; others use research_v4, which corrects twelve volume observations without changing prices. STREV uses 21 prior sessions; the others use 25. No prior result was rerun or migrated. Fractional close fills and flat costs omit spreads, impact, taxes and capacity—particularly relevant to ILLIQ. The small fixed basket, multiple investigated factors and lack of independent out-of-sample evidence prevent final validation. The December 2024 cutoff and October 1, 2025 onward holdout restriction remain intact.

## Assignment completion and PM decisions

Statuses describe repository evidence, not unverified work elsewhere. **Completed** means an artifact exists, not PM acceptance; **Incomplete** means a deliverable is not evidenced as complete; **Unverified** means coverage, measurement or approval remains unsettled.

| Requirement | Status | Evidence / remaining action |
|---|---|---|
| Historical-data and special-session research | Completed research; limits open | Versioned snapshots, official reconciliations and quality reports exist; retain corporate-action/vintage limits. |
| Ten strategy assessments and Strategy Logs | Completed for review | Eight provisional portfolios, two non-evaluable studies; PM approval pending. |
| Original five-factor portfolio assignment | Incomplete as five portfolios | Three original factors backtested; PM must accept or revise the two non-evaluable outcomes. Additional factors do not silently replace them. |
| Current official Nifty 100 snapshot | Completed | Official 100-name file exists; it is not historical membership. |
| Historical Nifty 100 membership | Unverified | Announcement-based reconstruction is feasible; archive completeness for 2021–2024 is not established. |
| At least three intraday providers | Incomplete | No completed provider/access/reliability comparison with active-session delay measurements found. |
| Subreddits and English/Hindi Wikipedia mappings | Incomplete | No completed India identifier/coverage mapping found. |
| Publication latency | Unverified | Existing checks show newer records arrived for three symbols, not measured publication delay or dependable latency. |
| Final acceptance criteria and PM decisions | Unverified / pending | No final thresholds or decisions recorded; distinguish developer baseline from PM-approved framework replacement. |
| Team code review | Incomplete in inspected evidence | No completed `code_review.md` and resolved-findings record identified; required before submission. |
| Destination repository / submission | Unverified destination; submission incomplete | Confirm destination, complete review and obtain explicit Git/PR approval; this task authorizes none. |

Please decide whether the two non-evaluable original factors satisfy the assignment, approve or revise the preliminary priorities and acceptance criteria, and prioritize the outstanding provider/mapping/membership/latency work. Any new validation study should predeclare data, costs, uncertainty checks and scope; no repeat run, new convention, holdout access or publication is authorized here.

**Evidence and verification:** [Strategy Log](strategy_log.md), [CSV](strategy_log.csv), [bundle verification](bundle_manifest.json), and [documented PM assignment](supporting/assignment_context.md#8-updated-pm-instructions). Metrics, links and inventory references were checked without running factors, portfolios or tests. The latest saved full suite is 353 passed; it was not rerun for this documentation revision.
