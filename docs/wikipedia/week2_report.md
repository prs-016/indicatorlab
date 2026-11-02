# Wikipedia attention: Week 2 report (James)

Run date: 2026-10-30. Everything below is produced by `python -m src.wiki_pipeline` and
`notebooks/wikipedia.ipynb` (Restart and Run All). Research numbers use data before 2025-10-01 only.

## 1. Re-pull outside the holdout

| | Research | Recent (dashboard and spike check only) |
|---|---|---|
| Daily views | 2015-07-01 to 2025-09-30 | 2025-10-01 to 2026-10-25 |
| Files | `data/raw/wikipedia/views_research/` | `data/raw/wikipedia/views_recent/` |
| Weekly table | `data/shared/attention_weekly_wikipedia_research.csv` (534 weeks x 51 stocks x 2 sources) | `..._recent.csv` (56 weeks) |

- 51 stocks: the 10 tracked ones plus the PDF's 50-stock strategy universe. All have every day from
  2015-07-01, with no zero-view days.
- **Article views include every redirect to the article.** Page views are counted under the title a
  reader asked for, so a renamed article's old views sit under the old title. Without this, Tesla
  (`Tesla_Motors` until 2017) and Meta (`Facebook,_Inc.` until Oct 2021) would show almost no views
  before their renames.
- **Caveat, META:** the company only got its own article in late 2019. Before that, Facebook's company
  attention sat on the `Facebook` article, which also covers the product. META's views are 0.02-0.2M a
  year in 2015-2019 versus 2.5-8.4M a year in 2020-2024. Its pre-2020 spikes (57 in total, the most of any stock)
  are mostly noise. Treat META as starting in 2020.
- **Caveat, GOOGL:** `Alphabet_Inc.` gets about a quarter of the views of `Google` (e.g. 39k vs 152k in
  one 2019 week). Worth agreeing with Joshua whether `Google` (or both) should be the title in `config.yaml`.

## 2. `flag_spikes` fixed (look-ahead)

- The robust z-score now uses the median and MAD of **earlier weeks only** (26 needed). It is the same
  rule, parameters (`config.yaml` `spike`) and output as Joshua's `src/reddit/spike_rule.py`.
- Zero baselines stay finite through the `+1` offset (`log((x+1)/(baseline+1))`). A zero MAD leaves rz
  undefined, so the week is not flagged and no `inf` appears. Both cases are tested.
- `test_changing_future_weeks_leaves_past_flags_unchanged` changes only the weeks after t and checks that
  baseline, abnormal, rz and spike up to t are identical. It passes, as do the three week-1 tests. The
  log-2 test now passes `offset=0`, because the shared rule adds 1.
- Research flags: 2.7% of stock-weeks spike on views and 2.7% on edits.

## 3. Returns after a spike

Mean return over the k weeks after a spike week, minus the same after all other weeks, in %. The 95%
CIs resample whole weeks 1,000 times, in blocks of k consecutive weeks because k-week returns of
neighbouring weeks overlap. Abnormal = return minus 52-week beta x SPY.

| Universe | Spike source | k=1 | k=2 | k=3 | k=4 |
|---|---|---|---|---|---|
| 10 tracked (223 spikes) | views, raw | +0.50 [-0.29, 1.26] | +0.55 [-0.56, 1.56] | +0.25 [-1.16, 1.75] | +0.15 [-1.85, 2.17] |
| 10 tracked | views, abnormal | +0.16 [-0.46, 0.81] | +0.17 [-0.84, 1.15] | -0.14 [-1.33, 1.10] | -0.56 [-2.19, 1.05] |
| 51 stocks (734 spikes) | views, raw | +0.27 [-0.09, 0.63] | +0.42 [-0.08, 0.95] | +0.61 [-0.03, 1.32] | +0.66 [-0.27, 1.57] |
| 51 stocks | views, abnormal | +0.13 [-0.15, 0.43] | +0.09 [-0.34, 0.51] | +0.09 [-0.43, 0.67] | -0.04 [-0.86, 0.69] |
| 51 stocks (735 spikes) | edits, abnormal | +0.18 [-0.12, 0.46] | +0.28 [-0.15, 0.69] | +0.32 [-0.27, 0.92] | +0.56 [-0.16, 1.25] |

**Finding:** no reliable difference. Spike weeks are followed by slightly higher raw returns, but none
of the 24 intervals (raw and abnormal, views and edits, k = 1-4) excludes zero. On abnormal returns,
which remove the market, the differences are close to zero. The week-1 AAPL check (same-week returns,
holdout data) could not show prediction. This test can, and it finds none on its own.
Week t's views end on Sunday, after week t's last close, so `ret_next1` starts after all of the week's attention is known.

## 5. Edit-summary analysis

Weekly per company: edits, distinct editors, bytes added/removed, reverts (`revert|rv|rvv|undid|undo`,
whole words) and keyword tags (`config.yaml` `wikipedia.edit_tags`). Tables: `data/processed/wikipedia/weekly_edits_*.csv`.

- **Volume:** TSLA (15 edits a week) and NFLX (14) are the most edited. AMD (2.9) and META (3.1) are the least.
  About 14% of edits are reverts (12,466 of 88,352 across 51 stocks).
- **Tags in view-spike weeks vs other weeks (lift):** layoff 5.0x, CEO/executive 4.0x, acquisition/merger
  3.5x, stock/shares 2.8x, legal 2.6x, earnings 2.5x, product/launch 2.3x. Edits overall are 2.3x higher.
  Tags tell you what happened, e.g. TSLA has many legal (0.37 a week) and CEO (0.29) edits.
- **Tone:** VADER calls 73% of non-empty summaries neutral, and 20% of summaries are empty. As the PDF
  expected, summaries are short and dry, and **the keyword tags carry far more information than tone**.
  Tone was not used further.
- **Timing (lift = rate around the event / base rate):**

  | Event | Signal | week t-2 | t-1 | t | t+1 | t+2 |
  |---|---|---|---|---|---|---|
  | views spike (51 stocks) | edits spike | 1.35 | **2.41** | **3.76** | 1.06 | 0.96 |
  | big price move (top 5% abs. abnormal return) | edits spike | 1.11 | 1.06 | **1.72** | 1.11 | 1.03 |
  | big price move | views spike | 1.22 | 1.43 | **3.10** | 1.67 | 1.38 |

  Edit bursts mostly come **in the same week** as view spikes and big price moves, not after them. They
  also come noticeably often **the week before** a view spike (2.4x), but not the week before a price
  move. Day by day (198 view-spike weeks with edits within 7 days), the busiest edit day falls a median
  of **0 days** from the busiest views day, spread evenly from -7 to +7. Days tied for the most edits
  count as their mean day; a first-day rule had wrongly suggested that edits come half a day earlier.
  So edits are a "something happened" signal at the same speed as views. They show no sign of running
  ahead of prices.

## 6. Last-3-weeks spike check (looking only)

`results/wikipedia/last3weeks_wikipedia.csv`: views and edits columns plus price moves for the weeks of
Sep 28, Oct 5 and Oct 12, 2026. Joshua's `spike_check_recent.py` can join it on ticker and week (see the
notes for Joshua below).

- **AMD, week of Sep 28:** views 1.5x the baseline (rz 3.0), a spike. The only edit was the acquisition
  history (World Labs). Views stayed high the next week (1.3x) but did not spike again. The stock was
  +0.5% that week and then -4.1%, -13.0% and -2.3% over the following three weeks.
- **TSLA, week of Oct 12:** views 2.1x (rz 4.6), the clearest spike. The edits added the second-generation
  Roadster re-reveal (Oct 2026). The stock had fallen 7.3% that week and rose 4.9% the next.
- No edit spikes in these three weeks. The other eight stocks were quiet on Wikipedia. AAPL's views have
  been below the baseline (0.8-0.9x) since the September launches.

## 7. Google Trends alternatives

| Option | Legal to use | History before 2023 | India / Hong Kong | Cost | Tracks AAPL Wikipedia views |
|---|---|---|---|---|---|
| Wikipedia page views | yes (open data, documented API) | yes, Jul 2015 | yes, via hi/zh Wikipedia (smaller audiences) | free | the reference |
| GDELT news volume and tone | yes (open data) | yes, Jan 2017 (DOC API) | yes, many countries and languages | free, rate-limited | not measured: GDELT refused all requests from this machine during the run (HTTP 429) |
| trendspy (scrapes Google) | no: unofficial scraper, exploring only | yes, 2004 (weekly only in windows of 5 years or less) | yes | free | level r = 0.20, weekly change r = 0.59 (2020-2025, term "Apple") |
| SerpApi Google Trends | yes (paid API) | yes, 2004 | yes | about $25/month for 1,000 searches (third-party listings) | same data as trendspy |
| Glimpse | yes (paid) | yes | yes | no public API price (tool from about $99/month) | modelled "absolute" volumes |

**Recommendation.** Keep **Wikipedia page views as the main search-attention source** and add **GDELT news
volume** as the second, free source for all three markets. Wikipedia is free and legal, has daily data
back to 2015, and is already in the pipeline. Its India and Hong Kong coverage depends on the size of
Hindi and Chinese Wikipedia, so pair English and local titles. GDELT is the only free, legal option that
measures news attention across countries from 2017. It also adds tone, but it is rate-limited and must be
cached. Google Trends itself moves with Wikipedia week to week (r = 0.59 on changes for AAPL) but not in
levels (r = 0.20), and the term "Apple" also picks up the fruit. So Google Trends adds information, but
the only legal way to get it is SerpApi, at about $25 a month. Take that up only if a strategy shows a
need for search data specifically. Glimpse's volumes are model estimates, and trendspy must stay exploratory.

## 8. Shared config

`config.yaml` and `src/config.py` come from Joshua's `reddit` branch unchanged (US filled; IN and HK left
for Jamal and Jack). I added one `wikipedia:` block: research start, redirect handling, revert and tag
keywords, the edit-burst ratio, bootstrap settings, the Wikipedia train/test split, the strategy rules
and the 41 extra strategy-universe titles.

## 9. API (`src/api/`)

- `GET /tickers`: every stock and source in `data/shared/attention_weekly_*.csv`, with first week, last week and week count.
- `GET /attention?ticker=AAPL&start=2024-01-01&end=2025-09-30&source=wikipedia,reddit_product`: weekly
  shared-table rows. A source matches exactly or as a prefix (`wikipedia` = views + edits).
- `GET /price?ticker=AAPL&start=...&end=...`: weekly close, return, returns 1-4 weeks after, and abnormal returns.
- One `TestClient` test per endpoint (`tests/test_api_wikipedia.py`).

## 11. Strategy: Wiki Attention Breakout (Wikipedia-only)

Rules were fixed before the first run (`src/wiki_strategy.py`):
- **Entry:** views spike + edit burst (edits at least 2x their 8-week median) + close above the 50-day
  average; buy at the next day's close.
- **Exit:** 4 weeks, an 8% fall, or a close below the 50-day average.
- **Sizing:** equal weight, max 10% per stock, with 50% exposure when SPY is below its 200-day average.
- **Costs and comparison:** 10 bps; 51 stocks; 200 random portfolios with the same dates, sizing and regime.

| Period | Trades | CAGR | Sharpe | Max DD | SPY Sharpe | Equal-weight Sharpe | Random median Sharpe | % random beaten |
|---|---|---|---|---|---|---|---|---|
| Train 2016-2019 | 54 | -0.7% | -0.32 | -5.4% | 1.11 | 1.56 | 0.37 | 2% |
| Test 2020-Sep 2025 | 92 | 3.3% | 0.94 | -5.7% | 0.78 | 0.96 | 0.41 | 96% |

**Decision: Keep on watch.** It beat 96% of random portfolios in test and beat SPY's Sharpe there, but
beat only 2% in train. That is the same pattern as the PDF's tgqm example, so the test result may be
specific to 2020-2025. The strategy is in cash most of the time (a few positions at 10% each), so its
CAGR is small even when its Sharpe is good. Next: run each signal alone and see what the edit-burst
filter adds. The Strategy Log row is in `results/wikipedia/strategy_log_rows.tsv`, ready to paste into the sheet.

**Product Buzz Lead** is implemented by Joshua (`src/reddit/strategy_product_buzz.py` on `reddit`). It
needs his Reddit tables, which are not on my machine. My weekly rows give its Wikipedia confirmation
signal (views up week over week, or edits at least 2x the median).

## Notes for Joshua

1. My weekly rows are in `data/shared/attention_weekly_wikipedia_{research,recent}.csv`, with one row
   per (week, ticker, source), where source is `wikipedia_views` or `wikipedia_edits`. Your
   `spike_check_recent.py` reads `attention_weekly_wikipedia.csv` (one file). Point it at the `_recent` file.
2. `strategy_product_buzz.weekly_features` joins `views` and `edits` from one row per (ticker, week). With
   two sources per week, collapse them first:
   `wiki.groupby(["ticker", "week"])[["views", "edits"]].first()`.
3. `flag_spikes` in `src/wiki_attention.py` is the same rule as your `spike_rule.flag_spikes`. Both can be
   replaced by the shared `spikes.py` once it is on `main`.
4. `src/api/main.py` includes only my router on this branch. When both PRs land, it needs both
   `include_router` lines.
