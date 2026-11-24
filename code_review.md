# Code Review — India Reddit integration
Reviewed: 2026-11-23
Files reviewed: 12

## Summary

The completed India configuration and market propagation are compatible with
shared main 13c58bcf. The existing pipeline is reused; there is no parallel India
collector. No submission-blocking finding remains. Historical matching precision
and corpus completeness are explicitly outside the demonstrated scope.

## Repo Structure

Reusable changes remain in src/reddit/, tests in tests/reddit/, configuration in
config.yaml and compact survey evidence in config/. No raw posts, credentials,
large datasets, frozen strategies or unrelated local changes are included.

## Test Coverage

174 configuration, matching, market-propagation, weekly and spike tests passed in
1.71 seconds. Tests deny network access and use synthetic post fixtures. They
cover qualified identifiers for all 100 current companies, ambiguous aliases,
US/HK preservation, cache retagging, default-US compatibility and end-to-end local
archive conversion through the existing matcher. No coverage percentage claimed.
Black and Ruff pass on all four contribution Python files; whitespace checks pass.
A detached committed-checkout verification is required before push.

## Findings

### config.yaml and tests/fixtures/india_reddit_preserved_config.json

**Issue:** Shared configuration compatibility.
**Severity:** Should fix — resolved.

Only the India market block was transferred. The preservation fixture is bound
to current main, retaining US/HK settings, the newer shared holdout, sentiment
configuration and the eight-week baseline. Frozen Week 3 studies are not changed.

### Research evidence and documentation

**Issue:** Earlier activation report described market propagation as unfinished.
**Severity:** Should fix — resolved.

The review copy now records implemented propagation and fresh tests. Compact
survey documentation identifies included versus local-only evidence. Archive
counts do not certify company-level historical attention or sentiment.

### Matching policy

**Issue:** Current names are not dated historical identities.
**Severity:** Informational.

Bare ambiguous tickers and unvalidated aliases remain disabled. Current-entity
rules must not be retrospectively treated as merger/demerger histories. Real-post
precision and recall are not established by passing synthetic tests.

## Checklist for the student

- [x] Preserve current shared configuration and other markets.
- [x] Reuse existing pipeline and preserve source/match provenance.
- [x] Include test dependencies and compact evidence only.
- [x] Run focused tests, Ruff, Black and whitespace checks.
- [x] Verify committed clean checkout before push (174 passed).

The two evidence CSV review copies use LF line endings; every parsed CSV field
was verified unchanged. Original local survey files remain unchanged.
