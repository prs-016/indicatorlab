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

## Follow-up review — November 27, 2026

The 100-company acceptance test now recognizes verified exact titles,
parent and group proxies, and a documented unavailable title. The
previous English-title blocker is resolved under the updated acceptance
policy. The patch retains the existing CSV columns, ledger fields,
resolver metadata keys, pipeline output columns and Reddit communities.

The 72 N1, configuration and Reddit regression tests passed, including
54 focused N1 and mapping tests. James's pipeline, attention, edits and
titles suites passed all 35 tests with ten pandas deprecation warnings.
A separate offline check passed all 11 proxies through James's article
selection, ticker-keyed cache naming and weekly output functions.
Solar Industries was omitted from acquisition and remained available for
stock lookup. Black, Ruff and Git whitespace checks passed. Coverage
percentage was not measured.

The prior 97 English title mappings, 67 Hindi titles and 12 historical
records were compared against the previous commit and preserved. The two
group articles returned public revisions and three days of pageviews each.
Proxy provenance stays in the registry and evidence ledger. James still
owns the optional pipeline hook and must retain that provenance when
enabling proxies. Teammate review of this revision is required before merge.
