> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# Alpha101_002 volume reconciliation and readiness

**12/12 targeted volume inconsistencies are independently verified and reconciled in a new research_v4.** Recommend this version for a provisional alpha101_002 diagnostic, pending user review and explicit backtest approval. No portfolio backtest was run, and this is not whole-tape volume certification or a final strategy decision.

## Version and preserved inputs

New dataset: `archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/`.
Parent: `archive:india_session_phase4d_20261029T020413Z_05541bac/research_v3/`, manifest SHA-256 `a99d6671002b8c15dc406d7b532556ee95cb96cb5503dd9e8555253d17e3ca42`.

The new version contains all nine full historical derived series, not merely the analysis slice. Exactly **12 CSV volume tokens** changed. Every date, price, adjustment ratio, other field and unaffected row token is unchanged; the six unaffected series files, including the benchmark, remain byte-identical. Original downloaded Yahoo and NSE files, all earlier manifests/datasets, the complete STREV output and the complete alpha101_001 output remain unchanged by recorded-hash verification.

The new dataset manifest links and hashes its parent and both JSON/CSV adjustment ledgers. Previous nominal quantities remain in the immutable parent, original NSE archives and each ledger entry. Converted quantities are **research quantities in frozen vendor units**, not claims about actual nominal NSE shares traded on those dates.

## Basis choice and independent evidence

Use the **existing frozen Yahoo volume convention locally surrounding each recovered session**. No unrelated Yahoo rows are rescaled. Corporate-action metadata supplies the multiplier; actual official/vendor quantities independently verify it. No fitted ratio, dividend multiplier, volume rounding, forward fill or guessed quantity is used.

| Stock | Documented later share event | Multiplier for all four recovered sessions |
|---|---|---:|
| RELIANCE.NS | 1:1 bonus, ex-date 2024-10-28 | 2 |
| HDFCBANK.NS | 1:1 bonus, ex-date 2025-08-26 | 2 |
| KOTAKBANK.NS | Face-value subdivision 5 to 1, ex-date 2026-01-14 | 5 |

The saved official NSE corporate-actions JSON is hash-verified and each transcribed action is matched back to its actual EQ response record. Supporting issuer/exchange evidence was previously retrieved and remains preserved: [Reliance issuer notice](https://www.ril.com/sites/default/files/2024-10/SE_16102024.pdf), [HDFC Bank issuer filing](https://www.sec.gov/Archives/edgar/data/1144967/000119312525191696/d22509dex99.htm), and [Kotak NSE notice](https://nsearchives.nseindia.com/content/circulars/CML72216.pdf). These are corporate-action metadata, including later events reflected in the frozen vendor vintage; no holdout prices were retrieved or used.

For every converted observation:

1. The original NSE archive is hash-verified and reparsed. Existing official verifiers require a unique EQ record, date/ISIN/OHLC validity and positive quantity, turnover and trade count. The parent's nominal quantity must equal that record.
2. The existing `parse_action` procedure classifies official actions. Only later bonus/split share multipliers through the frozen October 28, 2026 metadata horizon scale volume. Cash dividends do not scale volume. Unknown/duplicate actions and share changes inside an anchor bracket prevent verification.
3. Two independent NSE/Yahoo quantity records bracket the date and must satisfy **vendor quantity = official nominal quantity × documented share multiplier exactly**. The raw Yahoo source file, NSE archive URL/file/hash, values, event metadata and checks are retained. An approximate quantity match cannot define or calibrate the multiplier.
4. Only a fully verified conversion is written. All twelve must pass before the dataset directory is created.

## All twelve verified conversions

| Date | Stock | Official nominal shares | Multiplier | New research volume |
|---|---|---:|---:|---:|
| 2023-11-12 | HDFCBANK.NS | 1,975,463 | 2 | 3,950,926 |
| 2023-11-12 | KOTAKBANK.NS | 200,366 | 5 | 1,001,830 |
| 2023-11-12 | RELIANCE.NS | 709,922 | 2 | 1,419,844 |
| 2024-01-20 | HDFCBANK.NS | 12,920,293 | 2 | 25,840,586 |
| 2024-01-20 | KOTAKBANK.NS | 5,456,020 | 5 | 27,280,100 |
| 2024-01-20 | RELIANCE.NS | 3,641,697 | 2 | 7,283,394 |
| 2024-03-02 | HDFCBANK.NS | 895,265 | 2 | 1,790,530 |
| 2024-03-02 | KOTAKBANK.NS | 179,918 | 5 | 899,590 |
| 2024-03-02 | RELIANCE.NS | 358,150 | 2 | 716,300 |
| 2024-05-18 | HDFCBANK.NS | 528,557 | 2 | 1,057,114 |
| 2024-05-18 | KOTAKBANK.NS | 291,295 | 5 | 1,456,475 |
| 2024-05-18 | RELIANCE.NS | 213,020 | 2 | 426,040 |

### Exact bracketing support

| Recovered date | Left/right anchor dates | Stocks |
|---|---|---|
| 2023-11-12 | 2023-11-10 / 2023-11-13 | All three |
| 2024-01-20 | 2024-01-19 / 2024-01-23 | All three |
| 2024-03-02 | 2024-03-01 / 2024-03-04 | Reliance, HDFC Bank |
| 2024-03-02 | 2024-01-23 / 2024-03-04 | Kotak Bank |
| 2024-05-18 | 2024-05-17 / 2024-05-21 | All three |

Kotak's nearest left record on March 1 is deliberately **not accepted as exact support**: vendor 17,220,745 versus NSE 3,444,150 × 5 = 17,220,750. The five-vendor-share discrepancy is retained and remains unexplained; rounding/revision is not asserted as a fact. The conversion instead uses January 23 (6,780,824 nominal; 33,904,120 vendor) and March 4 (2,777,198 nominal; 13,885,990 vendor). Both are exact fivefold matches, with no intervening share action in the official record. The wider bracket and all rejected candidate attempts are explicit in the ledger. No tolerance was relaxed to obtain a pass.

## Signal-only recalculation

Only the unchanged original Vibe **alpha101_002** was recalculated, through the existing isolated `evaluate_factor` bridge. No other factor was recalculated and no portfolio simulator was invoked. Original open/close prices and factor formula remain unchanged. The working 25-session warm-up (November 26, 2020–January 1, 2021), 990-session evaluation through December 31, 2024, eight-stock universe and separate benchmark are unchanged.

The original date clock is preserved exactly for all 1,015 analysis sessions. Original portfolio settings remain recorded but are not executed: weekly top-two 50/50, subsequent eligible close, 10-bps absolute-NAV turnover cost, execution-aligned IC and daily net sqrt(252) Sharpe. No IC, Sharpe, portfolio cumulative return, orders or holdings were calculated.

Coverage after reconciliation:

- **7,916/7,920 finite evaluation scores**; four NaNs; 986/990 sessions have all eight finite.
- **208/209 weekly candidates** have all eight finite. The count includes the terminal December 31 candidate, which cannot execute after the cutoff.
- The same four intrinsic constant-rank NaNs remain: HDFCBANK.NS on August 9–11, 2021 and RELIANCE.NS on March 25, 2022. Only March 25 is a weekly signal date. No source observations are filled to eliminate these legitimate original-factor NaNs.
- No weekly top-two cutoff ties are introduced; daily exact-score ties remain on two dates.

Compared with research_v3, scores change on **32 daily dates**, common-name ranks on **31**, and candidate top-two membership on **18 daily dates**. Signal availability does not change. The new scores match the previously saved controlled volume-unit diagnostic within 1e-12; CSV index-name metadata is normalized for that numerical comparison.

| Weekly date | research_v3 candidate pair | research_v4 candidate pair |
|---|---|---|
| 2024-01-25 | RELIANCE.NS, AXISBANK.NS | RELIANCE.NS, HDFCBANK.NS |
| 2024-03-07 | TCS.NS, AXISBANK.NS | TCS.NS, SBIN.NS |
| 2024-05-24 | INFY.NS, ICICIBANK.NS | ICICIBANK.NS, HDFCBANK.NS |

These are **three membership changes**, not measured trades or performance differences. On November 17, 2023 the ordering changes from AXISBANK/HDFCBANK to HDFCBANK/AXISBANK; the same two stocks remain selected, so the equal-weight candidate target does not change. Ordered-pair changes and membership changes are separately recorded to avoid overstating the effect.

## Readiness decision and residual limits

**The identified twelve mixed-unit observations are resolved: 12 verified, 0 unresolved target conversions.** The specific material blocker that changed three weekly candidate memberships has been removed in a versioned, evidence-backed dataset. Recommend user approval of a provisional diagnostic using this exact research_v4, with the ordinary four NaNs retained and all existing methodology settings unchanged.

This conclusion is deliberately narrower than saying all historical volume conventions are proven:

- The extra pre-July-20, 2023 Reliance vendor volume/price scaling (approximately 2.166848 versus a twofold later bonus scale) remains unexplained in its exact vendor formula. The official demerger event and numerical boundary were verified previously; that does not establish a split or authorize an empirical-ratio repair. No recovered target date predates that event, so it is not used to derive any of these twelve multipliers. Its potential interpretation/signal-normalization limitations remain disclosed for a provisional experiment.
- Kotak's five-vendor-share March 1 discrepancy remains unchanged and cannot be represented as independently explained. It is distinct from the fivefold unit mismatch repaired in the recovered rows.
- The surrounding-volume convention is independently supported by actual records, but the full vendor tape is not certified session by session. Frozen prices/volumes are not historically point-in-time. Other research-view flags and incomplete exhaustive calendar-inventory certainty remain.

No newly verified unresolved **target volume inconsistency** remains. Unresolved vendor normalization and small historical record differences are retained as explicit research limitations, not silently declared resolved or transformed. If the user requires independently reconstructed nominal-volume history across every session, this version does not provide that and further source acquisition would be needed.

`backtest_ready=false`, `calendar_certified=false` and `portfolio_backtest_authorized=false` remain in the new manifest: this task approves data preparation and signal diagnostics only. Neither old STREV nor alpha101_001 diagnostic overrides apply to research_v4. A later run requires its own explicit approval and dataset-bound validation; no global gate was disabled.

## Code, tests and artifacts

- New `src/india_volume_reconciliation.py`: source-independent share-event audit, two exact anchor checks, token-preserving volume edits and an immutable twelve-conversion writer. It reuses `parse_action`; original factors, data adapters, STREV/alpha101_001 runners and portfolio accounting are not edited.
- New `tests/test_india_volume_reconciliation.py`: **25 offline synthetic cases** covering all twelve symbol/date conversions, rejection of inferred ratios/approximate anchors, cash versus share actions, cutoff/missing/unknown/duplicate evidence, byte preservation, no rounding, immutable versions, incomplete-ledger rejection and order-only versus membership effects.
- Complete suite: **218 passed in 23.54 seconds**, no failures or skips. Command:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

The output directory preserves the offline builder, verified event/quantity ledger, every rejected anchor attempt, exact changed-token list, signal matrices, NaN causes/coverage, daily and weekly before/after selections, comparison statistics, source hashes, protected-input inventory, test log and readiness review. The first prewrite attempt lacked UDiFF handling and created no dataset; the final builder handles both archive formats. A post-calculation comparison initially stopped on CSV index-name metadata, then completed after normalizing that metadata; no numeric input or output was changed to pass the check.

All original quantities, prices, previous datasets and prior backtest artifacts remain preserved. No portfolio backtest, package installation, commit, push or publication. Stop for review.


## Interrupted-task finalization — October 28, 2026 (Pacific)

**Finalized without rebuilding research_v4 or repeating factor/reconciliation calculations.**
The exact dataset manifest remains SHA-256
`9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`.
All 11 dataset-manifest files, 279 protected input/artifact hashes, twelve exact
volume-token changes and 24 independent quantity anchors passed verification.
The original NSE archives were reparsed for evidence checks only; no transformed
quantity or factor score was regenerated. All price/other CSV tokens and line
endings remain unchanged. STREV and alpha101_001 archives remain untouched.

The historical `build_execution_log.txt` is preserved byte-for-byte. Its final
index-name assertion (`None` versus `date`) is explained in the separate
`build_log_annotation.json`; the saved scores, dates and NaN patterns compare
successfully after normalizing only index-label metadata. The original numeric
error log was not rewritten to suggest that its first invocation succeeded.
The earlier inventory and report are retained as
`artifact_hashes.pre_finalization.json` and
`readiness_review.pre_finalization.md`.

The current outer `artifact_hashes.json` now inventories every finalized file
recursively, including historical copies, annotations, the read-only verifier
and the new test log. Only that root inventory itself is excluded to avoid a
self-referential hash. `inventory_repair_notes.json` records the three stale
entries and six previously unindexed files identified before finalization.

The complete automated suite was rerun with the established project-.venv
command: **218 passed in 19.89 seconds**, no failures or skips. The original
`test_results.txt` is preserved; the new run is saved separately as
`finalization_test_results.txt`. `verify_existing_v4.py` and
`finalization_validation.json` record the independent checks without invoking
the reconciliation writer, factor worker or portfolio simulator.

**Readiness recommendation: ready for one provisional alpha101_002 diagnostic
using this exact research_v4, pending explicit user approval.** All twelve
targeted material mixed-unit inconsistencies are resolved. The four intrinsic
NaNs and three changed weekly candidate memberships remain as reported above.
This is not whole-tape or historically point-in-time certification: the
unexplained pre-July-2023 Reliance vendor normalization, five-vendor-share Kotak
discrepancy and exhaustive calendar-inventory limits remain disclosed. Existing
manifest certification/backtest-approval flags stay false; no earlier diagnostic
override is transferred to this version. No portfolio backtest, commit, push or
publication occurred. Stop for user review.
