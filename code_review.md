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
