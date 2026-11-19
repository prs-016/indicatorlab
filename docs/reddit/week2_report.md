# Week 2 Reddit results (Joshua)

Generated 2026-10-25T23:48 UTC by `python -m src.reddit.week2_report`. Research numbers use data before 2025-10-01 only; the spike check (section 6) looks at the holdout weeks without testing.

## 1. Subreddit map

| ticker | subreddit | type | subscribers | first_post_utc | posts_per_week_2024 | volume_method | kept | reason |
|---|---|---|---|---|---|---|---|---|
| (sector) | hardware | sector | 4,309,138.0 | 2008-01-25 | 206.7 | aggregate_month | True |  |
| AAPL | apple | product | 6,132,166.0 | 2008-01-25 | 901.9 | aggregate_month | True |  |
| AAPL | iphone | product | 4,094,107.0 | 2008-01-25 | 1,746.5 | aggregate_month | True |  |
| AAPL | mac | product | 2,900,704.0 | 2008-01-25 | 744.4 | aggregate_month | True |  |
| AAPL | applewatch | product | 926,127.0 | 2013-02-11 | 705.7 | aggregate_month | True |  |
| AAPL | VisionPro | product | 86,282.0 | 2023-06-05 | 426.4 | aggregate_month | True |  |
| AAPL | AAPL | stock | 8,296.0 | 2012-08-21 | 9.0 | aggregate_month | False | < 20 posts/week in 2024 |
| MSFT | microsoft | product | 1,428,461.0 | 2008-01-25 | 293.7 | aggregate_month | True |  |
| MSFT | windows | product | 329,007.0 | 2008-04-05 | 282.9 | aggregate_month | True |  |
| MSFT | xbox | product | 921,643.0 | 2009-06-20 | 998.0 | aggregate_month | True |  |
| MSFT | MSFT | stock | 183.0 | 2021-08-20 | 0.2 | aggregate_month | False | < 20 posts/week in 2024 |
| NVDA | nvidia | product | 2,120,507.0 | 2010-04-16 | 646.8 | aggregate_month | True |  |
| NVDA | NVDA_Stock | stock | 81,590.0 | 2017-01-10 | 124.0 | sampled_14_days | True |  |
| TSLA | teslamotors | product | 3,405,403.0 | 2011-05-19 | 227.7 | aggregate_month | True |  |
| TSLA | TeslaModelY | product | 173,090.0 | 2016-05-03 | 560.3 | aggregate_month | True |  |
| TSLA | TeslaModel3 | product | 212,439.0 | 2015-09-05 | 662.2 | aggregate_month | True |  |
| TSLA | TeslaLounge | product | 187,287.0 | 2017-06-08 | 540.4 | aggregate_month | True |  |
| TSLA | teslainvestorsclub | stock | 87,131.0 | 2018-08-15 | 46.3 | aggregate_month | True |  |
| AMZN | amazon | product | 234,591.0 | 2008-07-03 | 274.7 | aggregate_month | True |  |
| AMZN | aws | product | 325,476.0 | 2008-01-26 | 278.0 | aggregate_month | True |  |
| AMZN | AmazonPrime | product | 172,930.0 | 2012-06-25 | 316.5 | aggregate_month | True |  |
| AMZN | AMZN | stock | 1,642.0 | 2011-09-08 | 1.7 | aggregate_month | False | < 20 posts/week in 2024 |
| META | facebook | product | 362,407.0 | 2008-02-29 | 729.3 | aggregate_month | True |  |
| META | OculusQuest | product | 569,500.0 | 2018-09-26 | 841.8 | aggregate_month | True |  |
| META | instagram | product | 962,135.0 | 2011-03-30 | 1,670.1 | aggregate_month | True |  |
| META | META_Stock | stock | 5.0 | 2022-06-18 | 0.2 | aggregate_month | False | < 20 posts/week in 2024 |
| GOOGL | google | product | 3,422,239.0 | 2008-01-26 | 595.5 | aggregate_month | True |  |
| GOOGL | Android | product | 3,046,269.0 | 2008-08-27 | 684.8 | aggregate_month | True |  |
| GOOGL | GooglePixel | product | 1,125,558.0 | 2016-09-02 | 864.8 | aggregate_month | True |  |
| GOOGL | GOOGL | stock |  |  |  |  | False | not in Arctic Shift |
| AMD | Amd | product | 2,164,629.0 | 2010-07-01 | 362.7 | aggregate_month | True |  |
| AMD | radeon | product | 65,565.0 | 2013-03-20 | 164.7 | aggregate_month | True |  |
| AMD | AMD_Stock | stock | 59,077.0 | 2016-09-02 | 73.6 | aggregate_month | True |  |
| NFLX | netflix | product | 1,741,927.0 | 2008-11-21 | 506.8 | aggregate_month | True |  |
| NFLX | NFLX | stock |  |  |  |  | False | not in Arctic Shift |
| JPM | Chase | product | 40,406.0 | 2010-04-17 | 110.1 | aggregate_month | True |  |
| JPM | JPM | stock |  |  |  |  | False | not in Arctic Shift |

## 2. Posts pulled and failed days (research window)

| subreddit | type | ticker | start | end | days_expected | complete | failed | partial | missing | posts_in_complete_days | raw_storage_mb |
|---|---|---|---|---|---|---|---|---|---|---|---|
| stocks | general |  | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 100540 | 51.4 |
| investing | general |  | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 101569 | 42.0 |
| wallstreetbets | general |  | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 397946 | 211.2 |
| hardware | sector |  | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 27574 | 17.8 |
| apple | product | AAPL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 123110 | 39.1 |
| iphone | product | AAPL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 237361 | 142.0 |
| mac | product | AAPL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 99549 | 75.3 |
| applewatch | product | AAPL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 93328 | 61.2 |
| VisionPro | product | AAPL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 27822 | 21.5 |
| microsoft | product | MSFT | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 33140 | 13.7 |
| windows | product | MSFT | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 36687 | 18.3 |
| xbox | product | MSFT | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 128064 | 78.0 |
| nvidia | product | NVDA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 105497 | 68.6 |
| NVDA_Stock | stock | NVDA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 13880 | 10.1 |
| teslamotors | product | TSLA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 34313 | 17.3 |
| TeslaModelY | product | TSLA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 72549 | 47.4 |
| TeslaModel3 | product | TSLA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 80904 | 49.3 |
| TeslaLounge | product | TSLA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 68155 | 44.5 |
| teslainvestorsclub | stock | TSLA | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 6894 | 6.5 |
| amazon | product | AMZN | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 37676 | 12.3 |
| aws | product | AMZN | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 36420 | 24.1 |
| AmazonPrime | product | AMZN | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 35094 | 28.7 |
| facebook | product | META | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 104200 | 62.6 |
| OculusQuest | product | META | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 109300 | 67.5 |
| instagram | product | META | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 208473 | 116.8 |
| google | product | GOOGL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 80756 | 42.4 |
| Android | product | GOOGL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 91919 | 36.2 |
| GooglePixel | product | GOOGL | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 127053 | 63.5 |
| Amd | product | AMD | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 66173 | 24.2 |
| radeon | product | AMD | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 33697 | 33.2 |
| AMD_Stock | stock | AMD | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 9847 | 10.4 |
| netflix | product | NFLX | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 60605 | 30.8 |
| Chase | product | JPM | 2023-01-01 | 2025-09-30 | 1004 | 1004 | 0 | 0 | 0 | 13198 | 8.1 |

**Total:** 2,803,293 posts, 0 failed days, 1,576 MB of raw JSON (gzip).

## 3. Hand labels and agreement

_Pending: second rater's 50 labels, then `label_eval sentiment --second <name>`._

**Match precision (hand-checked):**

_Pending: 100 match checks, then `label_eval match`._

## 4. Sentiment scorer comparison

_Pending: 300+ sentiment labels, then `label_eval sentiment`._

## 5. Cause vs reaction

**Pooled correlations (z-scored within stock, 95% bootstrap CIs over weeks):**

| direction | x | y | lag | n | pearson | spearman | ci_low | ci_high | block_ci_low | block_ci_high |
|---|---|---|---|---|---|---|---|---|---|---|
| forward | prod_chatter | abn_ret | 1 | 1340 | 0.015 | -0.002 | -0.040 | 0.072 | -0.041 | 0.070 |
| forward | prod_chatter | abn_ret | 2 | 1330 | 0.011 | 0.018 | -0.039 | 0.064 | -0.040 | 0.067 |
| forward | prod_chatter | stock_chatter | 1 | 1340 | 0.087 | 0.090 | 0.032 | 0.141 | 0.020 | 0.148 |
| forward | prod_chatter | stock_chatter | 2 | 1330 | 0.099 | 0.098 | 0.031 | 0.168 | 0.021 | 0.172 |
| reverse | abn_ret | prod_chatter | 1 | 1340 | -0.010 | 0.007 | -0.069 | 0.048 | -0.074 | 0.056 |
| reverse | abn_ret | prod_chatter | 2 | 1330 | -0.017 | -0.001 | -0.069 | 0.038 | -0.066 | 0.035 |
| reverse | stock_chatter | prod_chatter | 1 | 1340 | 0.002 | 0.015 | -0.053 | 0.058 | -0.072 | 0.074 |
| reverse | stock_chatter | prod_chatter | 2 | 1330 | -0.030 | 0.010 | -0.086 | 0.029 | -0.105 | 0.041 |

**Which direction is stronger** (|forward r| - |reverse r|; CI above 0 = product leads):

| forward | reverse | lag | forward_r | reverse_r | abs_diff | ci_low | ci_high |
|---|---|---|---|---|---|---|---|
| prod_chatter -> stock_chatter | stock_chatter -> prod_chatter | 1 | 0.087 | 0.002 | 0.085 | -0.004 | 0.128 |
| prod_chatter -> stock_chatter | stock_chatter -> prod_chatter | 2 | 0.099 | -0.030 | 0.069 | -0.025 | 0.149 |
| prod_chatter -> abn_ret | abn_ret -> prod_chatter | 1 | 0.015 | -0.010 | 0.005 | -0.055 | 0.059 |
| prod_chatter -> abn_ret | abn_ret -> prod_chatter | 2 | 0.011 | -0.017 | -0.005 | -0.053 | 0.045 |

## 6. Last-3-weeks spike check

| ticker | week | product_spike | stock_spike | wiki_views_spike | wiki_edits_spike | product_ratio | stock_ratio | ret_week | ret_next_week | first_spike_day_product | first_spike_day_stock |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AAPL | 2026-09-28 | False | False |  |  | 1.192 | 1.462 | -0.022 | 0.009 |  | 2026-09-29 (Tue) |
| AAPL | 2026-10-05 | False | False |  |  | 0.975 | 0.615 | 0.009 | 0.020 |  |  |
| AAPL | 2026-10-12 | False | False |  |  | 0.997 | 1.385 | 0.020 | 0.012 |  | 2026-10-13 (Tue) |
| AMD | 2026-09-28 | False | False |  |  | 1.248 | 1.294 | 0.005 | -0.041 |  | 2026-09-28 (Mon) |
| AMD | 2026-10-05 | False | False |  |  | 1.066 | 1.765 | -0.041 | -0.130 |  | 2026-10-05 (Mon) |
| AMD | 2026-10-12 | False | False |  |  | 0.901 | 1.035 | -0.130 | -0.023 |  | 2026-10-12 (Mon) |
| AMZN | 2026-09-28 | False | False |  |  | 0.997 | 0.837 | 0.007 | 0.043 |  |  |
| AMZN | 2026-10-05 | False | False |  |  | 1.230 | 0.769 | 0.043 | -0.047 |  |  |
| AMZN | 2026-10-12 | False | False |  |  | 1.106 | 1.222 | -0.047 | -0.008 |  | 2026-10-13 (Tue) |
| GOOGL | 2026-09-28 | False | False |  |  | 0.954 | 0.961 | -0.001 | 0.024 |  |  |
| GOOGL | 2026-10-05 | False | False |  |  | 0.845 | 0.986 | 0.024 | -0.031 |  | 2026-10-08 (Thu) |
| GOOGL | 2026-10-12 | False | False |  |  | 0.823 | 1.278 | -0.031 | -0.060 |  | 2026-10-13 (Tue) |
| JPM | 2026-09-28 | False | False |  |  | 1.152 | 1.333 | -0.031 | 0.007 |  | 2026-09-30 (Wed) |
| JPM | 2026-10-05 | False | False |  |  | 1.030 | 0.444 | 0.007 | 0.020 |  |  |
| JPM | 2026-10-12 | False | False |  |  | 1.212 | 1.778 | 0.020 | -0.024 |  | 2026-10-12 (Mon) |
| META | 2026-09-28 | False | False |  |  | 0.894 | 0.800 | -0.031 | -0.013 |  |  |
| META | 2026-10-05 | False | False |  |  | 0.878 | 0.720 | -0.013 | -0.013 |  | 2026-10-07 (Wed) |
| META | 2026-10-12 | False | False |  |  | 0.886 | 1.250 | -0.013 | -0.094 |  | 2026-10-12 (Mon) |
| MSFT | 2026-09-28 | False | False |  |  | 1.101 | 0.480 | 0.003 | 0.034 |  |  |
| MSFT | 2026-10-05 | False | False |  |  | 0.861 | 1.319 | 0.034 | -0.011 |  | 2026-10-07 (Wed) |
| MSFT | 2026-10-12 | False | False |  |  | 0.862 | 1.319 | -0.011 | -0.009 |  | 2026-10-13 (Tue) |
| NFLX | 2026-09-28 | False | False |  |  | 0.994 | 1.077 | -0.057 | 0.048 |  | 2026-09-29 (Tue) |
| NFLX | 2026-10-05 | False | False |  |  | 0.933 | 1.500 | 0.048 | 0.003 |  | 2026-10-07 (Wed) |
| NFLX | 2026-10-12 | False | False |  |  | 0.897 | 1.000 | 0.003 | -0.066 |  | 2026-10-17 (Sat) |
| NVDA | 2026-09-28 | False | False |  |  | 1.057 | 1.404 | 0.039 | -0.020 |  | 2026-09-28 (Mon) |
| NVDA | 2026-10-05 | False | False |  |  | 0.789 | 1.113 | -0.020 | -0.066 |  |  |
| NVDA | 2026-10-12 | False | False |  |  | 0.969 | 0.716 | -0.066 | -0.015 |  |  |
| TSLA | 2026-09-28 | False | False |  |  | 0.961 | 1.529 | -0.004 | 0.033 |  | 2026-09-29 (Tue) |
| TSLA | 2026-10-05 | False | False |  |  | 0.943 | 0.830 | 0.033 | -0.073 |  |  |
| TSLA | 2026-10-12 | True | False |  |  | 1.559 | 1.961 | -0.073 | 0.049 | 2026-10-16 (Fri) | 2026-10-16 (Fri) |

**Notes (draft from the top posts, for Joshua to check against the threads):**

- **TSLA, week of Oct 12 (the only Reddit spike in the three weeks).**
  - **What happened:** a Tesla demo / product event on Friday Oct 16. The top product posts react to "the demo" and a "new redesign" (r/TeslaLounge, 1,500–2,000 upvotes each), and r/wallstreetbets ran "Tesla has officially lost the plot..", a TSLA chart thread and posts about the Roadster.
  - **Which source spiked first:** neither. Product-subreddit posts went from about 100–145 a day to 399 on Oct 16 (235 on Oct 17). Stock-side posts went from 1–4 a day to 25 on the same day.
  - **Price:** TSLA fell 7.3% that week, which includes the Oct 16 close, and rose 4.9% the next week.
  - **Did it keep spiking?** No: there was no TSLA spike in the weeks of Sep 28 or Oct 5. The stock-subreddit ratio (1.96x) was high, but its robust z-score stayed under 2, so it is not flagged.
- **Large moves with no spike:**
  - AMD fell 13.0% in the week after Oct 5, with stock-subreddit posts at 1.76x their baseline but under the z-score cut.
  - META fell 9.4% and GOOGL 6.0% in the week after Oct 12, with no Reddit spike in either.

  Moves this size without a flagged spike are worth comparing with James's Wikipedia columns.
- **Caveat on "first spike day":** the daily check uses 2x a source's median daily posts over the previous 8 weeks. Stock-subreddit counts are only 0–5 posts a day for most of these stocks, so a single extra post can trip it. Read that column as noise for every stock except TSLA's Oct 16.


## 7. API endpoints

`GET /sentiment` and `GET /spikes` in `src/api/reddit.py`, tested in `tests/test_api_reddit.py`. Run `.venv/bin/uvicorn src.api.main:app` and open `/docs`.

## 8. Strategy results

_Pending: `python -m src.reddit.strategy_product_buzz`._
