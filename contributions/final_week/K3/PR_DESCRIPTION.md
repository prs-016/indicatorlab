# HK follow-up for the shared market-layer contribution

HK intraday orders could previously execute during lunch even though calendar
validation rejected the same timestamps. Missing lot records also assumed a
100-share lot. This revision applies the actual exchange schedule to single
and composite HK fills and terminal liquidation, changes missing-lot fallback
to one share with a warning, and adds an explicit daily-FX loader adapter.

## Changes

- Reuse XHKG holidays, sourced weather exceptions and half days for actual HK
  execution. Synchronize the composite fill clock and actual run interval.
- Preserve supplied lot sizes and cash leftovers; disclose missing-size
  assumptions. Explicit strict lot coverage remains available.
- Acquire complete daily `HKD=X` frames through Vibe's existing loader and
  require a caller-supplied close/publication policy before historical USD
  marking. Prior known rates carry forward; missing initial FX never backfills.
- Expose a sourced historical weather inventory and compare supplied daily
  `^HSI` bars against sessions. Missing bars retain their data-quality meaning
  until a historical closure is corroborated.
- Retain bilateral whole-HKD stamp-duty rounding and the dated 2021/2023
  boundaries. Existing broker, legacy flat-fee and slippage inputs remain
  explicit assumptions rather than a certified statutory cost schedule.

## Validation

260 selected tests passed across 14 files, including HK execution/FX/lot tests,
US/India/UK behavior, routing, calendar validation and the HSI loader. The run
emitted one existing Python 3.14/Pydantic-v1 compatibility warning. Scoped Ruff
passes and all seven touched Python files conform to Black. The incremental
nine-file patch passes `git apply --check` against the source checkout.
No empirical strategy cohort or frozen input/result was changed or rerun.

## Scope and remaining decisions

This is the HK half. The actual India implementation and joint interface still
need to be combined and tested before describing a shared India/HK B3 PR as
complete. Local checks are not remote CI or team acceptance. Every new upstream
commit must use `git commit -s`; no commit or remote push is made by this handoff.

Daily source labels do not certify FX completion/publication instants. The
adapter requires an explicit policy and reports that historical publication
times are not independently certified. Additional historical missing `^HSI`
bars need corroboration before a new closure is added.

The pre-existing 95-row HKEX-derived lot CSV is byte-identical and is not added
by this incremental patch. Its redistribution permission is unverified under
the HKEX website terms. Before publication, clear rights for the existing PR's
copy or omit it and use an operator-provided dated table. No fresh workbook was
downloaded and no publication-rights certification is claimed.

Full contract and sources: `agent/backtest/HK_FINAL_K3.md`.
