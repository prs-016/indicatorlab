# Week 4 report (Joshua) — in progress

Last updated 2026-11-13. Cutoff: research data before `holdout_start: 2026-11-01`; team split train
2016-06-01..2021-12-31, test 2022-01-01..2026-10-31 (`config.yaml`).

## Still open from Weeks 1-3 (first, per the guide)

| Item | Status 2026-11-13 |
|---|---|
| Human label check (120 items, both kappas, scorers graded both ways) | Sample drawn (`human120_sample.csv`: 11 years x investor/product, 30 overlap, 100 reused from the Week 3 sample). Labelling Mon-Tue; Opus labels (~$3.91) after `ANTHROPIC_API_KEY` is set |
| 100 match-precision checks (Week 2) | Sample ready; labelling page task `match` |
| FinBERT rescore of the corpus | Running again (resumed 2026-11-13); 15 of 33 subreddits done |
| Weekly tables + `week3_report.md` | After the rescore and the label check |
| Shared AWS stack | **Done** (us-east-2): bucket `indicatorlab-data`, live tables, $20 budget |
| Reddit pipeline on AWS | Image build/push and `sam deploy` in progress |
| Design issue A0 | Text ready (`docs/upstream/sentiment_attention_issue.md`); TODOs: James's A3 part, Reddit terms; FinBERT weights are CC BY-NC-SA 4.0 |
| A1 FinBERT PR | Branch ready (`feat/sentiment-finbert-scorer`); PR text `docs/upstream/A1_finbert_pr.md`; comparison table after the labels |
| Strategies | Rules drafted (`docs/reddit/week4_strategies.md`), awaiting review; runs need the backfill |
| PR #4 merge | Waiting on Prakhar |

## Week 4 work

| Task | Status |
|---|---|
| Cutoff to 2026-11-01, team split, hardcoded dates removed | Done; tests 435 passed, 66 skipped |
| Reddit backfill 2016-06..2022-12 (33 subreddits) | Running: 7 investor subreddits first (about 65 s per day of data, so about 43 h, done around Sun Nov 15), then the 26 product subreddits. Arctic Shift is answering many requests with "Timeout. Maybe slow down", so the pace is 2 s between requests |
| A2 Reddit attention loader | Branch `feat/reddit-attention-loader` (stacked on A1), 7 new tests; PR text `docs/upstream/A2_reddit_loader_pr.md` |
| B4 parallel runner | Schema `docs/upstream/B4_output_schema.md`; draft branch `feat/alpha-bench-parallel-universes` (worktree `vibe-trading-b4`), 36 related tests pass |
| India/HK subreddits in the hourly pull | Waiting for Jamal's and Jack's subreddit and ticker lists |
