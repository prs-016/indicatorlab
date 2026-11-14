# Code Review — IndicatorLab Hong Kong Week 3
Reviewed: 2026-11-13 (America/Los_Angeles)
Files reviewed: 122 changed/new paths (101 IndicatorLab HK/setup/reference/result/documentation paths, 21 Vibe contribution paths); unchanged India work excluded.

## Summary
The local HK implementation follows src/tests/results conventions and now includes five actually evaluated multi-source strategies in both markets, fast constituent quotes and a verified code-only upstream handoff. All ten strategy cases correctly DROP; an IC score-orientation reporting bug found during review was corrected in a separately frozen diagnostic, with original portfolio runs and exports preserved. Sixty-one HK tests pass, source/input hashes match, and both contribution patch routes reproduce all 21 target files. The remaining findings concern future research-run reuse and portability; local results are exploratory, and this review does not certify cloud deployment, GitHub publication or the guide's external team deliverables.

## Repo Structure

| Expected location | Status |
|---|---|
| README.md / AGENTS.md | Present; HK start guide, local commands, completion boundaries and frozen-result caution added. India guidance preserved. |
| .env.example / .gitignore / requirements.txt | Present; input/model/runtime artifacts ignored, selected compact HK evidence allowed. No credential-pattern match in changed text files. |
| src/ / tests/ | Present; HK live/calendar/reference/evaluation/research code and six HK test modules. Legacy code is separate from the new Week 3 runner. |
| results/ | Compact HK metrics, preregistration, diagnostic review and interpretation under results/hk/week3. Full native trade traces remain ignored. |
| config/ | Dated roster/lots and historical article-title references. These are curated metadata, not raw price archives. |
| notebooks/ / models/ / data/ | Existing project layout preserved; downloaded model, historical prices, text and operational observations stay ignored. No reusable new logic exists only in a notebook. |
| infra/ | Optional HK container/CloudFormation handoff; cfn-lint passed. No Docker image build or real account deployment claimed. |
| frontend/ | Existing project material preserved. No new front end was requested in the final scope. |
| Separate Vibe checkout/export | HSI_Vibe_Trading_Week3_Ready contains only code/docs/tests, patches, manifest and benchmark note. No Vibe source tree pasted into IndicatorLab. |

## Test Coverage

- Final scoped IndicatorLab HK suite: **61 passed**. Covers aliases/parser fields/batch failures, sessions and dated weather exceptions, local publication/current-age/PID identity, official lot parsing and reference preservation, actual native Vibe transaction parity, timing count/duration/non-overlap, duty dates/rounding, attention whole-book scaling, ablation rank removal, title logpage identity, net added text and corrected IC orientation.
- AWS sink tests use mocked boto3 endpoints but real Parquet serialization: Decimal upserts, all 95 records, correct S3 key and one snapshot per minute. Watchdog tests cover receipt age, closed sessions and reopening grace. No live AWS write was exercised.
- Focused Vibe HSI/quote suite: **91 passed**, one existing Python 3.14/LangChain Pydantic-v1 warning. Earlier selected integration/purity/look-ahead suite: **1,085 passed, 23 skipped**, one same compatibility warning. Not the entire upstream suite or remote CI.
- Real local study: ten base market cases, 104 drop-one evaluations and 4,000 timing-null simulations completed using the native engine transaction methods, with zero missing-lot fallbacks or rejected scheduled trades. These are scientific runs, not extra unit-test counts.
- Independent read-only audits verified all **49** frozen source/input hashes; all non-IC fields in reviewed base results match the original exports. All ten decisions were independently recomputed and remain DROP. The correction protocol/source hash and 124 unique IC diagnostic rows were verified.
- Both 01→02 and APPLY_ALL patches were independently applied to clean base files and all 21 destination hashes matched. All 13 new-file inspection copies and ZIP CRC/membership checks matched. No raw data, databases, models or private agent files in the package.
- Scoped Ruff/Black, AST parsing and Git whitespace checks passed. Main start-guide/report links resolve. `pytest_cov` is unavailable, so no numerical coverage percentage is claimed. Public-provider acquisition/retry behavior and full historical corporate-action/lot/fee fidelity lack exhaustive automated integration coverage; manual acquisition evidence does not certify every historical observation.

## Findings

### `src/hk/week3/features.py` (lines 395–397)
**Issue:** Original IC scoring remains unsuitable for future reuse without the review correction
**Severity:** Should fix (before a new research run; current reporting corrected)

```python
mask, rank, scale = strategy_week(bundle, strategy, variant, week, drop)
score = rank.where(mask, 0.0).where(bundle.weekly["rv63"].loc[week].notna())
scores[entry] = score.to_dict()
```

Negative priorities in Defensive Attention Gate/Information Compression put rejected zero-score names above stocks actually selected; zero-priority ablations can also erase their eligibility signal. The completed frozen source stays unchanged for audit. `src/hk/ic_diagnostic.py` now ranks eligible names above rejected ones with identical within-selection priority and original labels, and the main report/sheet use `_reviewed.csv`; original files remain preserved. Incorporate that tested correction into a newly versioned runner before any future study, rather than silently reusing this score. No current trade, Sharpe, DSR, timing control or decision changed.

### `src/hk/week3/run.py` (lines 39–50, 68–76)
**Issue:** Resume gate does not validate every frozen input/engine digest
**Severity:** Should fix (before a new/resumed incomplete study)

```python
for relative, expected in saved["source_hashes"].items():
    if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
        raise ValueError(
            "Preregistered source changed; record a new run rather than silently retesting"
        )
return
```

This verifies code on resume, but the initial recorded input hashes are not checked there; attention and engine digests are captured separately rather than all enforced before execution. The completed study's 49 source/input hashes plus engine hashes were checked after execution and again independently, so no mutation is evidenced in this result. Future runners should include every consumed input and engine digest in the preregistration and enforce them before resuming work. Do not rerun the completed test to address this future-use concern.

### `src/hk/week3/run.py` (line 20)
**Issue:** Research runner assumes a sibling checkout name
**Severity:** Should fix (portability)

```python
VIBE = ROOT.parent / "Vibe-Trading-upstream"
```

This works on Jack's documented Mac layout but requires a teammate to recreate that exact sibling name. A future version should accept an explicit checkout/interpreter path and validate its expected engine version. The upstream contribution itself does not depend on this local research runner or its folder layout.

## Checklist for the student

- [x] Complete the actual five-strategy US/HK evaluation and retain all failing results.
- [x] Correct IC reporting separately and preserve the frozen original study/exports.
- [x] Verify completed-study source/input integrity and immutable non-IC results.
- [x] Protect canonical title histories and frozen lot inputs from reference-refresh overwrites.
- [x] Export and independently verify the separate code-only Vibe patches/ZIP.
- [ ] Before any new study, incorporate the reviewed IC score into a newly versioned runner.
- [ ] Before resuming a future incomplete study, enforce all input/engine digests at the execution gate.
- [ ] Make future research-run checkout/interpreter paths configurable for teammate portability.

No unresolved Must fix blocks the current local handoff. Current lot/membership/vendor-adjustment assumptions, sparse English text, current classifier vintage, low exposure, benchmark conventions, Google intraday discrepancy and public-feed freshness limits are disclosed in the report/checklist; they limit scientific claims. The literal shared-sheet preregistration did not occur, and cannot be retroactively claimed. Actual upstream publication/CI, team issue/chat/coauthors, AWS deployment and James endpoint acceptance remain external actions under the user's local-only scope.

---

The pre-existing India review is preserved below verbatim as historical context; it was not re-reviewed or modified by the HK task.

# Code Review — IndicatorLab India
Reviewed: 2026-11-01 (America/Los_Angeles)
Files reviewed: 50 first-party implementation/test/documentation files; 154 selected evidence-package files checked by inventory/verifier (not treated as source code).

## Summary

The India implementation follows the DS3 src/tests separation, preserves isolated Vibe imports and has synthetic coverage of data validation, original factors, execution timing, costs, IC and approval boundaries. No credential-pattern matches were found in the proposed indexed files; raw market archives, virtual environments and duplicate drafts are excluded. Two submission blockers were identified and resolved after the read-only review under the user’s separate fix authorization: Git whitespace failures in portable review copies and a template-only root README that does not explain reviewer setup or distinguish portable evidence from archive-dependent experiment runners. This is a manual review under docs/codeReviewer.md, not PM approval, a new backtest or certification of the provisional economic findings.

## Repo Structure

| Expected area | Present? | Assessment |
|---|---|---|
| README.md | Yes | Initial template needs India review/setup entry point (finding below). |
| requirements.txt / pytest.ini | Yes | NumPy/pandas/SciPy/yfinance/pydantic and pytest declared; collection restricted to tests. |
| src/ | Yes | 22 Python files including the template example; reusable India logic is outside notebooks. |
| tests/ | Yes | 20 Python files; clearly labelled synthetic fixtures and isolated original-factor integration tests. |
| notebooks/ | Yes | Template documentation only; no correctness-critical notebook or notebook-only India pipeline found. |
| docs/ | Yes | Team review instructions plus required India context/methodology. Historical archive references are not shipped market data. |
| india_research/submission/ | Yes | Selected portable review copies; original-source hashes distinguished from bundle hashes. |
| results/ / models/ | Yes | Generated archives remain ignored; only existing tracked placeholders are retained. |
| frontend/ / infra/ | Yes | Template documentation; optional for this research-only scope. |
| .env.example / .gitignore | Yes | Environment template only; no actual credentials/environment/cache files proposed. |

Scope: reviewed source parsing/imports, public API docstrings, data/cutoff/finite-value checks, immutable writers, isolated worker protocols, official-record/calendar verifiers, factor/IC composition and sequential portfolio accounting. Reviewed the corresponding test fixtures and approval-boundary tests. All exposed module-level functions/classes have docstrings; nested worker/quality helpers are not independent public APIs. Evidence JSON/CSV/Markdown is reviewed for portability, numerical consistency and checksums, not as vendored implementation.

## Test Coverage

The synthetic suite exercises adapter alignment and benchmark separation, cutoff/warm-up, original factor formulas and future-input perturbations, missingness, official records/actions/quantity anchors, calendar gates, immutable versions, portfolio drift/turnover/costs, IC versus Sharpe, and factor-specific single-run permissions. Integration tests invoke actual Vibe functions in child processes; they require the existing pinned external checkout and explicit VIBE_PYTHON. They are offline; their portfolio examples are synthetic and do not repeat real-data experiments.

pytest-cov/coverage, ruff and flake8 are not installed in the project environment. No tools were installed; style was reviewed manually. No measured line/branch coverage percentage is claimed. After the authorized documentation/format fixes, the complete workspace suite passed **353 tests in 45.78s**, with no failures, skips or warnings. An independent export containing only the 213 indexed files (200 changed paths plus existing tracked baseline files) passed the same **353 tests in 43.87s**, with no failures, skips or warnings. The export had no ignored results archive, historical report directory or virtual environment. The existing external pinned Vibe checkout and project interpreter were explicitly supplied; this is not a claim that Vibe is bundled or that dependencies were newly installed.

Executed full-suite command:

```bash
VIBE_PYTHON=/home/jampip/indicatorlab/.venv/bin/python VIBE_TRADING_ROOT=/home/jampip/vibe-Trading .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

The indexed evidence package also passes its standard-library verifier: 153 file checksums, 81 internal Markdown links, ten entries, eight saved portfolio metric/accounting checks and two non-evaluable cases. Git’s staged whitespace check passes. A scoped credential-pattern scan found no matches; no comprehensive security certification is implied. All 1,133 protected original source/test/report/data/result files remain unchanged. Only review-copy formatting, package guide/checksums and current submission documentation were fixed; there was no new real-data factor scoring, ingestion or portfolio backtest. Historical full real-data diagnostic orchestration is not exercised end-to-end on a clean clone: the full market-data archives are intentionally excluded. The portable package verifier checks saved metrics without running strategies.

## Findings

### `india_research/submission/india_review_v1_20261101/strategy_log.csv` (lines 1–11), `strategy_log.md` (line 5), `supporting/india_data_quality_report.md` (lines 4–6)
**Issue:** Submission formatting / checksum consistency
**Severity:** Must fix

```text
india_research/submission/india_review_v1_20261101/strategy_log.csv:1: trailing whitespace.
```

Initial `git diff --cached --check` reports 15 errors: CRLF carriage returns in the eleven CSV records and trailing spaces in four review-copy Markdown lines. Normalize only the selected review copies, preserve CSV cell values, and update the bundle's affected hashes and transformation descriptions. Do not change historical drafts or original scientific artifacts. **Status: resolved for this submission.**

### `README.md` (initial lines 1–3); package `README.md` (lines 28–32)
**Issue:** Submission entry point / fresh-checkout documentation
**Severity:** Must fix

```markdown
# DS3 Project Template
```

The root README does not identify IndicatorLab or explain how to locate/verify the submission, configure the external Vibe checkout, or run the offline suite without missing ignored artifacts. The package also says nothing is staged or Git-tracked, a transient assertion that becomes misleading at submission. Add reviewer-facing instructions distinguishing saved-evidence verification, optional external Vibe integration tests and archive-bound single-run diagnostic entry points; preserve the team workflow. **Status: resolved for this submission.**

### `src/india_illiq_diagnostic.py` (lines 199–213), `src/india_phase2_diagnostic.py` (lines 136–191)
**Issue:** Hardcoded external checkout / duplicated orchestration
**Severity:** Should fix

```python
        run = backtest_phase2_factor(panel, factor, vibe_root='/home/jampip/vibe-Trading',
```

Archive-bound runners duplicate preflight/output orchestration and assume an external checkout at the author's absolute path; the ILLIQ runner imports helpers/constants from the earlier runner. This is not required for a clean reviewer evidence/test run and no new real-data invocation is authorized, so defer API/refactoring changes. Before any separately authorized rerun, make runtime locations explicit while retaining pinned evidence and narrow approvals. Existing source versions/results remain untouched in this submission task.

### `src/india_factor_readiness.py` (lines 16–39)
**Issue:** Generic finite-coverage diagnostic robustness
**Severity:** Should fix

```python
        valid=row.dropna().sort_values(ascending=False)
```

The helper's per-day valid-name count excludes NaNs but not infinities, whereas its aggregate finite-cell count uses np.isfinite. Inputs with infinities could therefore produce contradictory standalone coverage summaries. Inspected production factor boundaries reject/observe infinities and saved study outputs have none, so this does not invalidate archived results; defer a separate helper regression/fix rather than alter research behavior here.

### `src/india_phase2_factors.py` (lines 125–132); `src/india_phase2_readiness.py` (lines 43–55)
**Issue:** Worker-protocol coupling / maintainability
**Severity:** Should fix

```python
    return _WORKER.replace(old_import, "importlib.import_module(request['module_path'])").replace(
```

Extending/instrumenting the child protocol by exact source-string replacement is brittle. The factor integration guards expected occurrence counts and synthetic tests cover actual outputs, so no current submission failure was established. A future tested protocol abstraction should avoid text-dependent changes while preserving isolated imports and original factor definitions; no speculative rewrite is needed for this submission.

## Checklist for the student

- [x] Resolve selected-review-copy whitespace errors without numeric/source changes; refresh manifest and verify package.
- [x] Add an India reviewer entry point, external dependency instructions and clear archive-only runner limitations; remove transient package staging assertions.
- [ ] Future task: remove author-specific runtime locations and reduce duplicated diagnostic orchestration without broadening approvals.
- [ ] Future task: make standalone coverage valid-name counts consistently finite-aware with an explicit regression.
- [ ] Future task: reduce source-string coupling in isolated worker dispatch/instrumentation with regression coverage.

Submission disposition: **no unresolved Must fix findings** for local staging.
The three Should fix items remain documented, deliberately deferred under the
user’s instruction to fix submission blockers only. Historical context/report
paths are archive references; README and the portable bundle are the supported
review route. Staged selection is 200 paths: 154 evidence files, 20 India source
modules, 19 India test modules and 7 setup/context/review files (including AGENTS).
The 155-path evidence allowlist is fully included. Credentials, environments,
caches, ignored results, raw source data, duplicate drafts and unrelated modules
are excluded. Direct remote write authorization/authentication has not been tested;
no commit, push, PR or merge was attempted. Human/team review remains required.
