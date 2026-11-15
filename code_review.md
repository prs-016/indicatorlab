# Code Review — HK cross-market coordination update
Reviewed: 2026-11-14 (America/Los_Angeles)
Files reviewed: 25 Vibe target paths plus the contribution-only handoff documents.

## Summary
The package is rebased on upstream 19c83de9 and resolves two real MCP integration
conflicts while preserving newer upstream behavior. HK-specific fixes add dated
roster mismatch disclosure, canonical provenance/conflict handling, no-silent-
alias-price selection, explicit provider-native basis/missing policies, an HSI
availability identity and versioned metadata cache. Wikipedia remains primary;
no prices, units, historical membership or empirical strategy rules were silently
normalized or changed. The teammate's India research branch was inspected only.

## Repo Structure
The branch retains the eight contribution files and five concise root metadata/
documentation files. It contains no copied app, starter tree, raw data, database,
model, private agent source tree or India research. Source changes are isolated
to the Vibe target paths listed in MANIFEST and represented by the split patches.

## Test Coverage
- 141 focused HSI/quotes/metadata/MCP checks passed.
- 1,078 broader benchmark, purity and look-ahead checks passed; 23 skipped.
- The HSI patch alone passed 51 checks with no quote package installed.
- One existing Python 3.14/LangChain Pydantic compatibility warning remains.
- Scoped Ruff/Black, syntax, whitespace and both patch reconstruction routes
  pass. All 25 reconstructed destination hashes match the reviewed source tree.
- This is not the whole upstream suite, GitHub CI or actual HSI+NIFTY integration.
  No new portfolio/factor-performance run was used to validate metadata changes.

## Findings
No unresolved Must fix found in the scoped source review. Adjustment and volume
bases remain provider-native, and upstream filling behavior is disclosed rather
than reversed speculatively. `degraded` is not a complete-data/PIT certification;
consumers must read missing names, provenance, warnings and availability status.
The actual NIFTY fork/PR is still missing; no claim of joint compatibility is made.
The old 85-name exploratory benchmark remains explicitly historical evidence.

## Checklist for the student
- [x] Rebase minimal shared MCP additions without dropping newer upstream code.
- [x] Flag dated roster differences, canonicalize metadata and test ambiguity.
- [x] Register HK identity without inventing PIT verification.
- [x] Validate both patch routes and the standalone universe scope.
- [x] Keep the India branch and original research immutable.
- [ ] Obtain the actual NIFTY contribution and run the proposed joint fixture.
- [ ] Agree strict shared adjustment/volume/membership conventions before a
  scientific cross-market portfolio comparison.
