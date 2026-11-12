# Week 3 complex strategies: checklist against the task guide (James)

Checked on 2026-11-11 against "Indicator Lab — Week 3 Task Guide", Strategy Log section (pages 21-24).
Rules: `docs/wikipedia/week3_strategies.md`. Results: section 4 of `docs/wikipedia/week3_report.md`.
Code: `src/wiki_complex.py`.

## Requirement by requirement

| # | Guide requirement | Status | Evidence |
|---|---|---|---|
| 1 | At least 3 complex strategies | Done | S1 attention-gated momentum, S2 attention reversal, S3 news-tagged breakout |
| 2 | At least 4 indicators from at least 2 sources | Done | 5, 5 and 6 indicators. Sources: Wikipedia (views, edits, reverts, edit tags) and Yahoo price/volume. |
| 3 | At least 3 layers: regime, entry, exit/risk | Done | Each has the SPY 200-day regime, an entry layer and an exit/risk layer; S1 also has the attention gate. |
| 3a | Entry = "stock selection from attention + sentiment" | **Missing** | No sentiment in any entry layer. S2 and S3 select on attention; S1 selects on momentum. |
| 4 | At least one strategy uses attention as a risk filter | Done | S1 runs at half size after market-wide attention or edit-burst spikes. |
| 5 | US plus your own market | **Half done** | US done. India waits on Jamal's `config/india_wiki_titles.csv`. |
| 6 | Rules written in the sheet before the first run | **Half done** | Written to `week3_strategies.md` before the run, but not yet in the team sheet or committed. |
| 7 | Never change a rule after seeing test results | Done | Rules unchanged. Drop-one findings are reported as diagnostics only. |
| 8 | At least 30 train entries, else loosen on train only, each loosening logged as a new trial | Done | S1 has 320 and S2 has 686. S3 used all 3 loosening steps (13 entries) and is logged as DROP. |
| 9 | Costs: 10 bps per unit of turnover (US); Vibe engine costs for India/HK | Done for US | 10 bps; Vibe cross-check uses `slippage_us: 0.001`. |
| 10 | Sizing: inverse 63-day volatility, 10% cap, scaled by layers; week W trades at the start of W+1 | Done | Tested in `tests/test_wiki_complex.py`. |
| 11 | IC | Done | Reported for train and test. |
| 12 | Sharpe train / test vs the index | Done | "train / test" column in `results/wikipedia/week3_strategy_log_us.csv` |
| 13 | 200 random-entry-timing runs; KEEP needs ≥ 90% in both periods | Done | Same stocks, weights and holding lengths; seed 42; deterministic |
| 14 | Drop-one ablation | Done | `results/wikipedia/week3_drop_one_us.csv` |
| 15 | Deflated Sharpe counting every trial | Done | 27 trials: 20 Vibe factor strategies, Wiki Attention Breakout, and 6 runs here |
| 16 | KEEP/DROP with the reason logged | Done | All DROP; reasons in the log and the report |
| 17 | Report the trade count, eval table, drop-one, and US vs second market side by side | **Half done** | US only so far |

Not required by the guide: strategies built inside Vibe-Trading. As an extra check, all three also ran
through Vibe's backtest runner (`~/.vibe-trading/runs/indicatorlab_wiki_*_us/`). Its daily returns
correlate 0.93-0.99 with ours, and no decision changes.

## Results (US)

SPY Sharpe: train 1.00, test 0.66.

| Strategy | Entries train / test | Sharpe train / test | % random beaten train / test | Deflated Sharpe | Decision |
|---|---|---|---|---|---|
| S1 Attention-gated momentum | 320 / 226 | 1.12 / 0.25 | 26% / 0.5% | 0.17 | DROP |
| S2 Attention reversal | 686 / 458 | 0.91 / -0.25 | 71% / 18.5% | 0.03 | DROP |
| S3 News-tagged breakout (fully loosened) | 13 / 14 | 0.56 / 0.92 | 67% / 82.5% | 0.64 | DROP (under 30 entries) |

## To do

- [ ] Paste the rules from `week3_strategies.md` and the rows from `week3_strategy_log_us.csv` into the
      team sheet.
- [ ] Commit `week3_strategies.md` on its own, before the results commit.
- [ ] Write and pre-register a 4th strategy with sentiment in its entry layer, without changing S1-S3.
      Options:
      - FinBERT edit sentiment, which covers only the 10 tracked stocks, so 30 entries may be hard;
      - Joshua's Reddit sentiment, once his tables are available.
- [ ] Run the second market (India) once Jamal's title map exists, with Vibe's `india_equity` costs, and
      add the US vs India table.
