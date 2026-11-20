# Week 4 local Strategy Log: three unchanged hypotheses

These are the first three Week 3 hypotheses in their original list order. The new guide requires extending the test to October 31, 2026. The earlier 2022–September 2025 test has already been observed; the extension is not an untouched holdout. No rules are chosen from the extended-test results. This local log is prepared before the first Week 4 portfolio invocation; shared-sheet posting remains manual.

Train June 1, 2016–December 31, 2021; test January 1, 2022–October 31, 2026. `holdout_start` in config is the first excluded research date, November 1. November onward is display-only. Every completed Monday–Sunday UTC week W first acts at the following week's first actual market open. The partial October 26–November 1 week is excluded.

## Shared exact definitions

For stock i and session t, r=(close_t+cash_dividend_t)/close_(t-1)-1. RV20/RV63 are trailing sample standard deviations over 20/63 sessions. Weekly return is the product of (1+r) during that week minus one. Shock=weekly return/(last RV20×sqrt(5)). Volume/turnover activity is a proxy: weekly sum(close×vendor volume), divided by the median of the preceding eight completed weekly sums, with +1 in numerator and denominator. It is not certified nominal historical traded value.

Wiki view and edit ratios=(current completed weekly count+1)/(median of preceding eight full weeks+1). Views use Wikimedia user pageviews and the dated English title history. Net added text between historical weekly revision endpoints is processed by the unchanged team `FinbertScorer`/`prepare_text`, ProsusAI/finbert revision0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031, maximum512tokens. Sentiment=positive−negative, then the mean of observed additions in the trailing four weeks. Missing additions remain missing.

Index volatility=63-session sample std(r)×sqrt(252); stress reference is the 90th percentile of the strictly prior expanding history, at least126observations. Index downside=sqrt(mean(min(r,0)^2) over20sessions)×sqrt(252); its stress reference is the strictly prior expanding75th percentile, at least126observations. Beta=126-session covariance(stock,index)/index variance. Residual dislocation=sum of last five (stock return−beta×index return)/(63-session std of residual×sqrt(5)).

Market-attention proxy=mean across the configured sample of log(view ratio). Its z-score uses the preceding52weeks' mean and sample std, minimum26observations. This is attention in the five/ten-stock sample, not every constituent in the market.

All indicators enter only through completed weeks. A name needs a positive observed RV63. Each strategy has a regime layer, stock selection/priority layer, and execution/risk layer. Eligible stocks are weighted inversely to RV63; cap10%pername at entry, at mosttennames, unused cash idle, no leverage or shorting. Priority orders selection; rank IC separately scores eligible stocks as1+within-eligible percentile rank, rejected observed stocks0, missing lookbacksNaN.

Entries execute at the following week's first tradable open. Exit at first of a close-based stop (executed next tradable open), next weekly rebalance, or five market sessions. A stop uses (current close+cash dividends since entry)/(entry open×1.001)−1. There is no intrabar stop fill. Known calendar/split end limits stop new entries whose planned exit is outside the split. An unexpected non-executable terminal exit fails preflight; delayed exit overlapping a later same-name entry also fails. It never silently erases an earlier entry.

US costs use actual Vibe GlobalEquityEngine 10bpsslippage each side, no extra commission. HK uses its commission/levy/settlement/slippage, with dated0.10%/0.13%duty and whole-HKD ceiling. The dated2026-11-12official lot snapshot is an explicitly disclosed historical-lot assumption. No claim of historical lots or fully harmonized adjustment/volume.

## Liquidity repair

Buy negative volatility-scaled weekly returns when turnover, Wikipedia views and added-text sentiment support a temporary liquidity shock. Entry conditions: Shock<−shock threshold, activity ratio≥volume threshold, view ratio≥views threshold, sentiment≥sentiment threshold. Rank by−Shock. Halve new-book exposure if index volatility exceeds its prior expanding90th percentile. Close stop5%.

Threshold variants `(shock,volume,views,sentiment)` are tried in this fixed order: `(2,1.5,1.2,0.1)`, `(1,1,1,0)`, `(0.5,0.8,0.8,−0.1)`, `(0,0.5,0.5,−0.1)`.

## Defensive attention gate

Hold stocks at or below the cross-sectional median RV63, with trailing63-session median(close×volume) at or above the configured cross-sectional liquidity quantile, and observed sentiment at or above threshold. Rank by−RV63. Index-volatility size scale=min(1,0.10/index annual volatility); additionally halve the entire new weekly book when the sample market-attention z-score>1.5. Close stop8%.

Variants `(liquidity quantile,sentiment)` in fixed order: `(0.5,0)`, `(0.25,−0.05)`, `(0,−0.1)`. This is the required attention-as-risk-filter strategy.

## Residual repair

Buy residual dislocation<−shock threshold, activity ratio≥volume threshold, wiki edit ratio≥edits threshold, and sentiment≥sentiment threshold. Rank by−residual dislocation. Halve exposure if index downside exceeds its prior expanding75th percentile. Close stop6%.

Variants `(shock,volume,edits,sentiment)` in fixed order: `(2,1.5,1.5,0.1)`, `(1,1,1,0)`, `(0.5,0.8,0.8,−0.1)`, `(0,0.5,0.5,−0.1)`.

## Evaluation and selection fixed before execution

Select the first listed threshold variant producing at least30completed train entries, using counts only. Retain the final variant and mark ineligible if none reaches30. Both markets' choices are sealed before any extended test.

Complete TRAIN base portfolios,200random timing controls percase, and drop-one-indicator ablations before test. Random controls retain instrument, number, realized holding durations and weights and use the identical engine/costs. Any indicator whose removal leaves train returns and entry count unchanged makes that fixed-formula market case ineligible; do not tune formulas after seeing test.

For the candidate prefer strategies eligible in BOTH train markets: ≥30entries, timing percentile≥90, no unchanged train ablation. Among them choose the highest arithmetic mean train Sharpe, lexical strategyIDtie-break. If none is eligible, still identify the highest mean train strategy as an INELIGIBLE research nominee. Freeze candidate and train diagnostics before test. Nomination is not KEEP.

Run unchanged test once. Report weekly cross-sectional five-session open-to-open-plus-dividend Spearman IC (different from actual stop-controlled holding returns), annualized daily net Sharpe, max drawdown from initial cash, timing percentile, index Sharpe, ablations, and upstream DSR. KEEP only if≥30trainentries, neither redundant train indicator nor other eligibility failure,≥90th timing percentile in BOTH train and test, and test Sharpe above index.

Prior recorded search count268=21legacy strategies+101HSI factor attempts+22train variants+124base/ablation evaluations. Add every actual new train-selection and base/ablation invocation; timing nulls are controls, not searched candidates. DSR uses upstream `deflated_sharpe_ratio`, per-day Sharpes, all known trials, and dispersion from comparable observed current-period trials. Unavailable older Sharpes and undocumented searches are not fabricated.

Native candidate verification uses unchanged Vibe `python -m backtest.runner` on hash-sealed Yahoo frames, an embedded decision-date target CSV, and the runner's own one-bar shift. Record differences in weekly close/reopen vs target-rebalance semantics, separate dividends, dated duty, and native benchmark resolution. Explain Sharpe gaps>0.1 before claiming numerical agreement. Do not tune the candidate to match.
