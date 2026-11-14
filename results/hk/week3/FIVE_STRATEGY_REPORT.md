# Five strategies: completed local Week 3 evaluation

All five strategies were actually tested in both HK and US. **All ten market cases are DROP** under the guide's gates. DROP means insufficient evidence under this protocol, not proof that an economic idea can never work. No rule was changed after test results were opened.

Train: **2016-06-01–2021-12-31**. Test: **2022-01-01–2025-09-30**. Test IC is weekly cross-sectional Spearman rank correlation with the next five-session open-to-open return including cash dividends. Sharpe is annualized daily net Sharpe, zero risk-free/cash return. The CSV also contains train IC and USD Sharpes.

**IC review correction:** the table uses the separate selection-oriented diagnostic in `five_strategy_results_reviewed.csv`. The original frozen score incorrectly placed selected negative-priority names below rejected zero-score names for Defensive Attention Gate and Information Compression. The corrected score ranks eligible names above rejected names while preserving their original within-selection priority. Original IC exports remain preserved. No trades, returns, Sharpe, costs, timing controls, DSR or decisions were changed, and no portfolio was rerun. The same deterministic correction was applied to all 124 base/ablation ICs, including zero-priority ablations. Protocol and source hash were logged before that diagnostic.

| Market | Strategy | Test IC | Sharpe train / test | Index test SR | Entries train / test | Timing percentile train / test | Test DSR p | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HK | Liquidity repair | 0.1316 | -0.418 / 0.624 | 0.270 | 108 / 95 | 20.5 / 92.0 | 0.137 | DROP |
| HK | Defensive attention gate | -0.0086 | -0.362 / 0.071 | 0.270 | 202 / 175 | 25.5 / 62.5 | 0.017 | DROP |
| HK | Residual repair | 0.0840 | -0.201 / 0.864 | 0.270 | 60 / 71 | 34.0 / 98.5 | 0.254 | DROP |
| HK | Information compression | -0.1299 | -0.070 / -0.509 | 0.270 | 107 / 96 | 59.0 / 14.0 | 0.000 | DROP |
| HK | Attention exhaustion | 0.0426 | 0.004 / 0.502 | 0.270 | 91 / 72 | 63.5 / 89.5 | 0.094 | DROP |
| US | Liquidity repair | -0.0396 | 0.446 / 0.016 | 0.660 | 43 / 30 | 60.0 / 36.0 | 0.013 | DROP |
| US | Defensive attention gate | -0.0455 | 0.841 / 0.296 | 0.660 | 263 / 138 | 64.0 / 69.0 | 0.044 | DROP |
| US | Residual repair | 0.0181 | 0.634 / 0.836 | 0.660 | 51 / 41 | 77.0 / 93.5 | 0.232 | DROP |
| US | Information compression | -0.0289 | 0.288 / 0.263 | 0.660 | 245 / 160 | 10.5 / 51.0 | 0.040 | DROP |
| US | Attention exhaustion | -0.0392 | 0.747 / 0.140 | 0.660 | 224 / 143 | 54.0 / 38.5 | 0.024 | DROP |

KEEP required at least 30 completed train entries, test Sharpe above the index, and beating at least 90% of 200 random timing runs in **both** periods. IC and DSR are reported, with no invented extra threshold. All cases met the entry minimum; all failed at least one performance gate. HK benchmark is the HSI price index, US is SPY with cash dividends.

## What each strategy does and why it failed

### Liquidity repair

Buy contrarian weekly sell-offs when trading activity and independently observed Wikipedia information support a temporary liquidity-shock interpretation.

HK had positive test IC and beat the HSI test Sharpe, but its train timing percentile was only 20.5%. US test IC turned negative and net Sharpe fell to 0.016. The hypothesized reversal was not stable across markets or periods.

| Market | Formal failed gate(s) |
| --- | --- |
| HK | train below 90th-percentile timing control |
| US | test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control |

### Defensive attention gate

Hold liquid low-volatility stocks with nonnegative observed information sentiment, and halve the entire book after unusually high market-wide Wikipedia attention.

Both test Sharpes lagged their indices. The whole-book attention gate slightly helped HK test Sharpe (0.071 versus 0.067 without it), but hurt US test Sharpe (0.296 versus 0.322). That is weak, inconsistent evidence for this gate on these small books.

| Market | Formal failed gate(s) |
| --- | --- |
| HK | test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control |
| US | test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control |

### Residual repair

Buy stock-specific negative residual-return dislocations when volume, edit activity and text sentiment support a reversal rather than negative information.

The strongest test candidate: HK and US both beat their test indices and exceeded the 90th timing percentile in test. Neither passed the train timing gate (34% and 77%). Edit activity mattered in test: removing it cut HK Sharpe by about 0.59 and US Sharpe by about 0.73. This is a research lead, not a passing strategy.

| Market | Formal failed gate(s) |
| --- | --- |
| HK | train below 90th-percentile timing control |
| US | train below 90th-percentile timing control |

### Information compression

Buy stocks with low recent volatility relative to their longer history when Wikipedia attention and text sentiment suggest information interest without a price breakout requirement.

Reviewed selection-oriented test IC is negative in both markets, consistent with the weak portfolio results. HK test Sharpe was negative, and US lagged SPY. In US, removing the Wikipedia-view condition raised test Sharpe from 0.263 to 0.698; attention selection over-filtered this sample. This diagnostic does not authorize tuning against the same test period.

| Market | Formal failed gate(s) |
| --- | --- |
| HK | test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control |
| US | test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control |

### Attention exhaustion

Buy negative-return stocks after a Wikipedia attention spike begins fading, provided liquidity and observed text sentiment do not signal continuing information deterioration.

HK test Sharpe beat HSI, but its 89.5th timing percentile missed the required 90, and train was only 63.5. US had negative test IC and weak net Sharpe. The US test volume floor changed no trade or return when removed, so it adds no demonstrated value there and should be cut in a future, newly registered design.

| Market | Formal failed gate(s) |
| --- | --- |
| HK | train below 90th-percentile timing control; test below 90th-percentile timing control |
| US | test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control |

## How the seven requirements were handled

1. **Four or more indicators, two sources:** every strategy has five or six named indicators combining Yahoo price/volume with Wikimedia views, revisions and historical added-text sentiment. No unqualified thin Reddit source was silently included.
2. **Three layers:** an index-volatility/downside regime sets size; stock selection combines attention, sentiment and market features; close-based stops execute at the next tradable open, with a maximum five-session/next-week holding period.
3. **Attention as a risk filter:** the defensive strategy halves the entire next week's book after market attention z-score >1.5. This is separate from stock ranking.
4. **Two markets:** five HK stocks and ten US stocks, independently evaluated. This is not an all-HSI portfolio study.
5. **Rules before testing:** local immutable rules frozen at 2026-11-12T08:56:26.740443+00:00; both markets' count-only selections frozen before the first test run. A shared-sheet-ready CSV is included. The rules were **not posted to the team's shared sheet**; that literal external deliverable remains for Jack.
6. **Enough train trades:** tried only the prelisted variants in order, stopping at the first with 30 completed entries. Selection used entry counts, not Sharpe. Every attempted variant is retained in the full result archive. Final train counts range from 43 to 263.
7. **Costs:** actual Vibe GlobalEquityEngine order planning, execution, cash, lots and trade records. US stocks incur 10-bps slippage per side; no ETF entries or shorts. HK retains Vibe commission/levy/settlement/slippage and adds dated 0.10%/0.13% duty with whole-HKD ceiling. All scheduled trades executed without silent rejection or missing-lot fallback.

## Additional evaluation

- **4,000 random timing runs:** 200 for each of 5 strategies × 2 markets × 2 periods. Same instrument, count, realized holding durations and target weights; entry dates randomized within listing/execution bounds, no same-stock overlap. Each uses the same engine and costs. Dollar notional varies with portfolio equity, consistently with the candidate sizing rule.
- **104 drop-one evaluations:** each named indicator removed from both its gate and ranking role, and risk gates neutralized. See `five_strategy_ablations_reviewed.csv`; `sharpe_change` is ablated minus base. Any indicator that changes nothing is a removal candidate for a future preregistration; completed rules/results remain frozen.
- **268 recorded trials for DSR:** 21 legacy strategies + 101 HSI factor-screen attempts + 22 train variant runs + 124 base/ablation evaluations. Random timing controls are null draws, not searched strategies. The variance estimate uses comparable current-period daily Sharpes; unavailable older Sharpe values are not fabricated. This is a conservative documented-search approximation, not certification of unknown prior searches.
- **Preregistration integrity:** the 12 frozen code/config hashes and 22 initial input hashes still match after execution. The verification summary also records attention-input hashes and actual Vibe engine hashes.
- Two earlier preflight attempts failed before engine execution (calendar reconciliation and an import error). Both are retained with zero strategy trials. Calendar fixes follow official HKEX closure notices; no price row was fabricated to fill a closure.

## Material limits

These are exploratory research results. The selected five HK and ten US names are current large-company samples, with survivorship/selection bias. Three HK stocks have shorter listed histories. Historical Yahoo prices are current-vintage split-adjusted observations with separate cash dividends; stock-in-kind events, nominal historical share units and volume adjustment are not comprehensively certified. The official 2026-11-12 board-lot snapshot is an explicit historical-lot assumption, not a point-in-time lot history. Non-duty HK fees retain upstream constant defaults. These limitations preclude a production or fully point-in-time performance claim.

Only complete historical weeks enter signals; article snapshots precede entries, missing sentiment remains missing, and the first 512 tokens of net added English text are scored by fixed ProsusAI/finbert. The four-week observed-additions mean can be sparse. Wikimedia user pageviews exclude bots; historical suppressed/deleted titles may remain unavailable. Weekly archives and the fixed modern classifier do not prove what every historical investor could have consumed.

Per-stock entry caps and selective signals leave mean exposure around 1–7%; remaining cash earns zero. Benchmark exposure is a full index investment. Do not compare these net Sharpes as if risk, cash yield, universe or dividend conventions were identical. Small HK cross-sections make IC noisy. None of the results establishes why a mechanism works causally; the explanations above are interpretations supported by diagnostics.

## Files

- `five_strategy_results_reviewed.csv`: current requested what-it-does, IC, train/test Sharpe, keep/drop and formal reasons.
- `strategy_log_sheet_ready.csv`: five rules expanded to ten market rows, seven-requirement fields, outcomes and interpretation for manual sheet entry.
- `five_strategy_preregistration.json`, `five_strategy_selected_variants.json`: frozen definitions and train-only selections.
- `five_strategy_ablations_reviewed.csv`, `five_strategy_random_timing.csv`: current compact diagnostics; `five_strategy_ic_reviewed.csv` records original/reviewed IC and observation counts.
- `five_strategy_full_results.json`: local native trade records and complete trial ledger (ignored, about 17.2 MB).
- Ignored `data/hk_week3/runs/five_v2c_preflight_20261112/`: bounded engine input, requests, result arrays, immutable log and source hashes.

GitHub publishing, shared-sheet entry, team messages and actual cloud/frontend integration are not local backtest completion claims.

Original `five_strategy_results.csv`, `five_strategy_ablations.csv` and full result JSON preserve the initial IC statistics for audit. Use the reviewed exports for current IC reporting. This reporting correction is not a new searched strategy trial; the 268-trial portfolio ledger is unchanged.
