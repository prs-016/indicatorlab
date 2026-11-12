> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# Phase 4B: recovered NSE sessions on the frozen Yahoo-adjusted basis

Reviewed October 28, 2026 (Pacific). **24/24 stock conversions verified within the stated vintage-calibrated scope; no unresolved conversion among these 24. Dataset remains gated for full-calendar review and user approval. No portfolio backtest run.**

## Version and immutable sources

**Subsequent Phase 4C update:** The calendar audit (`india_calendar_phase4c_review.md`, historical/archival record not included; see archive index) found another genuine session, January 20, 2024, absent in all nine research_v2 histories. Its official nominal records were retrieved as evidence but not inserted or converted in Phase 4C. The 24 verified conversions documented here are unchanged; research_v2 and its manifest remain immutable. No calendar-certified dataset was created and global STREV readiness remains false.

New research version: `research_v2/research_manifest.json` (`research_manifest.json`, historical/archival record not included; see archive index). Its `derived/` contains nine separate histories with the three recovered dates added. The previous Yahoo snapshot, six original NSE files, their manifests, and the previous research_v1 evidence dataset were preserved and hash-checked. Existing stock observations in the new version were asserted numerically unchanged before serialization. This does not overwrite the earlier blocked experiment.

Audit artifacts in the version: `conversion_ledger.json` (24 detailed calculations), `conversion_ledger.csv`, `independent_dividend_checks.csv` (12 cash-event checks), and `official_corporate_actions.csv` (41 returned NSE records for the eight stocks). The parent evidence directory contains original downloaded bytes, three retrieval manifests including unsuccessful legacy URLs, `yfinance_convention.json`, and `build_research_v2.py`. The build script is network-free, validates hashes/source URLs/date/series/ISIN, requires a new destination, and writes only passing conversions. `src/india_adjustments.py` contains the calculation/verification logic; synthetic tests are in `tests/test_india_adjustments.py`.

Additional evidence retrieved: six official NSE bhavcopies bracketing the recovered sessions, official ex-dividend bhavcopies for eleven 2024 dates covering twelve stock dividends, NSE's corporate-action API response for November 1, 2023–October 28, 2026, and issuer/exchange documents for the later share-scale events. Old-format URLs for six post-July-2024 files returned 404; the corresponding official NSE UDiFF archives were retrieved successfully and parsed separately. No other exchange prices, post-2024 security prices, or forward-filled values were used.

## Adjustment convention and verification scope

The target is **the original snapshot's Yahoo-adjusted vintage**, not a claim to have independently recreated every future dividend adjustment or a historical point-in-time data feed. The inspected installed yfinance 1.7.0 `auto_adjust` function scales OHLC by Yahoo-supplied `Adj Close / Close`; it does not itself establish how Yahoo constructed those series. That source and its hash are recorded separately.

Split/bonus adjustment and cash-dividend adjustment are distinct:

- Let `N(t)` be the recovered official nominal close.
- Let `B(t)` be the cumulative later share multiplier through the snapshot vintage, independently supported by the returned NSE action history: 2 for Reliance (1:1 bonus), 2 for HDFC Bank (1:1 bonus), 5 for Kotak (face-value subdivision), and 1 for the other five stocks. Historical ISINs are checked against the original official session records.
- Choose the frozen December 31, 2024 price-basis anchor `D(T) = Yahoo Adj Close(T) / Yahoo Close(T)`. This observed anchor fixes the remaining vendor-vintage normalization, including the effect of later cash events. It is not invented or assumed to be 1.
- Independently reconstruct relative cash-dividend effects from each missing date to T: `D(t) = D(T) * product(1 - cash_dividend(e) / official_previous_nominal_close(e))` for `t < ex_date(e) <= T`.
- Compute the conversion factor `F(t) = D(t) / B(t)`, and adjusted OHLC `= official nominal OHLC * F(t)`.

Each cash amount/ex-date comes from official NSE corporate-action metadata. Pre-dividend nominal closes come from that ex-date's official equity bhavcopy PREVCLOSE field, with stock identity/date and positive trading evidence checked. Combined ordinary/special dividends are summed explicitly (TCS January 2024: 9 + 18 = 27; Infosys May 2024: 20 + 8 = 28). Official nominal cash amounts are not confused with split-adjusted Yahoo cash entries: HDFC 19.50 versus Yahoo 9.75; Kotak 2 versus Yahoo 0.40; Reliance 10 versus Yahoo 5 reflect the later share-scale changes.

**Independent checks:** all twelve official dividend-step factors agree with the corresponding frozen Yahoo factor changes; both independent nominal-price anchors around every missing date agree with reconstructed split, cash-dividend and total factors. There are 48 anchor records. NSE action metadata contains no split/bonus/dividend inside any of the six-date brackets, so no boundary is silently bridged. A conflicting anchor, action in the bracket, duplicate/unknown action or missing pre-dividend evidence causes an unresolved result, never a replacement price.

Numerical comparison uses relative tolerance `8 * float32 epsilon` (approximately 9.54e-7), chosen for the precision visible in the Yahoo snapshot, not tuned to strategy results. These are reconstructed values on a specified adjusted basis, not additional exchange-quoted prices or exact predictions of Yahoo's missing floating-point output.

**Limitation:** post-2024 cash-event adjustments are inherited through the explicitly chosen frozen terminal anchor rather than independently recomputed from holdout-period prices. Later corporate-action metadata is recorded, but no holdout prices were fetched to reconstruct its full cash-adjustment chain. The verification establishes consistency of the conversion with the chosen vintage using independent pre-cutoff action/price evidence; it does not certify the absolute correctness of every Yahoo adjustment. Later uniform rescalings cancel in STREV return ratios; vendor revisions remain a general limitation.

## Independently supported later share-scale events

- Reliance: [issuer October 16, 2024 filing](https://www.ril.com/sites/default/files/2024-10/SE_16102024.pdf), 1:1 bonus, record date October 28; NSE action history gives October 28, 2024 ex-date. Share multiplier 2, not a cash dividend.
- HDFC Bank: [issuer filing on SEC](https://www.sec.gov/Archives/edgar/data/1144967/000119312525191696/d22509dex99.htm), 1:1 bonus with August 27, 2025 record date and August 28 allotment; NSE metadata gives August 26 ex-date. Record, allotment and ex-dates are not interchangeable. Share multiplier 2.
- Kotak: [NSE CML72216](https://nsearchives.nseindia.com/content/circulars/CML72216.pdf), January 14, 2026 ex-date, face value 5 to 1 and new ISIN. Share multiplier 5.

The [official NSE corporate-action response](https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=01-11-2023&to_date=28-10-2026) is saved with its original bytes/hash. This response also records later dividends through the snapshot vintage; it supplies metadata rather than holdout price observations.

## All 24 calculations

`D` below includes the frozen terminal normalization and reconstructed pre-terminal dividend factors; `F = D/B`. Full source hashes, anchors, intermediate products and per-event calculations are in the JSON ledger. All rows pass the independent checks.

| Stock | Date | Official nominal close | Share multiplier B | Dividend factor D | Total factor F | Adjusted close |
|---|---|---:|---:|---:|---:|---:|
| RELIANCE.NS | 2023-11-12 | 2330.65 | 2 | 0.9880844229 | 0.4940422115 | 1151.439480 |
| RELIANCE.NS | 2024-03-02 | 2982.15 | 2 | 0.9880844229 | 0.4940422115 | 1473.307981 |
| RELIANCE.NS | 2024-05-18 | 2869.65 | 2 | 0.9880844229 | 0.4940422115 | 1417.728232 |
| TCS.NS | 2023-11-12 | 3357.30 | 1 | 0.9090205326 | 0.9090205326 | 3051.854634 |
| TCS.NS | 2024-03-02 | 4107.10 | 1 | 0.9153533725 | 0.9153533725 | 3759.447836 |
| TCS.NS | 2024-05-18 | 3851.45 | 1 | 0.9220063406 | 0.9220063406 | 3551.061321 |
| INFY.NS | 2023-11-12 | 1388.20 | 1 | 0.9215431960 | 0.9215431960 | 1279.286265 |
| INFY.NS | 2024-03-02 | 1656.30 | 1 | 0.9215431960 | 0.9215431960 | 1526.351996 |
| INFY.NS | 2024-05-18 | 1443.65 | 1 | 0.9215431960 | 0.9215431960 | 1330.385835 |
| HDFCBANK.NS | 2023-11-12 | 1500.00 | 2 | 0.9575343207 | 0.4787671603 | 718.150740 |
| HDFCBANK.NS | 2024-03-02 | 1430.75 | 2 | 0.9575343207 | 0.4787671603 | 684.996115 |
| HDFCBANK.NS | 2024-05-18 | 1466.05 | 2 | 0.9706098944 | 0.4853049472 | 711.481318 |
| ICICIBANK.NS | 2023-11-12 | 942.35 | 1 | 0.9756478247 | 0.9756478247 | 919.401728 |
| ICICIBANK.NS | 2024-03-02 | 1084.65 | 1 | 0.9756478247 | 0.9756478247 | 1058.236413 |
| ICICIBANK.NS | 2024-05-18 | 1130.75 | 1 | 0.9756478247 | 0.9756478247 | 1103.213778 |
| SBIN.NS | 2023-11-12 | 581.30 | 1 | 0.9470761383 | 0.9470761383 | 550.535359 |
| SBIN.NS | 2024-03-02 | 773.30 | 1 | 0.9470761383 | 0.9470761383 | 732.373978 |
| SBIN.NS | 2024-05-18 | 821.00 | 1 | 0.9470761383 | 0.9470761383 | 777.549510 |
| KOTAKBANK.NS | 2023-11-12 | 1752.50 | 5 | 0.9960351879 | 0.1992070376 | 349.110333 |
| KOTAKBANK.NS | 2024-03-02 | 1723.70 | 5 | 0.9960351879 | 0.1992070376 | 343.373171 |
| KOTAKBANK.NS | 2024-05-18 | 1696.95 | 5 | 0.9960351879 | 0.1992070376 | 338.044382 |
| AXISBANK.NS | 2023-11-12 | 1029.95 | 1 | 0.9976061583 | 0.9976061583 | 1027.484463 |
| AXISBANK.NS | 2024-03-02 | 1096.70 | 1 | 0.9976061583 | 0.9976061583 | 1094.074674 |
| AXISBANK.NS | 2024-05-18 | 1143.75 | 1 | 0.9976061583 | 0.9976061583 | 1141.012044 |

## Twelve independent cash-dividend step checks

All previous prices below are official nominal PREVCLOSE values; formulas use cash and price in the same share units. This avoids double-counting splits and does not use Yahoo's split-scaled dividend cash as nominal cash.

| Stock | Ex-date | Nominal cash | Official previous close | Expected factor | Observed Yahoo factor step | Pass |
|---|---|---:|---:|---:|---:|---|
| RELIANCE.NS | 2024-08-19 | 10 | 2956.40 | 0.9966175078 | 0.9966175793 | True |
| TCS.NS | 2024-01-19 | 27 | 3902.60 | 0.9930815354 | 0.9930814834 | True |
| TCS.NS | 2024-05-16 | 28 | 3880.40 | 0.9927842490 | 0.9927842562 | True |
| TCS.NS | 2024-07-19 | 10 | 4315.55 | 0.9976827983 | 0.9976827764 | True |
| TCS.NS | 2024-10-18 | 10 | 4109.00 | 0.9975663178 | 0.9975662568 | True |
| INFY.NS | 2024-05-31 | 28 | 1427.45 | 0.9803846019 | 0.9803846921 | True |
| INFY.NS | 2024-10-29 | 21 | 1865.35 | 0.9887420591 | 0.9887421382 | True |
| HDFCBANK.NS | 2024-05-10 | 19.5 | 1447.50 | 0.9865284974 | 0.9865284489 | True |
| ICICIBANK.NS | 2024-08-12 | 10 | 1171.60 | 0.9914646637 | 0.9914646946 | True |
| SBIN.NS | 2024-05-22 | 13.7 | 830.65 | 0.9835068922 | 0.9835069240 | True |
| KOTAKBANK.NS | 2024-07-19 | 2 | 1826.75 | 0.9989051594 | 0.9989052023 | True |
| AXISBANK.NS | 2024-07-12 | 1 | 1296.75 | 0.9992288413 | 0.9992288715 | True |

## Dataset integration and remaining gate

Only passing conversions were inserted into independent copies of the eight derived stock histories. The three already verified Nifty 50 price-index observations were inserted separately in index points; no equity split/dividend factor was applied to the index. Original observations and raw sources remain unchanged. New stock OHLC uses a common verified factor; new volumes are actual NSE shares traded, explicitly not an inferred Yahoo back-adjusted volume series. This volume convention is sufficient for the current positive-volume execution gate but requires review before turnover/liquidity comparisons using historical share quantities.

No nominal mixed-basis stock price was inserted. No interpolation, nearest-day ratio carry, invented price, blanket anomaly deletion, or `repair=True` was used. Share events after the missing dates are included even when they occur after 2024; only their metadata, not holdout price outcomes, was consulted.

**Readiness:** the three-session conversion gate is resolved (24 verified, 0 unresolved). The global `backtest_ready` flag remains false pending full evaluation/warm-up session-calendar certification and user review. Recovering these three sessions does not prove that all other official sessions are present. Existing unresolved anomaly flags and evidence-backed research-view exclusions still apply. No portfolio returns, IC, Sharpe or strategy decisions were produced.

The full test suite passed 95 tests with no failures, skips or warnings. New tests explicitly cover each of the three recovered sessions, separate split/dividend components, combined special dividends, disagreements between independent anchors, absent evidence, within-bracket actions, duplicate/unknown actions, and rejection of post-cutoff price anchors. Dataset construction initially caught an ISIN-column attribute-access error and an index-name preservation assertion; both were corrected before the version was created. The final build reported all 24 conversions and all 12 independent dividend checks passing.
