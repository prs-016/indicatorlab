# Hang Seng Index historical data archive

This folder contains a free, reproducible daily-price archive for the Hang Seng Index research universe. The default refresh requests all available history through the current Hong Kong calendar date and stores the newest completed Yahoo daily bar.

The latest verified refresh was retrieved at **2026-10-28 23:07 UTC**. The newest completed daily bar is **2026-10-28** for the HSI benchmark and all 95 current HSI constituents.

## Coverage

- 114 unique Hong Kong equity codes across the combined universe.
- 100 securities identified as HSI members at some point from 2014 through 2024.
- All 83 HSI constituents at 2024-12-31 have usable daily history.
- All 95 constituents effective 2026-09-07 have price files through 2026-10-28.
- 110 usable equity price files with 498,219 daily rows.
- The free `^HSI` benchmark covers 1986-12-31 through 2026-10-28 with 9,828 daily rows.
- The earliest equity history in this archive is HSBC (`0005.HK`) on 2000-01-03. Other securities begin on their earliest available Yahoo date or listing date.

Four historical securities do not have a usable original-listing file:

- `0011.HK` Hang Seng Bank: no reliable original-listing history from the selected free source.
- `0013.HK` Hutchison Whampoa: the code was later reused by an unrelated company. The later data was rejected.
- `0494.HK` Li & Fung: no reliable original-listing history from the selected free source.
- `1880.HK` Belle International: the code was later reused by an unrelated company. The later data was rejected.

No proxy, reused ticker, or successor security was inserted for these gaps.

## Files

- `hsi_universe.csv`: company map, Yahoo ticker, historical-universe flag, end-2024 HSI flag, current HSI flag, and source links.
- `coverage.csv`: complete coverage manifest with earliest and latest price dates, row count, status, checks, and local file path.
- `price_file_index.csv`: shorter lookup table for finding a ticker's date range and CSV path.
- `prices/<ticker>__daily__<first-date>_to_<last-date>.csv`: unadjusted OHLC, adjusted close, volume, dividends, and splits for each usable equity. The frequency and date range are visible in every filename.
- `benchmark/Hang_Seng_Index__HSI__daily__1986-12-31_to_2026-10-28.csv`: the free Hang Seng Index benchmark history.
- `validation_checks.csv`: row counts and per-file OHLC/source warnings.
- `validation_summary.json`: structural checks and overall result.
- `summary.json`: compact universe and coverage totals.
- `download_hsi_history.py`: rebuilds the universe and downloads prices.
- `validate_hsi_history.py`: reruns the structural and price checks.
- `probe_intraday.py`: checks recent unofficial Yahoo one-minute bars for selected tickers without treating them as an official real-time feed.

The summary workbook is in `outputs/hsi-market-history/hsi_history_summary.xlsx` at the repository root.

## Price conventions

Use `Adj Close` for ordinary total-return signals unless the strategy specifically needs raw execution prices. `Open`, `High`, `Low`, and `Close` are unadjusted Yahoo values. Do not calculate returns across splits from raw close.

The validation passes all critical checks: unique dates, positive close, nonnegative volume, complete adjusted close, expected universe counts, all 95 current constituents downloaded, and date-stamped filenames. Yahoo contains 646 reported OHLC consistency warning events where open or close falls outside the stated daily high-low range. The source values are preserved and every affected file is listed in `validation_checks.csv`. A strategy using intraday ranges should filter or independently verify those rows.

## Update frequency and live-data limit

These CSV files do not update themselves. Run the downloader whenever a refresh is needed. Because they contain daily bars, the normal schedule is once per Hong Kong trading day after the market closes and Yahoo has finalized that day's bar. Running it more often does not turn the daily archive into a live feed.

Yahoo can sometimes return recent one-minute bars. Use this only as an availability probe:

```bash
python3 probe_intraday.py 0700.HK ^HSI
```

The result is not guaranteed to be real-time, complete, or stable. It can be delayed, rate-limited, or unavailable, and intraday history is retained for only a short window. Official streaming HKEX data requires a licensed real-time vendor or a direct HKEX OMD-C service. Do not use the Yahoo probe as an execution-grade price feed.

## Membership caution

The historical-member flag and first/last membership observations are a research reconstruction from public review notices and a secondary public dataset. They prevent the most obvious current-member survivorship bias, but they are not a licensed official day-by-day composition file. The end-2024 and September 2026 snapshot counts reconcile to official HSI review publications.

For a strict point-in-time backtest, reconstruct every quarterly effective-date interval from the official review notices before trading on the membership field. Do not apply the 2026 list backward to earlier years.

## Rebuild

Download the pinned historical-company map, then run:

```bash
python3 download_hsi_history.py \
  --reference-map /path/to/stock_company_map.csv \
  --output-dir /path/to/research/hk_market_history

python3 validate_hsi_history.py /path/to/research/hk_market_history
```

The historical map was pinned to commit `bdb5c01084b314a94edfad155547d9373d0d8191`.

The downloader's default end is dynamic. To reproduce the original research cutoff through 2024-12-31, add `--end 2025-01-01`; Yahoo treats the end date as exclusive.

## Sources and limits

- [Hang Seng Indexes, August 2026 review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20260821T174500.pdf): official 95-constituent current snapshot.
- [Hang Seng Indexes, November 2024 review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20241122T174500.pdf): official end-2024 count and changes.
- [HistoricalIndexPrices, pinned commit](https://github.com/AndyLongest/HistoricalIndexPrices/tree/bdb5c01084b314a94edfad155547d9373d0d8191): historical-member discovery from 2014; not copied as the price source.
- [Yahoo Finance](https://finance.yahoo.com/): fresh daily price downloads through `yfinance`.
- [HKEX data marketplace](https://data.hkex.com.hk/): official all-market historical products.
- [HKEX real-time datafeeds](https://www.hkex.com.hk/Services/Market-Data-Services/Real-Time-Data-Services/Overview/Real_time-Datafeeds?sc_lang=en): official OMD-C market-data products and content levels.
- [yfinance download implementation](https://github.com/ranaroussi/yfinance/blob/main/yfinance/multi.py): supported intervals and the short retention window for intraday data.

Official HSI daily OHLC back to the 1969 launch and complete all-market HKEX history are licensed products. This free archive therefore uses the earliest reliable date returned by Yahoo for each security, not the opening date of the Hong Kong stock market.
