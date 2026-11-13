# Week 4 strategies (Joshua): rules written before any run

Status: **draft for Joshua's review. Nothing has been run.** Once approved, these rules go into the
Strategy Log as written; any later change is a new logged trial made from train results only.

Shared setup for all three:

| Item | Value |
|---|---|
| Universe | the 10 tracked US stocks (AAPL MSFT NVDA TSLA AMZN META GOOGL AMD NFLX JPM); India/HK attention is added when Jamal and Jack's subreddits are in the pull |
| Data | Reddit weekly tables (FinBERT sentiment, investor vs product subreddits), daily prices and volume (yfinance, adjusted) |
| Timing | week W = Mon-Sun UTC; signals use data through W only (past-only rolling windows); target weights start on the first trading day of W+1 |
| Train / test | 2016-06-01..2021-12-31 / 2022-01-01..2026-10-31 (`strategy.split`); test run once |
| Costs | 10 bps per unit of turnover (single stocks), 50 bps/yr borrow on shorts |
| Evaluation | at least 30 entries in train (else loosen on train only, logged as a new trial); 200 random-entry baselines with the same trade count, holding times and sizing; drop-one ablation; test Sharpe, max drawdown, random-baseline percentile, SPY Sharpe; deflated Sharpe over every trial ever logged (`deflated_sharpe_ratio`, Vibe `agent/src/quantlib/multipletesting.py`) |
| Keep rule | beats at least 90% of random runs in train **and** test, and beats SPY's Sharpe in test |

Shared indicator definitions (all per ticker, weekly, past-only):

- `att` = log((mentions_W + 1) / (median of mentions over W-8..W-1 + 1)), investor subreddits
- `att_prod` = same for the company's product subreddits
- `sent_dev` = FinBERT net sentiment (mean pos - neg) over W-3..W minus its mean over W-29..W-4
- `ret_1w` = close-to-close return of week W; `mom_12_1` = return from W-12 to W-1
- `abn_vol` = week W share volume / median weekly volume over W-20..W-1
- `mkt_att_z` = z-score of the cross-sectional mean of `att` against its own past 52 weeks

## S1. Attention-gated reversal

*Idea:* big one-week moves that come with a burst of retail attention tend to overshoot and partly reverse.

| Layer | Rule |
|---|---|
| Regime | full exposure while SPY closes above its 40-week average at the end of W, else 50% |
| Filter | only names in the top 30% of `att` this week **and** `abn_vol` > 1.5 |
| Entry | long the filtered names whose `ret_1w` is in the bottom third of the universe; short those in the top third; skip a long whose `sent_dev` < -0.15 (bad news, not overreaction) |
| Exit / risk | hold one week; per-name cap 25% of gross; gross 100%, net between -20% and +20%; halve exposure the week after `mkt_att_z` > 1.5 (**attention as a risk filter**) |
| Sizing | equal weight within each side |

Indicators: `att`, `ret_1w`, `abn_vol`, `sent_dev`, `mkt_att_z` (Reddit + price/volume).

## S2. Sentiment momentum, attention-capped

*Idea:* a lasting improvement in how investors talk about a stock, backed by price momentum, keeps paying
for a few weeks; crowded weeks are where it breaks.

| Layer | Rule |
|---|---|
| Regime | SPY above its 200-day average at the close of W: long-only book at 100%; below: 50% |
| Score | rank average of `sent_dev` and `mom_12_1` across the universe |
| Entry | long the top 3 by score, only if `att` > 0 (people are actually talking about it) and `n_scored` >= 20 posts in W |
| Exit / risk | hold up to 4 weeks; exit early when `sent_dev` turns negative or the name leaves the top 5; halve every position the week after `mkt_att_z` > 1.5 |
| Sizing | inverse 12-week volatility, capped at 40% per name |

Indicators: `sent_dev`, `mom_12_1`, `att`, `n_scored`, `mkt_att_z` (Reddit + price).

## S3. Product-buzz lead (Week 2 leftover, rebuilt)

*Idea:* customers get excited about a product (product subreddits) before investors do (investor
subreddits); buy when the product buzz is up and positive but investors have not caught on yet.

| Layer | Rule |
|---|---|
| Regime | SPY above its 200-day average: 100%; below: 50% |
| Signal | `att_prod` >= log(1.5) (product spike) **and** product-subreddit net sentiment > 0 |
| Confirmation | investor `att` < log(1.5) (no investor spike yet) **and** 20-day return below SPY's (not priced in) |
| Exit / risk | hold 4 weeks; exit early if investor `att` spikes and `ret_1w` > 10% (lead realised); max 4 names, 25% each |
| Sizing | equal weight |

Indicators: `att_prod`, product sentiment, `att`, 20-day relative return, `ret_1w` (Reddit + price).

## Candidate

Chosen after the train runs, from train numbers only: the strategy with the highest train Sharpe among
those that beat 90% of random runs in train, ties to the simpler one. Its write-up (rules, train Sharpe vs
random and SPY, test result, most important indicator from the ablation, deflated-Sharpe probability, why
it should hold in India and HK) goes in the sheet by Thu Nov 19, and it is re-run in Vibe-Trading
(`~/.vibe-trading/runs/<name>/`, `python -m backtest.runner`) to confirm the Sharpe within about 0.1.

## Questions for Joshua before the runs

1. Are these three the right ideas, or do you want to swap one?
2. S1 is long-short; the guide's borrow cost applies. Fine, or keep everything long-only?
