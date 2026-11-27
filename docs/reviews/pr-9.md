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
