# Code Review — Week 3 complex research publication
Reviewed: 2026-11-23
Files reviewed: 63

## Summary

The existing completed US research is packaged without rerunning historical
strategies or changing runtime strategy/evaluation modules. Public evidence
contains derived metrics and audit projections, not licensed source datasets.
No publication-blocking code finding remains after the fixes below. India data,
DSR and shared-sheet availability remain explicitly incomplete.

## Repo Structure

Ten existing reusable modules are in src/, portable offline tests are in tests/,
frozen definitions remain under india_research/reports/, and the curated evidence
is under the established india_research/submission/ convention. Existing shared
configuration, earlier studies, AGENTS.md and teammate work are excluded.

## Test Coverage

171 combined tests passed from an independent committed checkout in 147.38
seconds; one private-input join explicitly
skipped because licensed datasets are absent. Ten additional packaging tests
pass, independently checking the four original frozen rule hashes, source hashes,
legacy metadata dependencies, 1,200 actual null metric rows, their percentiles,
minimum-entry dispositions, registration qualifications and India quarantine.
These are offline checks, not new historical performance. Ruff and Black pass on
all 21 contribution Python files. No coverage percentage is claimed.
A clean committed-checkout verification precedes push.

## Findings

### tests/india_week3_test_support.py and integration tests

**Issue:** Machine-specific checkout paths.
**Severity:** Must fix — resolved.

Existing tests now use the established VIBE_TRADING_ROOT environment setting.
Original-Vibe integration skips explicitly when absent, fails on an invalid
configured path, and runs through the existing isolated subprocess when supplied.
No market or strategy code was changed.

### Frozen rules and common-runner metadata

**Issue:** Runtime metadata dependencies and stale source-freeze interpretation.
**Severity:** Must fix — resolved for the published package.

The original v1_2 rule files/checksums are verified unchanged. Two required legacy
parameter/specification dependencies are included byte-for-byte. The current
publication source manifest is explicitly separate from older source manifests:
no historical checksum is replaced to make a later framework version appear
identical. The original broader November 15 archive stays local and unchanged.
Archival narrative links can refer to local-only drafts; the new reviewer entry
points link only their included required evidence and identify this distinction.

### india_research/submission/week3_complex_v1_2_20261123/

**Issue:** Previous report links referred to ignored local results.
**Severity:** Must fix — resolved.

The new public package contains numerical summaries, ablations, all completed
null metrics, scalar trial projections including failures, frozen-rule hashes,
input provenance and exact sheet-import rows. Original source hashes and limited
review transformations are documented. Raw prices, corpus text, trade-fill price
records and private execution inputs remain excluded.

### Statistical and operational acceptance

**Issue:** Incomplete India evaluation, minimum entries and DSR.
**Severity:** Informational research outcomes, not passing validation claims.

WATM remains DROP; WVB/WCR remain INSUFFICIENT TRADES. No India backtest is
invented or run on quarantined observations. DSR remains N/A rather than assuming
an unsupported global trial count. Shared-sheet updates are not claimed.

## Checklist for the student

- [x] Preserve all runtime module and frozen-rule bytes.
- [x] Remove machine-specific test dependencies.
- [x] Include required metadata and independently verify frozen artifacts.
- [x] Publish reviewer-accessible derived evidence and honest missing results.
- [x] Run focused tests, Ruff, Black and whitespace/security review.
- [x] Complete independent committed-checkout verification before push.
