> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# India expansion factors: real-data signal-only readiness

## Readiness decision

**Stop for review before any real-data portfolio evaluation.** Four factors are
ready for a separately approved PROVISIONAL diagnostic under the unchanged frozen
price convention. `academic_illiq` is conditional on explicit acceptance of the
measured adjustment/proxy sensitivity. None is classified as mathematically
unsuitable in this basket. These are applicability recommendations, not Keep/Drop
or expected-profitability decisions; no realized portfolio returns were examined.

| Factor | Finite evaluation scores | NaNs / infinities | Eight-score weekly eligibility | Unique top-two / boundary ties | Recommendation |
|---|---:|---:|---:|---:|---|
| `alpha101_033` | 7,920 / 7,920 | 0 / 0 | 209 / 209 | 209 / 0 | Ready for provisional backtest with common vintage/calendar caveats |
| `alpha101_101` | 7,920 / 7,920 | 0 / 0 | 209 / 209 | 209 / 0 | Ready; preserve the original fixed 0.001 price-unit term |
| `alpha101_054` | 7,920 / 7,920 | 0 / 0 | 209 / 209 | 209 / 0 | Ready; monitor original flat-range/large-power denominator behavior |
| `alpha101_014` | 7,920 / 7,920 | 0 / 0 | 209 / 209 | 209 / 0 | Ready under the predeclared basis, with measured dividend/volume sensitivity warnings |
| `academic_illiq` | 7,920 / 7,920 | 0 / 0 | 209 / 209 | 209 / 0 | Conditional: frozen adjusted-INR closing-turnover proxy and vintage dependence must be accepted explicitly |

There are 990 evaluation sessions and 209 W-FRI candidate dates per factor. The
December 31, 2024 terminal candidate has no subsequent evaluation session;
**208** candidates per factor have a later eligible session. These are signal
candidates, not orders, executions or trades. There are no exact ties anywhere in
any factor's 990 daily score rows, no all-name ties, and no weekly second/third
near-ties at absolute score tolerance 1e-10. All candidate memberships are invariant
to ascending versus descending ticker ordering. No stock has a constant score
rank over the full evaluation. ILLIQ selections are concentrated but not degenerate:
Kotak appears in 127 pairs, TCS 92, Axis 91, SBI 57, Infosys 48 and ICICI 3;
Reliance/HDFC appear in none. This is a signal exposure description, not a result.

## Exact provenance and unchanged methodology

Audit artifacts: `archive:india_phase2_signal_readiness_20261029T050613Z/`.
Dataset:
`archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/research_manifest.json`.
Manifest SHA-256:
`9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`.
Nine history hashes, exact stock order, benchmark, runtime/HEAD and basis-evidence
binding are saved in `provenance.json`. The manifest's strict calendar/backtest
flags remain false and unchanged; this signal audit supplies no diagnostic override.

Input is the eight assigned NSE equities (Reliance, TCS, Infosys, HDFC Bank,
ICICI Bank, SBI, Kotak Bank, Axis Bank), with `^NSEI` separate. `load_factor_dataset`
verifies all nine histories and prepares 1,015 rows: 25 prior sessions from
November 26, 2020 through January 1, 2021 plus January 4, 2021–December 31, 2024.
No post-2024 price/volume observation or October 2025 onward holdout was used.
Later corporate-action metadata are used only to explain the already frozen
vendor units, not as historical trading signals.

Baseline calls use `src/india_phase2_factors.py::evaluate_phase2_factor`. The new
`src/india_phase2_readiness.py::original_diagnostic_scores` invokes the same
pinned original modules in isolated child processes, adding observation of raw
infinities/NaNs before JSON serialization and warning capture around original
compute. Baseline values agree exactly with the production integration for all
five factors. Original Vibe HEAD is
`7f6908b7e1b95d971f4151bfaf2382e2ce9485cf`; per-module/base/analysis hashes are
recorded with each original metadata response. Formula paths are under
`https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_033.py`,
`alpha_101.py`, `alpha_054.py`, `alpha_014.py`, and
`https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/academic/illiq.py`.
No formulas, registry metadata, original infrastructure or portfolio settings changed.

`weekly_profiles`/`membership_profile` from `src/india_alpha004_audit.py` enumerate
all admissible top-two pairs under original scores before ticker tie breaking.
They use the same W-FRI last-returned-session candidates and descending score/
ascending ticker selection as the established methodology. The next-session
execution convention, costs, benchmark methodology and IC/Sharpe definitions
remain unchanged but were not exercised on real data. No forward return labels,
IC, Sharpe, portfolio construction or trading simulation were calculated here.

## Missingness, numerical behavior and lookback checks

Every stock has zero missing evaluation scores for every factor. No required
OHLCV input is missing or infinite in the 1,015-row common input. There are no
zero-volume stock observations, flat OHLC ranges, zero factor denominators,
constant ten-session raw open/volume windows, or close changes exceeding 20%
in the evaluation. These are checks on this research view, not declarations that
every original Yahoo observation in its full historical archive was clean.

| Factor | First all-eight-finite input date | Original warm-up NaNs across input | Minimum weekly second–third score gap |
|---|---|---:|---:|
| `alpha101_033` | 2020-11-26 | 0 | 0.125 |
| `alpha101_101` | 2020-11-26 | 0 | 0.000286514 |
| `alpha101_054` | 2020-11-26 | 0 | 0.0000722441 |
| `alpha101_014` | 2020-12-10 | 72 (9 × 8) | 0.000456053 |
| `academic_illiq` | 2020-12-29 | 168 (21 × 8) | 0.00741928 |

All NaNs are explained by original warm-up; none is filled. The full per-cell
cause/denominator audit is in each factor's `input_and_missingness.csv`.
Original compute emitted no captured warnings and no final raw infinities,
including before pandas serialization can turn nonfinite output into nulls.
Original helpers may deliberately map undefined intermediate divisions/correlations
to NaN; this observation does not claim that no floating-point operation exists
inside those helpers. Current real inputs have no zero/invalid denominators;
synthetic regressions verify the undefined cases separately.

- #033 uses original percentile rank of `open/close - 1`: eight distinct daily
  ranks in this dataset. Same-session common OHLC scaling does not alter the ratio.
- #101 uses `(close-open)/(high-low+0.001)`. Its smallest denominator is
  1.7739426 INR on the frozen scale; score magnitudes change with scale because
  0.001 is fixed, but no tested daily rank or weekly selection changed. This
  measured result is not a proof of scale invariance on other prices.
- #054 retains the original fifth powers and `(low-high)*close^5` denominator.
  Minimum absolute nonzero denominator is approximately 5.24564e12 in these units;
  all inspected values are finite. A flat bar would be NaN, unlike #101's zero.
- #014 correlates **unranked** open and volume over ten sessions, multiplied by
  the cross-sectional rank of a three-step change in one-session close returns.
  Its warm-up is ten bars, not a ten-session rank correlation like #003.
  No evaluation window is incomplete or constant; no #003-style degeneracy occurs.
- ILLIQ requires one prior close plus 21 complete daily ratios. All 21-session
  denominators are positive; minimum current price × volume is about
  193,694,781 INR-proxy units. Cross-sectional sample standard deviation is
  positive throughout and the returned z-scores have unit sample dispersion.

Fifteen prefix recomputations (all five factors at December 30, 2022; July 19,
2023; October 25, 2024) reproduce the corresponding full-history prefixes with
rtol 1e-10/atol 1e-12 including NaN patterns. Five minimal-history checks reproduce
the final row with 1/1/1/10/22 bars respectively; maximum #014 difference is
3.851e-13 and ILLIQ 9.992e-16, consistent with rolling floating-point accumulation.
These checks support causal row alignment and no algorithmic future dependence.
They do **not** certify a historically point-in-time data vintage: later Yahoo
adjustments remain embedded in historical prices. Subsequent-close execution is
still required to avoid trading at a close used to form that day's signal.

## Input-convention diagnostics

All alternatives are labelled input-only diagnostics run through unchanged Vibe
compute; none is a chosen replacement convention or repaired dataset. Alternative
scores and every weekly pair comparison are saved separately. The table counts
changed ticker-selected memberships among 209 candidates; baseline and compared
alternative memberships are unique in these comparisons, with disjoint admissible
pair sets for every reported difference. Counts also equal nonterminal changes
except 127 below includes one terminal change (126 nonterminal).

| Diagnostic input change | #033 | #101 | #054 | #014 | ILLIQ |
|---|---:|---:|---:|---:|---:|
| Remove saved row-specific `Adj Close / Close` factor from all OHLC (Yahoo Close basis, **not nominal**) | 0 | 0 | 0 | 5 | 51 |
| Remove each stock's fixed terminal dividend normalization from OHLC | 0 | 0 | 0 | 0 | 31 |
| Remove known share price scaling, keep existing volume (deliberate unit mismatch for turnover) | 0 | 0 | 0 | 0 | 127 |
| Remove known share price scaling with reciprocal volume conversion | 0 | 0 | 0 | 1 | 4 |
| Convert only volume by known share factors (deliberate mismatch for turnover) | Not dependent | Not dependent | Not dependent | 1 | 153 |
| Reintroduce twelve old research_v3 volumes, diagnostically only | Not dependent | Not dependent | Not dependent | 2 | 11 |
| Treat existing zero volume as missing, diagnostically only | Not dependent | Not dependent | Not dependent | 0 | 0 |

Known-share scaling is HDFC ×2 and Kotak ×5 throughout this pre-2025 study, plus
Reliance ×2 before its October 28, 2024 bonus; volume conversion is reciprocal.
Official share-event source metadata/hashes are preserved from the prior #004
investigation and current NSE action records. Full nominal history before the
Reliance demerger is not reconstructed. Terminal normalization removal is a
controlled fixed-scalar sensitivity, not an independently reconstructed historical
adjustment vintage. Neither price-only nor volume-only mismatches is a valid
alternative for comparable turnover; their large effects demonstrate why units
must not be mixed. Paired price/volume conversion cancels the denominator scaling,
but the Reliance date-varying price conversion creates a nominal action jump in
the numerator: ILLIQ's four changed candidates are November 1, 8, 14 and 22, 2024,
within the resulting 21-observation window. This does not identify a defect in the
approved adjusted-return implementation or justify adopting action jumps.

#014's five Yahoo-Close-basis changes (23 daily top-two changes; 80 daily rank
changes) demonstrate cash-adjustment sensitivity, rather than ties or invalid
scores. The original corrected volume view differs from old uncorrected quantities
at two weekly #014 and eleven ILLIQ candidates. That is support for respecting
the verified corrections, not permission to revert them. Dates are enumerated in
`changed_weekly_candidate_dates.json`; official action-date score associations
are in `action_date_score_comparisons.csv`, without claiming causation from
proximity alone. Available official action metadata are not a complete independent
2020–2024 action inventory. No convention was selected using historical returns.

## ILLIQ turnover, volume and vintage finding

`academic_illiq` retains its original absolute-return / (close × volume), 21-session
mean and cross-sectional z-score. Under the developer-approved India exception,
prices are **INR adjusted prices**, not USD. Multiplying price by vendor-unit volume
produces a dividend-adjusted **closing-price turnover proxy**, not NSE actual
traded value. Actual exchange traded value is recorded separately in the audit.
Original metadata still lacks `equity_in` and still describes dollar volume; the
India exception is separately recorded as developer-approved research use, not
an upstream endorsement or explicit PM approval of the factor.

Reparsed original official NSE EQ records, verified their recorded source hashes
and instrument-specific positive trading evidence, and compared current research_v4:

`adjusted_close * vendor_volume ≈ official_nominal_close * official_quantity * D(t)`

`D(t)` is the saved Yahoo `Adj Close / Close` factor. All **256 observations across
32 dates passed** at `8 * float32 epsilon` relative tolerance; maximum absolute
relative error is **2.656182248594874e-7**. The new ledger
`official_turnover_proxy_reverification.csv` retains quantities, official nominal
closes, actual traded value, current proxy, expected proxy, ratios and source hashes.
The existing dataset-bound basis evidence loaded successfully. This does not
independently certify every daily share quantity or turn a vendor factor into an
independent reconstruction of all dividends/normalizations.

No zero volumes occur in the study input. A synthetic zero-volume test confirms
that original safe division leaves a daily NaN and invalidates the full ensuing
21-session mean for that stock, returning finite at the next clean window.
An all-zero-return synthetic basket confirms zero cross-sectional dispersion
remains NaN; neither missingness nor degenerate scores are filled. Existing
volume corrections are retained; small Kotak quantity uncertainty and unresolved
Reliance pre-July-2023 normalization are disclosed. Cancellation in sampled
price × volume products does not settle Reliance adjusted-return interpretation.

ILLIQ's 51/209 selection differences from removing dividend adjustments and
31/209 from removing a fixed terminal normalization show **material research
convention dependence**, even though all eight scores are numerically valid.
The frozen-vintage convention is documented and internally supported, so this
alone does not make the factor unsuitable. Recommendation is **conditional**:
only a separately approved frozen-proxy provisional experiment, explicitly
accepting these sensitivities and historical-vintage limits. Do not present it as
a nominal-turnover or historically point-in-time illiquidity test. No proposed
repair, new currency, dividend removal or volume convention is adopted.

## Tests, preservation and next approval

Complete command:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

**300 passed in 47.98 seconds**, no failures, skips or warnings. Thirteen new
`tests/test_india_phase2_readiness.py` cases use explicitly synthetic data and
actual isolated original functions: numerical observation, complete NaN causes,
original warm-up, zero-volume rolling propagation, flat denominators, constant
raw correlations, tie enumeration, terminal dates, nonfinite eligibility, bad
inputs and zero illiquidity dispersion. Prior 287 cases also pass.
An earlier targeted run passed twelve cases with pandas future-format warnings
from audit serialization; the helper now specifies `date_format='iso'` explicitly.
Original scoring code used before this harmless refinement is preserved with the
execution log; original numeric computations did not change.

At scoring completion all 643 captured files matched their starting hashes.
The set included the new audit helper created in this task; its subsequent
serialization-only refinement is documented separately. Final preservation checks
cover the other 642 files byte-for-byte: all previous archive:reports, versioned
snapshots, archived evidence and pre-existing implementation/tests. No old report
was edited. Final artifact inventory, full test log and source snapshots accompany
this review. AGENTS.md, weekly plan, project context and methodology are updated
to reflect completed signal audits, while retaining three provisional portfolio
backtests and the two original unsuccessful applicability studies.

Signal readiness is not portfolio validation, calendar certification, PM sign-off
or approval to repeat prior experiments. Await separate approval for any new
provisional diagnostic; retain the original cutoff, holdout, subsequent-close
execution, costs and all existing validation gates.
