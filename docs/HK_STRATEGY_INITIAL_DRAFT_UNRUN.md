> Historical, unrun initial three-strategy draft. Superseded before any performance test by config/hk_week3_research.json and the five-strategy immutable log. Do not interpret this file as current readiness.

# Week 3 candidate rules: local preregistration draft

Prepared before any new Week 3 strategy execution. These rules have not been
entered into the shared Strategy Log sheet, and **none of these candidates has
been backtested**. First put the rules in the sheet; record any train-only
changes as a new trial. Do not tune after inspecting the test period.

All three candidates run on US and HK independently. Train: 2016-06-01 through
2021-12-31; test: 2022-01-01 through 2025-09-30. No observation dated
2025-10-01 or later enters research. Current live quotes are operational
evidence, not historical strategy inputs. These are research hypotheses,
not claims about proprietary quant-firm strategies or expected profitability.

Common definitions: daily adjusted OHLCV with explicit corporate-action and
volume basis; features known at Friday's close execute at the next session's
open. Wikipedia abnormal attention uses `config.spike.baseline_weeks`, currently
8, excluding the current week. Missing history/text/FX/lot information is
missing, never a zero sentiment or zero-volume observation. FinBERT means
`ProsusAI/finbert`, with net positive-minus-negative article-added-text sentiment
aggregated only after its publication. Wikipedia edits require actual dated
diff text; present-day article text is not a substitute.

## 1. Liquidity-dislocation repair

Hypothesis: a temporary liquidity shock can reverse when company information
remains constructive. This is a contrarian rule.

- Regime: full exposure when the index's trailing 63-session volatility is
  below its expanding historical 90th percentile; otherwise half exposure.
- Entry, all conditions: previous week's stock return below minus twice its
  trailing 20-session daily volatility times sqrt(5); weekly turnover above
  1.5 times its past attention-baseline-window median; Wikipedia views above
  1.2 times the past baseline; FinBERT net added-text sentiment >0.1.
- Rank: most negative volatility-normalized weekly return first; at most ten
  names. Exit at the first of a 5% loss from entry or five trading sessions.
- Size: inverse trailing 63-session volatility, maximum 10% per stock, no
  redistribution above caps. Cash holds unused exposure.

Indicators: index volatility, stock return dislocation, turnover surprise,
Wikipedia view surprise and text sentiment. Sources: price/volume + Wikipedia.
Why it might fail: adverse-selection shocks persist, attention arrives late,
or the apparent reversal disappears after HK costs and next-open execution.

## 2. Defensive low-volatility book with an attention risk gate

Hypothesis: attention is more useful for scaling risk than picking winners.

- Regime: target 10% annualized index-volatility exposure, bounded [0,1],
  estimated from the previous 63 sessions.
- Entry: select the ten lowest-volatility stocks among names with 63-session
  median turnover above the cross-sectional median and nonnegative trailing
  four-week FinBERT Wikipedia-added-text sentiment. No price-momentum rank.
- Attention risk gate: market-wide abnormal Wikipedia views are averaged
  across eligible stocks. If the current observation exceeds its prior
  52-week mean by 1.5 prior standard deviations, halve **the whole book's**
  exposure for next week. The gate is not a stock-selection score.
- Exit/risk: rebalance every four weeks; 8% trailing stop, or negative text
  sentiment for two completed weeks; inverse volatility and 10% per-name cap.

Indicators: index volatility, stock volatility, turnover, article sentiment
and market attention z-score. Sources: price/volume + Wikipedia. Why it might
fail: crowding in defensive stocks, costs, slow article updates, or the risk
gate responding after a sell-off rather than before it.

## 3. Idiosyncratic sell-off with information confirmation

Hypothesis: a stock-specific sell-off can overshoot when new information is
not negative, while market-wide panics should be avoided.

- Regime: half exposure when the index's 20-session downside semideviation
  exceeds its expanding historical 75th percentile; otherwise full exposure.
- Entry: the stock's five-session residual return from a trailing
  126-session stock/index OLS beta is below minus two trailing residual
  standard deviations; volume exceeds 1.5 times its past 20-session median;
  Wikipedia edits exceed 1.5 times their past baseline; FinBERT net sentiment
  on those week's added text is >0.1. All fits use past observations only.
- Rank: most negative standardized residual first, at most ten names.
- Exit/risk: residual recovers to its previous 20-session mean, a 6% loss
  from entry occurs, or ten sessions elapse; inverse residual volatility,
  maximum 10% per stock, no leverage or shorts.

Indicators: downside regime, residual dislocation, volume surprise, edit
surprise and sentiment. Sources: price/volume + Wikipedia. Why it might fail:
negative fundamental news is missed by edited text, beta is unstable, or
illiquid executions overwhelm a small expected reversal.

## Required evaluation and current readiness

Run each candidate in both markets with identical timing and reporting:

1. At least 30 train entries. If insufficient, record a new train-only trial;
   do not label a seven-trade result validated.
2. Report cross-sectional Spearman IC against the predeclared next execution
   interval; reject dates with fewer than two usable stocks.
3. Report daily net Sharpe as `train / test`, plus the same benchmark Sharpe
   (SPY / ^HSI) and exposure/cash assumptions.
4. Run 200 random **entry-timing** schedules separately within each split,
   preserving instruments, number of trades, sides, sizes and realized holding
   durations. Use the same engine and cost settings. `src.hk.evaluation` builds
   these schedules; it has not been connected to a Week 3 execution runner.
5. Drop one indicator at a time and rerun with otherwise frozen rules. Specify
   removal of a gate as its neutral value, not as removal of the strategy.
6. Report Bailey–Lopez de Prado DSR using every attempted rule variant's
   unannualized Sharpe at the same observation frequency. The complete prior
   trial history is not yet available, so no numeric DSR is asserted.
7. KEEP only if test Sharpe exceeds the index and performance strictly beats
   at least 90% of timing-null runs in **both** periods. Otherwise DROP after
   an executed evaluation, with the failed gate and explanation.

Costs: US stocks 10 bps per unit turnover (ETFs 3 bps); no shorts here. HK uses
Vibe's HK engine, with documented taxes, duties, lots, slippage and date effects
from the design note. Fixed 10-bps-only legacy HK simulations do not satisfy it.

| Candidate | US IC / Sharpe | HK IC / Sharpe | Status |
|---|---|---|---|
| Liquidity-dislocation repair | N/A / N/A | N/A / N/A | UNRUN |
| Defensive attention risk gate | N/A / N/A | N/A / N/A | UNRUN |
| Idiosyncratic sell-off confirmation | N/A / N/A | N/A / N/A | UNRUN |

Missing prerequisites: verified historical title intervals, dated Wikipedia
views/edit diffs and their FinBERT outputs covering both splits, data-quality
review, historical lots/cost treatment, complete trial ledger, shared-sheet
preregistration and an engine-connected multi-source strategy runner. Current
reference mappings are not historically valid backtest inputs.
