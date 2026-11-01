# Research summary — Can Reddit chatter predict stock returns?

> **Week 2 note.** The Week 1 strategy backtests below used weeks through Sep 2026. From Week 2 the
> holdout starts Oct 1, 2025, so those results used holdout data and are kept only as a record.
> They are not valid research results under the new rules. Links to `results/` and `data/` point to
> local, git-ignored files.

*Indicator Lab (Advanced), Reddit component. Data through 2026-10-18 (UTC). All numbers below come
from executed scripts in this repository. The tables they come from are linked in each section.*

## Bottom line

* **Reddit chatter tracks events but does not predict returns among these 10 mega-caps.**
  Chatter spikes line up with earnings, product launches and big news. Trading on them did not beat
  simply holding the 10 stocks. The one profitable spike strategy (S1, buy spiked stocks) made the
  same return as buy-and-hold at a lower Sharpe. Its market-neutral version (S3), which isolates
  stock-picking skill, has Sharpe 0.25 (t = 0.48).
* **Apple's September launches reliably produce a 2× post spike** (3/3 years). The launches are
  scheduled in advance, so the spike carries no information the market doesn't already have, and the
  next-week returns (−0.1%, +2.6%, +4.9%) are three data points, not evidence.
* **Ticker matching is accurate enough to use:** agent-reviewed false-positive rate **8%** (4/50;
  10% if the one uncertain post counts as wrong). This still needs human verification.

## 1. Data coverage

| | r/stocks | r/investing | r/wallstreetbets |
|---|---|---|---|
| Days requested (2023-01-01 → 2026-10-18) | 1,387 | 1,387 | 1,387 |
| Days complete / partial / failed | 1,387 / 0 / 0 | 1,387 / 0 / 0 | 1,387 / 0 / 0 |
| Submissions archived | 138,154 | 125,804 | 493,388 |
| Earliest available post (verified) | 2008-06-27 08:49 UTC (`6p7r3`) | 2008-03-15 12:21 UTC (`6c6hw`) | 2012-04-11 16:40 UTC (`s4jw1`) |

* **757,346 unique submissions** in total, collected with about 14,100 paginated Arctic Shift requests
  (`limit=auto` returns about 100 posts, so busy r/wallstreetbets days needed up to 17 pages).
* **Independent check:** a `sort=desc` re-request for 30 random days found **0 posts missing** from
  the archive ([collection_spotcheck.csv](data/validation/collection_spotcheck.csv)).
* **QA:** 23/23 checks pass ([qa_report.md](results/tables/qa_report.md)), and 28 unit tests pass.
* The r/stocks June 2008 history claim is confirmed independently.
* Every week is complete except the first (2022-12-26), which contains only one in-range day. It is
  left empty rather than reported as zero.

### Data-quality findings (important for interpretation)

1. **Most archived posts were removed.** Across all quarters, 47–84% of submissions carry
   `removed_by_category` (mostly moderator removals). Among posts matching our tickers the share is
   lower: 74.5% were still visible. The headline `posts` metric counts all submissions, and a
   robustness metric `posts_visible` excludes removed ones. The two spike flags agree 96% of the time
   (ratio correlation 0.91).
2. **Archive timing changed in mid-2023.** Arctic Shift captured 2023-Q1/Q2 posts weeks to months
   after posting. From 2023-Q3 it captures within seconds, with a second capture about 1.5 days later
   (`_meta.retrieved_2nd_on`) that updates score and comment counts. Upvote and comment totals from
   early 2023 are therefore higher than later ones. Spike ratios compare only with the previous 4
   weeks, so this mostly affects the Q2→Q3 2023 transition.
3. **Volume drops from July 2026.** Daily post counts fall by about half from July 2026 (r/stocks
   about 105/day → about 45/day by September; r/investing about 70 → about 25). The data cannot tell
   whether this is a real decline in activity or an archive ingestion gap. Checking it against the
   live Reddit API (PRAW) needs credentials.
4. **Scores are snapshots.** `score` is Arctic Shift's archived value, not the current Reddit score.

## 2. Ticker matching and validation

* **Matching:** title + selftext, URLs stripped. Three methods are recorded per row (cashtag, upper-case
  ticker, curated company names), with ambiguity rules for META, AMD, Apple, Amazon and Alphabet.
* **Results:** 95,710 post×ticker rows from 71,538 posts. 44,040 matched only in the body, so body
  search matters. NVDA (25,771 posts) and TSLA (18,016) dominate; JPM (2,420) is the smallest.
  Source: [match_method_summary.csv](results/tables/match_method_summary.csv).
* **Validation:** 50 posts drawn with seed 42, stratified across all tickers, subreddits and methods,
  with 6 extra ambiguous capitalised "Meta" and 4 extra Apple/Amazon/Alphabet matches. File:
  [ticker_validation_50.csv](data/validation/ticker_validation_50.csv).

| | n | correct | incorrect | uncertain |
|---|---|---|---|---|
| cashtag | 10 | 10 | 0 | 0 |
| ticker | 10 | 9 | 1 | 0 |
| company name | 30 | 26 | 3 | 1 |
| **total** | **50** | **45** | **4** | **1** |

**False positive rate = 4 / 50 = 8%** (10% counting the uncertain post).

* **Who reviewed:** Claude (AI agent). The `human_label` column is empty for you to fill in.
* **What went wrong:** all errors are the company name used as a *tool, fund issuer or research
  source* rather than the subject: Google Finance, a "JPM US Small Cap Growth ETF" holding, a JP Morgan
  analyst report on another company, and Amazon's review pages.
* **META held up:** all 10 META samples were correct, including 7 ambiguous capitalised "Meta" matches.
* **Caveat:** the sample is stratified (ambiguous names oversampled), so 8% describes this sample,
  not the whole population.

## 3. Weekly chatter and spikes

* **Weeks** start Monday 00:00 UTC. `spike_ratio = week / median(previous 4 weeks)`, and a spike is
  flagged at ≥ 2. All 4 baseline weeks must be complete, and a zero baseline means no ratio.
* **Outputs:** [reddit_weekly.csv](data/processed/reddit_weekly.csv) (10 rows/week, 1,990 rows) and
  [reddit_weekly_by_subreddit.csv](data/processed/reddit_weekly_by_subreddit.csv).
* **Spike counts:** 1,053 combined-level spikes, of which 1,022 meet a ≥ 5 posts/week baseline
  (posts 191, comments 335, upvotes 496). Upvote spikes are the most extreme (NFLX up to 118×)
  because a single viral post dominates the weekly sum.
* **Most significant post-count spikes**
  ([top_post_spikes.csv](results/tables/top_post_spikes.csv); context is my reading of the calendar,
  not verified by this pipeline):

| # | Week of | Ticker | Posts | 4-wk median | Ratio | Coincides with |
|---|---|---|---|---|---|---|
| 1 | 2023-05-22 | NVDA | 408 | 20.5 | 19.9× | Nvidia's May-2023 earnings blowout |
| 2 | 2025-10-06 | AMD | 206 | 16.0 | 12.9× | AMD–OpenAI chip deal announcement |
| 3 | 2024-11-11 | NFLX | 94 | 9.0 | 10.4× | (likely the live-streamed Paul–Tyson fight) |
| 4 | 2025-01-20 | NFLX | 58 | 7.0 | 8.3× | Netflix Q4-2024 earnings |
| 5 | 2024-01-22 | NFLX | 93 | 12.0 | 7.8× | Netflix Q4-2023 earnings |
| 6 | 2025-07-21 | AMZN | 239 | 32.0 | 7.5× | — |
| 7 | 2023-01-30 | META | 138 | 19.0 | 7.3× | Meta Q4-2022 earnings (+23% day) |

## 4. Apple September event study

Event dates come from Apple's own pages (developer.apple.com news invitations and Apple Newsroom
press releases; URLs in [apple_events.csv](data/validation/apple_events.csv)). Weekly return =
last adjusted close of the Mon–Sun week ÷ previous week's − 1 (yfinance, split- and dividend-adjusted;
the last trading day is used when Friday is a holiday). Reddit weeks start Monday 00:00 UTC = Sunday
evening in New York, so every U.S. session falls inside one Reddit week. Full table:
[apple_event_study.csv](results/tables/apple_event_study.csv).

| Event | Week of | AAPL posts | 4-wk median | Ratio | 2× spike? | Visible-only ratio | Comments ratio | Event-week return | Next-week return |
|---|---|---|---|---|---|---|---|---|---|
| Wonderlust (2023-09-12) | 2023-09-11 | 76 | 29.5 | 2.58× | yes | 2.60× | 3.46× | −1.78% | −0.13% |
| It's Glowtime (2024-09-09) | 2024-09-09 | 73 | 29.0 | 2.52× | yes | 2.22× | 2.61× | +0.76% | +2.56% |
| Awe dropping (2025-09-09) | 2025-09-08 | 51 | 24.5 | 2.08× | yes | 1.30× | 2.81× | −2.34% | +4.88% |

1. **Did chatter spike?** Yes, all three years on posts, comments and upvotes. Part of the ratio comes
   from quiet late-August baselines, and Apple's late-July/early-August earnings weeks spike about as
   much. The 2025 post spike disappears when moderator-removed posts are excluded (1.30×); its
   comment spike (2.81×) remains.
2. **Event-week returns:** negative in 2023 and 2025, positive in 2024 (average −1.1%).
3. **Following week:** −0.13%, +2.56%, +4.88% (two of three positive).
4. **Predictive value:** none can be claimed. n = 3, and the spike is caused by a *scheduled*
   event the market already knows about, so it is correlation with a known catalyst, not a predictive
   signal. Across all 198 weeks, AAPL post volume and next-week return are uncorrelated (r = 0.0004).
   The 17 AAPL post-spike weeks were followed by a +0.94% average return versus +0.53% otherwise, a
   gap well within noise for n = 17.

Charts: [aapl_chatter_vs_price.png](results/charts/aapl_chatter_vs_price.png) and
[aapl_event_windows.png](results/charts/aapl_event_windows.png). Chart data:
[aapl_chart_data.csv](results/tables/aapl_chart_data.csv).

## 5. Strategy Log — five Reddit-indicator strategies (all results kept)

* **Method:** signal from Reddit week *s* → enter at the first adjusted open of week *s+1* → exit at
  the first open of week *s+2* (no look-ahead). Net of 10 bps per unit of turnover.
* **Sample:** 192 evaluation weeks, signal weeks 2023-01-30 → 2026-09-28.
* **Log:** append-only [strategy_log.csv](results/strategy_logs/strategy_log.csv) /
  [.md](results/strategy_logs/strategy_log.md). It also keeps the earlier partial-data runs.

| | Strategy | Total net | Ann. net | Sharpe (net) | t | Max DD | Logged verdict |
|---|---|---|---|---|---|---|---|
| S1 | spike momentum (long spiked) | +286.2% | +44.2% | 1.31 | 2.52 | −29.6% | PROMISING* |
| S2 | spike contrarian (short spiked) | −88.1% | −43.8% | −1.63 | −3.14 | −90.1% | FAILED |
| S3 | spiked minus 10-stock basket | +12.5% | +3.2% | 0.25 | 0.48 | −32.1% | WEAK |
| S4 | top-3 vs bottom-3 spike ratio | −16.9% | −4.9% | −0.25 | −0.48 | −27.7% | FAILED |
| S5 | short r/wallstreetbets spikes | −88.5% | −44.3% | −1.77 | −3.40 | −90.5% | FAILED |
| B0 | equal-weight buy-and-hold | +287.4% | +44.3% | 1.55 | 2.99 | −27.9% | benchmark |

\*S1 passes the rule fixed before the run (Sharpe ≥ 0.5, t ≥ 2). That rule did not include a benchmark
comparison. Against buy-and-hold, S1 adds −0.1%/yr at higher volatility (31.7% vs 25.8%), so it is
market exposure, not skill. **Benchmark-adjusted assessment: drop all five.** The logged verdict is
left unchanged, because editing it after seeing results would defeat the point of an append-only log.
The team sheet is [strategy_sheet.csv](results/strategy_logs/strategy_sheet.csv).

## 6. Vibe-Trading Alpha101 benchmarks (separate exercise, not Reddit signals)

The command was `vibe-trading alpha compare alpha101_002 alpha101_003 alpha101_006 alpha101_012
alpha101_013 --universe sp500 --period 2021-2024`, executed with exit code 0. The full log is
[alpha_compare_20261018T181427Z.log](results/strategy_logs/alpha_compare_20261018T181427Z.log).

| Rank | Alpha | IC mean | IC std | IR | IC > 0 | Days |
|---|---|---|---|---|---|---|
| 1 | alpha101_012 | 0.0056 | 0.0870 | 0.0647 | 51.2% | 1,003 |
| 2 | alpha101_002 | 0.0028 | 0.0659 | 0.0428 | 51.3% | 997 |
| 3 | alpha101_013 | 0.0014 | 0.0674 | 0.0205 | 50.7% | 1,000 |
| 4 | alpha101_003 | 0.0003 | 0.0626 | 0.0053 | 48.9% | 995 |
| 5 | alpha101_006 | −0.0009 | 0.1125 | −0.0081 | 49.4% | 995 |

* **What IC means here:** the daily cross-sectional Spearman rank correlation with next-day
  close-to-close return. The tool does **not** report Sharpe, cumulative return or drawdown, so none
  are reported here.
* **Data:** the universe uses current constituents (the tool warns that this is survivorship-biased),
  and 5 tickers failed to download.
* **Verdict:** all five are effectively zero.

## 7. Limitations

* **Universe:** 10 mega-caps only. Retail attention effects are more plausible in small caps.
* **Period:** 2023–2026 was a strong mega-cap bull market, which flatters long-only strategies and
  punishes shorts.
* **Multiple testing:** five Reddit strategies plus five alphas were tested, so one "significant"
  result is expected by chance.
* **Archive artefacts:** moderator removals, the 2023 archive-timing change and the July-2026 volume
  drop (§1).
* **Validation:** agent-reviewed only so far; human review is pending.
* **Price data:** yfinance adjusted prices; no borrow costs for shorts.
* **Data access:** the Reddit API (PRAW) is set up but untested without credentials.
