# Advanced Hong Kong Strategy Log

All candidates use point-in-time HSI membership, monthly ranking, next-close execution, capped inverse-volatility sizing and 10 bps one-way turnover costs.

| Strategy | What it does | Test IC | Test Sharpe | Keep/Drop | Why |
|---|---|---:|---:|---|---|
| Residual Momentum + Low Risk | Ranks market-model residual momentum and low idiosyncratic volatility, reducing exposure below the HSI 200-day average. | 0.083 | 0.639 | Keep | Positive holdout IC (0.083), Sharpe (0.639) beat the HSI (0.092), and it beat 98.0% of matched random portfolios. |
| Multi-Horizon Trend Consensus | Combines 1-, 3- and 12-to-1-month momentum so a stock must trend across several horizons. | 0.066 | 0.530 | Keep | Positive holdout IC (0.066), Sharpe (0.530) beat the HSI (0.092), and it beat 94.5% of matched random portfolios. |
| Breakout + Volume Confirmation | Looks for 63-day price breakouts supported by medium-term momentum and unusual volume. | 0.041 | 0.425 | Drop | It beat only 65.5% of matched random portfolios. |
| Crash-Aware Defensive Reversal | Buys short-term losers with low downside risk and low market beta, emphasizing market-stress periods. | 0.059 | 0.434 | Keep | Positive holdout IC (0.059), Sharpe (0.434) beat the HSI (0.092), and it beat 98.5% of matched random portfolios. |
| Regime-Adaptive Factor Ensemble | Uses momentum, trend and volume in bull regimes, then switches to reversal, low beta and low volatility below the HSI 200DMA. | 0.072 | 0.472 | Keep | Positive holdout IC (0.072), Sharpe (0.472) beat the HSI (0.092), and it beat 92.5% of matched random portfolios. |

## Interpretation limits

- These are institutional-style research ideas, not proprietary models from a specific quant firm.
- Only adjusted daily price and volume are consistently available, so there are no fundamentals, order-book features, borrow costs or short positions.
- The holdout ends on 30 September 2025 because that is the last fully reconstructed point-in-time membership date.
- Five candidates create multiple-testing risk; only the stated untouched holdout and random baselines are used for the decision.
