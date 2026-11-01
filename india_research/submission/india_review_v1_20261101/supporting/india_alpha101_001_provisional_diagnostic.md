> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# PROVISIONAL India alpha101_001 diagnostic

**One user-approved real-data diagnostic completed. No final Keep/Drop decision.**

Output: `archive:india_alpha101_001_PROVISIONAL_20261029T032703Z_711fe946/`.
Source: Phase 4D `archive:india_session_phase4d_20261029T020413Z_05541bac/research_v3/`.
Dataset manifest SHA-256: `a99d6671002b8c15dc406d7b532556ee95cb96cb5503dd9e8555253d17e3ca42`.
The existing STREV results and all recorded original inputs/evidence were hash-verified unchanged before and after execution.

## Exact methodology and scope

`src/india_alpha001_diagnostic.py` invokes only alpha101_001 via `src/india_factors.py::backtest_factor`, the original isolated Vibe `agent/src/factors/zoo/alpha101/alpha_001.py::compute`, original Vibe execution-aligned IC and unchanged Jack-adapted `simulate_portfolio`. No original formula, helper behavior or portfolio calculation was edited.

The eight-stock universe, separate ^NSEI benchmark and every `PortfolioConfig()` setting were verified equal to archived STREV: January 4, 2021–December 31, 2024, weekly W-FRI signals, top-two long-only 50/50 targets, descending original scores then alphabetical ticker for ties, eight finite scores required, subsequent eligible-close execution, 10 bps per absolute traded NAV, weight drift, zero cash interest/risk-free, sample daily standard deviation and sqrt(252) Sharpe. Initial cash days are included; no terminal liquidation or post-cutoff execution/IC label is invented.

A new approval record is restricted to alpha101_001, exact dataset/readiness-review hashes and unchanged settings. It accepts only the previously reviewed uncertainty about exhaustive historical calendar inventory; wrong scope, dates, data, warm-up or material calendar discrepancies remain failures. It does not broaden STREV's old approval, certify the archive, change existing manifest flags or authorize other real-data factors/repeat runs.

### Factor-specific warm-up

All **25 prior exchange sessions**, November 26, 2020–January 1, 2021, were verified against the reconstructed calendar, followed by **990 evaluation sessions**: **1,015 input sessions** in total. This adds four prior dates relative to STREV's input, without changing the evaluation period or the archived STREV run.

The original factor has metadata `min_warmup_bars=25`; its arithmetic conditional, 20-return standard deviation and five-row argmax leave the first **24 observations** NaN. This exact behavior was independently rechecked in saved outputs. `calendar_audit.json` retains the shared calendar auditor’s auxiliary 21-session offset check; the factor-specific 25-prior-session requirement is verified independently by exact calendar equality and recorded in `warmup_audit.json`. The 21-session auxiliary check does not define or replace Alpha #1’s computation. With 25 prior rows, all **7,920 evaluation stock/date scores are finite**. No warm-up fill, conditional rewrite or score substitution was used.

## Actual metrics — PROVISIONAL

| Metric | alpha101_001 portfolio | Nifty 50 |
|---|---:|---:|
| Cumulative return | **-1.5932% net** | **67.3032%** |
| Annualized daily Sharpe | **0.076889 net** | **0.978960** |
| Maximum drawdown | **-26.7722% net** | See saved daily benchmark NAV |

Gross cumulative return before the approved turnover costs was **30.6828%**. The net cumulative return was **68.8965 percentage points below** the benchmark. These are observations for this fixed provisional experiment, not a final strategy judgment. A slightly positive arithmetic-mean daily Sharpe can coexist with negative compounded return; Sharpe and geometric wealth growth are different calculations.

**Mean execution-aligned Spearman rank IC: -0.02375877**, calculated from **206 valid completed execution intervals**. There are 207 possible intervals from 208 target executions; one is undefined because the **March 31, 2023 signal has identical scores for all eight stocks**. The original Vibe IC omits that undefined correlation. It was neither replaced by zero nor silently included in the denominator. The final uncompleted execution interval is excluded by the same horizon policy used for STREV.

IC correlates each signal's all-eight-stock scores with returns from its actual execution close to the next execution close. It is neither portfolio Sharpe nor an IC information ratio. No alternate horizon was selected.

| Activity / cost accounting | Actual |
|---|---:|
| Daily evaluation observations | 990 |
| Rebalance executions | 208 |
| Stock trade legs | 698 |
| First execution | 2021-01-11 |
| Last execution | 2024-12-30 |
| Total absolute NAV turnover | 283.436168 |
| Sum of daily cost fractions | 0.283436168 |

Each trade leg is a nonzero stock weight adjustment, not a round trip or an entire rebalance. The cost-fraction sum is 28.3436% over changing daily NAV bases; it is not a direct percentage-point subtraction from terminal return. Daily net returns apply the approved multiplicative cost formula. No order was deferred/cancelled; the terminal December 31 signal is skipped because no later permitted close exists.

## Ties and actual selection effects

The original factor's discrete rolling argmax/rank scores produce ties on **all 990 evaluation days**. All eight scores tie on **17 daily dates**. Across **209 weekly candidate dates**, including the non-executable terminal signal, the top-two membership boundary is tied on **163** and all eight scores tie on one.

Of the **208 executed targets**, **162 (77.88%)** have membership determined partly or entirely by the existing alphabetical ticker tie break. One executed target follows an all-eight tie. In those 162 ambiguous targets, **280 of the 416 total selected-stock slots** come from a cutoff tie pool with more candidates than available slots. These are actual membership effects under the fixed rule, not merely ties between two stocks that would both be held anyway.

| Stock | Executed-target inclusions | Picks from an ambiguous cutoff pool by ticker rule |
|---|---:|---:|
| RELIANCE.NS | 37 | 12 |
| TCS.NS | 17 | 0 |
| INFY.NS | 55 | 40 |
| HDFCBANK.NS | 93 | 75 |
| ICICIBANK.NS | 52 | 47 |
| SBIN.NS | 28 | 6 |
| KOTAKBANK.NS | 31 | 16 |
| AXISBANK.NS | 103 | 84 |

The March 31 all-eight tie selects **AXISBANK.NS and HDFCBANK.NS** under the unchanged ticker rule. The final terminal candidate is counted in weekly signal statistics but stages no target. `weekly_selection_ties.json/csv` records each candidate's selected names, strict winners, cutoff pool, available slots, selected/rejected tied names and stageability; execution records and saved weights independently reconcile to these selections.

This is a tie-dependent portfolio result. No randomized, reversed, optimized or alternate-tie portfolio was run, so the portion of performance attributable to the tie rule is **not** estimated. The experiment quantifies membership dependence and preserves the approved rule; it does not claim economically unique rankings on those dates.

## Quality warnings and interpretation limits

- The 12 repeated-close flags remain; no missing-close, missing-volume, zero-volume or >20% adjusted close-move flags occur in the required input slice. No prices were repaired or observations excluded for this run.
- The source is a **frozen Yahoo-adjustment research vintage, not historically point-in-time data**. Later corporate-action scaling and the unresolved exact pre-demerger Reliance vendor normalization remain explicit limitations.
- The readiness audit established mixed volume units in 12 recovered observations for three stocks. Alpha101_001 uses close only; the unchanged simulator requires positive volume rather than volume-based sizing. Those quantities are all positive, so no conversion, repair or execution rule change was needed or performed.
- Calendar reconstruction and all required input dates passed; exhaustive amendment/publication inventory certainty is not claimed. The inherited strict certification flags remain false.
- The benchmark is a price index while equity histories carry dividend adjustments. Fixed eight-stock membership, fractional targets, flat turnover fees, initial cash, no spread/impact model and published-close/positive-volume execution approximations limit interpretation, especially in special sessions.
- All findings remain PROVISIONAL. No keep/drop, factor modification, other real-data factor run, parameter search or final report publication is authorized by this experiment.

## Tests, independent checks and saved provenance

Before execution, the complete project-.venv suite passed **193 tests in 27.33 seconds**, with no failures or skips. Sixteen new offline synthetic regressions in `tests/test_india_alpha001_diagnostic.py` verify approval restrictions, 25-session warm-up requirements, retained calendar failures, cutoff-pool membership, all-name ties, non-ambiguous ties among both winners, missing-score eligibility and terminal signal handling. Existing original-factor formula/causality and portfolio accounting tests passed.

After execution, an independent saved-artifact verifier checked all input, source, STREV and output hashes; the 25-session warm-up and 990-session evaluation; original leading NaNs and full evaluation coverage; every execution's strictly later timing, exact top-two and alphabetical membership; all 207 IC labels/206 valid ICs and the one constant-score omission; 698 trade legs, turnover and costs; recomputed net Sharpe/cumulative return/mean IC; unchanged certification flags; and exact equality of benchmark returns with archived STREV. No factor or portfolio was rerun for these checks.

Executed commands:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m src.india_alpha001_diagnostic --approved-alpha001-diagnostic
```

The one approved diagnostic is complete. The CLI creates a unique output and does not grant permission to repeat the experiment. `verify_saved_run.py` checks the existing saved results without another strategy execution.

Outputs include configuration/approval, dataset manifest/readiness review, calendar/warm-up checks, original scores/missingness, daily and weekly tie audits and stock counts, IC scores/return labels/defined and undefined intervals, daily gross/net/benchmark returns and NAV, holdings, executions, trade legs, order log, quality flags and warnings, metrics, test/console logs, Git/runtime/package versions, exact working source snapshots and original Vibe source hashes, and SHA-256 artifact inventory.

No existing STREV result, source dataset, factor definition or portfolio setting changed. No package installation, commit, push or publication. Stop for user review.
