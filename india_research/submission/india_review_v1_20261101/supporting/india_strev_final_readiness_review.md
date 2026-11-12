> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# Final calendar readiness review: Phase 4D research_v3

**Recommendation: suitable for a narrowly scoped provisional diagnostic STREV backtest, pending explicit user approval. No identified material calendar discrepancy remains.** This is a research readiness assessment, not exhaustive historical certification, authorization to run, or approval of final strategy results.

This review supersedes the blanket calendar-completeness blocker in the earlier Phase 4D review for the purpose of recommending a diagnostic experiment. It does not modify the frozen dataset, historical manifests, executable certification gate, portfolio methodology or factor definitions.

## Scope and verified comparison

Dataset: `archive:india_session_phase4d_20261029T020413Z_05541bac/research_v3/`. Its manifest, every generated dataset artifact, recorded original files, underlying evidence and recorded source-code hashes were rechecked successfully. New evidence and independent audit outputs are preserved in `archive:india_readiness_final_20261029T021058Z/` with source URLs, retrieval timestamps, original bytes and SHA-256 hashes.

The evaluation runs January 4, 2021 through December 31, 2024; January 1, 2021 is a real trading session used for warm-up. The required 21 preceding sessions are December 3, 2020–January 1, 2021. An earlier November 2020 Muhurat session cannot enter that 21-session window and is outside this audit's required scope.

| Period | Expected sessions | Matching dates in each of all nine histories |
|---|---:|---:|
| Required warm-up | 21 | 21 |
| 2021 evaluation, January 4 onward | 247 | 247 |
| 2022 | 248 | 248 |
| 2023 | 246 | 246 |
| 2024 | 249 | 249 |
| Evaluation total | 990 | 990 |

This is exact date-set equality, not merely matching aggregate counts. All 1,011 required dates occur in each of the eight assigned equities and ^NSEI, with usable positive closes; no supplied record appears on a reconstructed closure in that scope. The audit found zero missing sessions, zero invalid/missing closes or stock volumes, zero dated unknown classifications and zero mismatches in 7,920 stock/date 21-session lag comparisons. Weekly subsequent-session candidates were regenerated without selecting holdings or calculating returns. The final signal has no permitted execution after the cutoff.

## Authoritative calendars and amendments reviewed

The annual capital-market circulars were reread against the saved rule transcription:

- [2020 CMTR42877](https://nsearchives.nseindia.com/content/circulars/CMTR42877.pdf), issued December 11, 2019: establishes the December warm-up holiday basis.
- [2021 CMTR46623](https://nsearchives.nseindia.com/content/circulars/CMTR46623.pdf), issued December 11, 2020.
- [2022 CMTR50560](https://nsearchives.nseindia.com/content/circulars/CMTR50560.pdf), issued December 10, 2021.
- [2023 CMTR54757](https://nsearchives.nseindia.com/content/circulars/CMTR54757.pdf), issued December 8, 2022.
- [2024 CMTR59722](https://nsearchives.nseindia.com/content/circulars/CMTR59722.pdf), issued December 12, 2023.

Weekday sessions and weekend closures follow those exchange rules, with live-session and holiday amendments explicitly overriding them. Settlement-only, debt-market and mock-trading notices are not treated as equity closures or live sessions.

| Exception | Evidence and conclusion |
|---|---|
| 2021-11-04 Muhurat | CMTR50050, October 21, 2021; actual equity and separate index records newly verified. |
| 2022-10-24 Muhurat | CMTR54023, October 11, 2022; actual equity and separate index records newly verified. |
| 2023-11-12 Muhurat | CMTR59124, October 27, 2023; actual trading/index records and 8 conversions already verified in Phases 4A/B. |
| 2024-11-01 Muhurat | CMTR64628, October 19, 2024; actual equity and separate index records newly verified. |
| 2024-01-20 live Saturday | Final MSD60340, January 19, 2024 supersedes earlier DR plans; actual records and 8 conversions verified in Phase 4D. |
| 2024-03-02 live Saturday | MSD60677, February 14, 2024; actual records and conversions verified in Phases 4A/B. |
| 2024-05-18 live Saturday | MSD61893, May 7, 2024; actual records and conversions verified in Phases 4A/B. |
| 2023-06-28 open; June 29 closed | Actual June 28 equity/index records preserved in Phase 4C. New NSE Indices release directly confirms the exchange's trading-holiday amendment. |
| 2024-01-22 closed | NSE SURV60342, January 19 explicitly identifies the revised trading holiday and refers to positions as of January 20; clearing corroboration is also preserved. |
| 2024-05-20 closed | Cash-market CMTR61518, April 8, 2024, election holiday. |
| 2024-11-20 closed | Cash-market CMTR64960, November 8, 2024, election holiday. |

The new [NSE Indices press release of June 27, 2023](https://www.niftyindices.com/Press_Release/ind_prs27062023.pdf) explicitly identifies CMTR57285 and the holiday change from June 28 to June 29, with index changes moved to the June 28 close. This is authoritative trading-calendar corroboration, rather than inference from a settlement holiday. The original cash circular's earlier retrieval failure therefore does not leave an unresolved date classification. Likewise, [NSE SURV60342](https://nsearchives.nseindia.com/content/circulars/SURV60342.pdf) directly confirms the January 22 trading holiday despite the inaccessible original CMTR60338. Missing access to the original notice is a provenance limitation, not evidence of a possible extra session on those dates.

Fresh official daily verification covered December 3, 2020; January 1, 2021; November 4, 2021; October 24, 2022; and November 1, 2024: **40 unique EQ records and 5 separate Nifty 50 records**. Each equity has the matching date/ISIN, valid OHLC, positive quantity, turnover and trade count. November 2024 uses NSE's UDiFF archive, mapped to the existing official verifier after validating CM/NSE/STK and both trade/business dates. Raw records and source hashes are in the new evidence directory; `additional_official_records.csv` is a calendar-evidence table, not an instruction to insert unadjusted prices. The older recovered-session verification remains linked through unchanged ledgers. No nominal record was substituted into the adjusted dataset.

The web reader could not reopen the 2021/2022 Muhurat PDFs on one archive host; their previously retrieved bytes and hashes remain available, and fresh actual daily records independently establish those sessions. These access failures do not undermine the session classification.

## What is confirmed, what remains limited, and materiality

**Confirmed:** exact agreement between every required dataset date and the authoritative-rule reconstruction with the documented exceptions; actual instrument-specific trading and index publication on every identified exceptional live session; complete warm-up in the dataset; unchanged 21-session and weekly next-session clocks. No additional missing or contradictory session was identified by this review.

**Not conclusively proven:** an exhaustive archive-wide inventory of every amendment and actual daily publication for all 1,011 dates. Only the targeted official daily records and previously preserved evidence were independently inspected, not all 9,099 instrument/date records from official daily archives. The historical-index inventory API's earlier HTML responses remain unusable. Searches for further 2021–2024 holiday amendments/live Saturdays did not establish a complete inventory; absence from search results is not proof that no further notice exists. Rule-based reconstruction remains an evidence-supported inference for ordinary sessions.

An undiscovered genuine session would be material: it could shift the affected 21-session endpoints and the next eligible execution date, as the repaired January 20 omission demonstrated. However, there is currently **no specifically dated unresolved candidate**, contradictory notice, unexplained extra date or missing expected session. The remaining uncertainty is a nonspecific archival-coverage risk, not an identified calendar error. Requiring proof of absence of every unknown historical notice would exceed what is necessary for this diagnostic research run. A reasonable decision is to accept that residual uncertainty explicitly, while requiring any later concrete contradiction to stop the run, invalidate affected outputs and trigger a versioned calendar review.

January 19, 2024's next execution candidate is correctly January 20; January 22 remains closed. All live weekend and Muhurat dates stay in the session clock regardless of shorter hours. Execution-at-close and liquidity assumptions on short sessions remain portfolio-model limitations, not grounds to delete valid sessions. No new execution or trading assumption is approved here.

The **frozen Yahoo adjustment vintage is a separate documented research limitation**, not a calendar failure. The series are retrieval-time adjusted histories and are **not historically point-in-time data**. Post-2024 corporate-action effects embedded in their scale remain disclosed. This review does not independently reconstruct those effects or endorse point-in-time financial conclusions. Other unresolved price-quality flags remain visible and must accompany a diagnostic result; none were repaired or excluded by this review.

## Scoped recommendation and approval boundary

Recommend user approval for **one provisional diagnostic academic_strev experiment**, using only the frozen Phase 4D research_v3, the eight assigned stocks and separate ^NSEI benchmark, January 2021–December 31, 2024 with the 21-session warm-up, and the existing developer-approved configurable baseline. Preserve original factor calculations, special sessions, raw snapshots, all unresolved quality flags and the October 1, 2025 onward holdout restriction. Save configuration, dataset/manifest hashes, metrics definitions, execution logs, flags and this review with any approved output. Report results as provisional; no final strategy acceptance, optimization, other strategy evaluation or publication is implied.

The recorded `calendar_certified=false` and `amendment_coverage_confirmed=false` remain historically accurate for **exhaustive certification**. They should not be relabelled true merely to run a diagnostic. `readiness_recommendation.json` separately records the scoped assessment with `diagnostic_authorized=false`. Existing dataset manifests and executable gates are unchanged. Before a run, explicit user approval must be recorded and any diagnostic-only gate handling made transparent; this review itself neither implements nor authorizes bypassing validation.

## Validation and reproducibility

The new directory contains the original retrieval manifest/bytes, `audit_final_readiness.py`, exact date-set/lag/schedule outputs, `readiness_recommendation.json`, source/output hashes and test log. The audit script runs offline from repository root with `.venv/bin/python -B archive:india_readiness_final_20261029T021058Z/audit_final_readiness.py`; it recomputes structural outputs and checks the immutable Phase 4D dataset and its inherited source hashes. It does not certify, download, change strategy logic or run portfolios.

Relevant offline regression command:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider tests/test_india_calendar.py tests/test_india_reconciliation.py tests/test_india_adjustments.py tests/test_india_phase4d.py
```

**58 passed in 2.17 seconds; zero failures or skips.** These cover calendar reconstruction/unknown evidence, 21-session warm-up, next-session execution candidates, instrument-specific official verification, corporate-action boundaries, source integrity and keeping strict certification false when inventory coverage is unproven. Separate real-artifact assertions passed all hashes, exact 1,011-date equality for each series, 7,920 lag comparisons, 45 new official records and all 32 previously recovered stock conversions. No backtest ran; no raw data, source dataset or prior manifest changed; no commit or push occurred.
