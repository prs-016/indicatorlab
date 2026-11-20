# Week 4: three fixed strategies, extended evaluation

The three original hypotheses were retained before the new run, with complete TRAIN diagnostics and a train-only candidate selection before the extended TEST. The earlier test interval through September 2025 was already observed; this mandated extension is not an untouched holdout. No formulas or thresholds changed after test.

Train **2016-06-01–2021-12-31**. Test **2022-01-01–2026-10-31**. Research prices end at the last session, October 30. November onward is display-only. IC is mean weekly cross-sectional Spearman rank correlation with the next five-session open-to-open cash-dividend-inclusive return; Sharpe is annualized daily net at zero cash/risk-free return. The IC horizon differs from actual stopped holdings; constant/all-missing-score weeks are excluded, so IC is conditional on a usable cross-section.

| Market | Strategy | Test IC | Sharpe train / test | Test max drawdown | Timing percentile train / test | Index test Sharpe | DSR probability | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| HK | liquidity repair | 0.0520 | -0.418 / 0.175 | -5.92% | 20.5 / 84.5 | 0.119 | 0.010198 | DROP |
| HK | defensive attention gate | -0.0174 | -0.362 / -0.461 | -5.15% | 25.5 / 37.0 | 0.119 | 0.000147 | DROP |
| HK | residual repair | 0.0919 | -0.201 / 0.371 | -4.78% | 34.0 / 92.5 | 0.119 | 0.026896 | DROP |
| US | liquidity repair | -0.0404 | 0.446 / 0.050 | -1.76% | 60.0 / 41.5 | 0.719 | 0.004825 | DROP |
| US | defensive attention gate | -0.0320 | 1.118 / 0.514 | -2.33% | 93.0 / 79.5 | 0.719 | 0.056776 | DROP |
| US | residual repair | 0.0594 | 0.634 / 0.697 | -3.54% | 77.0 / 85.5 | 0.719 | 0.126052 | DROP |

## What each strategy does and why

### Liquidity repair

Buy contrarian weekly sell-offs when trading activity and independently observed Wikipedia information support a temporary liquidity-shock interpretation.

HK’s positive test IC did not produce an unusual enough return relative to the timing controls. The US negative IC and near-zero net Sharpe suggest that the contrarian filter did not transfer reliably to that sample.

HK: **DROP**. train below 90th-percentile timing control; test below 90th-percentile timing control. Train/test entries 108/143; test IC 0.0520. Removing turnover_ratio had the largest adverse TRAIN Sharpe effect (-0.399). These are diagnostics, not causal proof or permission to tune against test.
US: **DROP**. test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control. Train/test entries 43/38; test IC -0.0404. Removing wiki_views_ratio had the largest adverse TRAIN Sharpe effect (-0.168). These are diagnostics, not causal proof or permission to tune against test.

### Defensive attention gate

Hold liquid low-volatility stocks with nonnegative observed information sentiment, and halve the entire book after unusually high market-wide Wikipedia attention.

The US train edge faded in the extended test, while the HK portfolio had negative test Sharpe. Low volatility and attention gating did not provide a stable cross-market defensive result after the prescribed costs.

HK: **DROP**. test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control. Train/test entries 202/239; test IC -0.0174. Removing stock_volatility_rank had the largest adverse TRAIN Sharpe effect (-0.050). These are diagnostics, not causal proof or permission to tune against test.
US: **DROP**. test Sharpe does not beat index; test below 90th-percentile timing control. Train/test entries 263/191; test IC -0.0320. Removing wiki_added_text_sentiment had the largest adverse TRAIN Sharpe effect (-0.409). These are diagnostics, not causal proof or permission to tune against test.

### Residual repair

Buy stock-specific negative residual-return dislocations when volume, edit activity and text sentiment support a reversal rather than negative information.

HK beat its test index and timing baseline, but its poor train timing result prevents a KEEP. US test Sharpe was close to, but below, its index and did not pass the timing controls. The evidence remains inconsistent across markets and periods.

HK: **DROP**. train below 90th-percentile timing control. Train/test entries 60/102; test IC 0.0919. Removing index_downside_regime had the largest adverse TRAIN Sharpe effect (-0.176). These are diagnostics, not causal proof or permission to tune against test.
US: **DROP**. test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control. Train/test entries 51/55; test IC 0.0594. Removing wiki_edit_ratio had the largest adverse TRAIN Sharpe effect (-0.264). These are diagnostics, not causal proof or permission to tune against test.

## Candidate frozen from train only

**defensive attention gate** was frozen at 2026-11-16T05:06:16.367745+00:00. Selection: Prefer candidates eligible in both train markets (entries >=30, timing percentile >=90, no unchanged train ablation). Within that group, highest mean selected-variant TRAIN daily net Sharpe, lexical ID tie break. If none eligible, report highest mean as INELIGIBLE research nominee. No test metrics used. Train eligibility: **INELIGIBLE; research nominee only**. It is not a team final selection.

HK: Hold liquid low-volatility stocks with nonnegative observed information sentiment, and halve the entire book after unusually high market-wide Wikipedia attention. Train Sharpe -0.362, train index Sharpe 0.213, timing percentile 25.5%; test Sharpe -0.461, index 0.119, timing percentile 37.0%, max drawdown -5.15%, DSR probability 0.000147. The largest adverse TRAIN ablation was stock_volatility_rank (-0.050 Sharpe). Decision DROP: test Sharpe does not beat index; train below 90th-percentile timing control; test below 90th-percentile timing control.
US: Hold liquid low-volatility stocks with nonnegative observed information sentiment, and halve the entire book after unusually high market-wide Wikipedia attention. Train Sharpe 1.118, train index Sharpe 1.003, timing percentile 93.0%; test Sharpe 0.514, index 0.719, timing percentile 79.5%, max drawdown -2.33%, DSR probability 0.056776. The largest adverse TRAIN ablation was wiki_added_text_sentiment (-0.409 Sharpe). Decision DROP: test Sharpe does not beat index; test below 90th-percentile timing control.

The mechanism could be studied in other equity markets because volatility, liquidity stress and independent attention exist there, but these results do not establish portability. India has not been evaluated by this HK study; HK has been evaluated directly. A failed train/random gate cannot be rescued by attractive test results.

## Validation, costs and limits

- 2,400 actual timing-null portfolios, 200 per strategy/market/period, preserve instrument/count/duration/target size and use the same Vibe transaction engine and costs.
- 60 drop-one portfolios; all train ablations completed before candidate/test. No-op train indicators make a fixed case ineligible rather than being silently retained as useful.
- Frozen upstream DSR originally used 352 known trials. The displayed supplement conservatively counts 354: previous 268 + 12 new train-selection + 72 base/ablation + 2 native fixed-hypothesis verification invocations. The two validations are repeated checks, not claimed independent searches. Test-period dispersion includes their observed per-day Sharpes; train dispersion is unchanged. Older unavailable Sharpe values are not invented. Original 352 values remain in frozen outputs and separate sheet columns; see post_verification_dsr_summary.json. Search-history calibration remains approximate. Adding the two observed native Sharpes also changes the test dispersion estimate, so a reported probability can rise slightly despite the higher trial count; no selection or decision changed.
- Shared scorer copied unchanged from team reddit commit ca3d391cd596a08af6d7ea290563c2fb1712fda9, fixed FinBERT revision0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031. Missing additions remain missing.
- HK exact weather closures and lunch calendar are disclosed; FX uses previous observed close, no future fill, age ≤7 days (observed maximum 5 days). Zero missing actual stock-session closes after listing. Five missing GOOGL pageview weeks stay missing.
- US stock entries use 10 bps slippage; HK uses Vibe charges plus dated whole-HKD-ceiled 0.10%/0.13% duty. No ETF positions or shorts. Current 2026 lots are a historical assumption, not point-in-time lot history.
- Samples are five HK and ten US current large-company stocks, not full historical index membership. Price/volume corporate-action units and stock-in-kind actions are not comprehensively certified. Historical Wiki text, modern fixed classifier and reconstructed titles are not proof of information every investor saw.
- Small, low-exposure portfolios and full-investment benchmarks differ in risk/exposure/dividend conventions; idle cash earns zero. HSI benchmark is a price index, US SPY includes cash dividends.
- Exact rules/protocol/input/source hashes are included. Local preregistration does not mean rules were posted to the shared team sheet. No AWS deployment, remote issue/PR or team message is claimed.

## Native Vibe runner confirmation

Both unchanged `python -m backtest.runner` runs completed with hash-verified frozen Yahoo input frames, an embedded decision-date target CSV, no file writes from SignalEngine, and exactly the runner's own one-bar execution shift. The direct Sharpe-agreement check **fails** in both markets. The discrepancies were then explained from the sealed fill ledgers, without regenerating signals, resizing orders or repeating the test.

| Market | Research Sharpe | Native Sharpe | Difference | Research legs / native fills | Research slippage / native slippage |
| --- | ---: | ---: | ---: | ---: | ---: |
| HK | -0.461350 | -0.048155 | +0.413194 | 478 / 205 | HKD 153,869.02 / 39,098.58 |
| US | 0.513963 | 0.703567 | +0.189604 | 382 / 246 | USD 27,862.35 / 9,105.35 |

Research forces a weekly close and reopen even when a name is selected again. Native target rebalancing retains the overlapping position and trades only its quantity change. This substantially reduces turnover and execution costs, while producing similar invested symbol-days. Both use the same session dates and observable open plus signed 10-bps slippage; a double shift or a different evaluation window does not explain these gaps.

HK native ending equity exceeds research by **HKD 261,690.18**: HKD 151,016.98 lower fees + 114,770.45 lower slippage + 12,560.99 gross price/quantity-path difference − 16,658.24 missing dividend credits. Native still uses constant fractional 0.1% duty; changing duty and crediting dividends on its fixed fills yields Sharpe -0.027867, which still does not reproduce the weekly-roundtrip portfolio. Its native benchmark falls back to the equal-weight five-stock basket despite `benchmark: ^HSI`; it is not the research HSI baseline.

US native ending equity exceeds research by **USD 17,709.81**: USD 18,757.00 lower slippage + 431.49 gross price/quantity-path difference − 1,478.68 missing dividends. Both explicit commission totals are zero. Its ordered fixed-fill Sharpe bridge is 0.513963 → 0.497868 (remove research dividends) → 0.804428 (remove research slippage) → 0.802659 (native gross quantity path) → 0.703567 (native actual slippage). The same 1,212 sessions and first-entry date are used. HK similarly reconciles over 1,185 identical sessions.

Cash-plus-shares reconstructions agree with saved equity within HKD 0.00000004 and USD 0.000000003. These are accounting-only diagnostics with quantities held fixed, not investable alternate strategies. The ordered bridge is not a unique causal decomposition. See `HK_NATIVE_RECONCILIATION.md`, `US_NATIVE_RECONCILIATION.md` and their JSON evidence for exact formulas, checks and hashes.

The native runs are successful executions, but they are **not interchangeable numerical confirmations** of the research portfolios. The nominee remains INELIGIBLE/DROP; no parameter or cost was tuned to force agreement.

The attention-risk z-score averages the tracked study sample (five HK/ten US stocks), rather than the whole exchange. Calendar weather exceptions are sourced but not an exhaustive inventory. Research FX uses a conservative date-lagged Yahoo close proxy; provider publication instants are not independently certified.
