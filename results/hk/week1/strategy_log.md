# Hong Kong momentum strategy decisions

Evaluation period: 2021-04-07 to 2024-12-31.

| Strategy and what it does | Mean rank IC | Sharpe | Keep or drop | Why |
|---|---:|---:|---|---|
| **5-day momentum.** Ranks stocks by their past 5-day return and buys the top two weekly. | -0.029 | -0.26 | **Drop** | Negative IC and Sharpe suggest short-term noise and reversal. Frequent changes also made this the highest-turnover strategy. |
| **20-day momentum.** Ranks stocks by their past 20-day return and buys the top two weekly. | +0.004 | +0.11 | **Keep** | IC and Sharpe were slightly positive. Keep it as a simple baseline, but the edge is weak and needs a full-universe retest. |
| **60-day momentum.** Ranks stocks by their past 60-day return and buys the top two weekly. | -0.008 | -0.08 | **Drop** | Both IC and Sharpe were negative, so the slower signal did not predict the next week's relative winners. |
| **10/30-day moving-average momentum.** Ranks stocks by how far their 10-day average is above their 30-day average. | -0.011 | +0.20 | **Keep** | It had the best Sharpe and was the only strategy with a positive cumulative return. Its slightly negative IC means it still needs a larger retest. |
| **20-day risk-adjusted momentum.** Ranks 20-day return after dividing it by recent 20-day volatility. | -0.005 | -0.13 | **Drop** | Volatility scaling did not improve stock ranking. IC and Sharpe stayed negative. |

## IC definition

Mean weekly Spearman rank correlation between each signal and all five stocks' returns
over the following tradable holding week (195
observations per strategy). Positive is better. Values close to zero indicate little
consistent ranking power. The keep decisions are candidates for a full point-in-time
HSI retest, not final proof that the strategies work.
