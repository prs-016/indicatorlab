# Wikipedia: Week 3 progress (James)

Run on 2026-11-11, on research data only (weeks ending before 2025-10-01). This covers the Week 3
guide's quick fixes 1 and 2 and the first half of section 2 (the API, built against local files).

## 1. Team train/test split

`config.yaml` `wikipedia.split` is now the team split: train 2016-06-01 to 2021-12-31, test 2022-01-01 to
2025-09-30 (it was train 2016-2019, test 2020 to Sep 2025). The Wiki Attention Breakout rules are
unchanged (Week 2 report, section 6). Rerun with `python -m src.wiki_strategy`:

| Period | Trades | CAGR | Sharpe | Max DD | SPY Sharpe | Equal-weight Sharpe | Random median Sharpe | % random beaten |
|---|---|---|---|---|---|---|---|---|
| Train Jun 2016-Dec 2021 | 83 | -0.6% | -0.24 | -6.6% | 1.00 | 1.38 | 0.24 | 6% |
| Test Jan 2022-Sep 2025 | 55 | 5.5% | 1.56 | -3.1% | 0.66 | 0.76 | 0.52 | 100% |

**Decision: still Keep on watch.** The pattern is the same as under the old split: it beats every random
portfolio and SPY's Sharpe in test and almost none in train. Train now has 83 entries (the guide asks for
at least 30). The Strategy Log row is in `results/wikipedia/strategy_log_rows.tsv`.

This strategy has 3 indicators from 2 sources (Wikipedia, price), so it does not meet the new standard
for the Strategy Log (at least 4 indicators, 3 layers). It stays as the Wikipedia-only reference.

## 2. FinBERT on the shared scorer

`src/sentiment/finbert_scorer.py` is one scorer for Reddit and Wikipedia (the guide's step 1.5). It:
- loads `ProsusAI/finbert` once, on Apple MPS or CUDA when available;
- returns `label`, `sentiment_pos`, `sentiment_neg`, `sentiment_neu`, and `sentiment_net` = pos minus neg,
  which are the attention record's names;
- caches scores by text hash and model snapshot, so reruns only score new text, and a new model
  version rescores everything.

It is built from Joshua's `score_finbert` (`src/reddit/sentiment_scorers.py`), which keeps only the label
and pos minus neg. Joshua, if you agree, `score_finbert` can call it.

`src/wiki_sentiment.py` now uses it. The filters are unchanged: at least 5 words, at most 60 sentences
per stock-week. The weekly table now holds the mean of each probability, `sentiment_net`, and
`n_scored`. On the same 32,672 sentences the labels did not change (69% neutral, 16% negative,
14% positive; 28% are about old history). The net tone is now a mean of probabilities rather than a
share of labels:

| | Before (label share) | Now (mean P(pos) minus P(neg)) |
|---|---|---|
| Correlation with abnormal return, same week | 0.012 | 0.005 |
| Correlation with abnormal return, next week | -0.010 | -0.013 |

All 15 bootstrap confidence intervals still include zero
(`results/wikipedia/edit_sentiment_returns.csv`).

**Edit summaries, VADER and FinBERT** (the 10 tracked stocks, 29,796 non-empty summaries;
`results/wikipedia/summary_tone_vader_finbert.csv`):

| | Neutral | Positive | Negative |
|---|---|---|---|
| VADER | 72.5% | 16.7% | 10.9% |
| FinBERT | 92.4% | 2.4% | 5.2% |
| FinBERT agrees, among summaries VADER labels this way | 94.7% | 5.2% | 19.5% |

Overall agreement is 71.6%. FinBERT finds even less tone in summaries than VADER. VADER's tone mostly
comes from wiki markup:
- **Positive summaries:** "WP:" policy links appear in 20% of them and "Special:" (in revert notices)
  in 19%.
- **Negative summaries:** "no" appears in 11%, "dead" (dead links) in 10%, the section name
  "Criticism" in 8% and "error" in 7%.

This supports scoring the article text rather than the summaries.

## 3. API (built locally; deploy waits for the AWS resources)

`src/wiki_export.py` writes the attention records the guide asks for:
- `wiki_weekly.parquet` holds research weeks only: views as `value`, with baseline, ratio, spike and edit
  sentiment. Edits are in the same row (`edits`, `edits_ratio`, `edits_spike`).
- `wiki_current.parquet` holds "Hot right now": the last 7 published days of views, against the median of
  the 8 full weeks before them, using the same spike rule.
- `prices_weekly.parquet` holds research weeks of the weekly price panel.

They go to `data/processed/`, which matches the bucket's `processed/` layout.

`src/api/dashboard.py` adds these routes to the one FastAPI app:

| Route | Reads | Notes |
|---|---|---|
| `GET /health` | write time of each table | |
| `GET /attention/{ticker}?source=&market=&from=&to=` | `*_weekly.parquet` | research weeks only; 404 for an unknown ticker |
| `GET /sentiment/{ticker}?market=` | `*_weekly.parquet` | Reddit by `group` (investor / product), Wikipedia edits |
| `GET /spikes?week=&market=` | `*_weekly.parquet`, prices | size, sentiment, repeat (spiked in the 3 weeks before), and whether the bigger abnormal move came in the spike week or the week after; 422 for a holdout week |
| `GET /hot?market=` | `*_current.parquet`, live tables | ratio above 1, sorted, with today's move from the live table |
| `GET /live/{market}` | DynamoDB (`live/<market>.json` locally) | open or closed from the session hours in `config.yaml` (the HK lunch break is included); a "hot" badge on each quote |
| `GET /runs`, `/runs/{id}` | Vibe-Trading server | Bearer key read on the server, never sent to the browser |

`src/api/storage.py` reads `data/` locally, or `s3://indicatorlab-data` when `INDICATORLAB_DATA` points
there. It caches each table for 10 minutes (`api.cache_seconds`). CORS is limited to `CORS_ORIGINS`.

Tests: `tests/test_api_dashboard.py` runs 10 TestClient tests on fixture tables in `tests/fixtures/api/`.
They cover an unknown ticker (404), an empty week, a holdout week, the check that no research route
returns weeks from 2025-10-01 on, market hours, and the key staying server side.

A check on real data: `/spikes?week=2025-09-08` puts ORCL first, with views 9.6x baseline in the week of
Oracle's September earnings jump (+23% abnormal return that week).

## Open items

- **Reddit route clash.** Joshua's Week 2 router also has `GET /spikes` and `GET /sentiment` (taking
  `?ticker=`). It is mounted first so his tests pass. The dashboard's `/spikes?week=` takes over when his
  routes move under `/reddit/`, as the guide plans.
- **Holdout vs dashboard page 3.** "This week's spikes" reads `/spikes`, which the guide also says must
  not return weeks from 2025-10-01 on. As built, page 3 shows the latest research week, and `/hot` shows
  the current week. This needs a decision from Anay or Prakhar.
- **Waiting on others:** the AWS resources (bucket, tables, SSM, ECR) from Joshua; the live tables from
  Jamal and Jack; the Reddit `reddit_weekly.parquet` / `reddit_current.parquet` from Joshua.
- **Not started yet:** the Wikipedia pull on AWS, the App Runner deploy, dashboard v1, the upstream
  Wikipedia loader, 3 complex strategies with the full evaluation (IC, drop-one, deflated Sharpe), and
  the 50 blind labels for Joshua's kappa.
