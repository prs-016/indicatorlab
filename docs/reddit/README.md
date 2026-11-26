# Indicator Lab (Advanced) — Reddit chatter & stock returns

Research question: **can unusual Reddit chatter predict future stock returns?**
This pipeline collects historical r/stocks, r/investing and r/wallstreetbets submissions
from [Arctic Shift](https://arctic-shift.photon-reddit.com), matches 10 large-cap tickers
locally, builds weekly chatter metrics with the team's 2× spike definition, runs an Apple
September-event study, and benchmarks five Alpha101 strategies with Vibe-Trading.

Findings and limitations: [`week1_summary.md`](week1_summary.md).

## Layout

```
src/reddit/
  settings.py                paths, subreddits, date range, tickers
  arctic_client.py           polite HTTP client: ~1 s pacing, backoff, body-level error detection
  collect_reddit.py          collect | coverage | verify | status  (daily, paginated, resumable)
  build_posts.py             raw day files -> data/reddit/processed/posts.parquet (deduplicated by post id)
  match_tickers.py           cashtag / ticker / company-name matching on title + selftext
  validation_sample.py       seeded 50-post validation sample; --merge-labels computes the FPR
  backtest_strategies.py     Week 1 Reddit-spike strategies + benchmark -> append-only Strategy Log
  make_strategy_sheet.py     team-format strategy sheet from the log
  dashboard_server.py        local dashboard (frontend/reddit_dashboard/index.html)
  weekly_metrics.py          weekly metrics (Mon 00:00 UTC), completeness flags, spike columns
  apple_event_study.py       AAPL weekly returns (yfinance, adjusted) + September event table
  visualization.py           AAPL chatter-vs-price charts
  qa_checks.py               end-to-end QA -> results/reddit/tables/qa_report.md
  praw_client.py, check_praw_connection.py   Reddit API setup for future collection
  run_vibe_trading.sh, parse_strategy_log.py  Alpha101 benchmark run + parsed table
tests/reddit/                pytest: pagination/retry, matching, spikes (no look-ahead), returns
frontend/reddit_dashboard/   dashboard page
```

Local only (git-ignored, never committed):

```
data/reddit/raw/arctic_shift/<sub>/<YYYY>/<YYYY-MM-DD>.json.gz   raw API responses (every page + request metadata)
data/reddit/raw/manifest.csv   append-only collection log: status, n_posts, pages, attempts, UTC retrieval times
data/reddit/raw/coverage/, data/reddit/raw/prices/   raw coverage probes and price downloads
data/reddit/processed/         posts, matches, reddit_weekly*.csv, day_status, weekly returns
data/reddit/validation/        ticker_validation_50.csv, apple_events.csv, collection_spotcheck.csv
results/reddit/                tables/ charts/ strategy_logs/
logs/reddit/                   collect_reddit.log, pipeline.log
```

## Setup

```bash
uv venv --python 3.12 .venv          # or: python3.12 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## Reproduce the full analysis

All commands run from the repository root:

```bash
PY=.venv/bin/python

# 1. Earliest available post per subreddit (limit=1&sort=asc, verified by a second request)
$PY -m src.reddit.collect_reddit coverage

# 2. Historical collection, 2023-01-01 .. last complete UTC day. Safe to interrupt and re-run:
#    days recorded as `complete` are skipped; failed/partial days are retried.
$PY -m src.reddit.collect_reddit collect --start 2023-01-01
$PY -m src.reddit.collect_reddit status                 # -> results/tables/collection_summary.csv
$PY -m src.reddit.collect_reddit verify --n-per-sub 10  # independent sort=desc spot-check of archived days

# 3. Processing and analysis
$PY -m src.reddit.build_posts
$PY -m src.reddit.match_tickers
$PY -m src.reddit.weekly_metrics
$PY -m src.reddit.apple_event_study --refresh-prices
$PY -m src.reddit.visualization
$PY -m src.reddit.validation_sample                  # draws the 50-post sample (seed 42)
$PY -m src.reddit.validation_sample --merge-labels   # merges data/validation/agent_labels_50.csv, computes FPR

# 4. Quality checks and tests
$PY -m src.reddit.qa_checks
$PY -m pytest tests/reddit -q

# 5. Five Reddit-indicator strategies -> append-only Strategy Log (every run, every result)
$PY -m src.reddit.backtest_strategies --refresh-prices --note "why this run"
#    -> results/strategy_logs/strategy_log.csv / strategy_log.md, runs/<run_id>/*_weekly.csv
$PY -m src.reddit.make_strategy_sheet --who "Joshua"   # team-format sheet -> strategy_sheet.csv / .tsv

# 6. Alpha101 benchmark (separate exercise, not Reddit-derived)
src/reddit/run_vibe_trading.sh
$PY -m src.reddit.parse_strategy_log
```

### Dashboard

```bash
.venv/bin/python -m src.reddit.dashboard_server --port 8765   # then open http://localhost:8765
```

Shows live collection progress and ETA, weekly chatter per ticker with spike weeks, the Apple
event table and charts, top spikes, match counts, subreddit coverage and the Alpha101 table.
**Rebuild analysis** reruns build_posts → match_tickers → weekly_metrics → apple_event_study →
visualization on the days collected so far. It never starts collection.

The full collection is roughly 15,000 requests (about 9 hours at ~1 request/second; busy
r/wallstreetbets days need 10–17 pages because the API returns ~100 posts per response).

## Week 2: product subreddits, trusted sentiment, cause vs reaction

Week 2 research used data before 2025-10-01; since Week 4 the cutoff is `holdout_start` in `config.yaml`
(2026-11-01, so research data runs through 2026-10-31). Posts carry a
`period` column (`research` / `recent`); `build_posts.load_posts()` returns research posts only unless
asked, and every analysis asserts it saw no holdout week. The last-3-weeks check and the API are the
only consumers of `recent` rows.

Markets, stocks, subreddits, match patterns, Wikipedia titles, benchmarks, the spike rule and the
strategy settings live in `config.yaml` (loaded by `src/config.py`). Subreddit types:
`product` (every post counts for its company), `stock` and `general` (text-matched, the
`reddit_stock` source) and `sector` (r/hardware; text-matched, counted as `reddit_product`).

```bash
PY=.venv/bin/python
# Step 2: survey candidate subreddits (subscribers, first post, 2024 posts/week) -> results/reddit/tables/subreddit_map.csv
$PY -m src.reddit.subreddit_map --print-config
# Step 3: collect (resumable). A seeded priority pass first, so labelling can start early, then everything.
$PY -m src.reddit.collect_reddit collect --start 2023-01-01 --end 2025-09-30 --sample-days-per-year 15
$PY -m src.reddit.collect_reddit collect --start 2023-01-01 --end 2025-09-30      # run A (research)
$PY -m src.reddit.collect_reddit collect --start 2025-10-01 --end 2026-10-18      # run B (spike check only)
$PY -m src.reddit.collect_reddit status --end 2025-09-30                          # posts, failed days, storage
$PY -m src.reddit.build_posts && $PY -m src.reddit.match_tickers
# Steps 4-5: draw the hand-labelling samples, then label at http://localhost:8766
$PY -m src.reddit.label_samples match && $PY -m src.reddit.label_samples sentiment
$PY -m src.reddit.label_server --rater joshua                 # second rater: --rater <name> --double-only
$PY -m src.reddit.label_eval match --rater joshua
$PY -m src.reddit.label_eval sentiment --rater joshua --second <name>
# Step 5: score every post with the chosen scorer, then the weekly table (shared format)
$PY -m src.reddit.score_posts
$PY -m src.reddit.market_data && $PY -m src.reddit.reddit_weekly
# Step 6, 7, 9
$PY -m src.reddit.cause_reaction
$PY -m src.reddit.spike_check_recent
$PY -m src.reddit.strategy_product_buzz --note "why this run"
# Step 8: API
.venv/bin/uvicorn src.api.main:app --port 8000                # http://localhost:8000/docs
```

* **Spike rule** (`src/reddit/spike_rule.py`): baseline = median of the previous 8 weeks; abnormal =
  log((x + 1) / (baseline + 1)); spike when the ratio is at least 1.5 and the robust z-score of abnormal,
  using the median and MAD of *earlier* weeks only (26 needed), is at least 2. `tests/reddit/test_spike_rule.py`
  checks that changing future weeks never changes past flags.
* **Retries** (`config.yaml` `reddit.arctic_shift`): about 1 s between requests; on Timeout or Internal
  server error wait 10-30 s and retry up to 3 times, then the day is logged `failed` and retried on the
  next run. A page under 100 records ends a day (never followed by more posts in 12,059 Week 1 pages).
* **Sentiment**: four scorers in `sentiment_scorers.py`; the LLM uses a pinned model
  (`claude-haiku-5-5`), the fixed prompt `src/reddit/prompts/sentiment_v1.txt`, no thinking, JSON output,
  and a response cache. The API no longer accepts `temperature`, so reproducibility comes from the pinned
  model, fixed prompt and cache. The Loughran-McDonald CSV goes in `data/reddit/raw/lexicons/`.
* **Strategy split**: Reddit data starts in 2023, so train is 2023-01-02..2024-06-30 and test
  2024-07-01..2025-09-30 (`strategy.reddit_split`), logged as a departure from 2011-2019 / 2020-2025.

## Week 3: FinBERT, the Claude answer key, AWS and the `/reddit/*` API

```bash
PY=.venv/bin/python
# Label sample over 2016-06 .. 2025-09: seeded random pre-2023 days (kept out of the corpus), then the draw
$PY -m src.reddit.label_pool collect && $PY -m src.reddit.label_pool build
$PY -m src.reddit.label_samples sentiment
# Answer key written by Claude Opus (no hand labels); prints the cost and sends nothing without --confirm-cost
$PY -m src.reddit.auto_label --confirm-cost
$PY -m src.reddit.label_eval sentiment --rater claude-opus --scorers vader finbert llm   # + --second james
# Production scoring (cached by post_id, ticker, model_version), weekly tables, report
$PY -m src.reddit.score_posts --scorer finbert
$PY -m src.reddit.reddit_weekly
$PY -m src.reddit.week3_report
# AWS pipeline modes (see infra/README.md); INDICATORLAB_ROOT_URI=<local dir> runs them without AWS
$PY -m src.reddit.pipeline --mode hourly|weekly|seed
# API: /reddit/attention, /reddit/sentiment, /reddit/top-posts (src/api/reddit_routes.py)
INDICATORLAB_DATA_URI=data/reddit/processed .venv/bin/uvicorn src.api.main:app --port 8000
```

* **Shared scorer** (`src/sentiment/finbert_scorer.py`, built from James's `wiki_sentiment` classifier):
  ProsusAI/finbert at the revision pinned in `config.yaml` `sentiment`, all three probabilities kept, text =
  title + " " + body. A post naming several tracked stocks is scored per ticker on the sentences that name it.
* **Answer key** (`src/reddit/auto_label.py`, prompt `prompts/label_v1.txt`): Claude Opus labels every
  sampled (post, ticker) as positive / negative / neutral / skip with a one-line rationale, in the
  `label_server` file format. It is model-made, and the Haiku scorer shares its model family; the week 3
  report states both caveats. James's 50 blind labels (`sentiment_second_rater.csv`) give the kappa check.
* **Attention record** (`reddit_weekly.parquet`, `_by_type`, `reddit_top_posts`): the shared columns
  `ticker, market, source, week, value, baseline, ratio, spike, sentiment_pos/neg/neu, n_scored`.
  Research files stop before `holdout_start` (2026-11-01); `*_recent.parquet` hold later weeks for display only.
* The Week 2 routes (`src/api/reddit.py`: `/sentiment`, `/spikes`) were replaced by the `/reddit/*` router.

## Final week: Reddit for any stock, on demand (`src/reddit/on_demand.py`)

The any-stock dashboard (`POST /analyze`) asks for Reddit data about a ticker we may never have
collected. Two functions serve it, both taking the `ResolvedStock` dict from `src/resolve.py`:

| Function | Returns | Used for |
|---|---|---|
| `reddit_weekly_counts(stock)` | weekly post counts, 104 full weeks + the current partial week (`days_covered`) | Part 1: attention vs the 8-week baseline |
| `reddit_spike_posts(stock, week_monday)` | the week's top posts with FinBERT sentiment | Part 2: what people said in a spike week |

**Which subreddits.** The stock's company and market subreddits, our investing list `stocks, investing,
wallstreetbets, StockMarket, options, ValueInvesting`, and the India or HK list.

**How posts are found: saved posts first, keyword search as a backup.**
1. *Saved posts.* We already store every post of the 33 subreddits in config.yaml's US subreddit map
   (r/wallstreetbets, r/stocks, r/investing, sector and company subreddits): the research corpus up to
   Oct 31, 2026 (`data/reddit/processed/posts/<subreddit>.parquet`, or `processed/reddit_state/posts/` on
   S3), then the hourly job's `raw/reddit/date=YYYY-MM-DD/` files. For those subreddits the posts are
   matched locally, with no API call: two years of NVDA in r/nvidia, r/stocks, r/investing and
   r/wallstreetbets takes about a second on a laptop.
2. *Keyword backup.* The other subreddits (r/StockMarket, r/options, r/ValueInvesting, the India and HK
   lists) are not saved, so each search term (`$TICKER`, the ticker as a whole word, the short name, each
   alias) becomes an Arctic Shift `posts/search?subreddit=..&query=..` stream. Arctic Shift rations keyword
   search: on 2026-11-25 it answered 1 of 3 tries ("Timeout. Maybe slow down a bit") while plain listings
   always worked. So the backup gets a time limit (45 s for counts, 30 s for a spike week, 3 tries per
   request). A subreddit counts only if every one of its searches finished; otherwise it is listed in
   `coverage.skipped` and left out, so a week never mixes complete and half-fetched subreddits. Each
   search's progress is cached under `analyze/reddit_keyword/{subreddit}/{term}.json` and the next request
   continues from there, so a pre-warmed stock needs no keyword calls at all.

Arctic Shift requires a subreddit for `query`, refuses `limit=auto` with it, and treats `query` as plain
keywords (`A OR B` is not a boolean OR). The weekly `posts/search/aggregate` endpoint is not used: with
`query` it returned 0 in weeks where search found 100+ posts, and its buckets don't start on Monday
00:00 UTC (checked 2026-11-25).

**`coverage` (extra key on both results).** `saved` (subreddits read from saved posts), `searched`
(keyword backup finished), `skipped` (keyword backup failed or ran out of time: not in the counts),
`missing_days` (days after Oct 31 with no saved posts at all, so those weeks are too low), and for spike
posts `scores_refreshed`.

**Matching.** Saved posts and API hits are both checked locally with the same rules. The ticker must be a whole word in capitals (skipped when
it has at most 2 letters or is a common word like ON or NOW; `$TICKER` still counts). Names match as
whole words, any case. Hong Kong numeric codes are never searched as text, because "700" is a price;
those stocks are found by name and ADR alias. When `ambiguous_name` is true (Apple, Meta, Target,
Titan, ...), a post counts only if its title has the ticker or `$TICKER`, or the name sits within three
words of a finance word (stock, shares, earnings, calls, puts, buy, sell, price, market cap, guidance,
revenue, IPO, dividend). Posts are de-duplicated by Reddit id before counting.

**Tracked stocks** (in our stored US table) read `reddit_weekly.parquet` + `reddit_weekly_recent.parquet`
(from `INDICATORLAB_DATA_URI`). The weeks those tables lack are counted from the rows the table is built
from (`post_ticker_matches.parquet` up to Oct 31, the hourly job's `processed/reddit_hourly/` after), so the
whole series keeps the stored definition, where every post in a company's own subreddit counts. A stock
marked tracked that the table doesn't have (an India or HK list stock) is matched like any other stock.
Untracked counts are lower than tracked ones for the same stock because only posts that name it count.

**Caps:** the keyword backup fetches at most 20,000 posts per counts request and 1,000 per spike week;
hitting a cap sets `truncated: true` and that subreddit is skipped (its progress is kept for next time).
**Cache:** counts are cached for 6 hours under `analyze/reddit_counts/{market}/{TICKER}.json` with
`src/analyze/cache.py` (S3, or `INDICATORLAB_CACHE=local` for a laptop), or 30 minutes when a subreddit
was skipped; Part 2 is cached by the job runner.

**Spike-week posts.** Every matching post in the week (Mon 00:00 to the next Mon 00:00 UTC). Posts read
within hours of posting (the hourly files, keyword searches) still have a score near 0, so their score
and comment count are refreshed from Arctic Shift's `posts/ids` lookup (cheap, about 1 s per 100 posts)
before ranking by score, then comment count. The top `analyze.top_posts` (100) are scored with the shared FinBERT
scorer (same pinned revision, CPU, batch 16) on title + newline + body, dropping `[removed]` /
`[deleted]` bodies but keeping the title. The function returns probability means, `net = positive −
negative`, label counts, the 5 most positive and 5 most negative posts, and local ids `r1…r100` with
permalinks. Gemini only ever sees these ids.

**Caveats.**
* **Scores are a snapshot.** Arctic Shift stores a post's score and comment count from when it archived
  the post, so they can be lower than on Reddit today, and posts younger than about 36 hours can show 0 or 1.
  The "top posts" ranking uses these archived numbers.
* **The Nov 1–13 gap.** The hourly job's first run was 2026-11-13 04:24 UTC, so posts from Nov 1 until
  then are in neither the corpus nor the hourly files, and `coverage.missing_days` lists those days.
  `python -m src.reddit.backfill_hourly --start 2026-11-01 --end 2026-11-13T05:00` lists them from Arctic
  Shift (plain listing, saved to `data/reddit/backfill/` first); `--upload` then writes one
  `backfill.parquet` per day into `raw/reddit/` and `processed/reddit_hourly/`.
* **No level shift at Oct 31.** Day counts of both collections match Arctic Shift's own listing exactly
  (r/stocks on Oct 15, Oct 28, Nov 17 and Nov 20, checked 2026-11-25). November is busier because of the
  sell-off and NVDA's earnings, not because of the switch to hourly files.
* **Speed.** Reading two years of saved posts takes about 2.5 s per stock once the finished hourly days
  are in memory (they never change, so the process keeps them); the first cold read from a laptop took
  ~50 s. Then at most 45 s of keyword backup. Real runs: `logs/reddit/on_demand_real_runs_2026-11-25b.txt`.
* **Coverage outside the US.** Our saved subreddits are US ones. India and Hong Kong stocks get their
  mentions in r/wallstreetbets, r/stocks and r/investing from saved posts; their own subreddits depend on
  the keyword backup, so they appear in `coverage.skipped` whenever Arctic Shift refuses.
* **Keyword failures are never zeros.** A refused or unfinished keyword search leaves that subreddit
  out and lists it in `coverage.skipped`; the functions don't raise for it.

Tests: `pytest tests/test_reddit_on_demand.py` (saved posts written to a temp folder from
`tests/fixtures/reddit_on_demand/posts.json`, Arctic Shift mocked for the unsaved subreddits, FinBERT
mocked with fixed probabilities).

## Collection details

* **Endpoint:** `GET /api/posts/search?subreddit=<s>&after=<epoch>&before=<epoch>&limit=auto&sort=asc`.
  No `query=` parameter is used; ticker matching is done locally.
* **Pagination:** `limit=auto` returns ~100 posts per call, so each day is paged in ascending
  time order. The next page starts at `after = last_created_utc - 1`, re-covering the last
  second so posts with tied timestamps are not skipped; overlap is removed by post id. Paging
  ends when a page adds no new ids. If that final page is full (≥100 records) the day is marked
  `partial` because more posts than one page could share a single second.
* **Errors:** the API's "Timeout. Maybe slow down a bit" message arrives with HTTP 200 *or* 422
  and `data: null`; it, HTTP 429/5xx, timeouts and connection errors are retried with exponential
  backoff (2 s doubling, capped at 120 s, 8 attempts). A day that still fails is recorded as
  `failed` and is **never** treated as zero activity.
* **Completeness:** a subreddit-week counts only if all 7 UTC days are `complete`; the combined
  week needs all three subreddits. Incomplete weeks have empty metrics plus `*_observed` columns.
* **Scores:** `score` and `num_comments` come from Arctic Shift's archived snapshot (typically
  captured shortly after posting), not from live Reddit.

## Ticker matching

Three methods, strongest first, recorded per row: `cashtag` (`$AAPL`, case-insensitive),
`ticker` (upper-case whole word, plus GOOG for Alphabet) and `company_name` (curated aliases).
URLs are stripped first. Ambiguity rules: lower-case `meta` never counts, and capitalised `Meta`
counts only with company context (Meta's / Meta Platforms / a nearby stock word / Zuckerberg,
Facebook, Instagram, peer mega-caps, …). `AMD` must be upper-case. `Apple`, `Amazon` and
`Alphabet` must be capitalised, with exclusions such as Big Apple, Apple Hospitality, Amazon
rainforest and Nikola Tesla. "Chase" alone is not matched. See `src/match_tickers.py` and
`tests/test_matching.py`.

## Strategy Log

`src/backtest_strategies.py` turns the spike indicator into five weekly strategies on the 10
stocks: S1 spike momentum (long), S2 spike contrarian (short), S3 spiked-vs-universe (market
neutral), S4 attention-rank long/short (top 3 vs bottom 3 spike ratios) and S5 r/wallstreetbets
spike fade (short). B0, an equal-weight buy-and-hold, is the benchmark. To avoid look-ahead,
the signal from Reddit week s (ending Sunday 23:59 UTC, before the U.S. open) is traded from
the first open of week s+1 to the first open of week s+2. Net returns deduct 10 bps per unit of
turnover. **Every run appends every strategy to `results/strategy_logs/strategy_log.csv`, whatever
the outcome**; older runs are never overwritten. The Vibe-Trading Alpha101 runs are registered in
the same log as benchmarks. The verdict rule was fixed in advance: under 52 evaluation weeks is
"insufficient data"; net Sharpe ≥ 0.5 with t ≥ 2 is "promising (needs out-of-sample)"; Sharpe > 0
is "weak"; anything else is "failed". The dashboard's **Run 5 strategy tests** button does the
same thing as the command.

## Spike definition

`spike_ratio = metric_w / median(metric_{w-4..w-1})`, computed per ticker (and per subreddit in
the breakdown) and flagged when `≥ 2`. All four previous weeks must exist with complete coverage.
A zero or negative median makes the ratio undefined (NaN, not a spike); `*_zero_base_nonzero`
marks weeks that went from a zero baseline to non-zero activity.

## Reddit API (PRAW) setup — needs your action

Historical data comes from Arctic Shift. PRAW is prepared for collecting recent posts later:

1. Sign in to Reddit and open <https://www.reddit.com/prefs/apps>.
2. Click **create another app…**, choose type **script**, give it a name
   (e.g. `indicator-lab-reddit`), set *redirect uri* to `http://localhost:8080`, and create it.
3. The **client ID** is the string under the app name ("personal use script"); the
   **client secret** is labelled *secret*.
4. `cp .env.example .env` and fill in `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and a descriptive
   `REDDIT_USER_AGENT` such as `script:indicator-lab-reddit:v1.0 (by /u/<your_username>)`.
   Username and password are optional (read-only access does not need them).
   `.env` is git-ignored; never commit it.
5. Test it with `.venv/bin/python -m src.reddit.check_praw_connection`. It prints the 5 newest
   r/stocks titles, or exits 2 if credentials are missing. Secrets are never printed.

Make sure your use complies with Reddit's Data API terms (non-commercial research, respect rate limits).

## Vibe-Trading note

`vibe-trading` from `../Vibe-Trading/.venv` fails with `ModuleNotFoundError: No module named 'cli'`.
macOS has set the `hidden` flag on the venv's `.pth` files, and Python ≥ 3.11.8 skips hidden `.pth`
files, so the editable install is invisible. `src/run_vibe_trading.sh` uses the equivalent
`PYTHONPATH=agent .venv/bin/python -m cli alpha compare …`. A permanent fix (not applied) is
`chflags nohidden ../Vibe-Trading/.venv/lib/python3.11/site-packages/*.pth`.
