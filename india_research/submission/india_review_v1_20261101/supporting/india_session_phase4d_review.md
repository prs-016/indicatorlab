> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# Phase 4D: January 20, 2024 reconciliation

**Decision: STREV is not ready. The backtest gate remains closed.** January 20 is now reconciled, but numerical calendar agreement does not prove exhaustive official calendar-amendment coverage.

## Evidence and method

New version: `archive:india_session_phase4d_20261029T020413Z_05541bac/research_v3/`. The parent is Phase 4B `research_v2`; all previous rows, original Yahoo files and manifests remain unchanged, checked by SHA-256 and frame equality. No prices were fetched after December 31, 2024. No portfolio evaluation ran.

The January 20 equity bhavcopy and separate index publication were retrieved in Phase 4C and reverified from their preserved bytes. Phase 4D retrieved the January 23 bhavcopy; the first request timed out, and a subsequent request succeeded. The existing January 19 bhavcopy supplies the left anchor. January 22 is a documented closure, not a missing price row.

Official sources:

- [January 20 equity bhavcopy](https://nsearchives.nseindia.com/content/historical/EQUITIES/2024/JAN/cm20JAN2024bhav.csv.zip)
- [January 20 Nifty publication](https://nsearchives.nseindia.com/content/indices/ind_close_all_20012024.csv)
- [January 19 equity anchor](https://nsearchives.nseindia.com/content/historical/EQUITIES/2024/JAN/cm19JAN2024bhav.csv.zip)
- [January 23 equity anchor](https://nsearchives.nseindia.com/content/historical/EQUITIES/2024/JAN/cm23JAN2024bhav.csv.zip)

`src/india_phase4d.py` orchestrates the existing `verify_equities`, `verify_nifty50`, `audit_conversion`, `reconstruct_calendar` and `audit_calendar` functions. It adds no alternate adjustment formula. Every equity has a unique EQ record, matching date/ISIN, valid OHLC, positive traded quantity, traded value and trade count. Nifty 50 is separately verified as price-index points, not a tradable EQ security or total-return index; its reported constituent volume is not an index trade count.

## Verified January 20 observations

| Symbol | Nominal NSE close | Shares traded | Trades | Conversion factor | Adjusted close |
|---|---:|---:|---:|---:|---:|
| RELIANCE.NS | 2713.30 | 3641697 | 128579 | 0.494042211463 | 1340.48473236 |
| TCS.NS | 3860.65 | 516477 | 47373 | 0.915353372504 | 3533.85899756 |
| INFY.NS | 1648.85 | 1158144 | 41544 | 0.921543196004 | 1519.48649873 |
| HDFCBANK.NS | 1478.85 | 12920293 | 403196 | 0.478767160332 | 708.02481506 |
| ICICIBANK.NS | 1008.70 | 8788873 | 172248 | 0.975647824715 | 984.13596079 |
| SBIN.NS | 631.40 | 9886760 | 133765 | 0.947076138312 | 597.98387373 |
| KOTAKBANK.NS | 1806.80 | 5456020 | 222642 | 0.199207037578 | 359.92727550 |
| AXISBANK.NS | 1121.00 | 5055594 | 113131 | 0.997606158279 | 1118.31650343 |

Separate **Nifty 50 close: 21,571.80**, published constituent volume 162,073,740. No equity conversion factor is applied to the index.

**8/8 stock conversions verified; zero unresolved January 20 conversions.** Including the inherited 24, all 32 recovered stock/date conversions are now incorporated. The ledger records both anchor prices, source URLs/hashes, split and dividend factors, each cash step and each tolerance check. The parent ledger remains authoritative for its original 24 rows.

The Phase 4B formula is reused: adjusted price = nominal price / later share multiplier × frozen terminal Yahoo dividend ratio × subsequent pre-cutoff cash-dividend steps. Later share multipliers are 2 for Reliance, 2 for HDFC Bank, 5 for Kotak Bank and 1 for the others. Cash dividend effects remain separate. Both January 19/23 anchors independently pass split-scale, dividend-factor and total-factor checks at the established 8-float32-epsilon tolerance. Official January 20 OHLC is scaled by the verified factor; actual nominal volume is preserved, without inferred volume rescaling.

TCS went ex-dividend January 19 (Rs 9 ordinary + Rs 18 special = Rs 27). The January 19 close is already post-action, so this cash step is correctly excluded from January 20's subsequent-dividend product. Using January 18 as the left anchor across this action is rejected by the unchanged conversion function. No adjustment event occurs inside the January 19–23 bracket.

The normalization limitation remains: the December 31, 2024 frozen Yahoo Adj Close/Close ratio defines the vendor vintage. Post-2024 cash adjustments are not independently reconstructed, and these are not point-in-time historical price vintages. Later corporate-action metadata is inherited from Phase 4B; no holdout prices are used. All original unresolved anomaly flags remain applicable; no unrelated prices are repaired or excluded.

## Full calendar rerun and remaining evidence gaps

The audit covers January 4, 2021–December 31, 2024, plus the required **21 warm-up sessions December 3, 2020–January 1, 2021**, using the complete Phase 4C annual rules and overrides. January 1, 2021 is warm-up, explaining the 247 evaluation sessions in 2021.

- Expected evaluation sessions: **990** (2021: 247; 2022: 248; 2023: 246; 2024: 249).
- All eight equities and benchmark have the required records and valid closes: **zero discrepancies** against the reconstructed calendar.
- Missing/unverifiable dates under the retrieved rules: **zero**. This does not establish that no undiscovered amendment exists.
- 21-session stock/date lag mismatches: **zero**, down from 176. All 7,920 evaluation stock/date lookbacks match the expected clock.
- Weekly January 19 signal's next expected session is January 20, not January 23. The schedule is an availability audit, not executed trades.
- Muhurat sessions (2021-11-04, 2022-10-24, 2023-11-12, 2024-11-01), live Saturdays (2024-01-20, 2024-03-02, 2024-05-18), June 2023 holiday rescheduling and 2024 exceptional closures remain in the audit.

**Certification remains incomplete.** The annual circulars plus collected exceptional-session/amendment evidence do not prove an exhaustive amendment inventory. Phase 4C's direct cash-market circular retrievals for June 29, 2023 and January 22, 2024 failed; these dates have official corroborating records, but those failures are not proof of closure. Historical index inventory API attempts returned HTML and remain unusable. These are inherited evidence limitations, not newly discovered price discrepancies. See `india_calendar_phase4c_review.md` for URLs, issuance dates and access findings. No new claim of comprehensive source retrieval is made in Phase 4D.

`amendment_coverage_confirmed=false`, `calendar_certified=false`, and `backtest_ready=false` are retained in the new manifest/readiness file. No calendar-certified dataset is created. A complete official amendment/session inventory or an explicitly approved alternative scope is still needed before lifting this gate. Filling January 20 does not authorize bypassing it.

## Reproduction and artifacts

From repository root, after placing a verified January 23 retrieval manifest/archive in a new evidence directory:

```bash
.venv/bin/python -B -m src.india_phase4d NEW_EVIDENCE_DIRECTORY
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

The workflow reads frozen Phase 4B/4C evidence, rejects checksum failures and existing output versions, and never downloads. The output contains nine derived histories, JSON/CSV conversion ledgers, official quotes, expected calendar, discrepancies, lookbacks, weekly execution candidates, readiness and a manifest hashing evidence, original files, code and generated artifacts. Prior source paths are intentionally retained, not copied or overwritten.

Offline synthetic regressions cover all eight symbols' January 20 conversion boundary, rejection of a bracket crossing January 19's dividend, tampered source hashes, immutable versions, and filling the gap without opening the calendar gate. Existing official-record validation tests cover positive quantities/trades, separate benchmark handling and invalid records. Real-data artifact validation separately checks all eight ledger results and every generated hash; it is not a portfolio backtest.

**Executed validation:** complete project-.venv suite: **120 passed in 9.76s**, zero failures/skips. Separate real-artifact validation passed all original/evidence/code/output hashes, 8/8 conversion ledgers and 7,920 clock comparisons. No real-data strategy evaluation was executed.

## Final calendar review addendum

The subsequent [final readiness review](india_strev_final_readiness_review.md) recommends a provisional diagnostic only, pending user approval. New NSE Indices holiday-amendment evidence and 45 additional official instrument/date records support the calendar reconstruction. No specific material calendar discrepancy remains; exhaustive archive-wide certainty is not claimed. This scoped recommendation supersedes this report’s blanket diagnostic blocker, while the immutable historical manifest and strict certification flags remain unchanged. No backtest is authorized or executed by the review.
