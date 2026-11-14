> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# India snapshot quality review and proposed first STREV methodology

Reviewed: October 28, 2026. **Draft for user approval; not a final strategy report.**

**Phase 3 status update (October 28, 2026):** The developer has since approved the combined Vibe-Trading + Jack approach as the standard India methodology and authorized the configurable provisional baseline's implementation and offline tests. The proposal and approval-gate language below records the earlier review, not a new request to reapprove already authorized work. See [current methodology](methodology.md) for the implemented rules, distinctions from explicit PM approvals, and remaining final-evaluation gate. The original snapshot and findings below are preserved. No final real-data strategy evaluation has been run.

## Scope and evidence

**Phase 4B adjustment update:** See the [new adjustment review](india_adjustment_phase4b_review.md) for 24 verified stock conversions on the explicitly defined frozen Yahoo basis and a separate research_v2. Its official dividend/price reconstruction resolves the three recovered sessions' conversion gate, while full-calendar certification and user review still keep global backtest readiness false. No original snapshot values or manifests were changed; all original quality findings below remain historical observations about that snapshot.

**Session reconciliation update (October 28, 2026):** The subsequent Phase 4 preflight found all nine series omit November 12, 2023, March 2, 2024, and May 18, 2024. Official NSE bhavcopies and separate index CSVs have now verified all 24 equity closes/trading records and all three Nifty 50 closes. See official session reconciliation review (`india_session_reconciliation_review.md`, historical/archival record not included; see archive index) for exact values, sources, volumes/trade counts, adjustment-basis discrepancies, and the new versioned evidence dataset. No nominal stock quotes were inserted into Yahoo's adjusted series; all 24 adjusted conversions remain unresolved and the backtest gate remains closed. The original snapshot and its manifest are unchanged. The observations below describe that original snapshot, not a repaired dataset.

Snapshot: [`archive:india_history_phase2_a6f29fdafeeb/manifest.json`](../evidence/datasets/yahoo_snapshot_manifest.json). Its `raw/` and `derived/` CSVs were inspected and all 18 SHA-256 checksums verified against the manifest. Retrieval ran October 28, 2026, 21:36:42–21:37:00 UTC. There are 56,982 rows across exactly the eight assigned NSE stocks and `^NSEI`; every series ends December 31, 2024. Requests used an exclusive end of January 1, 2025, `auto_adjust=False`, `back_adjust=False`, `repair=False`, `keepna=True`, and corporate actions enabled. No holdout-dated rows are present. Neither data nor strategy code was modified in this review; no portfolio backtest or performance metric was calculated.

Evidence labels: **confirmed observation** means directly verified in this snapshot; **externally confirmed** means supported by the cited exchange/issuer source; **suspected** means an explanation still needs validation; **proposed** means a policy requiring approval. Authoritative findings establish only the claims explicitly described, not correctness of every surrounding price.

Inspected project sources: root `AGENTS.md`, `docs/india_project_context.md`, `india_research/weekly_plan.md`, `india_research/reports/india_data_quality_report.md`, `src/india_data.py`, `src/india_ingestion.py`, and `src/india_vibe_bridge.py`. The manifest's per-ticker flag arrays are the exhaustive machine-readable date inventory; the appendix below reproduces the requested flags for independent review.

## Confirmed snapshot observations

The eight stocks have 70 missing closes, 999 zero-volume rows, 1,148 repeated adjusted closes, and 31 adjusted-close changes strictly exceeding 20%. Of the repeated closes, 916 also have zero volume. Categories overlap. No observed nonpositive or infinite closes were flagged. Missing values include returned rows without prices, not just absent dates. Counts below exclude pre-listing/calendar corrections, since none have been applied.

| Ticker | Rows | Missing closes | Zero volume | Repeated close | Over 20% |
|---|---:|---:|---:|---:|---:|
| RELIANCE.NS | 7291 | 10 | 125 | 127 | 6 |
| TCS.NS | 5566 | 9 | 319 | 314 | 3 |
| INFY.NS | 7291 | 7 | 127 | 133 | 2 |
| HDFCBANK.NS | 7291 | 7 | 125 | 166 | 2 |
| ICICIBANK.NS | 5596 | 10 | 41 | 45 | 1 |
| SBIN.NS | 7291 | 9 | 125 | 141 | 2 |
| KOTAKBANK.NS | 5856 | 8 | 52 | 73 | 10 |
| AXISBANK.NS | 6532 | 10 | 85 | 149 | 5 |
| ^NSEI | 4268 | 30 | 1363 | 4 | 0 |

### Missing closes and session interpretation — high severity

All eight stocks lack closes on 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, and 2015-02-28. Additional stock-specific missing dates are in the appendix. `^NSEI` has 30 missing closes from 2008-11-27 to 2020-11-14.

STREV uses current and 21-row-lagged closes, so the 70 stock gaps cause 140 unavailable endpoint calculations after warm-up on the current individual stock calendars. Shared gaps also make every stock's endpoint unavailable 21 rows later: 2010-03-10, 2012-02-07, 2012-04-03, 2012-10-10, 2012-12-13, 2014-04-24, and 2015-03-31 respectively. These counts describe the current calendar, not a proposed cleaned calendar. Missing rows inside the lookback also affect whether 21 rows correspond to 21 actual sessions. Cross-sectional standardization can be affected for every stock when the valid universe changes.

**Externally confirmed calendar counterexample:** NSE's [2014–15 annual report](https://nsearchives.nseindia.com/global/content/about_us/NSEIL_Annual_Report_2015.pdf), section 1.6.1, identifies February 28, 2015 as a special trading session. All eight stocks and the index have missing closes on that date. This establishes a session-level coverage defect, but does not supply verified replacement stock closes. Never classify every Saturday/Sunday as a non-session. The status of the other shared missing dates remains unresolved here.

### Zero volume and repeated closes — context-dependent severity

All eight stocks have zero volume on July 28, 2005, and on April 24 and October 15, 2014. The two 2014 dates also have repeated stock closes. Stock zero-volume rows end February 28, 2015; most are earlier than 2010. Repeated closes continue later, including Kotak on December 11, 2024. A repeated close with positive volume is not by itself a data error. A zero-volume repeated close can represent a holiday, suspension, stale price, or vendor placeholder; session evidence is needed.

`^NSEI` has 1,363 zero-volume observations from September 17, 2007 to July 3, 2024. Index volume is not an individual-stock execution test. Its four repeated closes occur May 14, 2014; October 27, 2016; March 31, 2017; and May 8, 2024, with no repeated/zero-volume overlap.

Severity: low for isolated repeated positive-volume closes; medium for unexplained zero-volume/flat rows; high when combined with extreme price spikes or when they corrupt the session calendar. Volume does not directly enter STREV, but stale prices and false sessions do.

### All daily adjusted-close changes above 20%

These are observed changes, not independently verified exchange returns. Threshold crossings alone do not prove erroneous data or justify deletion.

| Ticker | Date | Adjusted-close change | Volume |
|---|---|---:|---:|
| RELIANCE.NS | 1996-07-16 | +20.774% | 858,611,628 |
| RELIANCE.NS | 1997-10-27 | +91.135% | 174,379,381 |
| RELIANCE.NS | 1997-11-05 | -48.426% | 95,911,986 |
| RELIANCE.NS | 2005-07-28 | +337.478% | 0 |
| RELIANCE.NS | 2005-07-29 | -76.994% | 106,627,570 |
| RELIANCE.NS | 2009-05-18 | +21.369% | 462,151 |
| TCS.NS | 2004-05-06 | +201.888% | 19,760 |
| TCS.NS | 2005-07-28 | +100.000% | 0 |
| TCS.NS | 2005-07-29 | -50.611% | 8,358,552 |
| INFY.NS | 2003-04-10 | -26.547% | 211,021,376 |
| INFY.NS | 2013-04-12 | -21.259% | 98,027,744 |
| HDFCBANK.NS | 2004-05-17 | -20.644% | 5,221,460 |
| HDFCBANK.NS | 2004-05-18 | +25.817% | 11,226,480 |
| ICICIBANK.NS | 2009-05-18 | +23.038% | 354,381 |
| SBIN.NS | 2009-05-18 | +20.027% | 586,240 |
| SBIN.NS | 2017-10-25 | +27.687% | 262,677,081 |
| KOTAKBANK.NS | 2002-01-31 | +20.016% | 3,032,500 |
| KOTAKBANK.NS | 2002-02-21 | +20.010% | 29,166,700 |
| KOTAKBANK.NS | 2002-03-04 | +20.016% | 64,728,000 |
| KOTAKBANK.NS | 2004-04-26 | +381.435% | 0 |
| KOTAKBANK.NS | 2004-04-27 | -80.203% | 818,000 |
| KOTAKBANK.NS | 2004-10-13 | +370.469% | 0 |
| KOTAKBANK.NS | 2004-10-14 | -78.899% | 779,400 |
| KOTAKBANK.NS | 2005-07-28 | +379.423% | 0 |
| KOTAKBANK.NS | 2005-07-29 | -79.333% | 2,525,900 |
| KOTAKBANK.NS | 2008-10-24 | -21.042% | 44,403,660 |
| AXISBANK.NS | 1999-03-03 | +23.592% | 102,500 |
| AXISBANK.NS | 1999-12-06 | +24.865% | 536,000 |
| AXISBANK.NS | 2003-07-03 | +20.042% | 5,637,970 |
| AXISBANK.NS | 2003-12-03 | +20.042% | 7,206,705 |
| AXISBANK.NS | 2020-03-23 | -27.911% | 37,622,635 |

## Investigation of highest-impact anomalies

### 1. July 28, 2005: confirmed exchange closure; invalid session returns

The [NSE press release dated July 27, 2005](https://nsearchives.nseindia.com/content/press/27072005.pdf) explicitly announces closure of both NSE and BSE on July 28. This is primary exchange evidence, not an inference from volume.

The snapshot nevertheless contains eight stock rows, all with zero volume. Reliance rises 337.48%, TCS 100%, and Kotak 379.42%, followed by apparent collapses on July 29. These July 28 observations cannot be normal NSE session returns. **High severity; confirmed non-session contamination.** On the existing vendor values, comparison from July 27 directly to July 29 gives Reliance +0.644%, TCS −1.222%, and Kotak −0.918%. These are diagnostics showing the spike's effect, not independently validated replacement returns or an applied cleaning operation. Do not separately discard July 29 just because its daily change uses the invalid July 28 denominator; recompute on an approved session calendar first.

### 2. TCS before August 25, 2004: confirmed listing conflict

[NSE's pre-2016 IPO table](https://www.nseindia.com/static/ipo-past-issues/prior-to-2016) lists TCS on August 25, 2004. [TCS's own stock-information page](https://www.tcs.com/investor-relations/stock-information) independently confirms that date. The snapshot contains **532 earlier TCS rows, August 12, 2002–August 24, 2004, including 531 nonmissing closes**. They cannot be accepted as ordinary listed TCS NSE trading history without identifying their provenance. This also disqualifies treating the May 6, 2004 +201.89% jump as an authenticated listed-TCS daily return. **High severity; confirmed instrument-history conflict, exact origin unresolved.** Recommend excluding pre-listing TCS observations from the research view after approval, with a listing-date rule recorded explicitly. Do not alter the original CSV.

### 3. Kotak April 26 and October 13, 2004: likely false sessions, not fully exchange-verified here

Observed zero-volume jumps are +381.43% and +370.47%, followed by −80.20% and −78.90%. Direct adjacent-observation comparisons skipping those suspect rows are −4.688% and −0.728%, respectively. These calculations strengthen suspicion but are not official price validation.

Contemporaneous [PTI reporting for April 26](https://www.rediff.com/money/2004/apr/26closed.htm) states both NSE and BSE were closed for elections. [Reporting dated October 11](https://www.rediff.com/money/2004/oct/11holiday.htm) confirms a BSE holiday on October 13; it is not direct NSE confirmation. These are secondary sources and are labelled accordingly. No primary NSE closure circular was retrieved for these two dates in this review. **High severity; strong closure evidence for April 26, unresolved NSE confirmation for October 13.** Do not elevate a BSE closure to confirmed NSE closure without evidence.

### 4. Reliance 1997 discontinuities and other extremes: unresolved

Reliance's October 27, 1997 +91.13% coincides with a recorded 2:1 split, while November 5 falls 48.43%. This is suspicious adjustment/timing behavior; the vendor event does not prove which price is wrong. No authoritative replacement prices or ex-date reconciliation were obtained. Other >20% events, including Infosys 2003/2013 declines, 2009 multi-stock jumps, SBI in 2017, and Axis in March 2020, remain unclassified rather than being presumed errors. High severity for unresolved scale discontinuities; medium investigation priority for isolated plausible market moves. The prior report's repair experiments were not authoritative validation and are not applied here.

### Access and verification limits

Official NSE historical stock closes/bhavcopies for the suspect dates were not obtained during this review. Some historical press-PDF endpoints, including October 12 and October 23, 2004, were inaccessible through the browsing tool; other accessible releases did not establish the required closure. This does not establish absence of records. No price has been reconstructed or claimed independently verified merely because a search result or secondary story exists. Before full-history evaluation, obtain the missing official session and corporate-action evidence or leave affected windows unresolved.

## Corporate-action basis and potential leakage

There are 25 vendor-recorded splits and 295 dividend events across the eight stocks. The event inventory below records split dates and dividend coverage; raw CSVs retain every exact dividend date/amount. Event dates may represent ex-dates rather than record/allotment dates and must be compared on that basis.

Derived OHLC uses the same positive finite `Adj Close / Close` ratio; volume is unchanged. Derived closes match raw Adj Close within approximately 4.6e-13. The 100 invalid ratios (70 stock and 30 index observations) coincide with missing closes. Every one of 282 ratio changes over 0.1% coincides with a vendor-recorded dividend date. These checks verify transformation consistency, not the exchange correctness of corporate-action histories. Yahoo Close is vendor-adjusted history even with auto_adjust=False; do not apply stock splits a second time. The older Reliance/BSE comparison needed a 2:1 price-basis reconciliation and only supports that January 2024 sample.

The snapshot was retrieved in 2026 and is not a point-in-time vintage. For STREV, a later stock-specific multiplicative rescaling applied equally to both endpoints cancels in `close_t / close_(t-21)`, so adjusted history alone is not proof of leakage. Vendor corrections, inconsistent factors, and revised event treatment can still change returns. Record this limitation; neither use holdout outcomes nor attempt to infer historical forecasts from revised levels. No October 2025 onward price rows were fetched into this snapshot. `^NSEI` is a price-index comparator; dividend-adjusted stocks are not a perfectly matched total-return comparison.

| Ticker | Split events: exact vendor dates | Dividends: count and first–last |
|---|---|---|
| RELIANCE.NS | 1997-10-27 (2:1); 2009-11-26 (2:1); 2017-09-07 (2:1); 2024-10-28 (2:1) | 29; 1996-05-24–2024-08-19 |
| TCS.NS | 2006-07-28 (2:1); 2009-06-16 (2:1); 2018-05-31 (2:1) | 82; 2004-10-28–2024-10-18 |
| INFY.NS | 1997-08-19 (2:1); 1999-02-10 (2:1); 2000-01-27 (2:1); 2004-07-01 (4:1); 2006-07-13 (2:1); 2014-12-02 (2:1); 2015-06-15 (2:1); 2018-09-04 (2:1) | 59; 1996-04-30–2024-10-29 |
| HDFCBANK.NS | 2011-07-14 (5:1); 2019-09-19 (2:1) | 28; 1997-06-09–2024-05-10 |
| ICICIBANK.NS | 2014-12-04 (5:1); 2017-06-20 (1.1:1) | 22; 2003-08-04–2024-08-12 |
| SBIN.NS | 2014-11-20 (10:1) | 29; 1996-06-03–2024-05-22 |
| KOTAKBANK.NS | 2004-08-25 (2:1); 2005-08-25 (2.5:1); 2010-09-13 (2:1); 2015-07-08 (2:1) | 23; 2002-01-23–2024-07-19 |
| AXISBANK.NS | 2014-07-28 (5:1) | 23; 1999-06-16–2024-07-12 |
| ^NSEI | None | None |

## Comparison with the prior India report

The earlier `india_data_quality_report.md` recorded the same 31 >20% flags and major 2005 spikes; their repetition does not validate them. Its 1,176 repeated closes and 935 repeated/zero-volume observations compare with 1,148 and 916 here; periods, retrieval settings, and vendor vintages differ, so no correction can be inferred from count differences. Its zero-missing-dates result tested date membership, not missing closing values inside rows. Its TCS March 18, 2025 official-price comparison is outside the required December 2024 cutoff and does not validate this snapshot. The TCS pre-listing conflict is a newly established limitation of the old historical-coverage interpretation.

## Proposed reproducible data policy — approval required, not applied

1. **Immutable provenance:** retain all snapshot files and hashes. Create a new versioned research view plus an exclusion/correction ledger with symbol, date, reason, evidence URL, decision date, old/new values, and affected windows. Never overwrite raw or original derived data. Recalculate flags after calendar corrections.
2. **Session calendar:** use an evidenced NSE cash-equity session calendar, including special weekend/Muhurat sessions. Remove only confirmed non-session rows from the research view, across all symbols consistently; first proposed confirmed removal is July 28, 2005. Keep unresolved dates flagged and block final results for affected windows. Do not use weekdays or the incomplete benchmark alone as the calendar. Recompute the unchanged 21-session factor after calendar correction.
3. **Listing validity:** mask TCS before August 25, 2004 in the research view. Document this as instrument validity, not an alternative ticker or factor. Do not demand fabricated pre-listing prices to retain eight-stock coverage.
4. **Missing closes:** no interpolation or forward-fill in signal/return inputs. On a genuine session, keep missing close as NaN. Proposed stricter eligibility requires all 22 closes spanning the 21-session lookback to be verified; apply a separate eligibility mask after invoking the unchanged Vibe factor. This is an added research filter and needs approval; Vibe's original formula checks its endpoints rather than every interior observation. Require all eight eligible names for the primary weekly comparison, otherwise skip/log the signal. Never renormalize unknowingly over a different research universe.
5. **Zero volume:** positive volume is required for portfolio executions, not for the mathematical STREV formula. Keep verified session prices; flag unexplained zero-volume session observations and withhold affected names/windows from evaluation until resolved. Do not blanket-remove days solely because volume is zero. Index volume never controls stock eligibility.
6. **Repeated closes:** retain positive-volume repetitions unless independent evidence contradicts them. Investigate zero-volume repetitions through calendar/session evidence. No automatic winsorization, synthetic returns, or assumed closures.
7. **Discontinuities:** flag absolute adjusted daily changes above 20%; this is a review threshold, not an error classifier. Correct only against independently verified prices and adjustment basis, in a separate documented view. Unexplained discontinuities block affected windows; do not discard the rebound mechanically. Prefer blocking the full 22-close eligibility window spanning a known unreliable point; re-evaluate after correcting the session calendar. A missing held-price/return blocks performance reporting rather than becoming zero.
8. **Timing of quality decisions:** calendar/listing corrections are retrospective data-quality reconstruction. Mark that explicitly. Never select exclusions, periods, costs, or holdings from IC/Sharpe outcomes; freeze policy before the first evaluation. Do not use future price behavior at a signal date to choose trades. An unresolved surprise encountered while holding an asset causes an incomplete run requiring review, not retroactive avoidance of that trade.

## Inspected implementations and proposed portfolio methodology

Jack's local `origin/jack` reference, `hk_week1/backtest_strategies.py`, supplies `weekly_signal_dates`, `build_rebalances`, `simulate`, `mean_rank_information_coefficient`, and `metrics`. It loads 2021–2024; ranks descending; holds the top two at equal target weights; selects weekly Friday-ending signal dates; executes at the next close with positive selected-stock volume; drifts weights; charges 0.001 times absolute target-minus-drifted weight changes; and calculates annualized daily net-return Sharpe with 252 sessions and zero risk-free rate. Its IC spans consecutive execution closes. These are reference choices, not approved India requirements.

Vibe paths under `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/`: `src/factors/zoo/academic/strev.py::compute` is negative trailing 21-session return followed by cross-sectional sample-standard-deviation z-scoring. `src/factors/factor_analysis_core.py::compute_ic_series` computes Spearman IC with at least five valid pairs. `compute_group_equity` is a daily quantile diagnostic, not the proposed lagged costed weekly simulator. `src/tools/alpha_bench_tool.py::_compute_forward_returns` produces next-session close-to-close labels. `bench_runner.py` reports IC statistics/IC information ratio, not portfolio Sharpe. `src/india_vibe_bridge.py` must remain isolated because both repositories use a package named `src`.

**Concrete proposed first baseline, requiring approval:**

| Decision | Proposed India rule | Relationship to Jack / limitation |
|---|---|---|
| Period | January 4, 2021–December 31, 2024, with at least 22 prior verified sessions for warm-up; first trade follows first eligible weekly signal | Matches Jack's broad period for comparability; not yet approved and not selected using performance. Does not validate older history. No holdout access |
| Factor and ranks | Invoke unchanged academic_strev; higher scores mean recent losers. Rank eight eligible stocks descending; equal-score tie broken lexicographically by ticker | Same descending mechanism; reversal scores replace momentum, not the factor definition |
| Holdings | Long-only top two, 50% target each; fractional weights, fully invested after entry, no leverage/shorts; initial cash | Matches Jack. This is a long-only realization of STREV, not a replication of the academic long-short factor portfolio |
| Rebalance | Last actual NSE session in each Friday-ending week; a special Saturday is grouped consistently by that calendar rule, not discarded | Jack's W-FRI grouping; must document special-session week assignment |
| Execution | Earliest later session close with reliable prices and positive volume for all buys AND sells; new weights earn returns only after that close | Extends Jack's selected-name volume test to outgoing holdings. A close/positive-volume daily-bar model is an approximation, not guaranteed auction fills |
| Pending orders | Cancel any unexecuted target when the next weekly signal arrives; replace it only using information then available; no overlapping queued targets | Explicit improvement over Jack's possible execution-date collisions; log every cancellation/delay |
| Valuation | Drift weights with verified adjusted close returns. No fillna(0) for an unknown held return; stop/report incomplete until resolved | Jack rejects missing input upfront but simulate contains fillna(0); do not carry that fallback into India |
| Costs | Base 10 bps per unit of traded notional: 0.001 × sum(abs(target − pretrade drifted weights)), including initial entry. Predeclare 0/10/25-bps sensitivity; no cost-driven selection | Matches Jack's base rate. Full replacement costs 20 bps of NAV; this is a modeling assumption, not a verified Indian statutory/broker schedule |
| Dividends | Adjusted-price return proxy; do not add dividends again | Consistent with selected price basis; disclose fractional-share and corporate-action approximation |
| Terminal date | Mark holdings at the final verified close on/before December 31, 2024; no forced terminal sale in baseline, disclose that convention | No post-cutoff labels or execution; terminal liquidation would require a separately approved rule |
| Primary IC | At each completed holding interval, Spearman correlation of signal scores across the eight stocks with their execution-to-next-execution returns; retain at least five valid pairs, report actual count and skipped dates | Jack's execution-aligned horizon using Vibe's IC implementation; correlation is across the eligible universe, not just two holdings. Last unmatched interval omitted |
| Secondary IC | Separately label next-session close-to-close IC; do not equate it with tradable weekly IC | Existing Vibe bridge diagnostic |
| Sharpe | sqrt(252) × mean(daily net portfolio returns) / sample_std(daily net portfolio returns), zero risk-free baseline; zero variance => undefined | Jack convention; IC mean/std is not portfolio Sharpe. Include entry costs and align benchmark dates |
| Benchmark | Separate ^NSEI price-index returns on exactly the evaluation dates; missing benchmark values block claimed complete comparison | State mismatch with dividend-adjusted stocks; do not add benchmark to factor ranks |

Weekly versus monthly holding, top-two versus a long-short portfolio, costs, annualization, and risk-free rate are all proposed modeling decisions. STREV's 21-session lookback does not itself mandate weekly trading. This proposal is deliberately explicit so approval precedes implementation and results.

## Approval gates and readiness

Approve or amend the data-view rules (calendar evidence, pre-listing mask, full-window eligibility, unexplained anomalies, zero-volume treatment), the 2021–2024 primary period/warm-up, and every portfolio rule above before implementing the simulator. Approve the 10-bps cost assumption/sensitivity, execution approximation, IC horizons, Sharpe/risk-free convention, dividend/index interpretation, and terminal marking policy. Keep/Drop thresholds are still unresolved: report exploratory evidence without a final Keep/Drop designation until a criterion is agreed. Reporting as final also requires resolving material data defects in the selected period, saving the exact configuration/data hashes and eligibility ledger, passing meaningful timing/cost tests, and user review of actual results. No new approval is needed to retain the already approved Vibe framework, assigned factor, cutoff, or holdout restriction.

**Current state:** review saved; original snapshot preserved; portfolio code not implemented; no final IC/Sharpe or strategy recommendation computed. Await user approval. This document is a research assessment, not a new standing instruction or an approved methodology.

## Appendix: exhaustive requested flag dates from the manifest

These are the original snapshot flags before any proposed calendar/listing correction. Counts and dates are not assertions that every flagged row is erroneous.

### RELIANCE.NS

<details><summary>missing_or_nonnumeric_Close: 10 observations</summary>

2003-04-14, 2004-04-26, 2004-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 125 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-05, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-12, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-07-18, 1997-08-15, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 127 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-05, 1996-08-15, 1996-08-16, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-12, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-03-07, 1997-03-24, 1997-03-25, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-07-18, 1997-08-08, 1997-08-15, 1997-09-19, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-02-24, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-07-14, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-02-12, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-12, 1999-04-14, 1999-04-27, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-16, 2001-10-26, 2001-11-16, 2001-11-23, 2001-11-30, 2001-12-13, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-07-07, 2004-10-22, 2004-11-15, 2004-11-26, 2005-11-04, 2008-11-27, 2011-09-28, 2014-04-24, 2014-08-11, 2014-10-15, 2019-04-30

</details>

<details><summary>move_over_20pct_adjusted_close: 6 observations</summary>

1996-07-16, 1997-10-27, 1997-11-05, 2005-07-28, 2005-07-29, 2009-05-18

</details>

### TCS.NS

<details><summary>missing_or_nonnumeric_Close: 9 observations</summary>

2003-04-01, 2004-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 319 observations</summary>

2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-11-29, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-03-21, 2003-04-01, 2003-04-02, 2003-04-03, 2003-04-04, 2003-04-07, 2003-04-08, 2003-04-09, 2003-04-10, 2003-04-11, 2003-04-14, 2003-04-15, 2003-04-16, 2003-04-17, 2003-04-18, 2003-04-21, 2003-04-22, 2003-04-23, 2003-04-24, 2003-04-25, 2003-04-28, 2003-04-29, 2003-04-30, 2003-05-01, 2003-05-02, 2003-05-05, 2003-05-06, 2003-05-07, 2003-05-08, 2003-05-09, 2003-05-12, 2003-05-13, 2003-05-14, 2003-05-15, 2003-05-16, 2003-05-19, 2003-05-20, 2003-05-21, 2003-05-22, 2003-05-23, 2003-05-26, 2003-05-27, 2003-05-28, 2003-05-29, 2003-05-30, 2003-06-02, 2003-06-03, 2003-06-04, 2003-06-05, 2003-06-06, 2003-06-09, 2003-06-10, 2003-06-11, 2003-06-12, 2003-06-13, 2003-06-16, 2003-06-17, 2003-06-18, 2003-06-19, 2003-06-20, 2003-06-23, 2003-06-24, 2003-06-25, 2003-06-26, 2003-06-27, 2003-06-30, 2003-07-01, 2003-07-02, 2003-07-03, 2003-07-04, 2003-07-07, 2003-07-08, 2003-07-09, 2003-07-10, 2003-07-11, 2003-07-14, 2003-07-15, 2003-07-16, 2003-07-17, 2003-07-18, 2003-07-21, 2003-07-22, 2003-07-23, 2003-07-24, 2003-07-25, 2003-07-28, 2003-07-29, 2003-07-30, 2003-07-31, 2003-08-01, 2003-08-04, 2003-08-05, 2003-08-06, 2003-08-07, 2003-08-08, 2003-08-11, 2003-08-12, 2003-08-13, 2003-08-14, 2003-08-15, 2003-08-18, 2003-08-19, 2003-08-20, 2003-08-21, 2003-08-22, 2003-08-25, 2003-08-26, 2003-08-27, 2003-08-28, 2003-08-29, 2003-09-01, 2003-09-02, 2003-09-03, 2003-09-04, 2003-09-05, 2003-09-08, 2003-09-09, 2003-09-10, 2003-09-11, 2003-09-12, 2003-09-15, 2003-09-16, 2003-09-17, 2003-09-18, 2003-09-19, 2003-09-22, 2003-09-23, 2003-09-24, 2003-09-25, 2003-09-26, 2003-09-29, 2003-09-30, 2003-10-01, 2003-10-02, 2003-10-03, 2003-10-06, 2003-10-07, 2003-10-08, 2003-10-09, 2003-10-10, 2003-10-13, 2003-10-14, 2003-10-15, 2003-10-16, 2003-10-17, 2003-10-20, 2003-10-21, 2003-10-22, 2003-10-23, 2003-10-24, 2003-10-27, 2003-10-28, 2003-10-29, 2003-10-30, 2003-10-31, 2003-11-03, 2003-11-04, 2003-11-05, 2003-11-06, 2003-11-07, 2003-11-10, 2003-11-11, 2003-11-12, 2003-11-13, 2003-11-14, 2003-11-17, 2003-11-18, 2003-11-19, 2003-11-20, 2003-11-21, 2003-11-24, 2003-11-25, 2003-11-26, 2003-11-27, 2003-11-28, 2003-12-01, 2003-12-02, 2003-12-03, 2003-12-04, 2003-12-05, 2003-12-08, 2003-12-09, 2003-12-10, 2003-12-11, 2003-12-12, 2003-12-15, 2003-12-16, 2003-12-17, 2003-12-18, 2003-12-19, 2003-12-22, 2003-12-23, 2003-12-24, 2003-12-25, 2003-12-26, 2003-12-29, 2003-12-30, 2003-12-31, 2004-01-01, 2004-01-02, 2004-01-05, 2004-01-06, 2004-01-07, 2004-01-08, 2004-01-09, 2004-01-12, 2004-01-13, 2004-01-14, 2004-01-15, 2004-01-16, 2004-01-19, 2004-01-20, 2004-01-21, 2004-01-22, 2004-01-23, 2004-01-26, 2004-01-27, 2004-01-28, 2004-01-29, 2004-01-30, 2004-02-02, 2004-02-03, 2004-02-04, 2004-02-05, 2004-02-06, 2004-02-09, 2004-02-10, 2004-02-11, 2004-02-12, 2004-02-13, 2004-02-16, 2004-02-17, 2004-02-18, 2004-02-19, 2004-02-20, 2004-02-23, 2004-02-24, 2004-02-25, 2004-02-26, 2004-02-27, 2004-03-01, 2004-03-02, 2004-03-03, 2004-03-04, 2004-03-05, 2004-03-08, 2004-03-09, 2004-03-10, 2004-03-11, 2004-03-12, 2004-03-15, 2004-03-16, 2004-03-17, 2004-03-18, 2004-03-19, 2004-03-22, 2004-03-23, 2004-03-24, 2004-03-25, 2004-03-26, 2004-03-29, 2004-03-30, 2004-03-31, 2004-04-01, 2004-04-02, 2004-04-05, 2004-04-06, 2004-04-07, 2004-04-08, 2004-04-09, 2004-04-12, 2004-04-13, 2004-04-14, 2004-04-15, 2004-04-16, 2004-04-19, 2004-04-20, 2004-04-21, 2004-04-22, 2004-04-23, 2004-04-26, 2004-04-27, 2004-04-28, 2004-04-29, 2004-04-30, 2004-05-03, 2004-05-04, 2004-05-05, 2004-07-27, 2004-08-12, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 314 observations</summary>

2002-08-15, 2002-08-29, 2002-09-10, 2002-10-02, 2002-10-15, 2002-10-17, 2002-11-06, 2002-11-19, 2002-11-29, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-03-21, 2003-04-03, 2003-04-04, 2003-04-07, 2003-04-08, 2003-04-09, 2003-04-10, 2003-04-11, 2003-04-14, 2003-04-15, 2003-04-16, 2003-04-17, 2003-04-18, 2003-04-21, 2003-04-22, 2003-04-23, 2003-04-24, 2003-04-25, 2003-04-28, 2003-04-29, 2003-04-30, 2003-05-01, 2003-05-02, 2003-05-05, 2003-05-06, 2003-05-07, 2003-05-08, 2003-05-09, 2003-05-12, 2003-05-13, 2003-05-14, 2003-05-15, 2003-05-16, 2003-05-19, 2003-05-20, 2003-05-21, 2003-05-22, 2003-05-23, 2003-05-26, 2003-05-27, 2003-05-28, 2003-05-29, 2003-05-30, 2003-06-02, 2003-06-03, 2003-06-04, 2003-06-05, 2003-06-06, 2003-06-09, 2003-06-10, 2003-06-11, 2003-06-12, 2003-06-13, 2003-06-16, 2003-06-17, 2003-06-18, 2003-06-19, 2003-06-20, 2003-06-23, 2003-06-24, 2003-06-25, 2003-06-26, 2003-06-27, 2003-06-30, 2003-07-01, 2003-07-02, 2003-07-03, 2003-07-04, 2003-07-07, 2003-07-08, 2003-07-09, 2003-07-10, 2003-07-11, 2003-07-14, 2003-07-15, 2003-07-16, 2003-07-17, 2003-07-18, 2003-07-21, 2003-07-22, 2003-07-23, 2003-07-24, 2003-07-25, 2003-07-28, 2003-07-29, 2003-07-30, 2003-07-31, 2003-08-01, 2003-08-04, 2003-08-05, 2003-08-06, 2003-08-07, 2003-08-08, 2003-08-11, 2003-08-12, 2003-08-13, 2003-08-14, 2003-08-15, 2003-08-18, 2003-08-19, 2003-08-20, 2003-08-21, 2003-08-22, 2003-08-25, 2003-08-26, 2003-08-27, 2003-08-28, 2003-08-29, 2003-09-01, 2003-09-02, 2003-09-03, 2003-09-04, 2003-09-05, 2003-09-08, 2003-09-09, 2003-09-10, 2003-09-11, 2003-09-12, 2003-09-15, 2003-09-16, 2003-09-17, 2003-09-18, 2003-09-19, 2003-09-22, 2003-09-23, 2003-09-24, 2003-09-25, 2003-09-26, 2003-09-29, 2003-09-30, 2003-10-01, 2003-10-02, 2003-10-03, 2003-10-06, 2003-10-07, 2003-10-08, 2003-10-09, 2003-10-10, 2003-10-13, 2003-10-14, 2003-10-15, 2003-10-16, 2003-10-17, 2003-10-20, 2003-10-21, 2003-10-22, 2003-10-23, 2003-10-24, 2003-10-27, 2003-10-28, 2003-10-29, 2003-10-30, 2003-10-31, 2003-11-03, 2003-11-04, 2003-11-05, 2003-11-06, 2003-11-07, 2003-11-10, 2003-11-11, 2003-11-12, 2003-11-13, 2003-11-14, 2003-11-17, 2003-11-18, 2003-11-19, 2003-11-20, 2003-11-21, 2003-11-24, 2003-11-25, 2003-11-26, 2003-11-27, 2003-11-28, 2003-12-01, 2003-12-02, 2003-12-03, 2003-12-04, 2003-12-05, 2003-12-08, 2003-12-09, 2003-12-10, 2003-12-11, 2003-12-12, 2003-12-15, 2003-12-16, 2003-12-17, 2003-12-18, 2003-12-19, 2003-12-22, 2003-12-23, 2003-12-24, 2003-12-25, 2003-12-26, 2003-12-29, 2003-12-30, 2003-12-31, 2004-01-01, 2004-01-02, 2004-01-05, 2004-01-06, 2004-01-07, 2004-01-08, 2004-01-09, 2004-01-12, 2004-01-13, 2004-01-14, 2004-01-15, 2004-01-16, 2004-01-19, 2004-01-20, 2004-01-21, 2004-01-22, 2004-01-23, 2004-01-26, 2004-01-27, 2004-01-28, 2004-01-29, 2004-01-30, 2004-02-02, 2004-02-03, 2004-02-04, 2004-02-05, 2004-02-06, 2004-02-09, 2004-02-10, 2004-02-11, 2004-02-12, 2004-02-13, 2004-02-16, 2004-02-17, 2004-02-18, 2004-02-19, 2004-02-20, 2004-02-23, 2004-02-24, 2004-02-25, 2004-02-26, 2004-02-27, 2004-03-01, 2004-03-02, 2004-03-03, 2004-03-04, 2004-03-05, 2004-03-08, 2004-03-09, 2004-03-10, 2004-03-11, 2004-03-12, 2004-03-15, 2004-03-16, 2004-03-17, 2004-03-18, 2004-03-19, 2004-03-22, 2004-03-23, 2004-03-24, 2004-03-25, 2004-03-26, 2004-03-29, 2004-03-30, 2004-03-31, 2004-04-01, 2004-04-02, 2004-04-05, 2004-04-06, 2004-04-07, 2004-04-08, 2004-04-09, 2004-04-12, 2004-04-13, 2004-04-14, 2004-04-15, 2004-04-16, 2004-04-19, 2004-04-20, 2004-04-21, 2004-04-22, 2004-04-23, 2004-04-26, 2004-04-27, 2004-04-28, 2004-04-29, 2004-04-30, 2004-05-03, 2004-05-04, 2004-05-05, 2004-06-25, 2004-07-27, 2004-08-12, 2004-10-22, 2004-11-15, 2004-11-26, 2005-11-04, 2008-11-27, 2010-07-14, 2010-10-29, 2014-04-24, 2014-10-15, 2019-03-19, 2019-04-03, 2020-09-15

</details>

<details><summary>move_over_20pct_adjusted_close: 3 observations</summary>

2004-05-06, 2005-07-28, 2005-07-29

</details>

### INFY.NS

<details><summary>missing_or_nonnumeric_Close: 7 observations</summary>

2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 127 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-01, 1996-04-05, 1996-07-17, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-12, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-07-18, 1997-08-15, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 133 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-01, 1996-04-05, 1996-05-01, 1996-06-17, 1996-06-21, 1996-07-17, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-05, 1996-11-06, 1996-11-12, 1996-12-09, 1996-12-13, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-02-06, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-07-18, 1997-08-15, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-02-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-05-14, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2014-04-24, 2014-10-15, 2017-02-28, 2019-03-06, 2020-05-05

</details>

<details><summary>move_over_20pct_adjusted_close: 2 observations</summary>

2003-04-10, 2013-04-12

</details>

### HDFCBANK.NS

<details><summary>missing_or_nonnumeric_Close: 7 observations</summary>

2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 125 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-05, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-12, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-07-18, 1997-08-15, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 166 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-05, 1996-06-07, 1996-07-11, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-06, 1996-11-12, 1996-11-21, 1996-11-22, 1996-11-25, 1996-11-26, 1996-12-02, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-01-24, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-05-07, 1997-06-06, 1997-07-18, 1997-08-15, 1997-09-24, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-05-18, 1999-06-25, 1999-09-13, 1999-10-19, 1999-11-05, 1999-11-08, 1999-11-18, 1999-11-23, 1999-12-31, 2000-01-26, 2000-02-25, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-10-13, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-08-23, 2001-09-06, 2001-10-02, 2001-10-19, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-01-07, 2002-03-22, 2002-03-25, 2002-03-29, 2002-05-01, 2002-06-13, 2002-07-09, 2002-08-05, 2002-08-15, 2002-08-28, 2002-09-10, 2002-09-20, 2002-10-02, 2002-10-08, 2002-10-15, 2002-11-06, 2002-11-15, 2002-11-19, 2002-11-27, 2002-12-25, 2003-02-05, 2003-02-13, 2003-02-17, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-09-04, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-13, 2004-01-20, 2004-01-26, 2004-02-02, 2004-02-12, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-07-15, 2004-08-25, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-09-29, 2005-11-04, 2005-12-27, 2006-08-29, 2008-11-27, 2009-04-30, 2009-10-13, 2010-11-29, 2012-01-02, 2012-09-13, 2013-01-14, 2013-12-02, 2014-04-24, 2014-10-15, 2017-03-23

</details>

<details><summary>move_over_20pct_adjusted_close: 2 observations</summary>

2004-05-17, 2004-05-18

</details>

### ICICIBANK.NS

<details><summary>missing_or_nonnumeric_Close: 10 observations</summary>

2003-04-14, 2004-04-26, 2004-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 41 observations</summary>

2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 45 observations</summary>

2002-07-12, 2002-08-15, 2002-08-26, 2002-09-10, 2002-09-12, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-18, 2003-05-01, 2003-05-06, 2003-05-23, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-13, 2004-04-14, 2004-06-07, 2004-10-22, 2004-11-15, 2004-11-26, 2004-12-01, 2005-01-03, 2005-11-04, 2008-03-19, 2008-11-27, 2009-10-14, 2011-11-14, 2012-08-23, 2013-12-11, 2014-04-24, 2014-10-15, 2017-08-01, 2017-08-18, 2021-12-30

</details>

<details><summary>move_over_20pct_adjusted_close: 1 observations</summary>

2009-05-18

</details>

### SBIN.NS

<details><summary>missing_or_nonnumeric_Close: 9 observations</summary>

2004-04-26, 2004-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 125 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-05, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-12, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-05-01, 1997-07-18, 1997-08-15, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 141 observations</summary>

1996-01-26, 1996-02-21, 1996-03-05, 1996-03-20, 1996-04-05, 1996-06-07, 1996-08-15, 1996-10-02, 1996-10-21, 1996-10-30, 1996-11-12, 1996-12-25, 1996-12-27, 1996-12-30, 1997-01-23, 1997-03-07, 1997-03-24, 1997-03-28, 1997-04-08, 1997-04-14, 1997-04-16, 1997-04-18, 1997-04-28, 1997-05-01, 1997-07-18, 1997-08-15, 1997-10-02, 1997-10-03, 1997-10-06, 1997-10-07, 1997-10-08, 1997-10-31, 1997-11-14, 1997-12-25, 1998-01-26, 1998-02-16, 1998-03-13, 1998-04-08, 1998-04-14, 1998-05-01, 1998-05-07, 1998-07-09, 1998-08-26, 1998-10-01, 1998-10-02, 1998-10-21, 1998-11-04, 1998-11-25, 1998-12-14, 1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-23, 1999-12-29, 1999-12-31, 2000-01-26, 2000-02-17, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-03-15, 2001-04-05, 2001-04-13, 2001-05-01, 2001-08-15, 2001-08-20, 2001-08-22, 2001-09-07, 2001-10-02, 2001-10-19, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-09-27, 2002-10-02, 2002-10-11, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-04-21, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2006-09-01, 2008-11-27, 2009-04-30, 2009-10-13, 2014-04-24, 2014-10-15, 2015-12-04, 2016-11-22, 2017-04-25, 2019-01-09, 2021-10-22, 2022-03-08, 2022-12-20, 2022-12-22, 2023-05-17, 2023-06-05

</details>

<details><summary>move_over_20pct_adjusted_close: 2 observations</summary>

2009-05-18, 2017-10-25

</details>

### KOTAKBANK.NS

<details><summary>missing_or_nonnumeric_Close: 8 observations</summary>

2003-04-14, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 52 observations</summary>

2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 73 observations</summary>

2001-07-12, 2001-08-13, 2001-08-14, 2001-08-15, 2001-08-20, 2001-08-21, 2001-08-22, 2001-08-23, 2001-08-24, 2001-08-29, 2001-09-05, 2001-09-06, 2001-09-11, 2001-09-13, 2001-09-25, 2001-10-02, 2001-10-03, 2001-10-26, 2001-10-30, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-05, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-12, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-18, 2003-05-01, 2003-06-19, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-08-18, 2004-10-22, 2004-11-15, 2004-11-26, 2005-09-09, 2005-11-04, 2006-08-31, 2008-11-27, 2009-04-30, 2009-10-13, 2010-05-03, 2010-11-16, 2012-08-02, 2012-11-19, 2014-02-11, 2014-04-24, 2014-10-15, 2016-03-17, 2016-05-18, 2021-06-30, 2023-03-06, 2024-09-04, 2024-12-11

</details>

<details><summary>move_over_20pct_adjusted_close: 10 observations</summary>

2002-01-31, 2002-02-21, 2002-03-04, 2004-04-26, 2004-04-27, 2004-10-13, 2004-10-14, 2005-07-28, 2005-07-29, 2008-10-24

</details>

### AXISBANK.NS

<details><summary>missing_or_nonnumeric_Close: 10 observations</summary>

2003-04-14, 2004-04-26, 2004-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2015-02-28

</details>

<details><summary>zero_volume: 85 observations</summary>

1998-12-25, 1999-01-20, 1999-01-26, 1999-03-02, 1999-03-18, 1999-03-25, 1999-03-29, 1999-04-02, 1999-04-14, 1999-04-27, 1999-04-30, 1999-09-13, 1999-10-19, 1999-11-08, 1999-11-10, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-08-15, 2000-09-01, 2000-10-02, 2000-12-25, 2001-01-26, 2001-03-06, 2001-04-05, 2001-04-13, 2001-05-01, 2001-07-23, 2001-08-15, 2001-08-22, 2001-10-02, 2001-10-26, 2001-11-16, 2001-11-30, 2001-12-17, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-08-15, 2002-09-10, 2002-10-02, 2002-10-15, 2002-11-06, 2002-11-19, 2002-12-25, 2003-02-13, 2003-03-14, 2003-03-18, 2003-04-14, 2003-04-18, 2003-05-01, 2003-08-15, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-04-26, 2004-10-13, 2004-10-22, 2004-11-15, 2004-11-26, 2005-07-28, 2005-11-04, 2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2012-01-07, 2012-03-03, 2012-09-08, 2012-11-11, 2014-03-22, 2014-04-24, 2014-10-15, 2015-02-28

</details>

<details><summary>repeated_adjusted_close: 149 observations</summary>

1998-12-02, 1998-12-03, 1998-12-04, 1998-12-09, 1998-12-25, 1998-12-28, 1999-01-06, 1999-01-20, 1999-01-25, 1999-01-26, 1999-02-05, 1999-02-15, 1999-02-19, 1999-03-02, 1999-03-18, 1999-03-25, 1999-03-29, 1999-04-02, 1999-04-12, 1999-04-14, 1999-04-27, 1999-04-30, 1999-05-12, 1999-05-18, 1999-05-25, 1999-06-15, 1999-07-01, 1999-07-02, 1999-08-12, 1999-08-13, 1999-09-13, 1999-09-15, 1999-09-23, 1999-10-05, 1999-10-12, 1999-10-19, 1999-11-08, 1999-11-10, 1999-11-22, 1999-11-23, 1999-12-31, 2000-01-26, 2000-03-15, 2000-03-17, 2000-03-20, 2000-04-14, 2000-04-21, 2000-05-01, 2000-07-28, 2000-08-15, 2000-08-18, 2000-09-01, 2000-09-08, 2000-09-11, 2000-09-12, 2000-10-02, 2000-10-31, 2000-12-25, 2001-01-11, 2001-01-26, 2001-03-06, 2001-03-27, 2001-04-05, 2001-04-13, 2001-05-01, 2001-05-04, 2001-06-05, 2001-06-28, 2001-07-23, 2001-07-31, 2001-08-01, 2001-08-15, 2001-08-22, 2001-09-11, 2001-10-02, 2001-10-26, 2001-11-09, 2001-11-16, 2001-11-30, 2001-12-12, 2001-12-17, 2001-12-20, 2001-12-25, 2002-03-25, 2002-03-29, 2002-05-01, 2002-07-25, 2002-08-06, 2002-08-15, 2002-09-05, 2002-09-10, 2002-10-02, 2002-10-10, 2002-10-11, 2002-10-15, 2002-10-16, 2002-10-17, 2002-11-01, 2002-11-04, 2002-11-06, 2002-11-19, 2002-12-05, 2002-12-09, 2002-12-20, 2002-12-25, 2003-01-13, 2003-02-13, 2003-02-28, 2003-03-14, 2003-03-18, 2003-03-26, 2003-04-18, 2003-05-01, 2003-08-15, 2003-09-30, 2003-10-02, 2003-11-26, 2003-12-25, 2004-01-26, 2004-02-02, 2004-03-02, 2004-04-09, 2004-04-14, 2004-10-22, 2004-11-15, 2004-11-26, 2005-06-20, 2005-07-22, 2005-07-28, 2005-08-11, 2005-08-30, 2005-11-04, 2005-12-08, 2006-08-14, 2006-09-05, 2006-12-07, 2007-04-16, 2008-11-27, 2009-04-30, 2009-07-24, 2009-10-13, 2011-11-22, 2013-02-20, 2013-04-09, 2014-04-24, 2014-10-15, 2019-01-23, 2019-12-31, 2022-11-22

</details>

<details><summary>move_over_20pct_adjusted_close: 5 observations</summary>

1999-03-03, 1999-12-06, 2003-07-03, 2003-12-03, 2020-03-23

</details>

### ^NSEI

<details><summary>missing_or_nonnumeric_Close: 30 observations</summary>

2008-11-27, 2009-04-30, 2009-10-13, 2010-02-06, 2011-05-31, 2011-07-14, 2011-11-24, 2011-12-26, 2012-01-02, 2012-01-07, 2012-03-03, 2012-05-21, 2012-08-28, 2012-09-08, 2012-11-11, 2013-01-01, 2014-01-01, 2014-02-17, 2014-03-22, 2014-04-24, 2014-10-15, 2015-01-01, 2015-02-28, 2015-04-15, 2016-01-01, 2016-08-12, 2018-01-01, 2019-01-01, 2019-10-27, 2020-11-14

</details>

<details><summary>zero_volume: 1363 observations</summary>

2007-09-17, 2007-09-18, 2007-09-19, 2007-09-20, 2007-09-21, 2007-09-24, 2007-09-25, 2007-09-26, 2007-09-27, 2007-09-28, 2007-10-01, 2007-10-03, 2007-10-04, 2007-10-05, 2007-10-08, 2007-10-09, 2007-10-10, 2007-10-11, 2007-10-12, 2007-10-15, 2007-10-16, 2007-10-17, 2007-10-18, 2007-10-19, 2007-10-22, 2007-10-23, 2007-10-24, 2007-10-25, 2007-10-26, 2007-10-29, 2007-10-30, 2007-10-31, 2007-11-01, 2007-11-02, 2007-11-05, 2007-11-06, 2007-11-07, 2007-11-08, 2007-11-12, 2007-11-13, 2007-11-14, 2007-11-15, 2007-11-16, 2007-11-19, 2007-11-20, 2007-11-21, 2007-11-22, 2007-11-23, 2007-11-26, 2007-11-27, 2007-11-28, 2007-11-29, 2007-11-30, 2007-12-03, 2007-12-04, 2007-12-05, 2007-12-06, 2007-12-07, 2007-12-10, 2007-12-11, 2007-12-12, 2007-12-13, 2007-12-14, 2007-12-17, 2007-12-18, 2007-12-19, 2007-12-20, 2007-12-24, 2007-12-26, 2007-12-27, 2007-12-28, 2007-12-31, 2008-01-01, 2008-01-02, 2008-01-03, 2008-01-04, 2008-01-07, 2008-01-08, 2008-01-09, 2008-01-10, 2008-01-11, 2008-01-14, 2008-01-15, 2008-01-16, 2008-01-17, 2008-01-18, 2008-01-21, 2008-01-22, 2008-01-23, 2008-01-24, 2008-01-25, 2008-01-28, 2008-01-29, 2008-01-30, 2008-01-31, 2008-02-01, 2008-02-04, 2008-02-05, 2008-02-06, 2008-02-07, 2008-02-08, 2008-02-11, 2008-02-12, 2008-02-13, 2008-02-14, 2008-02-15, 2008-02-18, 2008-02-19, 2008-02-20, 2008-02-21, 2008-02-22, 2008-02-25, 2008-02-26, 2008-02-27, 2008-02-28, 2008-02-29, 2008-03-03, 2008-03-04, 2008-03-05, 2008-03-07, 2008-03-10, 2008-03-11, 2008-03-12, 2008-03-13, 2008-03-14, 2008-03-17, 2008-03-18, 2008-03-19, 2008-03-24, 2008-03-25, 2008-03-26, 2008-03-27, 2008-03-28, 2008-03-31, 2008-04-01, 2008-04-02, 2008-04-03, 2008-04-04, 2008-04-07, 2008-04-08, 2008-04-09, 2008-04-10, 2008-04-11, 2008-04-15, 2008-04-16, 2008-04-17, 2008-04-21, 2008-04-22, 2008-04-23, 2008-04-24, 2008-04-25, 2008-04-28, 2008-04-29, 2008-04-30, 2008-05-02, 2008-05-05, 2008-05-06, 2008-05-07, 2008-05-08, 2008-05-09, 2008-05-12, 2008-05-13, 2008-05-14, 2008-05-15, 2008-05-16, 2008-05-20, 2008-05-21, 2008-05-22, 2008-05-23, 2008-05-26, 2008-05-27, 2008-05-28, 2008-05-29, 2008-05-30, 2008-06-02, 2008-06-03, 2008-06-04, 2008-06-05, 2008-06-06, 2008-06-09, 2008-06-10, 2008-06-11, 2008-06-12, 2008-06-13, 2008-06-16, 2008-06-17, 2008-06-18, 2008-06-19, 2008-06-20, 2008-06-23, 2008-06-24, 2008-06-25, 2008-06-26, 2008-06-27, 2008-06-30, 2008-07-01, 2008-07-02, 2008-07-03, 2008-07-04, 2008-07-07, 2008-07-08, 2008-07-09, 2008-07-10, 2008-07-11, 2008-07-14, 2008-07-15, 2008-07-16, 2008-07-17, 2008-07-18, 2008-07-21, 2008-07-22, 2008-07-23, 2008-07-24, 2008-07-25, 2008-07-28, 2008-07-29, 2008-07-30, 2008-07-31, 2008-08-01, 2008-08-04, 2008-08-05, 2008-08-06, 2008-08-07, 2008-08-08, 2008-08-11, 2008-08-12, 2008-08-13, 2008-08-14, 2008-08-18, 2008-08-19, 2008-08-20, 2008-08-21, 2008-08-22, 2008-08-25, 2008-08-26, 2008-08-27, 2008-08-28, 2008-08-29, 2008-09-01, 2008-09-02, 2008-09-04, 2008-09-05, 2008-09-08, 2008-09-09, 2008-09-10, 2008-09-11, 2008-09-12, 2008-09-15, 2008-09-16, 2008-09-17, 2008-09-18, 2008-09-19, 2008-09-22, 2008-09-23, 2008-09-24, 2008-09-25, 2008-09-26, 2008-09-29, 2008-09-30, 2008-10-01, 2008-10-03, 2008-10-06, 2008-10-07, 2008-10-08, 2008-10-10, 2008-10-13, 2008-10-14, 2008-10-15, 2008-10-16, 2008-10-17, 2008-10-20, 2008-10-21, 2008-10-22, 2008-10-23, 2008-10-24, 2008-10-27, 2008-10-29, 2008-10-31, 2008-11-03, 2008-11-04, 2008-11-05, 2008-11-06, 2008-11-07, 2008-11-10, 2008-11-11, 2008-11-12, 2008-11-14, 2008-11-17, 2008-11-18, 2008-11-19, 2008-11-20, 2008-11-21, 2008-11-24, 2008-11-25, 2008-11-26, 2008-11-27, 2008-11-28, 2008-12-01, 2008-12-02, 2008-12-03, 2008-12-04, 2008-12-05, 2008-12-08, 2008-12-10, 2008-12-11, 2008-12-12, 2008-12-15, 2008-12-16, 2008-12-17, 2008-12-18, 2008-12-19, 2008-12-22, 2008-12-23, 2008-12-24, 2008-12-26, 2008-12-29, 2008-12-30, 2008-12-31, 2009-01-02, 2009-01-05, 2009-01-06, 2009-01-07, 2009-01-09, 2009-01-12, 2009-01-13, 2009-01-14, 2009-01-15, 2009-01-16, 2009-01-19, 2009-01-20, 2009-01-21, 2009-01-22, 2009-01-23, 2009-01-27, 2009-01-28, 2009-01-29, 2009-01-30, 2009-02-02, 2009-02-03, 2009-02-04, 2009-02-05, 2009-02-06, 2009-02-09, 2009-02-10, 2009-02-11, 2009-02-12, 2009-02-13, 2009-02-16, 2009-02-17, 2009-02-18, 2009-02-19, 2009-02-20, 2009-02-24, 2009-02-25, 2009-02-26, 2009-02-27, 2009-03-02, 2009-03-03, 2009-03-04, 2009-03-05, 2009-03-06, 2009-03-09, 2009-03-12, 2009-03-13, 2009-03-16, 2009-03-17, 2009-03-18, 2009-03-19, 2009-03-20, 2009-03-23, 2009-03-24, 2009-03-25, 2009-03-26, 2009-03-27, 2009-03-30, 2009-03-31, 2009-04-01, 2009-04-02, 2009-04-06, 2009-04-08, 2009-04-09, 2009-04-13, 2009-04-15, 2009-04-16, 2009-04-17, 2009-04-20, 2009-04-21, 2009-04-22, 2009-04-23, 2009-04-24, 2009-04-27, 2009-04-28, 2009-04-29, 2009-04-30, 2009-05-04, 2009-05-05, 2009-05-06, 2009-05-07, 2009-05-08, 2009-05-11, 2009-05-12, 2009-05-13, 2009-05-14, 2009-05-15, 2009-05-18, 2009-05-19, 2009-05-20, 2009-05-21, 2009-05-22, 2009-05-25, 2009-05-26, 2009-05-27, 2009-05-28, 2009-05-29, 2009-06-01, 2009-06-02, 2009-06-03, 2009-06-04, 2009-06-05, 2009-06-08, 2009-06-09, 2009-06-10, 2009-06-11, 2009-06-12, 2009-06-15, 2009-06-16, 2009-06-17, 2009-06-18, 2009-06-19, 2009-06-22, 2009-06-23, 2009-06-24, 2009-06-25, 2009-06-26, 2009-06-29, 2009-06-30, 2009-07-01, 2009-07-02, 2009-07-03, 2009-07-06, 2009-07-07, 2009-07-08, 2009-07-09, 2009-07-10, 2009-07-13, 2009-07-14, 2009-07-15, 2009-07-16, 2009-07-17, 2009-07-20, 2009-07-21, 2009-07-22, 2009-07-23, 2009-07-24, 2009-07-27, 2009-07-28, 2009-07-29, 2009-07-30, 2009-07-31, 2009-08-03, 2009-08-04, 2009-08-05, 2009-08-06, 2009-08-07, 2009-08-10, 2009-08-11, 2009-08-12, 2009-08-13, 2009-08-14, 2009-08-17, 2009-08-18, 2009-08-19, 2009-08-20, 2009-08-21, 2009-08-24, 2009-08-25, 2009-08-26, 2009-08-27, 2009-08-28, 2009-08-31, 2009-09-01, 2009-09-02, 2009-09-03, 2009-09-04, 2009-09-07, 2009-09-08, 2009-09-09, 2009-09-10, 2009-09-11, 2009-09-14, 2009-09-15, 2009-09-16, 2009-09-17, 2009-09-18, 2009-09-22, 2009-09-23, 2009-09-24, 2009-09-25, 2009-09-29, 2009-09-30, 2009-10-01, 2009-10-05, 2009-10-06, 2009-10-07, 2009-10-08, 2009-10-09, 2009-10-12, 2009-10-13, 2009-10-14, 2009-10-15, 2009-10-16, 2009-10-20, 2009-10-21, 2009-10-22, 2009-10-23, 2009-10-26, 2009-10-27, 2009-10-28, 2009-10-29, 2009-10-30, 2009-11-03, 2009-11-04, 2009-11-05, 2009-11-06, 2009-11-09, 2009-11-10, 2009-11-11, 2009-11-12, 2009-11-13, 2009-11-16, 2009-11-17, 2009-11-18, 2009-11-19, 2009-11-20, 2009-11-23, 2009-11-24, 2009-11-25, 2009-11-26, 2009-11-27, 2009-11-30, 2009-12-01, 2009-12-02, 2009-12-03, 2009-12-04, 2009-12-07, 2009-12-08, 2009-12-09, 2009-12-10, 2009-12-11, 2009-12-14, 2009-12-15, 2009-12-16, 2009-12-17, 2009-12-18, 2009-12-21, 2009-12-22, 2009-12-23, 2009-12-24, 2009-12-29, 2009-12-30, 2009-12-31, 2010-01-04, 2010-01-05, 2010-01-06, 2010-01-07, 2010-01-08, 2010-01-11, 2010-01-12, 2010-01-13, 2010-01-14, 2010-01-15, 2010-01-18, 2010-01-19, 2010-01-20, 2010-01-21, 2010-01-22, 2010-01-25, 2010-01-27, 2010-01-28, 2010-01-29, 2010-02-01, 2010-02-02, 2010-02-03, 2010-02-04, 2010-02-05, 2010-02-06, 2010-02-08, 2010-02-09, 2010-02-10, 2010-02-11, 2010-02-15, 2010-02-16, 2010-02-17, 2010-02-18, 2010-02-19, 2010-02-22, 2010-02-23, 2010-02-24, 2010-02-25, 2010-02-26, 2010-03-02, 2010-03-03, 2010-03-04, 2010-03-05, 2010-03-08, 2010-03-09, 2010-03-10, 2010-03-11, 2010-03-12, 2010-03-15, 2010-03-16, 2010-03-17, 2010-03-18, 2010-03-19, 2010-03-22, 2010-03-23, 2010-03-25, 2010-03-26, 2010-03-29, 2010-03-30, 2010-03-31, 2010-04-01, 2010-04-05, 2010-04-06, 2010-04-07, 2010-04-08, 2010-04-09, 2010-04-12, 2010-04-13, 2010-04-15, 2010-04-16, 2010-04-19, 2010-04-20, 2010-04-21, 2010-04-22, 2010-04-23, 2010-04-26, 2010-04-27, 2010-04-28, 2010-04-29, 2010-04-30, 2010-05-03, 2010-05-04, 2010-05-05, 2010-05-06, 2010-05-07, 2010-05-10, 2010-05-11, 2010-05-12, 2010-05-13, 2010-05-14, 2010-05-17, 2010-05-18, 2010-05-19, 2010-05-20, 2010-05-21, 2010-05-24, 2010-05-25, 2010-05-26, 2010-05-27, 2010-05-28, 2010-05-31, 2010-06-01, 2010-06-02, 2010-06-03, 2010-06-04, 2010-06-07, 2010-06-08, 2010-06-09, 2010-06-10, 2010-06-11, 2010-06-14, 2010-06-15, 2010-06-16, 2010-06-17, 2010-06-18, 2010-06-21, 2010-06-22, 2010-06-23, 2010-06-24, 2010-06-25, 2010-06-28, 2010-06-29, 2010-06-30, 2010-07-01, 2010-07-02, 2010-07-05, 2010-07-06, 2010-07-07, 2010-07-08, 2010-07-09, 2010-07-12, 2010-07-13, 2010-07-14, 2010-07-15, 2010-07-16, 2010-07-19, 2010-07-20, 2010-07-21, 2010-07-22, 2010-07-23, 2010-07-26, 2010-07-27, 2010-07-28, 2010-07-29, 2010-07-30, 2010-08-02, 2010-08-03, 2010-08-04, 2010-08-05, 2010-08-06, 2010-08-09, 2010-08-10, 2010-08-11, 2010-08-12, 2010-08-13, 2010-08-16, 2010-08-17, 2010-08-18, 2010-08-19, 2010-08-20, 2010-08-23, 2010-08-24, 2010-08-25, 2010-08-26, 2010-08-27, 2010-08-30, 2010-08-31, 2010-09-01, 2010-09-02, 2010-09-03, 2010-09-06, 2010-09-07, 2010-09-08, 2010-09-09, 2010-09-13, 2010-09-14, 2010-09-15, 2010-09-16, 2010-09-17, 2010-09-20, 2010-09-21, 2010-09-22, 2010-09-23, 2010-09-24, 2010-09-27, 2010-09-28, 2010-09-29, 2010-09-30, 2010-10-01, 2010-10-04, 2010-10-05, 2010-10-06, 2010-10-07, 2010-10-08, 2010-10-11, 2010-10-12, 2010-10-13, 2010-10-14, 2010-10-15, 2010-10-18, 2010-10-19, 2010-10-20, 2010-10-21, 2010-10-22, 2010-10-25, 2010-10-26, 2010-10-27, 2010-10-28, 2010-10-29, 2010-11-01, 2010-11-02, 2010-11-03, 2010-11-04, 2010-11-08, 2010-11-09, 2010-11-10, 2010-11-11, 2010-11-12, 2010-11-15, 2010-11-16, 2010-11-18, 2010-11-19, 2010-11-22, 2010-11-23, 2010-11-24, 2010-11-25, 2010-11-26, 2010-11-29, 2010-11-30, 2010-12-01, 2010-12-02, 2010-12-03, 2010-12-06, 2010-12-07, 2010-12-08, 2010-12-09, 2010-12-10, 2010-12-13, 2010-12-14, 2010-12-15, 2010-12-16, 2010-12-20, 2010-12-21, 2010-12-22, 2010-12-23, 2010-12-24, 2010-12-27, 2010-12-28, 2010-12-29, 2010-12-30, 2010-12-31, 2011-01-03, 2011-01-04, 2011-01-05, 2011-01-06, 2011-01-07, 2011-01-10, 2011-01-11, 2011-01-12, 2011-01-13, 2011-01-14, 2011-01-17, 2011-01-18, 2011-01-19, 2011-01-20, 2011-01-21, 2011-01-24, 2011-01-25, 2011-01-27, 2011-01-28, 2011-01-31, 2011-02-01, 2011-02-02, 2011-02-03, 2011-02-04, 2011-02-07, 2011-02-08, 2011-02-09, 2011-02-10, 2011-02-11, 2011-02-14, 2011-02-15, 2011-02-16, 2011-02-17, 2011-02-18, 2011-02-21, 2011-02-22, 2011-02-23, 2011-02-24, 2011-02-25, 2011-02-28, 2011-03-01, 2011-03-03, 2011-03-04, 2011-03-07, 2011-03-08, 2011-03-09, 2011-03-10, 2011-03-11, 2011-03-14, 2011-03-15, 2011-03-16, 2011-03-17, 2011-03-18, 2011-03-21, 2011-03-22, 2011-03-23, 2011-03-24, 2011-03-25, 2011-03-28, 2011-03-29, 2011-03-30, 2011-03-31, 2011-04-01, 2011-04-04, 2011-04-05, 2011-04-06, 2011-04-07, 2011-04-08, 2011-04-11, 2011-04-13, 2011-04-15, 2011-04-18, 2011-04-19, 2011-04-20, 2011-04-21, 2011-04-25, 2011-04-26, 2011-04-27, 2011-04-28, 2011-04-29, 2011-05-02, 2011-05-03, 2011-05-04, 2011-05-05, 2011-05-06, 2011-05-09, 2011-05-10, 2011-05-11, 2011-05-12, 2011-05-13, 2011-05-16, 2011-05-17, 2011-05-18, 2011-05-19, 2011-05-20, 2011-05-23, 2011-05-24, 2011-05-25, 2011-05-26, 2011-05-27, 2011-05-30, 2011-05-31, 2011-06-01, 2011-06-02, 2011-06-03, 2011-06-06, 2011-06-07, 2011-06-08, 2011-06-09, 2011-06-10, 2011-06-13, 2011-06-14, 2011-06-15, 2011-06-16, 2011-06-17, 2011-06-20, 2011-06-21, 2011-06-22, 2011-06-23, 2011-06-24, 2011-06-27, 2011-06-28, 2011-06-29, 2011-06-30, 2011-07-01, 2011-07-04, 2011-07-05, 2011-07-06, 2011-07-07, 2011-07-08, 2011-07-11, 2011-07-12, 2011-07-13, 2011-07-14, 2011-07-15, 2011-07-18, 2011-07-19, 2011-07-20, 2011-07-21, 2011-07-22, 2011-07-25, 2011-07-26, 2011-07-27, 2011-07-28, 2011-07-29, 2011-08-01, 2011-08-02, 2011-08-03, 2011-08-04, 2011-08-05, 2011-08-08, 2011-08-09, 2011-08-10, 2011-08-11, 2011-08-12, 2011-08-16, 2011-08-17, 2011-08-18, 2011-08-19, 2011-08-22, 2011-08-23, 2011-08-24, 2011-08-25, 2011-08-26, 2011-08-29, 2011-08-30, 2011-09-02, 2011-09-05, 2011-09-06, 2011-09-07, 2011-09-08, 2011-09-09, 2011-09-12, 2011-09-13, 2011-09-14, 2011-09-15, 2011-09-16, 2011-09-19, 2011-09-20, 2011-09-21, 2011-09-22, 2011-09-23, 2011-09-26, 2011-09-27, 2011-09-28, 2011-09-29, 2011-09-30, 2011-10-03, 2011-10-04, 2011-10-05, 2011-10-07, 2011-10-10, 2011-10-11, 2011-10-12, 2011-10-13, 2011-10-14, 2011-10-17, 2011-10-18, 2011-10-19, 2011-10-20, 2011-10-21, 2011-10-24, 2011-10-25, 2011-10-28, 2011-10-31, 2011-11-01, 2011-11-02, 2011-11-03, 2011-11-04, 2011-11-08, 2011-11-09, 2011-11-11, 2011-11-14, 2011-11-15, 2011-11-16, 2011-11-17, 2011-11-18, 2011-11-21, 2011-11-22, 2011-11-23, 2011-11-24, 2011-11-25, 2011-11-28, 2011-11-29, 2011-11-30, 2011-12-01, 2011-12-02, 2011-12-05, 2011-12-07, 2011-12-08, 2011-12-09, 2011-12-12, 2011-12-13, 2011-12-14, 2011-12-15, 2011-12-16, 2011-12-19, 2011-12-20, 2011-12-21, 2011-12-22, 2011-12-23, 2011-12-26, 2011-12-27, 2011-12-28, 2011-12-29, 2011-12-30, 2012-01-02, 2012-01-03, 2012-01-04, 2012-01-05, 2012-01-06, 2012-01-07, 2012-01-09, 2012-01-10, 2012-01-11, 2012-01-12, 2012-01-13, 2012-01-16, 2012-01-17, 2012-01-18, 2012-01-19, 2012-01-20, 2012-01-23, 2012-01-24, 2012-01-25, 2012-01-27, 2012-01-30, 2012-01-31, 2012-02-01, 2012-02-02, 2012-02-03, 2012-02-06, 2012-02-07, 2012-02-08, 2012-02-09, 2012-02-10, 2012-02-13, 2012-02-14, 2012-02-15, 2012-02-16, 2012-02-17, 2012-02-21, 2012-02-22, 2012-02-23, 2012-02-24, 2012-02-27, 2012-02-28, 2012-02-29, 2012-03-01, 2012-03-02, 2012-03-03, 2012-03-05, 2012-03-06, 2012-03-07, 2012-03-09, 2012-03-12, 2012-03-13, 2012-03-14, 2012-03-15, 2012-03-16, 2012-03-19, 2012-03-20, 2012-03-21, 2012-03-22, 2012-03-23, 2012-03-26, 2012-03-27, 2012-03-28, 2012-03-29, 2012-03-30, 2012-04-02, 2012-04-03, 2012-04-04, 2012-04-09, 2012-04-10, 2012-04-11, 2012-04-12, 2012-04-13, 2012-04-16, 2012-04-17, 2012-04-18, 2012-04-19, 2012-04-20, 2012-04-23, 2012-04-24, 2012-04-25, 2012-04-26, 2012-04-27, 2012-04-30, 2012-05-02, 2012-05-03, 2012-05-04, 2012-05-07, 2012-05-08, 2012-05-09, 2012-05-10, 2012-05-11, 2012-05-14, 2012-05-15, 2012-05-16, 2012-05-17, 2012-05-18, 2012-05-21, 2012-05-22, 2012-05-23, 2012-05-24, 2012-05-25, 2012-05-28, 2012-05-29, 2012-05-30, 2012-05-31, 2012-06-01, 2012-06-04, 2012-06-05, 2012-06-06, 2012-06-07, 2012-06-08, 2012-06-11, 2012-06-12, 2012-06-13, 2012-06-14, 2012-06-15, 2012-06-18, 2012-06-19, 2012-06-20, 2012-06-21, 2012-06-22, 2012-06-25, 2012-06-26, 2012-06-27, 2012-06-28, 2012-06-29, 2012-07-02, 2012-07-03, 2012-07-04, 2012-07-05, 2012-07-06, 2012-07-09, 2012-07-10, 2012-07-11, 2012-07-12, 2012-07-13, 2012-07-16, 2012-07-17, 2012-07-18, 2012-07-19, 2012-07-20, 2012-07-23, 2012-07-24, 2012-07-25, 2012-07-26, 2012-07-27, 2012-07-30, 2012-07-31, 2012-08-01, 2012-08-02, 2012-08-03, 2012-08-06, 2012-08-07, 2012-08-08, 2012-08-09, 2012-08-10, 2012-08-13, 2012-08-14, 2012-08-16, 2012-08-17, 2012-08-21, 2012-08-22, 2012-08-23, 2012-08-24, 2012-08-27, 2012-08-28, 2012-08-29, 2012-08-30, 2012-08-31, 2012-09-03, 2012-09-04, 2012-09-05, 2012-09-06, 2012-09-07, 2012-09-08, 2012-09-10, 2012-09-11, 2012-09-12, 2012-09-13, 2012-09-14, 2012-09-17, 2012-09-18, 2012-09-20, 2012-09-21, 2012-09-24, 2012-09-25, 2012-09-26, 2012-09-27, 2012-09-28, 2012-10-01, 2012-10-03, 2012-10-04, 2012-10-05, 2012-10-08, 2012-10-09, 2012-10-10, 2012-10-11, 2012-10-12, 2012-10-15, 2012-10-16, 2012-10-17, 2012-10-18, 2012-10-19, 2012-10-22, 2012-10-23, 2012-10-25, 2012-10-29, 2012-10-30, 2012-10-31, 2012-11-01, 2012-11-02, 2012-11-05, 2012-11-06, 2012-11-07, 2012-11-08, 2012-11-09, 2012-11-11, 2012-11-12, 2012-11-15, 2012-11-16, 2012-11-19, 2012-11-20, 2012-11-21, 2012-11-22, 2012-11-23, 2012-11-26, 2012-11-27, 2012-11-29, 2012-11-30, 2012-12-03, 2012-12-04, 2012-12-05, 2012-12-06, 2012-12-07, 2012-12-10, 2012-12-11, 2012-12-12, 2012-12-13, 2012-12-14, 2012-12-17, 2012-12-18, 2012-12-19, 2012-12-20, 2012-12-21, 2012-12-24, 2012-12-26, 2012-12-27, 2012-12-28, 2012-12-31, 2013-01-01, 2013-01-02, 2013-01-03, 2013-01-04, 2013-01-07, 2013-01-08, 2013-01-09, 2013-01-10, 2013-01-11, 2013-01-14, 2013-01-15, 2013-01-16, 2013-01-17, 2013-01-18, 2014-01-01, 2014-02-17, 2014-03-22, 2014-04-24, 2014-10-15, 2015-01-01, 2015-02-28, 2015-04-15, 2016-01-01, 2016-08-12, 2017-04-17, 2018-01-01, 2018-04-27, 2018-05-21, 2018-07-06, 2018-07-13, 2018-08-10, 2018-09-11, 2018-09-24, 2018-10-10, 2018-10-25, 2018-11-06, 2018-11-15, 2018-11-26, 2018-11-27, 2019-01-01, 2019-10-27, 2020-02-17, 2020-09-17, 2020-11-14, 2021-03-08, 2021-04-07, 2021-05-27, 2021-07-14, 2022-08-16, 2023-03-22, 2023-08-16, 2024-02-19, 2024-04-01, 2024-07-01, 2024-07-02, 2024-07-03

</details>

<details><summary>repeated_adjusted_close: 4 observations</summary>

2014-05-14, 2016-10-27, 2017-03-31, 2024-05-08

</details>

<details><summary>move_over_20pct_adjusted_close: 0 observations</summary>

None

</details>


### Phase 4D status

January 20, 2024 is now reconciled: 8/8 stock conversions pass the existing
Phase 4B procedure and the separate Nifty 50 close is verified. The new
research_v3 has zero full-period calendar discrepancies or 21-session clock
mismatches, but exhaustive amendment coverage remains unverified. The backtest
gate remains closed; vintage-adjustment limitations and unresolved anomaly flags
remain. See `india_research/reports/india_session_phase4d_review.md` (repository
root path) for evidence, ledger, hashes and remaining certification requirements.
