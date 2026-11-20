Authors: @Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016.

Add the Hang Seng Index as an Alpha Zoo benchmark universe, alongside the NIFTY
100 contribution. `hsi` is accepted by the API, CLI, agent tools and frontend.
Membership is parsed from Wikipedia with revision provenance and checked against
a dated published constituent count; an invalid or unavailable roster fails
clearly instead of substituting a benchmark universe.

Design issue: insert the posted B0 issue URL before publishing.

This branch is stacked on Jampip's NIFTY 100 commit
`342259f40d04ad79f586f9585384ce44b3025058`. The three NIFTY loader/context functions
are unchanged. Shared registrations and translations include both markets. Quotes,
cloud deployment, the market layer, parallel execution and comparison reports are
separate scopes.

HSI uses the shared HK provider chain, canonical `.HK` aliases, source provenance,
explicit missing-data metadata, a 90% sector-coverage gate and a labeled OHLC4
VWAP approximation. Prices remain provider-native; mixed adjustments or unknown
volume units are disclosed. Current constituents/sector labels have survivorship
bias and are not point-in-time membership. `hsi_v3` prevents old permissive roster
caches from bypassing the new validation.

Validation (backend commands from `agent/`, frontend commands from `frontend/`):

```bash
python -m pytest -q tests/test_alpha_bench_*.py tests/test_nifty100_api_cli.py tests/test_nifty100_sector_vwap.py tests/test_bench_universe_selection.py tests/factors/test_alpha_purity.py tests/factors/test_lookahead.py tests/test_hsi_membership_reference.py tests/test_hsi_benchmark_validation.py tests/test_data_availability.py
# 1,228 passed, 23 skipped
npm run test:run
# 982 passed in 101 files
npx tsc --noEmit
# passed
```

Scoped Ruff and whitespace checks passed. The selected 184-test joint HSI/NIFTY
suite also passed with socket and DNS access denied, recording zero attempts.
HTTP calls are mocked in tests. These are local checks, not remote CI or the full
backend suite.

Outstanding benchmark limitation: the real 2016-01-01/2026-10-31 Alpha101 run
stopped at roster validation: Wikipedia has 85 distinct members against the dated
95-member reference effective 2026-09-07. Zero factors were evaluated, and annual
price-coverage counts are unavailable. Resolve the source/policy discrepancy and
append the real benchmark/yearly-coverage evidence before treating B2's required
empirical deliverable as complete. No historical v2 results are relabeled.
