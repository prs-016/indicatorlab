# Non-Momentum Hong Kong Strategy Log

The five candidates avoid positive trend and breakout ranking. All use point-in-time HSI membership, monthly ranking, next-close execution, capped inverse-volatility sizing and 10 bps one-way turnover costs.

| Strategy | What it does | Test IC | Test Sharpe | Keep/Drop | Why |
|---|---|---:|---:|---|---|
| Defensive Low Risk | Selects stocks with low market beta, low downside deviation and low idiosyncratic volatility. | 0.084 | 0.494 | Keep | Positive holdout IC (0.084), Sharpe (0.494) beat the HSI (0.092), and it beat 98.5% of matched random portfolios. |
| Oversold Mean Reversion | Buys recent losers that are far below their 20-day average and have a low 14-day RSI. | -0.012 | 0.054 | Drop | Holdout IC was non-positive (-0.012); Sharpe (0.054) did not beat the HSI (0.092); it beat only 46.5% of matched random portfolios. |
| Liquidity Quality | Favors high and stable traded value with low Amihud price impact. | 0.049 | 0.351 | Drop | It beat only 82.0% of matched random portfolios. |
| Shareholder Yield Quality | Combines trailing dividend yield, payment frequency and low downside risk. | 0.066 | 0.670 | Keep | Positive holdout IC (0.066), Sharpe (0.670) beat the HSI (0.092), and it beat 100.0% of matched random portfolios. |
| Volatility Compression | Selects narrow high-low ranges, stable realized volatility and small overnight gaps. | 0.079 | 0.609 | Keep | Positive holdout IC (0.079), Sharpe (0.609) beat the HSI (0.092), and it beat 98.0% of matched random portfolios. |

## Interpretation limits

- The inputs are daily OHLCV and dividends. There are no accounting fundamentals, order-book features, borrow costs or short positions.
- Oversold Mean Reversion uses recent returns contrarily; it is not a positive momentum or trend strategy.
- Dividend data is sourced from the same free Yahoo archive and is not independently audited against company filings.
- The holdout ends on 30 September 2025 because that is the last fully reconstructed point-in-time membership date.
- Keep means retain for further research, not approve for live trading.
