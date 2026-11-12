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

`src/wiki_sentiment.py` now scores with Joshua's shared scorer, `FinbertScorer` in
`src/sentiment/finbert_scorer.py`, from his `sentiment-scorer` branch (merged into `wikipedia`). That is
the guide's step 1.5: Reddit and Wikipedia use identical code. The scorer:
- uses `ProsusAI/finbert` at the revision pinned in `config.yaml` `sentiment`;
- returns `sentiment_label`, `sentiment_pos`, `sentiment_neg` and `sentiment_neu`; Wikipedia adds
  `sentiment_net` = pos minus neg, the attention record's name;
- keeps scores in its `ScoreCache` (`data/processed/wikipedia/finbert_cache/`), keyed by each sentence's
  hash and the model version, so reruns only score new text.

An earlier version of this branch had its own scorer at the same path. It was replaced by Joshua's, and
rescoring all 32,672 sentences with his gave identical labels, with probabilities differing by at most 1e-7.

The filters are unchanged: at least 5 words, at most 60 sentences
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

Tests: `tests/test_api_dashboard.py` runs 12 TestClient tests on fixture tables in `tests/fixtures/api/`,
on the dashboard router alone (in the merged app Joshua's Week 2 router still owns `/spikes`), and
`tests/test_api_storage.py` covers the S3 and DynamoDB reads with a mocked boto3.
They cover an unknown ticker (404), an empty week, a holdout week, the check that no research route
returns weeks from 2025-10-01 on, market hours, and the key staying server side.

A check on real data: `/spikes?week=2025-09-08` puts ORCL first, with views 9.6x baseline in the week of
Oracle's September earnings jump (+23% abnormal return that week).

## 4. Three complex strategies (US)

The rules are in `docs/wikipedia/week3_strategies.md`, written before the first run and unchanged since.
Each strategy has 5 or 6 indicators from 2 sources (Wikipedia; Yahoo price and volume) and 3 or 4
layers: regime, entry, and exit/risk. S1 uses attention as a risk filter. Run with
`python -m src.wiki_complex`; it writes `results/wikipedia/week3_strategy_log_us.csv`,
`week3_drop_one_us.csv`, and the trades, weights and daily returns per strategy.

**Setup.** Costs are 10 bps per unit of turnover. Sizing is inverse 63-day volatility, capped at 10%.
Week W signals trade at the first close of W+1. The random baseline is 200 runs with random entry timing
(seed 42), keeping each trade's stock, weight and holding length. The deflated Sharpe counts 27 trials:
the 20 Vibe factor strategies, Wiki Attention Breakout, and the 6 runs below. SPY Sharpe is 1.00 in train
and 0.66 in test.

| Strategy | Entries train / test | Sharpe train / test | CAGR train / test | Max DD train / test | % random beaten train / test | IC train / test | Deflated Sharpe | Decision |
|---|---|---|---|---|---|---|---|---|
| S1 Attention-gated momentum | 320 / 226 | 1.12 / 0.25 | 15.3% / 2.2% | -17.0% / -19.9% | 26% / 0.5% | 0.004 / 0.011 | 0.17 | DROP |
| S2 Attention reversal | 686 / 458 | 0.91 / -0.25 | 6.3% / -1.6% | -7.7% / -14.1% | 71% / 18.5% | -0.001 / -0.013 | 0.03 | DROP |
| S3 News-tagged breakout | 1 / 1 | 0.29 / 0.41 | 0.1% / 0.3% | -0.5% / -1.0% | 54% / 62% | 0.008 / 0.008 | 0.25 | DROP |
| S3, loosening (a) no volume | 6 / 1 | 0.88 / 0.41 | 0.4% / 0.3% | -0.7% / -1.0% | 91% / 62% | 0.008 / 0.008 | 0.25 | DROP |
| S3, loosening (b) + 50-day trend | 13 / 14 | 0.56 / 0.92 | 0.6% / 1.9% | -1.6% / -2.3% | 67% / 82.5% | 0.008 / 0.008 | 0.64 | DROP |
| S3, loosening (c) + views ratio 1.5 | 13 / 14 | 0.56 / 0.92 | 0.6% / 1.9% | -1.6% / -2.3% | 67% / 82.5% | 0.008 / 0.008 | 0.64 | DROP |

**Why each is dropped:**
- **S1:** its test Sharpe (0.25) is below SPY's, and it beats few random-timing runs. Random entry dates on
  the same stocks do better (median Sharpe 1.26 train, 1.06 test), so the gain comes from which stocks it
  holds, not when. Its momentum IC is close to 0.
- **S2:** good in train, but it loses money in test and beats only 18.5% of random runs there.
- **S3:** too rare. In train, only 23 of 14,841 stock-weeks have a views spike, an edit burst and an
  earnings or product tag, before the price conditions are applied. Even fully loosened it has 13 entries,
  below the guide's 30. Step (c) adds nothing, because a views ratio of at least 1.5 is almost the same set
  of weeks as a spike (408 vs 406). Its test result (Sharpe 0.92, above SPY) is on 14 trades, and it beats
  82.5% of random runs, not 90%.

**Drop-one** (`week3_drop_one_us.csv`; Sharpe change train / test when the indicator is removed):
- **S1:**
  - Dropping the 50-day trend changes the Sharpe by -0.14 / +0.49 (test 0.74).
  - The attention gates matter little: z-score +0.05 / +0.07, edit-burst breadth +0.10 / -0.02.
  - The regime layer: +0.03 / -0.14.
- **S2:** dropping the volume filter gives +0.15 / +0.76, and dropping the attention filter gives
  -0.27 / +0.59.
- **S3 (step c):**
  - The news tags carry it in train (-0.37 when dropped).
  - The regime and volume rows change nothing: SPY was above its 200-day average whenever S3 held a
    stock, and volume was already dropped by loosening.

These are diagnostics only. The rules are not changed after seeing test results, and a variant built
from them would be a new trial.

**Vibe-Trading cross-check.** `python -m src.wiki_complex --vibe` writes each final version as a
Vibe run dir in `~/.vibe-trading/runs/indicatorlab_wiki_*_us/`. Each has `config.json`, a `SignalEngine`
that reads the target weights from `code/weights.csv`, `source: yfinance` and `slippage_us: 0.001`.
Run one from its directory:

```bash
cd ~/.vibe-trading/runs/indicatorlab_wiki_s1_us
PYTHONPATH="<Vibe checkout>/agent" <venv>/bin/python -m backtest.runner "$PWD"
```

US codes are written as `TICKER.US`, because Vibe reads a bare `BRK-B` as a China B share. Vibe fills at
the next open, and with `position_adjustment: hold` it applies entries and exits but not the weekly
resizes, so its numbers are a check rather than an exact replay:

| Strategy | Vibe Sharpe train / test | Ours | Daily return correlation train / test |
|---|---|---|---|
| S1 | 1.14 / 0.56 | 1.12 / 0.25 | 0.97 / 0.95 |
| S2 | 0.70 / -0.10 | 0.91 / -0.25 | 0.93 / 0.96 |
| S3 (step c) | 0.48 / 0.87 | 0.56 / 0.92 | 0.98 / 0.99 |

No decision changes: S1's Vibe test Sharpe is still below SPY's 0.66.

**India** follows once Jamal's `config/india_wiki_titles.csv` exists. Vibe's `india_equity` engine will
then set the costs.

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
  Wikipedia loader, the India run of the complex strategies, and the 50 blind labels for Joshua's kappa.
