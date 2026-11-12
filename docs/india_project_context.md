# IndicatorLab — India Project Context

## 1. Purpose

This document provides project context for AI coding agents working on the India portion of IndicatorLab.

**Project:** IndicatorLab
**Repository:** `https://github.com/prs-016/indicatorlab`
**Working branch:** `india`
**Local location:** `/home/jampip/indicatorlab`
**Reference repository:** `/home/jampip/vibe-Trading`

### Objectives

Develop and evaluate Indian stock-market data infrastructure and trading strategies.

Primary responsibilities:

1. Evaluate the reliability of free historical Indian stock data.
2. Identify a reliable Nifty 100 constituent source.
3. Investigate historical Nifty 100 membership changes.
4. Compare NSE and BSE market data.
5. Test five reversal strategies.
6. Investigate live Indian market data APIs.
7. Prepare India-specific data and code for integration with IndicatorLab.

The developer is learning data science, machine learning engineering, APIs, backtesting, and collaborative software development. Explain important technical choices rather than treating implementation as a black box.

## 2. Repositories

### IndicatorLab

GitHub: `https://github.com/prs-016/indicatorlab`

This is the team's development repository.

Use the existing project structure and review its documentation before making changes:

- `README.md`
- `docs/AGENTS.md`
- `docs/DesignDoc.md`
- `docs/codeReviewer.md`

Work on the `india` branch. Do not modify `main` directly.

The correct repository for the final India pull request should still be confirmed with the project manager.

### Vibe-

GitHub: `https://github.com/HKUDS/vibe-Trading`

This repository provides financial research, factor evaluation, and backtesting functionality.

Relevant components include:

- `agent/src/tools/alpha_bench_tool.py`
- `agent/src/factors/bench_runner.py`
- `agent/src/factors/bench_runner_strict.py`

The original assignment specifically requests studying `_load_sp500_panel` in `alpha_bench_tool.py` to understand how to implement a comparable Nifty 100 universe loader.

Vibe-Trading supplies the original factor and IC implementations in the combined India methodology below. Do not assume it is the repository where IndicatorLab deliverables should be submitted.

## 3. Existing India Files

Current location:

`india_research/`

```text
india_research/
├── data/
│   ├── 500325 (1).csv
│   ├── ind_nifty100list.csv
│   ├── ind_prs22082025.pdf
│   ├── nifty100_source.txt
│   └── daily_update_check.txt
└── reports/
    └── india_data_quality_report.md
```

These files contain prior research. Preserve them.

Before moving or restructuring files, check the repository's conventions and confirm that no important records will be overwritten.

Do not commit unnecessarily large datasets or generated files without checking `.gitignore` and repository policies.

## 4. Original Assignment

### Historical data

Use `yfinance` with `period="max"` for:

```python
STOCKS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
]

BENCHMARK = "^NSEI"
```

For each ticker, record:

- First available date
- Last available date
- Historical observation count
- Stock splits
- Missing trading dates
- Price movements exceeding 20%
- Repeated closing prices
- Suspicious zero-volume observations
- Evidence of daily updating
- Comparison against an independent source

### Nifty 100

Use official NSE Indices data.

Source:

`https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-100`

Investigate whether historical membership announcements make point-in-time constituent reconstruction possible.

### Strategies

The initial assignment requests five reversal-oriented factors:

```text
academic_strev
alpha101_001
alpha101_002
alpha101_003
alpha101_004
```

Original requested benchmark command:

```bash
python mini_bench.py \
  --tickers RELIANCE.NS TCS.NS INFY.NS HDFCBANK.NS \
  ICICIBANK.NS SBIN.NS KOTAKBANK.NS AXISBANK.NS \
  --benchmark ^NSEI \
  --factors academic_strev alpha101_001 alpha101_002 \
  alpha101_003 alpha101_004 \
  --end 2024-12-31
```

**Important:** `mini_bench.py` has not been found in the inspected local repositories or teammate branches. Do not assume this command currently works.

**PM decision** (confirmed October 28, 2026): The project manager approved using Vibe-Trading instead of the unavailable mini_bench.py for India's five-strategy backtesting assignment. Jack's Hong Kong implementation is a useful reference. At that decision, the exact India factor definitions and evaluation methodology remained to be verified; the subsequent developer-approved implementation is documented below.

**Developer decision** (October 28, 2026): Use Vibe-Trading's original reversal-factor calculations and IC functions together with Jack-adapted portfolio simulation and Sharpe as the standard IndicatorLab India methodology until instructed otherwise. This is a developer-approved baseline; no explicit PM approval of the combined portfolio rules or parameter values is recorded. The PM-approved framework replacement, assigned factors/universe, original cutoff, and holdout restriction remain in force.

**Provisional portfolio baseline:** 2021–2024, top-two long-only equal-weight targets, weekly Friday-ending signals, subsequent eligible-close execution, 10-basis-point costs per unit of absolute traded NAV, execution-aligned IC, and annualized daily net-return Sharpe (252 sessions/year, zero risk-free baseline). These assumptions are configurable. Retain isolated Vibe child processes because both repositories have conflicting `src` package names. See `docs/india_backtesting_methodology.md` for precise timing, data exclusions, configuration, limitations, and approval provenance.

Phase 3 implements the simulator and STREV composition with offline synthetic tests. Authorization does not extend to final strategy evaluations or publication. Only independently verified, auditable exclusions may be applied to research copies; preserve snapshots and valid special sessions and retain unresolved anomaly flags. Calendar certification, anomaly resolution, and final Keep/Drop criteria remain outstanding.

## 5. Completed Research

### Historical coverage

Successfully downloaded maximum available daily histories for all eight stocks and the benchmark using `yfinance`.

Historical coverage varies by ticker. Several stocks have observations extending back to the 1990s, while others start in the early 2000s.

The complete recorded findings are in:

`india_research/reports/india_data_quality_report.md`

Consult that report for exact counts, dates, and investigations instead of recreating historical findings from memory.

### Missing dates

An initial comparison against the benchmark's available trading dates returned zero missing dates for the eight stocks.

This should not be interpreted as proof that every historical record is valid, nor that the data covers every possible exchange trading session.

### Stock splits and anomalies

Stock splits were retrieved using the `yfinance` ticker interface.

The historical-data review identified:

- Several daily movements exceeding 20%.
- Repeated closing prices.
- Many early zero-volume observations.
- Suspicious historical price jumps associated with possible unit adjustments or corporate actions.

`yfinance` was also tested using `repair=True`.

Some extreme price changes were reduced, particularly for Reliance Industries and Kotak Mahindra Bank. Other anomalies remained.

The repaired observations were not independently verified as universally correct.

Preserve both source data and cleaning decisions.

### NSE versus BSE validation

Official BSE historical data for Reliance Industries was obtained and compared with NSE/Yahoo Finance data.

A comparison of 21 January 2024 observations required accounting for the price-adjustment basis.

After applying the appropriate 2:1 price-scale adjustment in that comparison:

- Average absolute percentage difference: approximately 0.032%.
- Maximum absolute percentage difference: approximately 0.155%.

This supports agreement for that limited sample. It does not prove equivalence across all stocks or years.

The official BSE file is:

`india_research/data/500325 (1).csv`

### Daily updating

A later Yahoo Finance check found that RELIANCE.NS, TCS.NS, and ^NSEI had advanced from October 21, 2026, to October 23, 2026.

This demonstrates that newer records became available between checks.

The exact publication time and regular update delay remain unverified.

See `india_research/data/daily_update_check.txt`.

## 6. Nifty 100 Research

Downloaded the official constituent file:

`india_research/data/ind_nifty100list.csv`

Verified:

- Exactly 100 constituent rows.
- Company name, industry, symbol, series, and ISIN columns.

The file is a downloaded snapshot, not a historical membership database.

### Historical membership

Official NSE Indices announcement:

`india_research/data/ind_prs22082025.pdf`

Published August 22, 2025.

Changes effective September 30, 2025.

Five companies removed:

```text
DABUR
HEROMOTOCO
ICICIPRULI
INDUSINDBK
SWIGGY
```

Five companies added:

```text
HINDZINC
MAXHEALTH
MAZDOCK
ENRIN
SOLARINDS
```

Finding:

Official NSE press releases provide historical additions, removals, and effective dates.

This establishes that historical reconstruction is feasible in principle.

**Not yet established:** Whether the available announcement archive is complete enough to reconstruct the Nifty 100 universe across the entire intended backtesting period.

Avoid survivorship bias by distinguishing current constituents from historical constituents.

## 7. Lessons From Teammate Branches

### Jack's Hong Kong branch

Inspected the team's `jack` branch.

Important files:

```text
hk_week1/check_data.py
hk_week1/backtest_strategies.py
hk_week1/data_note.md
hk_week1/strategy_log.md
hk_week1/strategy_report.json
hk_week1/strategy_results.csv
```

Jack developed a standalone backtesting implementation rather than including `mini_bench.py`.

His implementation provides examples of:

- Historical stock-data validation
- Momentum signal calculations
- Cross-sectional stock ranking
- Weekly portfolio rebalancing
- Execution timing to reduce look-ahead bias
- Transaction costs
- Spearman rank IC
- Annualized Sharpe ratio
- Benchmark comparisons
- Reproducible performance reports

Use the implementation as the portfolio-accounting reference for the developer-approved combined baseline. The precise India specification is `docs/india_backtesting_methodology.md`; do not blindly copy Jack's missing-return fallback, selected-stock-only execution checks, or hardcoded strategy decisions.

The India assignment uses reversal factors rather than Jack's five momentum strategies.

Verify that signals, trade execution, and forward returns are aligned correctly.

### Wikipedia branch

Inspected the team's `wikipedia` branch.

Important files:

```text
src/wiki_attention.py
notebooks/wikipedia.ipynb
tests/test_wiki_attention.py
```

The branch provides examples of:

- Retrieving external data through APIs
- Mapping financial tickers to external entities
- Aggregating daily observations
- Calculating attention signals
- Identifying spikes
- Separating reusable modules from notebooks
- Writing automated tests

Potential concerns identified during review:

- Risk of using full-series statistics when calculating historical signals
- Exploratory analysis conducted within the holdout period
- Differences between implementation thresholds and the PM's specified spike rule

The Wikipedia branch is not a substitute for the India reversal backtester.

## 8. Updated PM Instructions

The newer assignment adds several requirements.

### Live Indian market data

Investigate at least three sources capable of providing intraday Indian stock prices during NSE trading hours.

For each source, record:

- Provider
- Supported Indian tickers
- Whether data is live or delayed
- Measured delay during an active trading session
- Free or paid access
- API-key requirements
- Whether the provider is official or third-party
- Limitations and reliability

NSE trading hours specified by the PM are 8:45 PM–3:00 AM Pacific, although local time should be verified against India Standard Time and daylight-saving changes.

Do not claim that a feed is real-time based solely on marketing descriptions. Measure its observed freshness.

### Attention-source preparation

Find relevant Indian-company subreddits and Wikipedia pages in English and Hindi.

Document identifiers and coverage so attention research can later expand beyond US stocks.

### Holdout period

The newer team instructions identify October 1, 2025, as the beginning of the holdout period.

Research and strategy selection must not use holdout results.

The original India backtest explicitly ends December 31, 2024.

Preserve the original cutoff for those five tests until the PM confirms a change.

### Code review and submission

Before pushing code:

1. Run the team's `ds3-code-review` process described in `docs/codeReviewer.md`.
2. Inspect the generated `code_review.md`.
3. Fix applicable findings.
4. Run relevant tests again.
5. Commit changes on the appropriate feature branch.
6. Push and open a pull request for review.

Confirm the final destination repository with the PM before pushing.

## 9. Remaining Work

Priority order:

1. Review the implemented developer-approved combined baseline and resolve remaining calendar/anomaly and reporting decisions.
2. Complete the remaining original reversal-factor integrations; STREV composition and the configurable portfolio simulator have offline tests, not final market-data validation.
3. Generate IC, Sharpe, and other agreed performance metrics.
4. Complete five Strategy Log entries.
5. Complete the three-provider Indian live-data investigation.
6. Record relevant Indian-company Wikipedia and subreddit mappings.
7. Review the Nifty 100 historical-membership archive's completeness.
8. Verify data update timing during an active trading session.
9. Prepare reusable code, automated tests, and final documentation.
10. Run code review and submit the India branch.

Some work can proceed independently while the original benchmarking script remains unavailable.

## 10. Instructions for Codex

### Before making changes

- Read the repository README.
- Read applicable `AGENTS.md` instructions.
- Read `docs/india_project_context.md`.
- Inspect existing code and file structure.
- Verify the active Git branch.
- Check for uncommitted changes.
- Avoid overwriting existing research.

### Development approach

Work incrementally.

For each task:

1. Explain the objective briefly.
2. Identify the files that will change.
3. Implement the smallest useful component.
4. Explain important Python code and algorithms.
5. Run appropriate tests.
6. Report results and unresolved issues.
7. Stop for review before starting another major component.

### Correctness requirements

- Avoid look-ahead bias.
- Respect the agreed holdout cutoff.
- Use consistent price-adjustment conventions.
- Distinguish signals from realized returns.
- Explain how IC and Sharpe are calculated.
- Do not fabricate results, API responses, or source data.
- Do not silently repair suspicious data.
- Avoid hardcoding historical index membership as if it never changed.
- Do not silently change the requested five factors.
- Preserve reproducibility and record limitations.

### Git and security

- Work only on the intended branch.
- Do not push, merge, or delete branches without approval.
- Do not commit secrets, credentials, or unnecessary datasets.
- Review `.gitignore` and the repository's instructions.
- Keep changes focused and testable.

### Learning requirement

The developer wants to understand the implementation, not merely receive generated code.

Use concise explanations, introduce important concepts when they arise, and proceed one step at a time.

When assumptions are uncertain, explicitly identify them rather than treating them as requirements.

## 11. Open Questions for the PM

- Is IndicatorLab the official destination for the India pull request?
- Does the PM require amendments to the developer-approved combined baseline? Do not delay already authorized implementation to request the same developer approval again.
- Which final Keep/Drop criteria should govern the original five factors? Their definitions remain unchanged.
- Should India research stay under `india_research/`, or move into the shared repository structure?
- What historical Nifty 100 membership coverage is required?
- Which Indian live-data providers are preferred?
- What price-delay threshold is acceptable?
- Is the `ds3-code-review` skill installed and configured for contributors?
- What functionality must be completed before India-market integration?

## 12. Current Status

**Provisional STREV diagnostic completed:** The user approved one diagnostic
using Phase 4D research_v3 after the final calendar review. All 136 tests passed;
mean execution-aligned rank IC was 0.07338394 and net daily annualized Sharpe
0.843175 (990 evaluation observations, 208 executions). Results remain PROVISIONAL;
no final Keep/Drop or additional run is approved. Strict certification flags and
original data/manifests remain unchanged. See
`india_research/reports/india_strev_provisional_diagnostic.md` for the dataset-bound
exception, outputs, benchmark comparison, warnings and source provenance.

Historical data research and the Nifty 100 source investigation have made substantial progress.

The original five reversal-factor implementations exist in Vibe-Trading. IndicatorLab's STREV bridge, ingestion, and configurable combined portfolio workflow have offline synthetic tests. The remaining four original Alpha101 OHLCV integrations now exist in `src/india_factors.py`, with synthetic factor/portfolio regressions and a common 25-session warm-up. Their real-data evaluations remain unauthorized and unexecuted. Volume-basis comparability (#2/#3) and adjusted cross-sectional price-rank sensitivity (#3/#4) need explicit review; see `india_research/reports/india_four_factor_integration_review.md`. All final strategy evaluations remain outstanding.

The new live-market API comparisons have not yet been completed.

The India branch has not yet been pushed.

**Next development objective:** Review Phase 3 implementation and the selected-period data/calendar limitations. Obtain authorization before final strategy evaluations; do not change the original factor definitions, December 31, 2024 cutoff, or holdout restriction.


### Four-factor real-data signal audit (no portfolio runs)

The four unchanged Vibe factors have now been scored on research_v3. #1 has
complete coverage and is ready for a provisional diagnostic with tie caveats;
#2 is held because recovered/vendor volume units are demonstrably inconsistent
and change three weekly candidate selections; #3 never has all eight finite
scores and is unsuitable under the unchanged eligibility rule; #4 has complete
coverage but severe ties and price-basis sensitivity, requiring explicit review.
No portfolio performance was calculated, no factor or data convention changed,
and STREV outputs remain unchanged. See
`india_research/reports/india_four_factor_real_readiness_review.md` for exact
counts, NaN causes, official evidence and unresolved vendor scaling.


### Completed provisional alpha101_001 diagnostic

The user subsequently approved one #1 real-data portfolio diagnostic. It is
complete, with all 193 tests passing, net cumulative return -1.5932%, daily net
annualized Sharpe 0.076889 and execution-aligned mean rank IC -0.02375877
(206 valid intervals, one constant-score undefined interval). Ticker tie breaking
affects 162/208 executed targets. The same eight-stock/STREV portfolio baseline
was used with the required 25-session warm-up. All results remain PROVISIONAL;
no Keep/Drop or other real-data factor run is authorized. Source data and all
STREV artifacts remain unchanged. See
`india_research/reports/india_alpha101_001_provisional_diagnostic.md`.


### Alpha101_002 volume preparation completed

The user authorized resolving the twelve known mixed-unit volume observations.
All twelve are verified from documented share events and exact bracketing
NSE/Yahoo quantities in a new research_v4; only volume tokens change. Original
prices, source data and completed STREV/#1 results remain unchanged. #2 coverage
remains 7,916/7,920 with four intrinsic NaNs; three weekly candidate memberships
change. Recommend a provisional diagnostic after explicit user approval; no #2
portfolio backtest has run. Broader pre-demerger Reliance normalization and a
small Kotak record discrepancy remain disclosed, not repaired. See
`india_research/reports/india_alpha101_002_volume_readiness_review.md`.


### Completed provisional alpha101_002 diagnostic

The user subsequently approved one #2 portfolio diagnostic using the verified
research_v4. It completed after 235 passing tests: mean execution-aligned rank
IC 0.01814609 (206 intervals), daily net annualized Sharpe 0.498502, net cumulative
return 38.0712%, 207 executions and 689 stock trade legs. Four original NaNs stay
unfilled; the missing March 25, 2022 signal preserves holdings and extends one
IC interval to ten sessions. Results remain PROVISIONAL with Reliance, Kotak
and historical-vintage limitations retained. No other real-data factor or repeat
run is approved. See `india_research/reports/india_alpha101_002_provisional_diagnostic.md`.


### Alpha101_003 investigation (signal-only)

All 6,847 undefined scores are explained by constant ten-session ranked inputs:
5,588 open-only, 1,224 both and 35 volume-only. TCS's adjusted open rank is 1.0
throughout the 1,015 input sessions. The small price-separated basket is a
verified contributor, not a mathematical shortage of correlation observations.
Changed price/volume conventions, including sampled-validated post-demerger
nominal proxies, do not produce any all-eight-eligible day. Retain #3 as a
non-evaluable assigned-universe experiment; only propose a separately approved,
predeclared point-in-time broader-universe validity study. The current Nifty 100
snapshot cannot establish 2021–2024 membership. No portfolio or actual universe
change was run. See `india_research/reports/india_alpha101_003_investigation.md`.


### Alpha101_004 pre-backtest decision completed

Option (b): unsuitable for the intended factor-ranking evaluation under the
current eight-stock/top-two setup. Scores are complete, but 193/209 candidate
memberships depend on ticker ties and 120 weeks allow any pair. Only 16 weeks
have unique memberships. The 99 price-convention differences include ten
disjoint and 89 overlapping admissible-pair comparisons. Documented share/cash
normalizations materially affect level ranks, while alternatives remain heavily
tied. No return-based convention selection or portfolio run occurred. See
`india_research/reports/india_alpha101_004_readiness_decision.md`; this supersedes
the earlier preliminary conditional readiness recommendation without rewriting
the report frozen into previous experiments.


### Strategy-expansion Phase 2: approved integration of strategies 6–10

The developer approved `alpha101_033`, `alpha101_101`, `alpha101_054`,
`alpha101_014` and `academic_illiq` for reusable integration and offline tests.
`src/india_phase2_factors.py` invokes the unchanged original Vibe modules through
the existing isolated worker protocol, data adapter, Jack-inspired portfolio
accounting and original execution-aligned IC. It preserves the eight equities,
separate benchmark, 2021–2024 boundaries, 25 prior sessions and portfolio costs.
The original five implementations and archived research remain unchanged.

India use of country-agnostic `academic_illiq` is an explicit developer-approved
research exception despite missing upstream `equity_in` metadata, not an upstream
endorsement or an explicit PM approval. Inputs are INR adjusted closing prices
and frozen vendor-unit quantities; close × volume is a closing-price turnover
proxy, not actual exchange turnover or dollars. All 256 sampled official-record
comparisons across 32 dates pass their recorded numerical tolerance. Dataset-bound
evidence is mandatory; unsupported/mismatched bases fail closed. This does not
resolve every daily quantity, Reliance return normalization or historical vintage
limitations. No factor formula or source dataset was changed.

The suite passes 287 cases, including 37 new synthetic integration regressions.
Ten strategies are source-investigated at different depths: five originals have
empirical assessments, three have provisional portfolio backtests, two are
non-evaluable/unsuitable, and five additions were integrated and then separately signal-audited, without
real-data portfolio backtests. Integration provides no new run permission or calendar waiver.
See `india_research/reports/india_phase2_integration_review.md` and the weekly plan.


### Strategy-expansion Phase 2 signal-only readiness completed

The user separately authorized real-data scoring and input-convention diagnostics,
not portfolio evaluation. All five original implementations yield 7,920 finite
scores each across 990 sessions, no evaluation NaNs/infinities/ties and 209 unique
eight-name weekly selections (208 with a subsequent session). Original warm-up
NaNs are 72 for #014 and 168 for ILLIQ, entirely before evaluation. Twenty causal
prefix/minimum-window checks pass; frozen vendor history is still not point-in-time.

Recommend #033, #101, #054 and #014 for a separately approved provisional diagnostic
under the predeclared basis. #014 has five weekly differences without dividend
adjustments. ILLIQ is conditional: 51/209 differ on the Yahoo Close basis and
31/209 on removing fixed terminal normalization. These are measured sensitivities,
not chosen replacement conventions. The adjusted-INR closing-turnover proxy passes
all 256 reparsed official-record checks; actual traded value stays separate.
No zero volumes or invalid denominators occur in this study view; synthetic tests
verify original zero-volume rolling NaNs and zero dispersion without filling.

Complete suite: 300 passed, including 13 new signal-audit regressions. At the signal-only audit stage, the three prior
provisional portfolio experiments were the only completed real-data backtests;
all original datasets, saved results and earlier reports remain unchanged. Strict
calendar/backtest flags are retained. See
`india_research/reports/india_phase2_signal_readiness_review.md` and
`results/india_phase2_signal_readiness_20261029T050613Z/` for provenance, scores,
per-cell causes, every weekly pair, sensitivities and the conditional recommendation.


### Four separately approved Phase 2 provisional diagnostics completed

The user approved one portfolio run each for #033/#101/#054/#014 and explicitly
excluded ILLIQ. All four completed using research_v4, original Vibe factor/IC,
25 prior sessions and the unchanged Jack-inspired portfolio baseline. Each has
990 daily observations, 208 executions, 207 valid execution-aligned IC intervals,
no tie-dependent executed selections and no labels/executions after 2024. Saved
accounting, targets, trade legs and costs independently reconcile. #101 retains
its 0.001 denominator constant; #014 retains its five-of-209 dividend-convention
selection sensitivity. No convention was selected from realized returns.

Complete suite: 329 passed, including 29 new scoped runner/ledger regressions.
A JSON serialization failure before any #033 factor/portfolio invocation was
preserved, corrected and regression-tested before successful runs. All 773 prior
files and seven result inventories verify unchanged. Current scope is ten
investigated strategies: seven PROVISIONAL portfolio backtests, two unsuccessful
applicability assessments and conditional/unrun ILLIQ. The four approvals are
consumed; no repeats, ILLIQ portfolio run or final Keep/Drop is authorized.
See `india_research/reports/india_phase2_provisional_backtests.md` for the full
comparison, source/data hashes, output directories and frozen-vintage/calendar
limitations. Existing strict certification flags remain false and unchanged.


### Separately approved ILLIQ diagnostic and ten-strategy comparison

The user explicitly accepted the previously declared adjusted-INR close × vendor-
volume proxy, India metadata exception and measured 51/209 dividend/31/209 fixed-
normalization sensitivities for one ILLIQ portfolio diagnostic. It completed on
research_v4 with the original Vibe formula/IC and unchanged 25-session preparation
and portfolio settings: IC -0.00310559 (207 intervals), daily net Sharpe 0.748968,
net cumulative return 70.4904%, 208 executions and 491 stock legs. Signals reproduce
the readiness audit; every target, next-session execution, return label and cost
reconciles. No post-2024 label or observation was used.

This is a closing-price turnover proxy, not actual NSE turnover, a nominal history
or a historically point-in-time vintage. Original country metadata still omits
India: developer research exception only, no upstream endorsement. No alternative
convention was selected from returns. Frozen-vintage, Reliance/Kotak, benchmark
and exhaustive-calendar-inventory limitations remain documented; strict flags are
unchanged. Current product checks pass on 256 source-hashed official observations.

Complete suite: 353 passed, including 24 new scoped ILLIQ tests. All 1,036 earlier
files and eight completed-run inventories verify unchanged. Current ten-strategy
scope is eight PROVISIONAL portfolio diagnostics plus two non-evaluable factors
(#003/#004), with no final Keep/Drop labels. The previous seven-strategy report is
preserved; use `india_research/reports/india_ten_strategy_provisional_comparison.md`
for current comparison, exact output/provenance and accepted caveats. The single
ILLIQ approval is consumed; no repeat, new convention or publication is authorized.
