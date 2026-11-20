# Week 4 B2: Hang Seng Index universe

Use **B2_ON_NIFTY.patch** for the guide's stacked B2 route. Its exact dependency is
Jampip/Vibe-Trading `feat/alpha-bench-nifty100` commit
`342259f40d04ad79f586f9585384ce44b3025058`. It adds HSI alongside NIFTY 100 and
preserves the three NIFTY loader/context functions byte for byte. The only change
to a NIFTY backend test is allowing `hsi` in the shared discovery descriptions.

`01_hsi_universe_week4.patch` is an alternate standalone patch for upstream
`1dbe5d515519565a47f0127b4e6d6fc4fbb5e4d2`. Choose one route, never both. Each
manifest records the patch and destination-file SHA-256 hashes. The preferred
route has 27 destination files; the standalone route has 26.

Apply inside the appropriate clean Vibe-Trading checkout:

```bash
git apply --check /path/to/B2_ON_NIFTY.patch
git apply /path/to/B2_ON_NIFTY.patch
```

## What changed

- Backend, API/CLI, both tool descriptions, frontend benchmark/compare selectors,
  HK factor-to-panel mapping and all 11 translations recognize `hsi`.
- Wikipedia is the benchmark source, parsed with pandas; canonical four-digit
  `.HK` codes must be distinct and equal the dated official published count.
  Invalid symbols, duplicates, source failures and missing revision provenance
  fail with safe messages. HTTP failure reasons match the NIFTY implementation.
- The shared HK price chain remains in use with source provenance. Fewer than
  two instruments with observed close prices is a clear error. The HSI sector
  threshold is independently named and set to 90%; VWAP is labeled OHLC4.
- Metadata explicitly records HKD, `equity_hk`, current membership, missing
  observations and the limits of provider-native adjustment/volume conventions.
- `hsi_v3` prevents prior permissive 85-name/frozen-fallback caches from bypassing
  the new strict roster check. No changes are made to other universes' cache keys.
- Existing operational `fetch_constituents()` and its quote fallback are retained;
  the benchmark calls a separate strict helper. No live collector or app changed.

## Real benchmark remains blocked by a source discrepancy

The actual Alpha101 benchmark was attempted on 2026-11-15 for
2016-01-01 through 2026-10-31. The real Wikipedia source returned **85** names;
the dated official reference is **95**, effective 2026-09-07. Strict validation
stopped before prices/factor evaluation (`n_alphas_tested: 0`). See
`benchmark_attempt.json`. No annual price-coverage table or performance statistics
are claimed. The historical v2 benchmark is preserved elsewhere and is not
relabelled as this run.

The Week 4 guide's fail-on-count policy supersedes v2's permissive degraded
benchmark behavior. Wikipedia remains the primary source. The dated official
reference may itself age after later reviews; it is not an automatic substitute
or point-in-time membership. A current source/policy decision is still needed
before a valid full-period benchmark can finish.

Once that discrepancy is legitimately resolved, the portable helper runs the
benchmark and writes annual observed-close coverage only on success:

```bash
python run_hsi_benchmark.py --vibe-root /path/to/Vibe-Trading --output /path/to/bench-evidence
```

## Validation

Backend test commands in `VALIDATION.json` run from `agent/`; frontend commands
run from `frontend/`. The dedicated offline guard is a temporary local test
harness; the product tests mock network calls themselves.

Preferred HSI-on-NIFTY route: **1,228 related backend tests passed, 23 skipped**;
**982 frontend tests passed in 101 files**; TypeScript, scoped Ruff and patch
whitespace passed. A selected 184-test joint suite additionally denied socket and
DNS access: **zero attempts**. Tests mock HTTP calls.

Standalone route: 1,106 related backend tests passed, 23 skipped; 968 frontend
tests passed in 101 files; TypeScript, scoped Ruff and whitespace passed. These
routes/suites overlap; do not add their counts.

B3's HK market patch was also applied on the preferred combined state. Only the
README append needed reconciliation; both usage sections were retained. A
181-test focused HSI/NIFTY/HK-market/composite suite passed. This subset overlaps
the other tests. See `VALIDATION.json` for exact commands and scope.

Existing environment warnings: Python 3.14/Pydantic v1, Vite native-config
migration, and npm package engine minimums above installed Node 24.14.1. All stated
checks passed despite those warnings. This is selected local validation, not the
full upstream backend suite or remote CI.

A signed-off/coauthored local commit is prepared on `feat/alpha-bench-hsi-week4`;
see `LOCAL_BRANCH.json` for its exact head and unchanged NIFTY dependency. No
teammate branch, existing HKVT v2 package, running app, AWS service, remote push
or upstream PR was changed by this package preparation.
