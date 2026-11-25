# Code Review — Final Week N1 India symbols

Reviewed November 24, 2026 Pacific
Files reviewed: 5 N1 files

## Summary

The India resolver adapter reuses the published Wikipedia data contract
and follows the shared lookup exceptions. The N1 metadata interface
is ready for resolver integration. Full English Wikipedia coverage remains
an explicit acceptance blocker.

## Repo Structure

The adapter and shared exceptions are in src/markets, tests are in tests,
and the resolver handoff and evidence are in docs. The original research
and teammates' active configuration remain outside the N1 diff.

## Test Coverage

46 tests passed and the strict all-title acceptance test expectedly failed.
Offline tests verify the exact lookup spellings, BSE preference and fallback,
untracked behavior, provider failure handling, metadata, aliases, ambiguous
names and subreddit exports. Live yfinance validation was outside this
review. Black, Ruff and whitespace checks passed.

## Findings

### `src/markets/india_symbols.py` (lines 70–75)

**Issue:** Twelve unresolved English article identities.
**Severity:** Must fix to satisfy the full N1 acceptance criterion.

The adapter retains null for the missing titles. Replacing an Indian
listing with a parent or group page would give James a different entity's
pageviews.

## Checklist for the student

- [ ] Resolve the 12 missing English articles with verifiable listed-entity evidence.
- [ ] Connect and test the resolver against the shared exception and metadata contracts.

---

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
