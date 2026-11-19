# Week 4 report: Wikipedia attention (James)

Draft, 2026-11-18. The sections on the API/dashboard, A3/A4 and open items are still to be written.

## Cutoff change and data
- **Cutoff:** team decision on Nov 11: `holdout_start: 2026-11-01` in `config.yaml`.
  - Train is unchanged: 2016-06-01 to 2021-12-31.
  - Test is now 2022-01-01 to 2026-10-31.
  - There is no separate holdout run.
- **Coverage:**
  - The Wikipedia research tables for all 51 US stocks end with the week of Oct 19–25, 2026. No research
    row is dated on or after Nov 1.
  - Edits have no gap through Oct 2026 (1,580–1,893 edits a quarter from 2025 Q3 to 2026 Q3).
  - FinBERT edit sentiment (shared scorer, pinned ProsusAI/finbert) is extended to Oct 2026: 7,138 scored
    sentences in 2026.
- **Raw caches are kept per cutoff.** New pulls go to folders named `<kind>_<period>_20261101`.
  - The Oct-2025 caches were only read, never changed.
  - The new diff cache was seeded from the old one, keeping only revision pairs that still match.
- **Week 3 outputs** are kept in `results/wikipedia/pre_cutoff_20251001/` (and the matching
  `data/processed` and `data/shared` folders).
- **Known limit:** the S&P 500 constituent list is still the one as of 2025-09-30. That data starts in
  Nov 2021, so it is test and display data only.

## Strategies
Rules:
- S1–S4: `week3_strategies.md`;
- S5–S7: `week4_strategies.md`, approved on 2026-11-18 before any run.

No rule changed after test results were seen. Every row has:
- 10 bps costs;
- 200 random-entry runs;
- the drop-one ablation;
- the deflated Sharpe, now from Vibe-Trading's `deflated_sharpe_ratio`, with 31 trials:
  - the 20 Vibe factor strategies and Wiki Attention Breakout;
  - S1, S2, S3 and its 3 loosenings;
  - S4, S5, S6 and S7.

**Reruns reproduce the train period exactly.** S1–S3 have the same train trades, Sharpe, IC and
random-run percentile as in Week 3. Only test numbers changed.

The Wiki Attention Breakout's train random percentile moved from 5.5% to 4.0%, although its train
Sharpe is the same. Its random portfolios draw a stock for every trade in one sequence, so the extra
test-period trades change the train draws. It is far below 90% either way.

SPY Sharpe is 1.00 in train and 0.72 in test.

| Strategy | Train Sharpe | Test Sharpe | Random beaten, train / test | IC train / test | DSR | Decision |
|---|---|---|---|---|---|---|
| Wiki Attention Breakout | -0.24 | 1.47 | 4% / 99.5% | – | – | Keep on watch (Week 2 rule) |
| S1 Attention-gated momentum | 1.12 | 0.50 | 26% / 0.5% | 0.004 / 0.026 | 0.34 | DROP |
| S2 Attention reversal | 0.91 | 0.17 | 71% / 41.5% | -0.001 / -0.019 | 0.13 | DROP |
| S3 News-tagged breakout (loosen 2 = 3) | 0.56 | 1.04 | 67% / 97% | 0.008 / 0.006 | 0.79 | DROP (13 train entries) |
| S4 Sentiment-confirmed attention | 0.60 | 0.25 | 20% / 23% | -0.004 / -0.012 | 0.17 | DROP |
| S5 Bad-news overreaction reversal | 0.31 | 0.12 | 15% / 32% | -0.006 / -0.037 | 0.11 | DROP |
| S6 Positive-tone momentum, uncrowded | 1.32 | 0.87 | 64% / 29.5% | 0.011 / -0.002 | 0.65 | DROP |
| S7 Trend with attention/sentiment risk filters | 1.32 | 0.82 | 93.5% / 4% | 0.004 / 0.006 | 0.61 | DROP |

None meets every KEEP mark.

**Sentiment adds nothing, in the drop-one runs or the IC.**
- Removing the sentiment filter *raises* S5's train Sharpe from 0.31 to 0.88.
- S6's sentiment level helps in train (1.10 without it, against 1.32) but not in test (0.93 without it,
  against 0.87).
- Every sentiment IC is within ±0.04 of zero.

This agrees with the Week 2 result that weekly edit sentiment had no detectable link with returns.

All results and the Strategy Log rows are in `results/wikipedia/`:
- `week4_strategy_log_us.csv`;
- `week4_drop_one_us.csv`;
- `week4_strategy_log_rows.tsv`, where old rows are marked "pre-cutoff change".

### Candidate: S7, trend with attention/sentiment risk filters
The rule, written before the runs: the highest train Sharpe among the Week 4 strategies that beat at
least 90% of random runs in train.

S7 is the only one that qualifies with at least 30 train entries: train Sharpe 1.32, beating 93.5% of
random runs. S3 loosen 1 also beat 91%, but it had 6 entries and a lower Sharpe (0.88).

**Vibe-Trading check.** Run dir `~/.vibe-trading/runs/indicatorlab_wiki_s7_us`, run with
`python -m backtest.runner`:
- Vibe gives a Sharpe of 1.29 in train and 0.81 in test, against our 1.32 and 0.82.
- Daily returns correlate at 0.94 in both periods.
- That is well within the 0.1 tolerance.

What the team should know before the Nov 21 pick:
- **Its edge is trend-following, not Wikipedia.** In the train drop-one runs, removing the attention or
  sentiment layers leaves the Sharpe level or raises it:
  - without the stock risk filter (views spike plus negative tone): 1.33;
  - without the market attention z-score: 1.36;
  - without the market sentiment shock: 1.43.
- **Its test result is weak against chance.** The test Sharpe (0.82) beats SPY (0.72), but only 4% of
  the random-entry runs. The random-run median is 1.07, because almost any long-only timing did well in
  2022–2026. The deflated Sharpe is 0.61 after 31 trials. So it is a DROP under the KEEP rule.
- The test numbers are reported but did not affect the choice.

Of these strategies, S7 has the best train evidence. But that evidence does not show that the
Wikipedia layers add anything. If the team wants a candidate whose edge comes from attention, none of
James's strategies has shown one.
