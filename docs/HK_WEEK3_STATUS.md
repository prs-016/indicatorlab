# Jack's Week 3: local completion and external handoff

Final handoff reviewed 2026-11-13 (America/Los_Angeles). Evidence artifacts
retain their actual UTC run timestamps. Jack handles GitHub publishing; work
here is local. No GitHub write, force push, team message or cloud deployment.

Later local cleanup: the pasted app in `indicatorlab-Jack` was moved to the
sibling `/Users/jackgui/Desktop/hk/Vibe Trading Original/` archive. Original
research/data, Git HEAD/index and all 49 frozen study hashes were preserved.
Those working-tree removals have not been staged, committed or pushed here.

| Guide task | Local work and evidence | External or qualified remainder |
|---|---|---|
| 1. Clean branch | Fresh `jack-clean` from origin/main; only HK code in src/hk, selected outputs in results/hk and dated references in config. Original branch/archive preserved. Code review saved in code_review.md. | Jack's fork/commit/push; Jamal review before any remote Jack replacement. No remote branch cleanup claimed. |
| 2. Cross-market issue | Complete HK calendar, HKD/USD, board-lot and stamp-duty draft in HK_CROSS_MARKET_DESIGN.md, with primary sources. Two missing 2023 full closures and one late open patched/tested. | Agree shared interfaces with Jamal, add real four-author identities, post issue. Historical partial-session audit is not exhaustive. |
| 3. HSI universe | 21-path filtered Vibe contribution; current Wikipedia parsing/revision date, degraded full fallback, alias dedup, shared loader chain, sector gate, VWAP proxy, survivorship metadata, API/CLI/tests. Actual bounded Alpha101 benchmark: 100 factors tested, 1 skipped, 85/85 names loaded. | Upstream PR/remote CI and human review; Wikipedia 85-name membership lags official 95 and is not point-in-time. Jack handles publishing. |
| 4. Tool B design | Official dated lot table covers all 95; daily FX/availability convention; dated duty/rounding and weather-policy note. This week's requested design deliverable is prepared locally. | Full tool B implementation is next week's work. Historical lot/fee/exemption certification remains incomplete. |
| 5. Live quotes | Five-second 95-stock local worker, calendar/backoff, latest view/daily history/minute Parquet. Ten-minute audit: 10.63-s median, 86.58-s p95, 90.95% <60 s. One near-time closing Google sample agrees. Mock-tested optional DynamoDB/S3 sink; cfn-lint-valid container/scheduler/watchdog/alarm template. | Not universal <60 s; earlier intraday comparison discrepancy retained. Real AWS deployment, S3/Dynamo acceptance, James endpoint and posting delay to chat are external and unperformed. |
| 6. HK attention | Numeric Arctic Shift 2024 survey; no eligible market-specific source. Config matching rules. 95-symbol English/Chinese mapping with 295 combined HK/US title intervals, creation/move evidence and zero unresolved chain discontinuities. | No English Laopu article exists; one pre-merge Chinese earliest date left blank; CHALCO article scope shared; suppressed/deleted historical aliases may be unavailable. |
| 7. Complex strategies | User requested five: all five tested in US+HK, all >=30 train entries, 4,000 timing controls, 104 drop-one evaluations, IC/train-test Sharpe/DSR, complete documented trial count 268. All ten cases DROP. Immutable local preregistration and sheet-ready export saved. | Rules were not posted to the actual team sheet before testing; cannot claim that retroactively. Shared-sheet entry and team reporting are Jack's actions. Current lots/universe/vendor-adjustment limitations remain explicit. |

Start at `../HK_START_HERE.md` for exact file locations and commands.
Results: `../results/hk/week3/FIVE_STRATEGY_REPORT.md`.
Code-only Vibe export: `/Users/jackgui/Desktop/hk/HSI_Vibe_Trading_Week3_Ready/`
and sibling ZIP; older contribution folders are superseded.

The requested local implementation and actual five-strategy evaluation are
complete. The guide's full end-to-end "Done when" conditions are **not all
complete**, because several require publishing, cloud access or teammates.
None has been silently marked done.
