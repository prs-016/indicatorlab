# Jack Week 4 checklist and results

**November 18 addition:** the local [HK live frontend](../frontend/live_markets/README.md)
and read-only `/live/hk` adapter are implemented. It displays the existing
95-stock snapshot with five-second refresh, exchange/session times and explicit
freshness/error states. [Scope and files](HK_LIVE_DASHBOARD.md). AWS, the full
team dashboard/API and remote publishing remain separate pending work.

Reviewed locally on November 15, 2026 against the Week 4 guide, particularly
pages 10–15 and 19–23. This report distinguishes local deliverables from external
completion. AWS is deferred at the user's request; Jack handles GitHub publishing.

## Earlier work and outstanding external steps

Week 1–3 source/data/results remain preserved. The original clean checkout's
34 preregistered source/input hashes still match. Week 4 intentionally changes
active Jack configuration; pre-change copies are also saved in
`data/hk_week4/preserved_pre_week4_sources/`. Older tests ended September 2025 and
are not relabeled as this longer evaluation.

The shared-sheet rules were not posted before local testing. Timestamped local
rules/protocols and a sheet-ready export exist; they cannot retroactively prove
shared-sheet preregistration. Upstream PRs, posted issues, team messages and
AWS/API acceptance remain external actions, with no completion claimed here.

## The seven Jack items

| # | Guide item | Completed locally | Remaining / limit |
|---|---|---|---|
| 1 | Clean Jack; separate Vibe work | Research/source/results remain on Jack; no app tree added. Three signed-off feature branches are saved in the existing Vibe clone. HKVT contains the separate contribution package. | Create/use a Vibe fork for upstream PRs; IndicatorLab's HK branch is the mentor handoff. Main is unchanged. |
| 2 | B2 HSI universe | Backend, API/CLI, frontend and 11 locales; 700/0700.HK alias regression; strict roster validation; tested alongside NIFTY. | **Benchmark incomplete:** Wikipedia returns 85 names versus the dated official 95-name reference. Strict validation stops before evaluation. Annual loaded-name coverage is unavailable; source/policy resolution and PR remain. |
| 3 | B3 HK market layer | Sourced calendar/weather/lunch corrections, prior-available FX helper, dated HKEX lots, actual-engine duty/rounding and composite timestamp dispatch; tests pass. | Combine Jamal's India pieces and publish the joint B3 PR. Current lots are not historical lots; certified historical FX publication times are not shipped. |
| 4 | B6 design and branch | Complete issue-ready design and a concrete local branch directly above HK B3. | Post/agree the shared issue. Multicurrency portfolio execution is a proposed later implementation. |
| 5 | live_hk AWS/lunch/alarm/delay | Separate shared loop and offline fault/calendar tests; existing worker unchanged. November 12 ten-minute delay evidence retained. November 18: local HK frontend and read-only live/health adapter added. | **AWS deferred.** Deployment, session alarms, James's deployed endpoint and group-chat posting have not been accepted. |
| 6 | HK subreddit and full HSI title handoff | Config references 95 symbols and 270 dated title intervals; one unknown date is excluded. Surveyed HK-specific subreddits did not qualify, so selected lists remain empty with evidence. | Send the prepared handoff to Joshua/James and agree the ingestion contract. No sources or missing dates were invented. |
| 7 | Random baselines | Three strategies evaluated in HK and US, 200 controls per case/split: **2,400 null portfolios**, plus **60 drop-one evaluations**. | All six cases are DROP. No eligible cross-market final candidate emerged. |

## Strategy results and candidate

Open [the full report](../results/hk/week4/THREE_STRATEGY_REPORT.md),
[compact metrics](../results/hk/week4/three_strategy_results.csv),
[sheet-ready log](../results/hk/week4/strategy_log_sheet_ready.csv) and
[candidate paragraph](../results/hk/week4/CANDIDATE_WRITEUP.md).

Train: 2016-06-01–2021-12-31. Test: 2022-01-01–2026-10-31; the last price session
is October 30. The active config cutoff is 2026-11-01 and baseline is eight weeks.
The new data snapshot contains 18 price/FX files, 15 attention panels and 5,648
shared-FinBERT text records. This strategy cohort is five HK and ten US stocks;
it is not a full point-in-time historical index universe.

All training entry-count choices, 200-run baselines and ablations finished before
candidate selection and the one extended test. Every selected case has at least
30 train entries; every drop-one indicator changed the training return path.
Defensive Attention Gate was frozen as an **ineligible research nominee** from
train only. It is not a passing team final-strategy candidate.

Both native `backtest.runner` confirmations completed. Their Sharpe differences
exceed 0.1 because native target retention incurs substantially less turnover
than the research rule's weekly close/reopen, with additional dividend/duty and
quantity differences. Saved-fill accounting reconciles the cash/Sharpe bridges.
These are explained differences, not interchangeable portfolio confirmation.
No strategy rule or parameter changed to improve the test results.

Frozen study DSR counted 352 invocations. The clearly separated reporting
supplement conservatively counts 354 after two fixed-hypothesis native checks;
original results remain unchanged. Unknown prior searches/Sharpe samples are not
fabricated, so calibration is explicitly approximate. The earlier 2022–September
2025 test interval was already observed; this is a mandated extension, not a fresh
untouched holdout.

The first launch failed before any portfolio calculation because of a relative
subprocess path. Its source/log is retained in `three_v1_20261115`. A tested
absolute-path fix preceded the sole actual evaluation in `three_v2_paths_20261115`.

## Where the local work lives

- `src/hk/week4/`, `config/hk_week4_research.json`, ignored `data/hk_week4/`.
- `results/hk/week4/`: compact metrics, rules/protocol, nulls, ablations, log,
  candidate, trial ledger, native reconciliation and verification summaries.
- `src/live/` and `HK_WEEK4_LIVE_LOCAL.md`: opt-in shared loop; no service launch.
- `config/hk_week4_handoff.json` and `HK_WEEK4_HANDOFF.md`: team config export.
- `src/hk/week4_compare.py` and `HK_WEEK4_B4_B5_DRAFT.md`: tested B5 consumer and
  B4/B5 schema proposal, awaiting agreement.
- `contributions/week4/`: same upstream package as the separate
  `/Users/jackgui/Desktop/hk/HK vt/indicatorlab` HK checkout.

Local Vibe branches in `/Users/jackgui/Desktop/vib/Vibe-Trading`:
`feat/alpha-bench-hsi-week4`, `feat/market-layer-hk-week4`, and
`feat/cross-market-portfolio-design-week4`. Main remains checked out and unchanged;
user-created untracked files were preserved. No remote push or AWS action occurred.

## Validation

**103 local HK/config tests passed** in the permanent checkout. Scoped Ruff and
whitespace checks passed. Upstream preferred B2: 1,228 related backend passed,
23 skipped; 982 frontend passed, TypeScript passed. B3: 153 selected tests passed.
Current HSI/NIFTY/B3 compatibility: 181 passed with zero socket/DNS attempts.
These overlapping selections are not summed or represented as full upstream CI.
The research report verifies 79 source/input/upstream hashes after evaluation.
