# Week 4 complex strategies: rules (James)

Written on 2026-11-18, before any of these were run. The S1–S4 reruns on the new window use their Week 3
rules unchanged (`week3_strategies.md`).

A strategy with fewer than 30 train entries is loosened, using train data only, in the order listed under
it. Each loosening is logged as a new trial. Rules never change after test results are seen.

## What changed since Week 3 (team decision, Nov 11)
- **Periods:** train 2016-06-01 to 2021-12-31 (unchanged); test 2022-01-01 to 2026-10-31.
  - Data from 2026-11-01 on (config `holdout_start`) is never loaded for research.
  - There is no separate holdout run: the test window is the final check.
- **Reruns:** Wiki Attention Breakout and S1–S3 are rerun with unchanged rules, and S4 has its first run.
  - Their Week 3 rows stay in the log, marked "pre-cutoff change".
  - Their Week 3 outputs are kept in `results/wikipedia/pre_cutoff_20251001/`.
- **Deflated Sharpe:** now computed with Vibe-Trading's `deflated_sharpe_ratio`
  (`agent/src/quantlib/multipletesting.py`), as the guide requires. It gives the same number as the Week 3
  formula (tested).
- **Trial count:** each distinct rule set counts once, so a rerun of the same rules on a longer window is
  not a new trial. The count includes:
  - the 20 Vibe factor strategies and Wiki Attention Breakout (21);
  - S1, S2, S3 and S3's 3 loosenings (6);
  - S4 and its loosenings;
  - S5–S7 and their loosenings.

## Common to S5–S7
Same as Week 3 unless stated:
- **Universe:** the 51 US stocks in `config.yaml`. Benchmark: SPY.
  - India and HK attention are added with the same rules once Jamal's and Jack's Wikipedia title maps are
    in config (due Nov 20); costs then come from B3, or Vibe's India engine until B3 lands.
- **Sources:**
  - Wikipedia: views, edits and edit-summary tags; FinBERT sentiment of the text added each week, from the
    shared scorer `src/sentiment/finbert_scorer.py` (pinned ProsusAI/finbert).
  - Price/volume: Yahoo daily OHLCV.
  - Reddit data starts in 2023, so it cannot be part of a strategy with a 2016–2021 train window.
- **Timing:** week W's data acts from the first trading day of W+1. Stops are seen at a close and traded
  at the next close.
- **Sizing:** inverse 63-day volatility, capped at 10% per stock, reset on each signal day, then
  multiplied by the regime and risk layers.
- **Regime (layer 1):** full size when SPY closes week W above its 200-day average; half size when below.
- **Costs:** 10 bps per unit of turnover.
- **Evaluation:** as in Week 3:
  - IC (train and test);
  - Sharpe, train / test, vs SPY;
  - 200 random-entry runs: must beat at least 90% in both periods;
  - drop-one ablation;
  - deflated Sharpe;
  - KEEP only if every pass mark is met.
- **Sentiment terms:**
  - `sentiment_net` (week W) = mean P(positive) − P(negative) over the sentences added to the article that
    week. At least 5 words per sentence and at most 60 sentences per stock-week.
  - `n_scored` = number of those sentences.
  - Sentiment change = `sentiment_net` minus the mean of the scored weeks among the previous 26 weeks; at
    least 8 scored weeks are needed (as in S4).
  - A week with no scored sentence has no sentiment value; it never counts as neutral.

## S5. Bad-news overreaction reversal
Hypothesis: a stock in a long-term uptrend that draws a burst of attention on negative news and falls
that week tends to overshoot, then partly recovers.

Indicators (5): SPY 200-day trend, abnormal views, `sentiment_net`, week-W abnormal return, the stock's
200-day trend. Sources: Wikipedia (views, FinBERT sentiment) and price.

- **Layer 1, regime:** the common SPY rule.
- **Layer 2, entry (weekly), all must hold for week W:**
  1. Abnormal views in the top 30% of the universe that week.
  2. `sentiment_net` < 0, with at least 2 sentences scored.
  3. Friday's close above the stock's 200-day average.
  4. Week-W return minus SPY's is below 0.

  Buy up to 5 qualifying stocks, those with the most negative week-W abnormal return.
- **Layer 3, exit (first that hits):** 2 weeks held; a 7% stop from the entry price (not trailing).
- **IC signal:** −(week-W abnormal return) among stocks meeting entry rules 1 and 2.
- **Loosening if under 30 train entries, in order:**
  - (a) at least 1 sentence scored instead of 2;
  - (b) abnormal views in the top 50% instead of 30%.

## S6. Positive-tone momentum, uncrowded
Hypothesis: 12-1 momentum lasts longer when the news flow written into the article is positive and the
stock is not yet drawing a crowd, and when no legal or layoff news is breaking.

Indicators (5): SPY 200-day trend, 12-1 momentum, 13-week sentiment level, views ratio (crowding),
legal/layoff edit tags. Sources: Wikipedia (views, edits, FinBERT sentiment) and price.

- **Sentiment level:** the mean `sentiment_net` over the scored weeks among weeks W−12 to W. At least 3
  scored weeks are needed.
- **Layer 1, regime:** the common SPY rule.
- **Layer 2, entry (first signal day of each month).** Rank by 12-1 momentum the stocks that meet all of:
  1. Sentiment level > 0.
  2. Views ratio < 1.5 in week W (not crowded).
  3. No `legal` or `layoff` edit-summary tag in weeks W−3 to W.

  Hold the top 10.
- **Layer 3, exit:**
  - At the monthly rebalance, sell any stock no longer in the top 10.
  - A 10% trailing stop at any time.
- **IC signal:** sentiment level against the next month's return.
- **Loosening if under 30 train entries:** (a) at least 2 scored weeks instead of 3.

## S7. Trend with attention-and-sentiment risk filters
This is the "attention as a risk filter" strategy. The entry is plain trend-following, so the ablation
shows directly what the attention and sentiment layers add.

Indicators (6): SPY 200-day trend, the stock's 200-day trend, 26-week return, stock bad-news flag
(views spike plus negative sentiment), market attention z-score, market sentiment shock. Sources:
Wikipedia (views, FinBERT sentiment) and price.

- **Layer 1, regime:** the common SPY rule.
- **Layer 2, entry (weekly):** hold every stock whose Friday close is above its 200-day average and whose
  26-week return is above 0.
- **Layer 3, stock risk filter (weekly):** exclude a stock for the next 4 weeks when, in week W:
  - its views spike (the shared spike rule); and
  - `sentiment_net` < 0 (at least 1 sentence scored).
- **Layer 4, market risk filter (weekly), exposure multipliers:**
  - **Market attention z:** the universe-mean abnormal views of week W, as a z-score against the previous
    52 weeks. If it is above 1.5, × 0.5 (S1's z part).
  - **Market sentiment shock:** the mean `sentiment_net` across scored stocks in week W, at least 10 stocks
    scored. If it is more than 1 standard deviation below its mean over the previous 26 weeks, × 0.5.
  - Both multipliers can apply, giving a minimum of 0.25.
- **Layer 5, exit:**
  - The weekly rule fails (close below the 200-day average, or the 26-week return ≤ 0).
  - The stock risk filter fires.
  - A 12% trailing stop.
- **IC signal:** 26-week return.
- **Loosening:** none needed. A weekly trend hold on 51 stocks gives far more than 30 entries.

## Candidate
The candidate is chosen on Nov 19 from **train** results only, among the strategies run in Week 4 (the
reruns, S4 and S5–S7):
1. Highest train Sharpe among those that beat at least 90% of random runs in train.
2. On a tie, the one with fewer indicators.

It is confirmed in Vibe-Trading (Sharpe within about 0.1 of ours) before nomination. Its test numbers are
reported, but they don't affect the choice.
