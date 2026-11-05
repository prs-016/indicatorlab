# Wikipedia attention: Week 2 report (James)

Run date: 2026-11-04 (company-to-article matching refined; see 1b). Everything below is produced by `python -m src.wiki_pipeline` and
`notebooks/wikipedia.ipynb` (Restart and Run All). Research numbers use data before 2025-10-01 only.

## 1. Re-pull outside the holdout

| | Research | Recent (dashboard and spike check only) |
|---|---|---|
| Daily views | 2015-07-01 to 2025-09-30 | 2025-10-01 to 2026-11-01 |
| Files | `data/raw/wikipedia/views_research/` | `data/raw/wikipedia/views_recent/` |
| Weekly table | `data/shared/attention_weekly_wikipedia_research.csv` (534 weeks x 51 stocks x 2 sources) | `..._recent.csv` (57 weeks) |

- 51 stocks: the 10 tracked ones plus the PDF's 50-stock strategy universe. All have every day from
  2015-07-01, with no zero-view days, except META (from 2019-11-25, see 1b).
- `data/shared/attention_weekly_wikipedia.csv` has both periods in one file, for Joshua's `src/reddit` code.
- **Article views include every redirect to the article.** Page views are counted under the title a
  reader asked for, so a renamed article's old views sit under the old title. Without this, Tesla
  (`Tesla_Motors` until 2017) and Meta (`Facebook,_Inc.` until Oct 2021) would show almost no views
  before their renames.
- META and GOOGL are matched differently from the other stocks; see section 1b.

## 1b. Matching stocks to articles

`python -m src.wiki_titles` checks every title in `config.yaml` against Wikipedia and Wikidata. All 52
titles pass: each is the article itself (not a redirect or a disambiguation page), and each Wikidata item
lists the stock's ticker, except Netflix's, which has no ticker field.

- **META starts in late Nov 2019.** Until then `Facebook, Inc.` (renamed `Meta Platforms` in Oct 2021) was an
  80-byte redirect to the `Facebook` product article. So META's 2015-2019 "views" (150-600 a day vs
  5,000-23,000 after) and edits were redirect noise, and they produced 57 spikes, the most of any stock.
  A title now counts from the first full week after its first revision of at least
  `min_article_bytes` (400). Redirects are under 200 bytes and a new stub is about 400. META's series
  starts on 2019-11-25 (the split from `Facebook` was drafted on Sunday Nov 24). The `Facebook` product article is not added: it is the product, as
  `iPhone` would be for Apple.
- **GOOGL = `Alphabet_Inc.` + `Google`.** `Google` (Google LLC, the operating company) gets about 5x
  Alphabet's views (26k vs 6k a day in 2019) and existed before Alphabet (created 10 Aug 2015). Its
  Wikidata item lists GOOGL/GOOG, and Joshua's Reddit rules already match "Google" for GOOGL. Weekly
  changes of the two articles' views correlate only 0.22-0.27, so Alphabet alone missed most of
  GOOGL's attention. Views, edits and edit sentiment are now summed over both, each from its own start.
  `config.yaml` titles can be a list per language for this.
- **Redirects stay in.** Old names carry most of some stocks' views: `The_Home_Depot` 82% of HD's,
  `Cisco_Systems` 65% of CSCO's, `Advanced_Micro_Devices` 60% of AMD's, `Salesforce.com` 52% of CRM's.
  Across all 2,145 redirects, the largest that are not a name of the company are merged product or brand
  pages, each at most 2.2% of a stock's views (e.g. `Goldman_Sachs_controversies`, `PediaSure` for ABT,
  `Nvidia_Shield`). So no exclusion list is needed.
- **Vandal blanking is ignored.** 29 of the 51 articles were blanked at least once (size under 400 bytes
  for a few minutes). Only the first article-sized revision sets the start, so these keep their full history.

## 2. `flag_spikes` fixed (look-ahead)

- The robust z-score now uses the median and MAD of **earlier weeks only** (26 needed). It is the same
  rule, parameters (`config.yaml` `spike`) and output as Joshua's `src/reddit/spike_rule.py`.
- Zero baselines stay finite through the `+1` offset (`log((x+1)/(baseline+1))`). A zero MAD leaves rz
  undefined, so the week is not flagged and no `inf` appears. Both cases are tested.
- `test_changing_future_weeks_leaves_past_flags_unchanged` changes only the weeks after t and checks that
  baseline, abnormal, rz and spike up to t are identical. It passes, as do the three week-1 tests. The
  log-2 test now passes `offset=0`, because the shared rule adds 1.
- Research flags: 2.6% of stock-weeks spike on views and 2.7% on edits.

## 3. Returns after a spike

Mean return over the k weeks after a spike week, minus the same after all other weeks, in %. The 95%
CIs resample whole weeks 1,000 times, in blocks of k consecutive weeks because k-week returns of
neighbouring weeks overlap. Abnormal = return minus 52-week beta x SPY.

| Universe | Spike source | k=1 | k=2 | k=3 | k=4 |
|---|---|---|---|---|---|
| 10 tracked (191 spikes) | views, raw | +0.49 [-0.41, 1.38] | +0.73 [-0.49, 1.91] | +0.46 [-1.09, 2.15] | +0.48 [-1.73, 2.77] |
| 10 tracked | views, abnormal | +0.13 [-0.60, 0.89] | +0.29 [-0.79, 1.44] | +0.02 [-1.27, 1.53] | -0.27 [-2.23, 1.56] |
| 51 stocks (702 spikes) | views, raw | +0.24 [-0.13, 0.62] | +0.44 [-0.09, 0.98] | +0.66 [-0.04, 1.40] | +0.73 [-0.21, 1.65] |
| 51 stocks | views, abnormal | +0.11 [-0.18, 0.42] | +0.10 [-0.34, 0.54] | +0.12 [-0.43, 0.70] | +0.03 [-0.78, 0.81] |
| 51 stocks (730 spikes) | edits, abnormal | +0.19 [-0.11, 0.47] | +0.26 [-0.15, 0.66] | +0.30 [-0.31, 0.89] | +0.48 [-0.18, 1.21] |

**Finding:** no reliable difference. Spike weeks are followed by slightly higher raw returns, but none
of the 24 intervals (raw and abnormal, views and edits, k = 1-4) excludes zero. On abnormal returns,
which remove the market, the differences are close to zero. The week-1 AAPL check (same-week returns,
holdout data) could not show prediction. This test can, and it finds none on its own.
Week t's views end on Sunday, after week t's last close, so `ret_next1` starts after all of the week's attention is known.

## 5. Edit-summary analysis

Weekly per company: edits, distinct editors, bytes added/removed, reverts (`revert|rv|rvv|undid|undo`,
whole words) and keyword tags (`config.yaml` `wikipedia.edit_tags`). Tables: `data/processed/wikipedia/weekly_edits_*.csv`.

- **Volume:** TSLA (15 edits a week) and NFLX (14) are the most edited of the tracked stocks. AMD (2.9) and MSFT
  (3.7) are the least. About 14% of edits are reverts (12,738 of 90,825 across 51 stocks).
- **Tags in view-spike weeks vs other weeks (lift):** layoff 4.7x, CEO/executive 4.0x, acquisition/merger
  3.4x, stock/shares 2.6x, legal 2.5x, product/launch 2.4x, earnings 2.4x. Edits overall are 2.3x higher.
  Tags tell you what happened, e.g. TSLA has many legal (0.37 a week) and CEO (0.29) edits.
- **Tone:** VADER calls 73% of non-empty summaries neutral, and 20% of summaries are empty. As the PDF
  expected, summaries are short and dry, and **the keyword tags carry far more information than tone**.
  Tone was not used further.
- **Timing (lift = rate around the event / base rate):**

  | Event | Signal | week t-2 | t-1 | t | t+1 | t+2 |
  |---|---|---|---|---|---|---|
  | views spike (51 stocks) | edits spike | 1.47 | **2.46** | **3.92** | 1.21 | 0.95 |
  | big price move (top 5% abs. abnormal return) | edits spike | 1.09 | 1.09 | **1.80** | 1.14 | 1.04 |
  | big price move | views spike | 1.22 | 1.57 | **3.14** | 1.77 | 1.44 |

  Edit bursts mostly come **in the same week** as view spikes and big price moves, not after them. They
  also come noticeably often **the week before** a view spike (2.5x), but not the week before a price
  move. Day by day (190 view-spike weeks with edits within 7 days), the busiest edit day falls a median
  of **0 days** from the busiest views day, spread evenly from -7 to +7. Days tied for the most edits
  count as their mean day; a first-day rule had wrongly suggested that edits come half a day earlier.
  So edits are a "something happened" signal at the same speed as views. They show no sign of running
  ahead of prices.

## 5b. Sentiment of the text editors add (FinBERT)

Edit summaries say little, so this scores the article text itself (`src/wiki_sentiment.py`). For each
stock-week it takes the net change from the revision live at Monday 00:00 to the one live at the end of
the week (so vandalism reverted within the week drops out). It keeps the new or changed prose sentences
(5+ words; no infobox, table or moved paragraphs), and FinBERT (`ProsusAI/finbert`, trained on financial
news) labels each one positive, negative or neutral. A week is "negative" when it adds more negative than
positive sentences. The data covers the 10 tracked stocks (GOOGL: both articles; META from Nov 2019)
in the research period.

- **Volume:** 4,553 stock-weeks had edits and 3,628 added at least one sentence: 32,672 sentences in all.
  69% are neutral, 16% negative and 14% positive. 1,073 weeks were mostly negative and 1,069 mostly positive.
- **Much of the "new" text is old history.** 28% of sentences name only years at least 2 years before the
  week, because editors re-add or rewrite history sections. These are a little less negative
  (14.5% vs 17.2%).
- **Returns (abnormal, in %, 95% block-bootstrap CIs):**

  | Comparison | same week | k=1 | k=2 | k=3 | k=4 |
  |---|---|---|---|---|---|
  | negative-edit weeks vs the rest (1,073 vs 2,555) | +0.00 [-0.32, 0.34] | -0.10 [-0.40, 0.22] | -0.22 [-0.66, 0.21] | -0.05 [-0.69, 0.52] | +0.20 [-0.48, 0.88] |
  | positive-edit weeks vs the rest (1,069 vs 2,559) | -0.03 [-0.37, 0.29] | +0.04 [-0.31, 0.38] | -0.10 [-0.62, 0.39] | -0.10 [-0.73, 0.50] | -0.25 [-1.00, 0.40] |
  | view-spike weeks: negative vs positive edits (67 vs 43) | -1.49 [-4.00, 0.90] | +0.82 [-1.18, 2.81] | +1.43 [-1.32, 4.19] | -0.28 [-3.39, 2.73] | +0.28 [-3.25, 3.85] |

**Finding:** edit sentiment carries no return signal. All 15 intervals include zero, and the correlation
of a week's net tone with its abnormal return is 0.01 (same week) and -0.01 (next week). The only hint is
in view-spike weeks: when editors add negative text to a stock everyone is reading, it did 1.5% worse that
week than when they added positive text. That gap is too uncertain (67 vs 43 weeks) to use, and it is a
reaction, not a prediction. Wikipedia text follows the news, and old history drowns out what is new.
`results/wikipedia/edit_sentiment_{returns,summary}.csv`; rerun with `python -m src.wiki_sentiment analyse`.

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
| Train 2016-2019 | 51 | -0.8% | -0.38 | -5.5% | 1.11 | 1.56 | 0.32 | 2% |
| Test 2020-Sep 2025 | 88 | 3.4% | 1.02 | -5.9% | 0.78 | 0.96 | 0.38 | 98% |

**Decision: Keep on watch.** It beat 98% of random portfolios in test and beat SPY's Sharpe there, but
beat only 2% in train. That is the same pattern as the PDF's tgqm example, so the test result may be
specific to 2020-2025. The strategy is in cash most of the time (a few positions at 10% each), so its
CAGR is small even when its Sharpe is good. Next: run each signal alone and see what the edit-burst
filter adds. The Strategy Log row is in `results/wikipedia/strategy_log_rows.tsv`, ready to paste into the sheet.

**Product Buzz Lead** is implemented by Joshua (`src/reddit/strategy_product_buzz.py` on `reddit`). It
needs his Reddit tables, which are not on my machine. My weekly rows give its Wikipedia confirmation
signal (views up week over week, or edits at least 2x the median).

## Notes for Joshua

1. My weekly rows are in `data/shared/attention_weekly_wikipedia_{research,recent}.csv`, with one row
   per (week, ticker, source), where source is `wikipedia_views` or `wikipedia_edits`. The pipeline also
   writes `attention_weekly_wikipedia.csv` (both periods), the file your `spike_check_recent.py` and
   `strategy_product_buzz.py` read, so they work unchanged.
2. `strategy_product_buzz.weekly_features` joins `views` and `edits` from one row per (ticker, week). With
   two sources per week, collapse them first:
   `wiki.groupby(["ticker", "week"])[["views", "edits"]].first()`.
3. `flag_spikes` in `src/wiki_attention.py` is the same rule as your `spike_rule.flag_spikes`. Both can be
   replaced by the shared `spikes.py` once it is on `main`.
4. In `config.yaml`, GOOGL's Wikipedia title is now a list (`[Alphabet_Inc., Google]`). Read titles with
   `wiki_pipeline.article_titles`, not as a string. The merge with `main` keeps both API routers.
