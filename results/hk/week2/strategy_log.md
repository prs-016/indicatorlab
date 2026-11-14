# Hong Kong Strategy Log

Signals use point-in-time HSI membership, next-close execution and 10 bps one-way turnover costs.

| Strategy | What it does | Test IC | Test Sharpe | Decision | Why |
|---|---|---:|---:|---|---|
| 5-day momentum | Ranks HSI members by 5-day adjusted-price return; buys the top 10 weekly. | -0.015 | -0.347 | Drop | Failed the 90th-percentile random-baseline hurdle in both train and test. |
| 20-day momentum | Ranks HSI members by 20-day adjusted-price return; buys the top 10 weekly. | 0.002 | -0.014 | Drop | Failed the 90th-percentile random-baseline hurdle in both train and test. |
| 60-day momentum | Ranks HSI members by 60-day adjusted-price return; buys the top 10 weekly. | 0.014 | -0.124 | Watch | The edge cleared the random-baseline hurdle in only one period, so it is not stable enough to keep. |
| 10/30-day moving-average momentum | Ranks HSI members by the 10-day average divided by the 30-day average; buys the top 10 weekly. | 0.014 | 0.117 | Watch | The edge cleared the random-baseline hurdle in only one period, so it is not stable enough to keep. |
| 20-day risk-adjusted momentum | Ranks 20-day momentum divided by 20-day volatility; buys the top 10 weekly. | 0.011 | 0.310 | Watch | The edge cleared the random-baseline hurdle in only one period, so it is not stable enough to keep. |
| TGQM composite | Monthly 50% 12-to-1 momentum, 30% low volatility and 20% reversal; top 10 inverse-vol weighted, 15% cap, 50% exposure below HSI 200DMA. | 0.096 | 0.613 | Keep | Beat at least 90% of random portfolios in both periods and exceeded the HSI test Sharpe. |

## Honest limitations

- Historical point-in-time membership begins in late 2014, so train is 2015-2019, not 2011-2019.
- Constituent returns use Yahoo adjusted prices (include distributions), while ^HSI is a price index; the equal-weight comparison is therefore more like-for-like.
- The free historical reconstruction is checked against official review counts but is not a licensed HSI constituent-history product.
