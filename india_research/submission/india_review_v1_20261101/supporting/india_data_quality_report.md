> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# India Stock Market Data Quality Investigation
**Project:** Vibe-Trading
**Market:** India — National Stock Exchange (NSE)
**Investigation date:** October 21, 2026
**Status:** Preliminary investigation — additional validation pending

## 1. Objective

The purpose of this investigation was to evaluate the reliability of freely available Indian stock market data from Yahoo Finance using Python's `yfinance` library. The investigation focused on historical data coverage, missing trading dates, stock splits, abnormal price movements, repeated closing prices, and consistency with official exchange records. The goal was to determine whether the data is suitable for testing trading strategies.

## 2. Historical Data Coverage

Historical data was successfully retrieved for eight Indian stocks and the Nifty 50 index (`^NSEI`) using `period="max"`.

| Ticker | First Available Date | Total Rows |
|---|---|---:|
| RELIANCE.NS | 1996-01-01 | 7,728 |
| TCS.NS | 2002-08-12 | 6,004 |
| INFY.NS | 1996-01-01 | 7,731 |
| HDFCBANK.NS | 1996-01-01 | 7,731 |
| ICICIBANK.NS | 2002-07-01 | 6,033 |
| SBIN.NS | 1996-01-01 | 7,729 |
| KOTAKBANK.NS | 2001-07-02 | 6,295 |
| AXISBANK.NS | 1998-11-27 | 6,969 |
| ^NSEI | 2007-09-17 | 4,684 |

All datasets had a last recorded date of October 21, 2026.

When compared against the available Nifty 50 trading dates, none of the eight stocks had missing records during their overlapping periods. However, this comparison does not establish completeness before September 2007 or guarantee the accuracy of individual records.

## 3. Stock Splits and Abnormal Price Movements

Stock split information was retrieved using `yf.Ticker(ticker).splits`.

The initial investigation identified **31 daily closing-price movements exceeding 20%** across the eight stocks.

Several extreme movements appeared inconsistent with ordinary market behavior:

- Reliance: +337.48% on July 28, 2005, followed by −76.99%.
- TCS: +100% on July 28, 2005, followed by −50.61%.
- Kotak Bank: +379.42% on July 28, 2005, followed by −79.33%.

The `yfinance` repair function was tested on these three stocks.

| Stock | Original Flags | After Repair | Repaired Rows |
|---|---:|---:|---:|
| RELIANCE | 6 | 2 | 483 |
| TCS | 3 | 3 | 0 |
| KOTAKBANK | 10 | 4 | 3 |

The repair function reduced the number of extreme price movements for Reliance and Kotak Bank but did not correct the TCS anomalies. The repaired-row counts indicate modified records, not necessarily the number of independently verified errors.

## 4. Repeated Closing Prices

The investigation identified 1,176 instances of consecutive identical closing prices across the eight stocks. Of these, 935 were accompanied by zero trading volume.

TCS had the highest number, with 317 repeated closes, including 309 with zero volume.

Most zero-volume repeated-price observations occurred before 2010. However, some recent records also required investigation.

One example was TCS on March 18, 2025:

| Source | Closing Price | Volume |
|---|---:|---:|
| Yahoo Finance (`TCS.NS`) | ₹3,299.90 | 0 |
| Official NSE | ₹3,552.45 | 3,069,109 |

The official NSE record confirmed that trading occurred that day. This provides strong evidence that the Yahoo Finance record was incorrect or stale.

Other repeated-price dates corresponded to market closures, demonstrating that zero-volume observations are not necessarily data errors.

## 5. NSE vs. BSE Validation

Official Bombay Stock Exchange (BSE) historical data was downloaded for Reliance Industries for January 2024.

The initial comparison showed an approximately 50% difference because Yahoo Finance reflected Reliance's October 2024 two-for-one stock split, while the BSE historical records retained pre-split prices.

After adjusting the BSE prices for the split:

| Metric | Result |
|---|---:|
| Trading dates compared | 21 |
| Average absolute price difference | 0.032% |
| Maximum price difference | 0.155% |
| Dates exceeding 2% difference | 0 |

This comparison provides strong evidence that Reliance's Yahoo Finance closing prices accurately reflect market prices for the tested period after accounting for corporate actions.

Historical NSE/BSE comparisons were also completed using Yahoo Finance for TCS and Axis Bank in 2024, producing average differences of approximately 0.033% and 0.043%, respectively.

The other six Yahoo Finance BSE symbols did not return usable 2024 histories, so comprehensive cross-exchange verification remains incomplete.

## 6. Preliminary Conclusion

The investigation indicates that Yahoo Finance provides extensive Indian stock market history, with recent observations showing promising consistency against official exchange data.

However, older records contain substantial anomalies, including extreme price movements, repeated closing prices, and zero-volume observations. Automated repair improves some of these issues but does not resolve all of them.

**The data is promising for strategy backtesting, provided that corporate actions are handled consistently and suspicious observations are validated or excluded using documented rules.** The entire historical dataset should not yet be considered fully verified.

## 7. Remaining Work

- Confirm that new data appears after the next NSE trading session.
- Determine approximately when updated daily records become available in Pacific Time.
- Complete additional historical price checks against official exchange records.
- Retrieve the current Nifty 100 constituent list and investigate historical membership availability.
- Run five reversal strategies using `mini_bench.py`, record their IC and Sharpe ratios, and complete the Strategy Log.
- Review `_load_sp500_panel` in `agent/src/tools/alpha_bench_tool.py` for the planned Nifty 100 implementation.

**Sources:** Yahoo Finance through `yfinance`; official NSE Security-wise Archives (Equities); official BSE Stock Prices historical CSV (`500325 (1).csv`).
