# Hong Kong work: all weeks on Jack

This checkout is **/Users/jackgui/Desktop/hk/indicatorlab-Jack**, on branch
`Jack`. It combines your older research archive with the completed Week 3
code, reports, references and tests. `indicatorlab-clean` is the previous
working checkout; it is not necessary to switch repositories to commit this branch.

| Work | Where it is in this repository |
|---|---|
| Maximum-history download/validation code | `src/hk/history/` |
| Week 1 code and results | `src/hk/week1/`, `results/hk/week1/` |
| Week 2 code and results | `src/hk/week2/`, `results/hk/week2/` |
| Week 3 five-strategy code and results | `src/hk/week3/`, `results/hk/week3/` |
| Live quote collector and local controls | `src/hk/live.py`, `src/hk/local_service.py` |
| HK references/configuration | `config/`, `config.yaml` |
| Design, PR draft and task status | `docs/HK_*`, `docs/VIBE_PR_DRAFT.md` |
| Optional cloud deployment handoff | `infra/hk_live/` |
| Preserved original Week 1/2 archive | `research/hk_market_history/`, `research/hk_week1/`, `research/hk_week2/` |

The raw prices, full research run/model and active live worker remain local.
Original historical inputs are in `research/` here; newer ignored inputs and
the currently running worker remain in `../indicatorlab-clean/data/`. The
GitHub submission contains code, compact results and reference metadata.

## Commit and push this branch

```bash
cd "/Users/jackgui/Desktop/hk/indicatorlab-Jack"
git add .
git commit -m "Combine Hong Kong research and Week 3 deliverables"
git push origin Jack
```

If a prepared merge is pending, the normal commit command finishes that merge.
No force push or replacement of remote history is needed. Select `Jack` on
GitHub and open `results/hk/week3/FIVE_STRATEGY_REPORT.md` for the current results.

## Five completed strategies

Open **[the results report](results/hk/week3/FIVE_STRATEGY_REPORT.md)**.
It explains each strategy, reports IC and after-cost train/test Sharpe, gives
KEEP/DROP and why, and includes the seven requirements and limitations.
All five were tested in both HK and US; all ten market cases are DROP.
Every case had at least 30 completed train entries. There are 4,000 random
timing controls and 104 drop-one evaluations. Nothing was tuned after test.

- [Compact metrics](results/hk/week3/five_strategy_results_reviewed.csv)
- [Sheet-ready Strategy Log](results/hk/week3/strategy_log_sheet_ready.csv)
- [Drop-one results](results/hk/week3/five_strategy_ablations_reviewed.csv)
- [200-run timing results per case/period](results/hk/week3/five_strategy_random_timing.csv)
- [Frozen preregistration](results/hk/week3/five_strategy_preregistration.json)
- [Selected train-only variants](results/hk/week3/five_strategy_selected_variants.json)
- [Verification and input hashes](results/hk/week3/research_verification_summary.json)

Implementation: `src/hk/week3/`. The completed local input/model/trade evidence
remains in `../indicatorlab-clean/data/hk_week3/`. Its immutable run is
`../indicatorlab-clean/data/hk_week3/runs/five_v2c_preflight_20261112/`; do not rerun or tune its test.
The local rules log substitutes for the user's local-only work, but does not
retroactively fulfill posting rules to the shared team sheet before testing.

## Files to contribute to Vibe Trading

The [Vibe Trading contribution package](contributions/vibe-trading/README.md)
is now inside this repository at **contributions/vibe-trading/**, so it can be
reviewed on the same **Jack** branch as your other HK deliverables. It includes
patches containing the 21 changed/new upstream code/docs/test paths. The
older local `HSI_Vibe_Trading_Week3_Ready` folder/ZIP is an equivalent export:

- `01_hsi_universe.patch`: HSI benchmark universe, normalization, API/CLI and tests.
- `02_hk_quotes.patch`: optional HK quote tool/collector and MCP integration;
  depends on 01 for the HSI snapshot helper.
- `APPLY_ALL.patch`: alternative to applying 01 then 02. Do not apply all three.
- `README.md`, `MANIFEST.json`, `BENCH_SUMMARY.md` and the upstream license. New code is inside the patches; inspection duplicates are omitted.

Both application routes were independently applied to clean base files and
byte-matched against the worktree. No raw/live market archive is included.
The actual upstream checkout is `../Vibe-Trading-upstream`, branch
`feat/alpha-bench-hsi`, base `67ce0ca5c9b2a3e3d321217eff043dad913a27fa`.
You handle your fork, commits, real co-author details, DCO and pull requests.
The IndicatorLab research merge is on `Jack`. Upstream Vibe acceptance/CI has not been verified here.

The actual HSI Alpha101 benchmark finished: 100 factors tested, one skipped,
85/85 Wikipedia names loaded. See [summary](results/hk/week3/hsi_alpha101_summary.json).
This is exploratory factor IC, not a costed strategy Sharpe claim. The current
Wikipedia roster has 85 names and lags the separate official 95-name snapshot.

## Faster HSI constituent stock quotes

For the already running worker, use the Python environment in
`../indicatorlab-clean` and run its `src.hk.local_service status` command there.
Do not start a duplicate worker just because the source is now also in `Jack`.
On a fresh installation, create a virtual environment from `requirements.txt`;
the following commands then operate that installation's own local worker:

```bash
.venv/bin/python -B -m src.hk.local_service status
.venv/bin/python -B -m src.hk.local_service start
.venv/bin/python -B -m src.hk.local_service stop
```

The worker fetches 95 HSI constituent **stocks** every five seconds during
HKEX continuous sessions, pausing for lunch, holidays and closed hours.
It resumes next session while the Mac and process stay running. It cannot
collect while the Mac sleeps and has no reboot/login daemon.

- `../indicatorlab-clean/data/live_hk/current/latest.json`: latest observations, atomically replaced.
- `../indicatorlab-clean/data/live_hk/current/status.json`: coverage, poll latency and session state.
- `../indicatorlab-clean/data/live_hk/current/daily/YYYY-MM-DD/observations.jsonl`: growing daily history.
- `../indicatorlab-clean/data/live_hk/current/snapshots/date=YYYY-MM-DD/HHMM.parquet`: minute snapshots.
- [Ten-minute audit](results/hk/week3/live_delay_summary.json) and
  [per-stock ages](results/hk/week3/live_delay_by_symbol.csv).

Measured 95/95 names on 120/120 polls: median last-trade age **10.63 seconds**,
p95 86.58 seconds, **90.95% below one minute**. Five-second polling is not a
guaranteed new trade every five seconds or a universal sub-minute feed.
Read `ts_exchange` and `ts_received`; the status command recalculates age now.

[Google comparison](results/hk/week3/quote_comparison_summary.json): one closing
sample agreed on price/change and volume within display rounding, with provider
times two seconds apart. Earlier intraday snapshots disagreed, so intraday
clock/accuracy reconciliation remains qualified. Raw quantity is preserved.

These are constituent quotes, not the numerical Hang Seng Index level. The
separate historical HSI benchmark lives in the preserved original archive.
The Vibe quote contribution also needs an operator to run it; publishing code
does not create a permanent shared market-data service.

## Other seven-task deliverables

- [Task checklist](docs/HK_WEEK3_STATUS.md): local evidence and external remainder.
- [HK design note / issue draft](docs/HK_CROSS_MARKET_DESIGN.md): calendar,
  daily FX convention, official board lots and dated bilateral stamp duty.
- `config/hk_board_lots_2026-11-12.csv`: official HKEX lot snapshot, all 95 covered.
- `config/hk_wiki_titles.csv`: English/Chinese historical titles and evidenced
  effective dates. `config/hk_wiki_title_intervals.csv` adds interval ends.
  [History evidence](results/hk/week3/wiki_history_summary.json): 95 HK symbols,
  94 English articles, 95 Chinese articles; one earliest date unavailable.
- [Reddit 2024 survey](results/hk/week3/reddit_survey_2024.csv): no surveyed
  market-specific subreddit met 20 posts/week; errors remain errors, not zeros.
- `infra/hk_live/`: optional container/scheduler/IAM/alarm handoff, validated
  offline. No Docker build, AWS deployment or James `/live/hk` integration.
- [Vibe reviewer draft](docs/VIBE_PR_DRAFT.md).

## Historical archive and checks

Maximum-history original data remain under
`research/hk_market_history/prices/`; use that folder's
`price_file_index.csv` for each file's date range and `benchmark/` for HSI.
They were preserved, not freshly revalidated as all-market, maximum-possible
history. Migrated legacy code is `src/hk/history`, `week1`, `week2`; old metrics
are in `results/hk/week1` and `week2`. They use older splits/methods.

New strategy bars end 2025-09-30; train begins 2016-06-01 and test 2022-01-01.
Operational live quotes and current lot/roster references are separate.
Current-lot and current-universe assumptions remain explicit research limits.

Checks: 61 IndicatorLab HK tests; 91 focused Vibe HSI/quote tests; earlier
1,085 selected Vibe integration/purity/look-ahead tests (23 skipped, one existing
Python compatibility warning). Scoped Ruff/Black, whitespace, source/input
hashes, split-patch reconstruction and cfn-lint pass. This is not remote CI,
the entire Vibe suite, cloud acceptance or completion of external team actions.

IC reporting was corrected in a separately logged review without rerunning portfolios; original exports are preserved. Read the report notice before using old metrics. Future reference refreshes create ignored snapshots under data/hk_reference_refresh and never replace frozen lots or canonical title history.
