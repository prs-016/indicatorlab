# Code Review — Jack HK dashboard connection repair
Reviewed: 2026-11-19 local PT
Files reviewed: 19 changed source/test/launcher/documentation files; existing collector controls, API integration and frozen-input manifest inspected as dependencies. Scoped repair review; earlier reports are retained below.

## Summary
The reported loading failure was reproduced as a stopped local API and stopped quote collector. The repair adds a managed local launcher, consistent quote-source discovery, and distinct frontend recovery states. Startup reuses the existing collector and one matching API; the stop command verifies process identity before signalling. No unresolved Must fix or Should fix findings remain in this repair scope. The separate Vibe contribution packages, frozen studies and AWS resources are outside this change.

## Repo Structure

| Expected item | Present / assessment |
|---|---|
| README and setup | Root navigation and frontend README explain start, stop, direct-file recovery and restart after reboot |
| Reusable source | Lifecycle and source discovery in `src/hk/`; existing API adapters retained in `src/api/` |
| Frontend | Existing `frontend/live_markets/` extended; no new framework or package dependency |
| Tests | New `tests/test_hk_dashboard_startup.py`; frontend recovery cases extend the existing Node suite |
| Dependency declaration | Existing requirements suffice; managed local launcher uses POSIX file locking on Mac/Linux |
| Data/results | Runtime state/logs remain under ignored `data/hk_dashboard/`; quote snapshots and research results are not published by this repair |
| Deployment | Local loopback service only; no login daemon or AWS deployment |

Tracked and nonignored file inventory was inspected without reviewing third-party code or ignored generated data. The publication manifest permits exactly the 19 reviewed files and records all other existing nonignored files for preservation.

## Test Coverage

- **51 selected Python cases passed**: 25 existing dashboard, 22 lifecycle/source-discovery and 4 existing Reddit API cases. New coverage includes explicit/freshest/late sources, future clock tolerance, detached startup, duplicate prevention, stale process records, incomplete startup, collector reuse, unknown collector state, foreign configurations/ports, bounded health responses and a process-exit race during stop.
- **21 Node cases passed**, including transport/HTTP/data distinctions, wrong-server responses and working HK coverage when other feeds are absent. JavaScript syntax checks and scoped Ruff passed.
- Chrome/Playwright checks used the actual feed with **95 quotes**, observed an automatic timestamp update, retained prices during an outage, exercised 503/invalid-response/recovery states, and checked direct-file recovery and mobile overflow. No page script errors were observed.
- Static build and launcher shell syntax passed. All **75 frozen strategy source/input hashes** match the permanent checkout; no empirical strategy evaluation was run.

These counts describe the staged repair before guarded publication. Broader permanent-checkout HK/config checks and the final running-service smoke check are recorded separately in the local publication evidence. No instrumented coverage percentage is claimed because pytest-cov is not installed. AWS and other-market service contracts remain external acceptance checks.

## Findings

No unresolved Must fix or Should fix issues in the reviewed scope. Review findings concerning foreign-checkout reuse, possible duplicate collectors, pre-health detached children, unbounded health responses and stop-time process exits were resolved before this final review and have focused regressions. The review itself changed only this report; implementation fixes were performed under the user's separate repair request.

The browser refresh interval is five seconds; it does not certify provider latency. Reopening the launcher is necessary after a Mac restart, and the existing collector requires an awake host. The dated 95-stock operational roster is still distinct from historical membership and the standalone upstream HSI loader.

## Checklist for the student

No unresolved Must fix or Should fix items in this scoped review. Use the local start/stop launchers; follow the separately documented team API and AWS acceptance process when deployment is requested.

---

# Previous review retained — November 18, 2026

# Code Review — Jack HK live dashboard
Reviewed: 2026-11-18
Files reviewed: 23 dashboard source/test/setup/navigation files, plus the existing API router and repository instructions. Scoped change review; inherited research/India code is covered only by prior reports below.

## Summary
The HK display follows the existing plain HTML/CSS/JS framework, reads the existing collector through a read-only API, and does not change frozen research or start a second collector. Quote provenance, coverage, receipt age and exchange time are explicit; source failures do not fabricate prices. No Must fix or Should fix findings were identified within this local HK display scope. Full team API integration and AWS hosting remain external acceptance steps, not completed deliverables.

## Repo Structure

| Expected item | Present / assessment |
|---|---|
| README / setup | Root navigation and `frontend/live_markets/README.md`, local launcher and `.env.example` updated |
| Reusable backend | `src/api/live_data.py`, `src/api/live_routes.py`, `src/hk/dashboard.py`; no notebook-only logic |
| Frontend | `frontend/live_markets/`; existing Reddit frontend retained |
| Tests | `tests/test_hk_dashboard.py`, `frontend/live_markets/tests/model.test.mjs` |
| Dependencies | Existing root requirements cover FastAPI/uvicorn/calendar/boto3; no npm dependencies or added packages |
| Data / models / build | No new raw data/model; static output ignored, latest quotes read without copying them into Git |
| Infra | Existing collector handoff retained; later static S3/CloudFront + separate API described, no deployment claimed |
| Branch / contribution scope | IndicatorLab Jack only; HKVT, main and teammate branches excluded |

Existing tracked inventory: 439 paths before this frontend addition. Reviewed changes add only source, tests, a launcher and documentation, and preserve earlier uncommitted Week 4 work. No credential-bearing environment files or quote snapshots are included in this change.

## Test Coverage

- **25 new Python cases passed**, covering alias de-duplication, invalid row isolation, missing data, separate trade/receipt ages, session/lunch/holiday handling, read-only paginated DynamoDB with Decimals, sanitized errors, HTTP contracts, static serving and safe build configuration.
- **4 existing Reddit API cases passed** in the same selection. Its router remains mounted unchanged.
- **9 Node cases passed** for response validation, missing prices, search/filter/sort/watchlists, market breadth, exchange-time formatting and unavailable local storage.
- Browser checks used the actual 95-stock local snapshot: desktop/mobile, search, watchlist, details, pause/manual refresh, automatic polling, retained keyboard focus, outage/recovery, initial unavailable state, header timestamps, placeholders, and explicit unsupported feeds. Optional `/hot` badge rendering was checked separately with a browser-scoped fixture, not presented as actual attention data. No browser script errors or mobile horizontal overflow were observed.
- Scoped Ruff, JavaScript syntax checks, launcher syntax and static build passed. The build contains five public assets only; an injected secret in the test environment does not enter public config.
- All **75 frozen strategy source/input hashes** matched before publication. No portfolio or live trading evaluation was performed.

`pytest-cov` is not installed in the existing environment, so no instrumented coverage percentage is claimed. AWS calls use mocks; actual AWS IAM/table/network acceptance, the full team `/hot` contract and other market feeds are not validated here. The prior review below retains the broader research-suite evidence.

## Findings

No actionable Must fix or Should fix findings in the reviewed local HK display change. Remaining integration boundaries are documented rather than concealed: the dated 95-name operational roster is not historical membership; prices are nominal, volume units pass through; a five-second display poll is not proof of provider latency; India/US and the full attention dashboard require the team's service. The static frontend alone cannot run collection or query DynamoDB; server-side IAM stays outside the browser.

## Checklist for the student

No unresolved Must fix or Should fix items in this scoped review. Before later deployment, perform the separate team API/AWS acceptance checks described in the frontend README; no remote publication or team acceptance is implied by these local checks.

---

# Previous review retained — November 15, 2026

# Code Review — Jack Week 4 local delivery
Reviewed: 2026-11-15 local PT / 2026-11-16 UTC
Files reviewed: 37 primary source/test/config/package records; additional navigation, result and reconciliation documents inspected. Scoped final review, not a full review of inherited team code.

## Summary
The completed local study reports six DROP cases honestly, retains the train-only ineligible nominee, and does not present the two successful native runner executions as matching numerical confirmations. The relative-path repair occurred before any performance evaluation, is covered by a focused regression, and all 22 frozen source-file hashes still match the permanent checkout. The source layout, compact evidence and separate HKVT upstream package follow the intended local scope. The two identified delivery metadata updates are resolved in the final publication: final research reports/status are included, and actual feature-branch transfer state is verified.

## Repo Structure

| Expected item | Present / assessment |
|---|---|
| README/navigation | Present; final Week 4 status/report links need the delivery refresh below |
| Dependency file | `requirements.txt`; research, shared scorer and optional live sink dependencies declared |
| Reusable source | `src/hk/week4/`, `src/live/`, `src/hk/week4_compare.py`; source is outside notebooks |
| Tests | HK/config unit and integration tests, including relative run path regression |
| Data/models | Local and ignored; no new raw dataset/model is proposed for Git |
| Results | Compact CSV/JSON/Markdown outputs allowlisted; 10.6 MB full trace remains ignored |
| Frontend/infra | Existing team context retained; no new runnable Vibe application pasted here; AWS deliberately deferred |
| Upstream contribution | Separate HKVT `contributions/week4/`; historical v2 preserved separately |
| Environment/secrets | No tracked `.env` file found; credential values were not printed during review |

Inventory at review: 439 tracked paths and 68 new nonignored paths in Jack, with no new nonignored file above 5 MB. The 29 entries in the Week 4 package manifest all match their SHA-256 hashes; the Jack and HKVT mirrors match exactly, including their package manifests. Package version 3 is distinct from the preserved historical v2.

## Test Coverage

The parent recorded **103 HK/config tests passed** on the permanent checkout, with the four earlier environment-dependent skips resolved in the native environment, and Ruff passing across new Python files. This final review did not repeat tests or empirical runs; no coverage percentage is claimed because instrumented coverage was not run.

The relative-path regression changes the working directory, calls `run(Path("relative-study"))`, intercepts the pre-portfolio freeze point and verifies that the directory is absolute. `run()` resolves/expands the directory before requests are persisted or workers change their working directory. The preserved v1 failure therefore does not supply strategy performance; the separate v2 study supplies the observed results.

Previously recorded upstream checks remain separately scoped: B2 1,228 related backend passes/23 skips and 982 frontend passes; current combined HSI/NIFTY/B3 181 selected offline passes. Overlapping suite counts must not be added. Remote CI and AWS acceptance were not performed.

## Findings

### `docs/HK_WEEK4_STATUS.md` (lines 25–35 at review; final compact result publication)
**Issue:** Delivery metadata still describes the completed evaluation as queued.
**Severity:** Resolved in final delivery.

```markdown
|7|Random baselines in backtests|Week3 preserved; Week4 code, protocol and inputs ready for200timing controls per case/split|Fresh evaluation queued after permanent local copy|
```

The permanent study has completed six market cases, 2,400 timing controls and 60 ablations, so this pending language is stale. Publish the final compact reports/ledger/reconciliation evidence, update item 7 and the report links, and allowlist the compact final files while keeping full traces and raw inputs ignored. The final status must continue to say AWS, remote PRs/team posting, and the roster-blocked real HSI benchmark/yearly coverage are incomplete or deferred.

### `contributions/week4/LOCAL_BRANCHES.json` (final `transfer_status` field; both package mirrors)
**Issue:** Recorded branch transfer state is still a preparation placeholder.
**Severity:** Resolved in final delivery.

```json
"transfer_status": "prepared; final local transfer pending"
```

Replace this only after verifying the actual local feature refs in the existing Vibe checkout; preserve its checked-out `main` worktree. Keep both package mirrors and the manifest hashes synchronized. This local transfer must not be described as a remote fork push or upstream PR.

## Evidence and limits retained

- The 22 frozen source hashes match. The preregistration records 53 additional input hashes (75 combined); this final review did not reread the raw dataset in full.
- Train base/random/ablation checks precede the candidate/test marker. The candidate is explicitly ineligible; none of the six cases is marketed as KEEP.
- The new cutoff, first-following-session timing, selected-score IC orientation, MDD, delayed-exit and overlap checks remain as previously reviewed. No strategy source was changed during this delivery audit.
- HK/US direct native Sharpe differences remain approximately +0.413194/+0.189604, both outside the 0.1 agreement criterion. Fixed-fill cash reconstructions explain the differences; those are arithmetic diagnostics, not new strategies or matching confirmations. The native HK benchmark basket is not relabeled as HSI.
- The original 352-trial DSR outputs are preserved. Any displayed 354-invocation supplement must be labeled separately as conservatively including the two repeated native checks; do not rewrite the frozen ledger or claim independent searches.
- B2 strict Wikipedia validation still observes 85 against the dated 95 reference, evaluates zero factors, and produces no annual coverage. No prior 85-name benchmark is relabeled as the required new run.
- B3 is the tested HK contribution, not a completed joint India/HK upstream PR. B6 is design/branch preparation, not a completed multicurrency portfolio implementation. Shared schema agreement, messages and Strategy Log posting remain external actions.

## Checklist for the student

- [x] Publish the final compact Week 4 results, ledger and HK/US reconciliation evidence; update the queued status/report links and preserve the ignored raw/full traces.
- [x] Verify local feature refs, update the transfer record and synchronize package mirrors/manifests without implying remote publication.

These are final delivery metadata tasks. No additional strategy tuning, empirical rerun, or source change is requested by this review.

## Final delivery resolution

The two metadata findings above are resolved by the final copy: compact reports/status and explicit allowlist are published; branch transfer state is verified; both package mirrors and their rebuilt manifest are checked. Original strategy sources/results are unchanged, and the 10MB full trace remains ignored. The HSI source discrepancy, native numerical non-equivalence, no eligible nominee, external publication and deferred AWS are reported limitations rather than hidden completion claims.
