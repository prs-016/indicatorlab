# Code Review — India Wikipedia integration
Reviewed: 2026-11-23
Files reviewed: 9

## Summary

The existing published adapter and its paired CSV/ledger remain unchanged.
All 100 constituent identities now have a portable disposition table, while
unresolved company identities remain explicit rather than parent substitutions.
No blocking implementation finding remains within the mapping-package scope.

## Repo Structure

Adapter in src/, offline tests in tests/, mapping/evidence in config/ and
integration instructions in docs/. No pageviews, historical text, credentials,
private notes or unrelated research are included.

## Test Coverage

16 adapter and coverage tests pass. These include all 13 existing adapter
regressions and three all-company disposition/history tests. The tests cover
schema, duplicate handling, ambiguous current titles, missing or unsupported
dates, unknown intervals and the exact YAML-facing export. No network acquisition
or historical completeness is inferred. Ruff, Black and whitespace checks pass.
A fresh committed checkout is verified before publication.

## Findings

### config/india_wiki_coverage.csv

**Issue:** Twelve identities lack a separate verified English company mapping.
**Severity:** Informational — explicitly unresolved.

The bounded official metadata/search recheck did not justify parent/group
substitutions. Two searches were throttled and stopped. Coverage means every
company has a documented disposition, not that all 100 have Wikipedia articles.

### Mapping history

**Issue:** Unknown dates and incomplete historical entity scope.
**Severity:** Informational.

All 136 unknown starts remain unknown. Existing historical titles are not an
aggregation whitelist. James must use the existing separate history interface
and review intervals before historical collection; no teammate pipeline changed.

## Checklist for the student

- [x] Preserve published adapter/CSV/ledger bytes.
- [x] Document all 100 companies and unresolved identities.
- [x] Reject parent redirects and avoid fabricated effective dates.
- [x] Add offline tests and verify the committed package before push.
