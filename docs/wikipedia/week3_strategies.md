# Week 3 complex strategies: rules (James)

Written on 2026-11-11, before any of these were run. Per the guide, rules never change after the test
results are seen. A strategy with fewer than 30 train entries is loosened using train data only, in the
order listed under it, and each loosening is logged as a new trial.

## Common to all three
- **Universe:** the 51 US stocks in `config.yaml` (10 tracked + 41 strategy universe). Benchmark: SPY.
  India follows once Jamal's `config/india_wiki_titles.csv` exists; costs then come from Vibe's
  `india_equity` engine.
- **Data sources:**
  - Wikipedia: weekly page views, edits, reverts and edit-summary tags (shared weekly table).
  - Price/volume: Yahoo daily adjusted OHLCV.
- **Periods:** the team split, train 2016-06-01 to 2021-12-31 and test 2022-01-01 to 2025-09-30. No data
  from 2025-10-01 on is loaded.
- **Timing:**
  - Week W runs Monday to Sunday. Its Wikipedia values and its last close (Friday) are known by Monday.
  - Signals from week W trade at the close of the first trading day of week W+1. Wikimedia publishes a
    day's views the next day, so this respects the guide's 1-day publication lag.
  - Daily exits (stops) are seen at a close and traded at the next day's close.
- **Sizing:**
  - Each held stock gets weight min(10%, (1/vol) / sum of (1/vol) over held stocks), where vol is its
    63-day daily return volatility. The rest stays in cash.
  - Weights are reset on every signal day and held fixed between signal days.
  - The total is then multiplied by the regime and gate layers.
- **Regime (every strategy):** full size when SPY's last close of week W is above its 200-day average;
  half size when below.
- **Costs:** 10 bps per unit of turnover (the sum of absolute weight changes).
- **Full evaluation (the guide's table):**
  - **IC:** Spearman rank correlation of each strategy's signal with next-period returns, averaged over
    signal dates; reported for train and test.
  - **Sharpe:** train and test after costs, compared with SPY. To keep, it must beat SPY's Sharpe in test.
  - **Random baseline:** 200 runs with random entry timing. Each run keeps every trade's stock, weight and
    holding length, but draws a new entry date within the same period. To keep, the strategy must beat at
    least 90% of the runs in both train and test.
  - **Drop-one:** rerun with each indicator removed in turn. An indicator that changes nothing is cut.
  - **Deflated Sharpe** (Bailey and López de Prado), counting every trial so far:
    - the 20 Vibe factor strategies;
    - Wiki Attention Breakout;
    - these 3 strategies and any loosened versions.

    The variance of trial Sharpes comes from the strategy and drop-one runs on the same period.
  - **Decision:** KEEP only if every pass mark is met; otherwise DROP, with the reason logged.

## S1. Attention-gated momentum (attention as a risk filter)
Indicators (5): SPY 200-day trend, market attention z-score, edit-burst breadth, 12-1 momentum, 50-day trend.
- **Layer 1, regime:** the common SPY rule.
- **Layer 2, attention gate (market level, weekly):** half size for week W+1 if either holds.
  - The market attention z-score is above 1.5. Market attention is the mean across stocks of week W's
    abnormal views, log((views + 1) / (8-week median + 1)). Its z-score is against the 52 weeks before W.
  - Edit-burst breadth is above the 90th percentile of all earlier weeks (at least 52 needed). Breadth is
    the share of stocks with edits at least 2x their 8-week median.

  Undefined values (too little history) leave the gate open.
- **Layer 3, entry (monthly):** on the first signal day of each month, rank stocks above their 50-day
  average by 12-1 momentum (close 21 trading days ago / close 252 days ago - 1). Hold the top 10.
- **Layer 4, exit:**
  - At the monthly rebalance, sell names that left the top 10 or closed below their 50-day average.
  - A 10% trailing stop from the highest close since entry, checked daily.
  - A stopped-out stock may come back only at the next monthly rebalance.
- **IC signal:** 12-1 momentum against the next month's return.
- **Loosening if under 30 train entries:** not expected (10 names a month).

## S2. Attention reversal
Indicators (5): abnormal views, last week's abnormal return, revert share, volume ratio, SPY 200-day trend.
- **Layer 1, regime:** the common SPY rule.
- **Layer 2, entry (weekly), among stocks in the top 30% of week W's abnormal views:**
  - Keep only those whose revert share is at most 50% (reverts / edits in week W; 0 when there were no
    edits) and whose volume ratio is at least 1.3. The volume ratio is week W's mean daily volume over the
    mean daily volume of the 50 trading days before week W.
  - Buy the 5 with the lowest abnormal return in week W (stock return minus SPY return).
- **Layer 3, exit:** after one week (at the next signal day), or a close 6% below entry.
- **IC signal:** minus week W's abnormal return, among the top 30% of abnormal views, against week W+1's
  return.
- **Loosening if under 30 train entries:** (a) volume ratio at least 1.0; (b) drop the volume filter.

## S3. News-tagged breakout
Indicators (6): views spike, edit burst, news tags, 20-day breakout, volume ratio, SPY 200-day trend.
- **Layer 1, regime:** the common SPY rule.
- **Layer 2, entry (weekly), all must hold for week W:**
  1. A views spike (the shared spike rule).
  2. An edit burst: edits at least 2x their 8-week median.
  3. News tags: at least one earnings or product-launch tag in week W's edit summaries, and no legal or
     layoff tag.
  4. Friday's close is the highest of the last 20 closes.
  5. Volume ratio (as in S2) at least 1.5.
- **Layer 3, exit (first that hits):**
  - Views at or below their baseline (ratio of 1 or less) for 2 weeks in a row after entry.
  - An 8% trailing stop.
  - 6 weeks held.
- **IC signal:** abnormal views of week W against week W+1's return.
- **Loosening if under 30 train entries, in order:**
  - (a) drop the volume condition;
  - (b) also accept a 50-day-average trend instead of the 20-day high;
  - (c) also accept a views ratio of at least 1.5 instead of a full spike.
