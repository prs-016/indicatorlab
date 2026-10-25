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
