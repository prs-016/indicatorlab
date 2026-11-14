# Hong Kong Week 1 Data Note (2021–2024)

## Decision summary

The six downloaded files are usable for a **pipeline smoke test** and for the first five momentum experiments, with two cautions:

1. Rows with zero volume must not be treated as tradable observations.
2. Tencent's pre-5 January 2023 `Close` history is vendor-adjusted for the Meituan distribution in specie, so it is not a literal HKEX tape close even though `auto_adjust=False` was used.

The current five stocks are not enough for a credible cross-sectional Hang Seng factor study. A later production loader should use the point-in-time HSI membership on each date.

## Local data audit

Each file has 982 rows from 4 January 2021 through 31 December 2024 and exactly the same date set as `^HSI`.

| Check | Result |
|---|---:|
| Duplicate dates | 0 in every file |
| Rows missing OHLCV | 0 in every file |
| Non-positive closes | 0 in every file |
| Impossible OHLC ranges | 0 in every file |
| Negative volume | 0 in every file |
| Adjusted daily moves over 25% | 0 in every file |
| Zero-volume rows | 4–6 per stock; 0 for `^HSI` |

Every zero-volume stock row also has identical open, high, low, and close values. Mark these rows non-tradable. They occur on:

- All five stocks: 11 February 2021, 31 January 2022, 24 December 2024, and 31 December 2024.
- `0388.HK`, `0941.HK`, and `1299.HK` only: 15 January 2024 and 9 February 2024.

These rows can remain in an adjusted-price signal panel if needed for calendar alignment, but they should be excluded from volume/liquidity tests and should not be used as simulated execution bars.

Run the reusable audit without downloading again:

```bash
python3 research/hk_week1/check_data.py
```

Download fresh files only when intentionally requested:

```bash
python3 research/hk_week1/check_data.py --refresh
```

## Price cross-checks

Raw-looking local values were checked against official HKEX daily quotations and Google Finance chart values. Prices below agree after ordinary display rounding.

| Source | Symbol | Date | Reference close | Local close | Reference daily volume | Local daily volume |
|---|---|---:|---:|---:|---:|---:|
| HKEX | `0005.HK` | 2024-04-23 | 64.25 | 64.25 | 30,252,026 | 30,252,026 |
| HKEX | `0941.HK` | 2024-10-23 | 72.70 | 72.70 | 26,196,016 | 26,196,016 |
| HKEX | `0005.HK` | 2024-11-12 | 69.45 | 69.45 | 18,903,390 | 18,903,390 |
| Google Finance | `0005.HK` | 2024-10-25 | 68.85 | 68.85 | — | 6,907,348 |
| Google Finance | `0388.HK` | 2024-10-25 | 312.80 | 312.80 | — | 5,301,559 |
| Google Finance | `0700.HK` | 2024-10-25 | 421.00 | 421.00 | — | 11,951,879 |
| Google Finance | `1299.HK` | 2024-10-25 | 62.85 | 62.85 | — | 31,594,206 |
| Google Finance | `0941.HK` | 2024-11-01 | 71.60 | 71.60 | — | 11,937,990 |
| Google Finance | `^HSI` | 2024-10-04 | 22,736.87 | 22,736.87 | — | 4,620,000,000 |

Google Finance's five-year chart displays rounded/aggregated volume, so it was used only as a price spot-check. HKEX was used for the exact daily-volume comparisons.

Tencent's historical values require special care. The last day trading with entitlement to Tencent's Meituan distribution was 4 January 2023. The local OHLC values before 5 January 2023 are back-adjusted and therefore contain values that are impossible as exchange-quoted ticks (for example, `342.870056` on 4 January 2023). This is a vendor treatment of the non-cash distribution, not evidence that the exchange traded at that fractional price. Use `Adj Close` consistently for momentum signals, but use an HKEX-quality unadjusted tape series for exact execution-price or corporate-action work.

Sources: [HKEX 23 April 2024 daily quotations](https://www.hkex.com.hk/eng/stat/smstat/dayquot/d240423e.htm), [HKEX 23 October 2024 daily quotations](https://www.hkex.com.hk/chi/stat/smstat/dayquot/d241023c.htm), [HKEX 12 November 2024 daily quotations](https://www.hkex.com.hk/eng/stat/smstat/dayquot/d241112e.htm), [Google Finance](https://www.google.com/finance/), and [Tencent's Meituan distribution announcement](https://static.www.tencent.com/uploads/2022/11/16/b92d6f78a14cbcc512c2b48f0942dd9f.pdf).

## What “rebuild past Hang Seng members from quarterly reviews” means

The constituent list shown today is not the list that existed in 2021, 2022, 2023, or 2024. A historical backtest must use the stocks that were actually members on each test date; otherwise it has survivorship/look-ahead bias.

The point-in-time series **can be reconstructed** for 2021–2024:

1. Start with the full HSI constituent list effective 7 December 2020 (52 constituents).
2. Apply each quarterly review's additions and deletions on its effective date: 15 Mar, 7 Jun, 6 Sep, and 6 Dec 2021; 7 Mar, 13 Jun, 5 Sep, and 5 Dec 2022; 13 Mar, 5 Jun, 4 Sep, and 4 Dec 2023; 4 Mar, 11 Jun, 9 Sep, and 9 Dec 2024.
3. Check the HSI “Historical Change of Constituents” feed for ad-hoc removals or replacements between regular reviews.
4. In code, store membership as effective-dated intervals (`member_from`, `member_to`) and join each trading date to the interval that contains it.

The official quarterly releases include the post-review constituent list, so the reconstruction is feasible. Examples: [starting 2020 review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20201113T000000.pdf), [first 2021 review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20210226T000000.pdf), [June 2023 review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20230512T175000.pdf), and [final 2024 review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20241122T174500.pdf). The official [HSI index page](https://www.hsi.com.hk/en-hk/indexes/all-indexes/index-details/?seriesCode=hsi) exposes both the current constituents and the historical-change section.

## Board lots

| Symbol | Company | Shares per board lot | 2021–2024 finding |
|---|---|---:|---|
| `0700.HK` | Tencent | 100 | No change found |
| `0005.HK` | HSBC | 400 | No change found |
| `1299.HK` | AIA | 200 | No change found |
| `0941.HK` | China Mobile | 500 | No change found |
| `0388.HK` | HKEX | 100 | No change found |

HKEX stock-option references expose the underlying board lot directly or as `contract size ÷ number of board lots`. Historical HKEX notices also show the same trading units before the test window. Sources: [HKEX stock-options list](https://www.hkex.com.hk/products/listed-derivatives/single-stock/stock-options?sc_lang=en), [HKEX 2015 contract-size notice](https://www.hkex.com.hk/News/News-Release/2015/150528news?sc_lang=en), and [Tencent board-lot circular](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2014/EFIC_DT_049_e.pdf).

For a production historical loader, a dated securities-master file is preferable to treating present values as timeless. HKEX's [Securities Master File](https://www.hkex.com.hk/eng/ods/historicalDataProfile.aspx?ProductID=Nq3KhAsvcacOWweFE23e5MoNHGf6Vny0QLn0MdGu01E%3D&SchemeID=aXpa0RNxwT7f8%2BKBnubgF0JoF1Y5mCRyMocLBiDVR9U%3D&isPrint=Y) contains board-lot size but is a paid historical product.

## How to test the five strategies yourself

Use adjusted closing prices and keep every other rule identical. Calculate the signal after day `t` closes, shift it by one trading day, rank stocks, hold the top-ranked names at equal weight, and rebalance weekly. Do not use data after 31 December 2024.

| Strategy | Signal |
|---|---|
| 5-day momentum | `adj_close.pct_change(5)` |
| 20-day momentum | `adj_close.pct_change(20)` |
| 60-day momentum | `adj_close.pct_change(60)` |
| 10/30-day moving-average momentum | `adj_close.rolling(10).mean() / adj_close.rolling(30).mean() - 1` |
| 20-day risk-adjusted momentum | `adj_close.pct_change(20) / daily_return.rolling(20).std()` |

The repository currently has no `mini_bench.py`, and `alpha_bench_tool.py` accepts only `csi300`, `sp500`, and `btc-usdt`. Ask the team for the missing script (or confirm that it lives on another branch) before inventing a command-line interface. Once it is present, run `python3 path/to/mini_bench.py --help` and map the five signals above into its actual interface.

For the five-stock smoke test, use the same portfolio size, costs, execution lag, and rebalance dates for every strategy. Board-lot rounding matters only if the test simulates a fixed amount of cash and share quantities. Also state that adjusted-stock returns are not perfectly like-for-like with the `^HSI` price index, which excludes dividends.
