> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# PROVISIONAL India alpha101_002 diagnostic

**One user-approved diagnostic completed on verified research_v4. No final Keep/Drop decision.**

Results: `archive:india_alpha101_002_PROVISIONAL_20261029T040140Z_4784a95f/`.
Dataset: `archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/`.
Dataset manifest SHA-256: `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`.
Readiness review SHA-256: `f2ed66105d57c98b4816a85b7505b274241696f468bcf5d4262db7aeecfaf6bc`.

## Preflight, original implementation and approved methodology

The finalized reconciliation package's exact inventory hash and all 40 recorded artifacts were verified. Its read-only verifier reparsed the source NSE/Yahoo quantities, confirming the 12 corrected volume observations, 24 exact anchors, unchanged prices/other tokens and preserved older results. The dataset was not rebuilt or reconciled again. The prior **218-test baseline** was verified from the preserved finalization record/log. After adding 17 approval/provenance-boundary regression cases, the complete suite passed **235 tests in 20.01 seconds**, with no failures or skips, before execution.

New `src/india_alpha002_diagnostic.py` runs only `alpha101_002` via the existing isolated Vibe bridge and `backtest_factor`. It calls unchanged Vibe `agent/src/factors/zoo/alpha101/alpha_002.py::compute`: negative six-session correlation of cross-sectional ranks of two-session log-volume changes and intraday open-to-close returns. It uses original Vibe IC and the existing Jack-inspired `simulate_portfolio`; no formula, NaN rule or helper changed. Original factor/base/IC hashes were checked against the earlier audited source versions and preserved with code snapshots.

All `PortfolioConfig()` values were checked against the archived STREV configuration: eight assigned NSE equities, separate ^NSEI benchmark, January 4, 2021–December 31, 2024 evaluation, weekly W-FRI signals, top-two long-only 50/50 targets, original-score descending/ticker ascending ordering, eight finite scores required, strictly subsequent eligible-close execution, 10 bps per absolute traded NAV, weight drift, zero cash interest/risk-free and sample-standard-deviation daily net Sharpe scaled by sqrt(252). Initial cash days are included; no forced terminal liquidation or post-cutoff observations are used.

The common **25 prior sessions**, November 26, 2020–January 1, 2021, support the original factor's declared ten-bar warm-up. There are **1,015 input sessions and 990 evaluation sessions**. Generic shared calendar validation retains its auxiliary 21-session offset check; the full input date set and 25 prior sessions are checked separately, without redefining this factor's lookback.

The user approval is bound to #2, research_v4, exact readiness/package hashes and unchanged settings. It permits this single provisional diagnostic, accepting only the reviewed exhaustive-calendar-inventory uncertainty; it does not authorize another factor, repeat experiment, data repair, changed settings or a final Keep/Drop. All certification flags in the original dataset remain unchanged and false.

## Actual results — PROVISIONAL

| Metric | alpha101_002 portfolio | Nifty 50 benchmark |
|---|---:|---:|
| Cumulative return | **38.0712% net** | **67.3032%** |
| Annualized daily Sharpe | **0.498502 net** | **0.978960** |
| Maximum drawdown | **-20.2087% net** | See saved daily benchmark NAV |

Gross cumulative return before approved turnover costs was **82.2180%**. Net cumulative return was **29.2320 percentage points below** the benchmark. These measurements do not establish a final factor acceptance decision or statistical significance.

**Execution-aligned mean Spearman rank IC: 0.01814609**, over **206 valid completed intervals**, with **zero undefined IC intervals**. For each successfully executed target, IC correlates its signal-close scores across all eight stocks with their return from the actual execution close to the next successful execution close. It is not portfolio Sharpe or IC information ratio, and the last uncompleted holding interval is not given a fabricated exit label.

| Execution / cost accounting | Actual |
|---|---:|
| Evaluation daily observations | 990 |
| Successful rebalance executions | 207 |
| Stock trade legs | 689 |
| First / last execution | 2021-01-11 / 2024-12-30 |
| Total absolute NAV turnover | 277.211127 |
| Sum of daily cost fractions | 0.277211127 |

Trade legs are nonzero stock weight adjustments, not entire rebalances, round trips or asserted exchange share orders. The 27.7211% sum of daily cost fractions is measured over changing NAV bases; it is not a direct percentage-point deduction from terminal return. Costs reconcile to turnover at 0.001 per unit and apply multiplicatively to each day's gross return. All individual costs, trade legs and daily returns/NAV are saved.

## NaNs, skipped signals and execution-aligned labels

The real factor scores match the prior research_v4 signal-only audit: **7,916 of 7,920 finite evaluation scores**, four original NaNs, 986 fully finite daily rows and 208 of 209 fully finite weekly candidates. The 209 candidates include the terminal December 31 date, which cannot stage a later trade. There are no weekly top-two cutoff ties. Leading warm-up contributes 56 missing cells; those are saved separately from evaluation missingness.

The four evaluation NaNs remain exactly:

- HDFCBANK.NS: August 9, 10 and 11, 2021.
- RELIANCE.NS: March 25, 2022.

All four arise from constant ranked-input correlation windows, not missing downloaded observations. No NaN was filled or score synthesized. Only March 25 is a weekly signal date; its target was skipped because fewer than eight scores were available. Existing holdings remained and drifted normally. The terminal December 31 candidate was also skipped because no later permitted execution exists. No order was deferred or cancelled.

The skipped March 25 signal creates a **ten-session** completed IC interval: the March 17, 2022 signal executed March 21 and is labelled through the next successful execution on **April 4, 2022**. There was no invented March 28 rebalance/fee. Other completed IC intervals span 3 sessions (4 intervals), 4 sessions (44), or 5 sessions (157), reflecting the actual session calendar. `ic_intervals.csv` records every signal, entry/exit date, session length and pair count.

Every execution is strictly after its signal and on/before **December 31, 2024**. Every return-label entry/exit is on/before that cutoff; last successful execution is December 30. The benchmark return series matches the archived STREV series exactly, preserving the same first-evaluation-close reporting convention.

## Research_v4 provenance and unresolved limitations

The twelve recovered quantities use independently verified surrounding frozen-vendor units: Reliance ×2, HDFC Bank ×2 and Kotak Bank ×5. The ledger, nominal source quantities, exact anchors and dataset manifest are copied into this output; all original snapshots and prior backtests remain unchanged. No additional volume transformations were made during this run.

Remaining limitations are explicitly retained:

- **Reliance:** the exact pre-July-2023 vendor non-split price/volume normalization is not independently explained. No empirical-ratio fix was invented. Its potential effect on interpretation around that corporate event remains a real research limitation.
- **Kotak:** the March 1, 2024 five-vendor-share discrepancy remains unmodified; rounding/revision is not asserted as proven.
- **Historical vintage:** these are frozen vendor-adjusted histories, **not historically point-in-time data**. Later corporate-action metadata helps define that frozen share basis; no holdout prices were fetched or used. Full-tape official volume or exhaustive historical-calendar certification is not claimed.
- **Price quality:** the 12 repeated-close flags remain visible. No missing/zero-volume, missing-close or >20% adjusted-close-move flags occur in this analysis slice. Repeated closes are observations, not proof of invalid prices; none were excluded or repaired.
- **Portfolio realism:** fixed eight-stock selection, fractional holdings, flat costs, positive-volume/published-close execution proxies and absent spread/impact/tax modelling limit interpretation, especially in short special sessions. Nifty 50 is a price index while the stock histories carry dividend adjustments.

No remaining execution blocker occurred. These limitations keep the results PROVISIONAL and prevent a claim of definitive strategy validation.

## Tests, saved outputs and independent post-run checks

The 235-test full suite includes the original 218 tests plus **17 new synthetic** cases in `tests/test_india_alpha002_diagnostic.py`. They reject changed approval, factor, dataset/review/package hashes, portfolio settings, warm-up, calendar failures and incomplete volume verification. Existing original-factor formula, causal timing, missing-data, turnover, IC, Sharpe, source-integrity and cutoff tests passed. Synthetic tests for other factors are part of the required full suite; **no other real-data factor was run**.

An independent saved-output verifier passed all **324 protected input hashes**, current output/source hashes, 12 corrected volumes, session counts/cutoff, original score equality/four NaNs, all 207 execution timings and top-two equal weights, all 206 IC return labels, the ten-session skipped-signal interval, 689 trade legs and turnover/cost reconciliation, numerical Sharpe/cumulative-return/IC identities, identical archived benchmark returns and unchanged certification flags. It did not recalculate a factor or rerun a portfolio.

Exact executed commands:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m src.india_alpha002_diagnostic --approved-alpha002-diagnostic
```

The one approved experiment is complete; another run requires new authorization. The output contains exact configuration/approval, reviewed evidence and volume ledger, all used OHLCV/benchmark matrices, source scores/NaNs/causes and coverage, IC scores/return labels/interval dates, daily portfolio/gross/net/benchmark returns and NAV, holdings, executions, trades, costs, order log, flags/warnings, metrics, original 218-test and new 235-test logs, console output, source snapshots and Git/package/runtime provenance, and a complete SHA-256 inventory. `verify_saved_run.py` checks these saved results without another backtest.

The original research_v4 package, STREV and alpha101_001 results, factor definitions and approved settings remain unchanged. No commit, push, package installation or publication. Stop for review.
