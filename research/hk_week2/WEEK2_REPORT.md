# Hong Kong Week 2 Report

## Result

Seven of the eight operational checklist lines are complete. The only partial item is a literal real-time 09:30–16:05 HKT polling run: the poller is implemented and the latest completed session was replay-audited, but it would be misleading to label that replay as a live observation.

The data and engineering controls pass:

- 95/95 current HSI constituents are downloaded.
- The end-2024 roster has 83 names: 82 downloadable plus `0011.HK`, whose reliable free original-listing history is unavailable.
- The `^HSI` benchmark begins on 31 December 1986 and the archive reaches 4 November 2026.
- All 19 official review counts from 7 December 2020 through 8 September 2025 reconcile exactly.
- The `hsi` factor-test universe is wired to `equity_hk`, masks securities outside their effective membership intervals and uses adjusted OHLCV.
- 40 focused/regression tests pass.

## Strategy decisions

Signals are calculated after the close and executed at the next close. All strategies pay 10 bps per unit of one-way turnover, use at least 30 eligible names, and are evaluated on an untouched 2020–30 September 2025 test after the 2015–2019 train. Each strategy is compared with 200 matched random portfolios, the HSI price index and a point-in-time equal-weight HSI portfolio.

| Strategy | What it does | Test IC | Test Sharpe | % random beaten | Decision | Why |
|---|---|---:|---:|---:|---|---|
| 5-day momentum | Top 10 by 5-day return, weekly | -0.015 | -0.347 | 6.5% | Drop | Short-term noise/reversal and the highest turnover. |
| 20-day momentum | Top 10 by 20-day return, weekly | 0.002 | -0.014 | 79.5% | Drop | It did not clear the random hurdle in either period. |
| 60-day momentum | Top 10 by 60-day return, weekly | 0.014 | -0.124 | 46.5% | Watch | It cleared the hurdle only in train. |
| 10/30-day MA | Top 10 by 10-day MA ÷ 30-day MA, weekly | 0.014 | 0.117 | 94.0% | Watch | It cleared the hurdle only in test. |
| 20-day risk-adjusted momentum | Top 10 by momentum ÷ volatility, weekly | 0.011 | 0.310 | 100.0% | Watch | Strong test, but the train percentile was only 86.5%. |
| TGQM composite | Monthly 50% 12-to-1 momentum, 30% low volatility, 20% reversal; inverse-vol top 10, 15% cap, 50% exposure below HSI 200DMA | 0.096 | 0.613 | 97.5% | **Keep** | Cleared the 90% random hurdle in train and test and beat the HSI test Sharpe of 0.092. |

The generic assignment standard asks for a 2011 training start, but point-in-time membership begins in late 2014. The train therefore starts in 2015 rather than fabricating pre-source membership.

## Data and live-source findings

- The five focus stocks have daily histories beginning between 2000 and 2010; `^HSI` starts in 1986.
- Yahoo reports one Tencent 5-for-1 split on 15 May 2014. It exposes no separate bonus-issue classification.
- Historical Yahoo OHLC inconsistencies and zero-volume bars are counted and preserved rather than silently repaired.
- Five readings for each focus stock succeeded on Yahoo, Tencent and Eastmoney (75 successful price observations). All three matched Google Finance's 4 November 2026 closes exactly.
- Median request latency was 268.8 ms for Yahoo, 908.6 ms for Tencent and 3,062.7 ms for Eastmoney in this small after-close sample.
- Futu OpenD was not running locally. HKEX is the authoritative source, but anonymous real-time API access/redistribution is not available; a licensed product is required.
- The latest-session Yahoo replay begins at 09:30 HKT and ends at 16:08 HKT. Four names had 329–331 bars; AIA had 320 bars and more one-minute gaps.

## Key files

- `outputs/HK_Week2_Checklist_and_Strategies.xlsx`: meeting-ready workbook.
- `outputs/strategy_results.csv`: train/test results and decisions.
- `outputs/random_baseline_results.csv`: all 2,400 random-period outcomes.
- `outputs/hsi_membership_intervals.csv`: effective-dated membership table.
- `outputs/hsi_review_count_checks.csv`: 19 official count controls.
- `outputs/hsi_current_constituents.csv`: current official 95-name roster.
- `outputs/live_source_readings.csv`: five repeat readings per public provider and focus ticker.
- `live_poller.py`: one-minute full-session poller.
- `hk_attention_config.json`: English/Chinese names, Wikipedia titles and subreddit targets.

## Reproduce

```bash
python3 research/hk_market_history/download_hsi_history.py \
  --reference-map /path/to/HistoricalIndexPrices/data/stock_company_map.csv \
  --output-dir research/hk_market_history

python3 research/hk_market_history/validate_hsi_history.py research/hk_market_history
python3 research/hk_week2/build_week2_evidence.py
python3 research/hk_week2/backtest_hsi_strategies.py

# Start before 09:30 HKT and leave running until after 16:05 HKT.
python3 research/hk_week2/live_poller.py

cd agent
python3 -m pytest \
  tests/test_alpha_bench_universe_metadata.py \
  tests/test_analysis_reliability.py \
  tests/test_bench_universe_selection.py -q
```

## Sources

- [Official HSI index page](https://www.hsi.com.hk/en-hk/indexes/all-indexes/index-details/?seriesCode=hsi)
- [Current 95-name official review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20260821T174500.pdf)
- [Starting 52-name official review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20201113T000000.pdf)
- [End-2024 official review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20241122T174500.pdf)
- [Pinned historical reconstruction](https://github.com/AndyLongest/HistoricalIndexPrices/tree/bdb5c01084b314a94edfad155547d9373d0d8191)
- [HKEX weekly stock-options board-lot reference](https://www.hkex.com.hk/-/media/HKEX_Common/Market/Products/Listed-Derivatives/Single-Stock/Weekly-Stock-Options/HKEX_infosheet_WeeklyStockOptions_EN.pdf)
- [HKEX Basic Market Prices guidance](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Market-Data-Services/Real-Time-Data-Services/Data-Licensing_/HKEX_IS-Guiding-Note/Guiding-Notes-on-Basic-Market-Prices-Service_eng-v202304.pdf)
