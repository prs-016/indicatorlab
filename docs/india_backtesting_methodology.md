# India backtesting methodology

Decision date: October 28, 2026. Status: **developer-approved provisional baseline,
standard until instructed otherwise; final strategy evaluations are not authorized.**

## Approval provenance

The developer approved combining **Vibe-Trading's original factor calculations
and IC functions with Jack-adapted portfolio accounting and Sharpe**. This
supersedes earlier language treating the combination solely as a proposal.

The recorded PM decision approves using Vibe-Trading instead of unavailable
`mini_bench.py`. The assignment also fixes the eight NSE equities, `^NSEI`, the
five named reversal factors, December 31, 2024 inclusive cutoff, and the October
1, 2025 onward holdout restriction. **No PM approval of the portfolio parameter
values below is recorded.** Their authority is the developer's current instruction.

The five factors remain `academic_strev`, `alpha101_001`, `alpha101_002`,
`alpha101_003`, and `alpha101_004`. STREV is wired end to end; `src/india_factors.py` now adds the four original
Alpha101 OHLCV integrations, tested with synthetic inputs only. All use the
unchanged portfolio baseline and original Vibe IC; no other real-data factor
evaluation has been authorized. No factor definition is replaced
by a momentum rule or by portfolio weighting logic.

## Source and architecture

- `src/india_backtest.py::prepare_research_view`: independent research copy,
  evidence-backed exclusions and a returned ledger; unresolved flags remain.
- `src/india_vibe_bridge.py::evaluate_strev`: calls Vibe's unchanged
  `agent/src/factors/zoo/academic/strev.py::compute` in an isolated child.
- `src/india_backtest.py::simulate_portfolio`: pure sequential accounting,
  adapted from local `origin/jack` commit `725b40b`,
  `hk_week1/backtest_strategies.py` (`build_rebalances`, `simulate`, `metrics`).
- `src/india_vibe_bridge.py::compute_rank_ic`: calls Vibe's original
  `agent/src/factors/factor_analysis_core.py::compute_ic_series` on explicit
  execution-interval labels. It never substitutes IC information ratio for Sharpe.
- `src/india_backtest.py::backtest_strev`: composes those pieces and returns
  provisional results, data flags, exclusion ledger, configuration and factor
  source hashes. Nothing downloads, writes outputs, or executes on import.

Both repositories use `src` packages: retain isolated subprocess imports. Use
the project virtual environment for both parent and child. The code neither
patches Vibe nor reimplements STREV or rank correlation.

## Configurable baseline

`PortfolioConfig` defaults:

| Setting | Baseline |
|---|---|
| Evaluation dates | 2021-01-04 through 2024-12-31; input includes preceding warm-up |
| Holdings | Top two scores, long-only, 50% target each, fractional weights |
| Ranking | Descending original Vibe score; equal scores sorted by ticker |
| Signal universe | All eight finite scores required; configurable minimum |
| Rebalancing | Last supplied session of each `W-FRI` period |
| Execution | Subsequent eligible close, never the signal's own close |
| Costs | 10 basis points per unit of absolute traded NAV |
| Sharpe | Daily net excess returns, sample standard deviation, sqrt(252), zero annual risk-free baseline |

Dates, holdings count, weekly anchor, minimum signal names, cost rate,
annualization, and annual risk-free rate are configurable. End dates after
December 31, 2024 are rejected, including dates before the later team holdout.
No cost or parameter search is performed. Annual risk-free rate affects Sharpe
only; uninvested cash earns zero in this baseline.

Prices must be declared adjusted and have exactly the eight assigned stock
columns; the benchmark stays separate. STREV requires 21 prior intervals (22
closing observations). Its original endpoint/missing-value behavior is preserved;
the previously proposed full-22-close eligibility filter has **not** been adopted
implicitly. A missing score skips/logs a weekly target if the configured minimum
is not met. Existing holdings persist unless a later target executes.

## Causal accounting and execution

For each supplied session close:

1. Value existing holdings using current/prior closes and drift their weights.
   A missing held price raises an error; no partial Sharpe or zero-return fill is
   produced. Missing unheld prices are preserved.
2. Attempt the pending target from an earlier signal. Require a reliable current
   price and positive volume for every changed position, including outgoing
   holdings. Missing/zero volume defers the entire order.
3. Apply turnover costs and replace weights only if execution succeeds.
4. Observe today's closing scores. If this is a weekly signal close, cancel any
   still-unfilled old target and stage a new eligible target for a later close.

Thus a prior target may execute at the next signal's close, before that new
signal is staged. An unfilled order never survives past replacement by a new
signal. Delays/cancellations/skipped signals are logged; an unresolved final
order expires. There is no forced terminal liquidation or post-cutoff price use.

Turnover is `sum(abs(target - pretrade_drifted_weights))`: initial entry is 1,
complete replacement is 2. Costs are `turnover * cost_bps / 10000`, and net return
is `(1 + gross_return) * (1 - cost_fraction) - 1`. This deliberately matches
Jack's proportional-cost accounting approximation, rather than a share-level
cash/fee solver. Costs include initial entry. Equal weights are targets, not
daily constant weights. Evaluation includes initial cash days before first
execution, unlike Jack's common-first-execution reporting start; this convention
is explicit and can be changed through the configured evaluation start.

Positive daily volume plus a close is an execution approximation, not proof of
available closing-auction liquidity. No shorting, financing, borrow, board lots,
slippage schedule, or actual Indian fee/tax breakdown is modeled. Ten basis
points is a developer-approved provisional assumption, not a verified fee quote.
Dividends are already represented through adjusted returns and are not added twice.

## IC, Sharpe, and benchmark

For consecutive executed targets, label each interval with its initial signal
date and compute **all eight stocks' execution-to-next-execution returns**.
Pass these paired score/return frames to Vibe's Spearman IC function. It requires
at least five valid pairs and drops undefined correlations. Return the IC series
and exact label matrices so the horizon, valid-pair count, and omitted terminal
interval can be inspected. IC does not use only the two portfolio holdings.

The final execution has no subsequent execution label and is omitted from this
primary IC. The existing next-session IC remains a separately labelled factor
diagnostic. Neither IC mean/std nor a deflated IC statistic is portfolio Sharpe.

Sharpe is `sqrt(annualization) * mean(daily_net_return - daily_rf) /
std(daily_net_return - daily_rf, ddof=1)`, where
`daily_rf = (1 + annual_risk_free) ** (1 / annualization) - 1`.
Insufficient observations or zero variance returns undefined Sharpe; missing or
infinite returns fail. `^NSEI` returns align to the same evaluation sessions,
start at zero on the first evaluation date, and never enter stock ranking.
Missing/invalid benchmark prices fail a complete comparison. Adjusted-stock
returns versus a price index are not a matched total-return comparison.

## Verified exclusions and outstanding data review

Original Phase 2 raw and derived snapshot files remain immutable. Only these
evidence-backed operations are applied to copies:

- Remove July 28, 2005 across the panel: [NSE's July 27 closure
  announcement](https://nsearchives.nseindia.com/content/press/27072005.pdf).
- Mask TCS closes/volume before August 25, 2004: [NSE listing
  record](https://www.nseindia.com/static/ipo-past-issues/prior-to-2016).

Ledger entries record evidence, affected dates/counts, operation and reason.
Retain original hashes/snapshot as the source of original values. No inferred
exchange holiday, unexplained spike, or zero-volume observation is automatically
deleted. No interpolation, winsorization, or `repair=True` is used.

Preserve supplied special sessions, including February 28, 2015. A calendar is
an explicit input assumption: neither `simulate_portfolio` nor the adapter
certifies its completeness. Weekly grouping uses actual supplied rows; a special
Saturday belongs to the following Friday-ending period and can execute an order
from the preceding Friday. Dropping all weekends would be wrong.

The returned long-form stock flags cover missing closes/volume, zero volume,
repeated closes and adjusted changes over 20%, recomputed after the two verified
operations. Original manifest flags and OHLC/corporate-action evidence remain
available in the untouched snapshot. Unresolved flags do not automatically alter
trades; they prevent treating an unreviewed result as final. Later price changes
are never used to retroactively choose earlier trades. Unknown held valuations
stop a run rather than creating hindsight exclusions.

See [snapshot review](../india_research/reports/india_snapshot_quality_review.md)
for exhaustive dates, source limitations and pending archive verification.
Adjusted prices are retrieval-time vendor history; uniform later multiplicative
rescaling cancels in STREV ratios, but vendor revisions are not ruled out.

## Validation and release gate

Phase 4C reconstructed the 2021–2024 calendar with required warm-up from official
annual cash-market circulars and documented amendments/special sessions. It found
research_v2 lacks January 20, 2024 for all eight stocks and the index, despite
independent official records establishing actual trading/publication. The audit
expects 990 evaluation sessions and 21 warm-up sessions (December 3, 2020–January
1, 2021), with 176 stock/date lookback-clock mismatches caused by the omitted day.
Complete amendment coverage remains unconfirmed; historical-index API responses
were HTML and were rejected as evidence. No calendar-certified version was
created. See the [Phase 4C report](../india_research/reports/india_calendar_phase4c_review.md).
`src/india_calendar.py` keeps the data, lookback and evidence-completeness checks
explicit; vendor-calendar agreement alone cannot open the readiness gate.

The blocked Phase 4 preflight identified absent special sessions on 2023-11-12,
2024-03-02 and 2024-05-18. The original NSE evidence version preserves all 27
verified nominal closes. Phase 4B independently cross-checked 24 stock conversions
to the frozen Yahoo vintage using official action metadata, pre-cutoff dividend
steps, and bracketing official price anchors; a new research_v2 incorporates only
passing rows. Post-2024 cash adjustment normalization is defined by the frozen
pre-cutoff terminal Yahoo ratio, not independently rebuilt from holdout prices.
See the [Phase 4B review](../india_research/reports/india_adjustment_phase4b_review.md)
for the exact verification scope. These three-session checks do not certify the
full calendar or authorize portfolio evaluation: `backtest_ready=false` remains
in force pending calendar certification and user review. Prior versions and their
manifests remain unchanged.

From repository root with the project environment active:

```bash
VIBE_PYTHON=/home/jampip/indicatorlab/.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

`tests/test_india_backtest.py` uses labelled synthetic fixtures for timing,
holdings, weight drift, turnover/cost accounting, delays/cancellations, missing
prices/volumes, benchmark separation, IC horizons, real isolated Vibe IC and
STREV composition, future-data invariance, configurable parameters, verified
exclusions, and special sessions. No real snapshot strategy evaluation is part
of these tests.

The developer approved implementation and the provisional baseline, not final
strategy evaluation/publication. Before final results: obtain authorization to
evaluate, review the selected-period calendar and anomalies, freeze the exact
configuration/snapshot hashes, retain the exclusion ledger and flags, and review
outputs. Keep/Drop criteria remain undecided. Nothing in this document authorizes
commits, pushes, PRs, publication, or changing PM-established dates/factors.


### Phase 4D status

January 20, 2024 is now reconciled: 8/8 stock conversions pass the existing
Phase 4B procedure and the separate Nifty 50 close is verified. The new
research_v3 has zero full-period calendar discrepancies or 21-session clock
mismatches, but exhaustive amendment coverage remains unverified. The backtest
gate remains closed; vintage-adjustment limitations and unresolved anomaly flags
remain. See `india_research/reports/india_session_phase4d_review.md` (repository
root path) for evidence, ledger, hashes and remaining certification requirements.


### Approved provisional diagnostic execution

The user subsequently approved one academic_strev diagnostic using Phase 4D
research_v3 and the unchanged baseline above. The completed experiment is
`results/india_strev_PROVISIONAL_20261029T021955Z_21d1a038/`.
`src/india_diagnostic.py` binds the manifest and final-readiness-review hashes,
reruns structural checks, and records an exception only for exhaustive calendar
inventory certainty. It does not relabel certification flags, alter data, or
authorize repeat/other-factor/final evaluations. See
`india_research/reports/india_strev_provisional_diagnostic.md` (repository root
path) for provisional metrics, 136 passing tests and limitations.


### Four-factor integration

`src/india_factors.py` validates aligned adjusted OHLCV, isolates the four original
Vibe modules, retains original NaNs/zero-volume semantics and source hashes, and
composes the existing simulator/IC functions. A common 25 prior-session window
(November 26, 2020 onward) supports all four metadata warm-ups without changing
evaluation dates or STREV's completed run. See
`india_research/reports/india_four_factor_integration_review.md` for exact
dependencies, NaN behavior and the unverified volume-basis/price-rank limitations.
Real-data evaluations need separate authorization; STREV's pinned diagnostic
exception is not generalized. `pytest.ini` confines discovery to `tests/` so
immutable experiment source copies cannot shadow the test suite.


### Signal-only readiness findings

The four-factor signal audit ran original Vibe calculations without portfolio
simulation. Read `india_research/reports/india_four_factor_real_readiness_review.md`
before any new evaluation: #2's verified volume-unit mismatch needs a reviewed
versioned policy, #3 has no all-eight-finite signal under the fixed baseline,
and #4 has strong price-basis/tie sensitivity. The audit's volume/price
alternatives are diagnostics only; none changes the approved inputs or settings.
No final Keep/Drop or portfolio approval follows from those findings.


### Separately approved alpha101_001 diagnostic

One subsequent user-approved #1 diagnostic completed using the exact archived
STREV portfolio settings and original Vibe factor/IC. The only input-window
difference is its 25 prior-session warm-up. The scope-bound runner and audit
record retain strict calendar flags and freeze dataset/readiness/source hashes.
No alternate tie rule was used: weekly cutoff pools/rejections and actual
executed ticker choices are saved, including the undefined IC caused by one
all-name tie. See `india_research/reports/india_alpha101_001_provisional_diagnostic.md`.
No other real-data factor or repeated experiment is approved.


### Versioned volume basis for prospective alpha101_002 diagnostic

research_v4 at `results/india_alpha002_volume_reconciliation_20261029T034510Z/`
converts only twelve recovered nominal NSE quantities to their independently
verified surrounding frozen-vendor units (Reliance ×2, HDFC Bank ×2, Kotak ×5).
Cash dividends never scale volume; two exact official/vendor anchors and
documented share events are mandatory. All prices and previous versions remain
unchanged. See `india_research/reports/india_alpha101_002_volume_readiness_review.md`.
The original #2 formula, portfolio settings and intrinsic NaNs stay unchanged.
This dataset preparation does not authorize a portfolio run or transfer any
earlier dataset-bound diagnostic exception to research_v4.


### Separately approved alpha101_002 diagnostic

One subsequent user-approved #2 diagnostic completed on research_v4 with the
unchanged Vibe factor/IC and Jack-inspired baseline. The dataset/package/review
hashes, 12 corrected observations and recorded 218-test baseline were verified;
235 tests passed before execution. Missing original scores use the existing
eight-name signal rule, so one skipped weekly target yields a ten-session
execution-to-execution IC interval rather than a fabricated fixed-week label.
See `india_research/reports/india_alpha101_002_provisional_diagnostic.md`. Strict
source certification flags, original datasets and prior results are unchanged;
no repeated or other real-data factor run is authorized.


### Alpha101_003 applicability result

The unchanged #3 is non-evaluable under the assigned eight-finite-score rule:
its price-level ranks are persistently constant and all 6,847 NaNs have explicit
zero-variance causes. Do not fill scores, tune the hard-coded ten-session window
or relax eligibility to manufacture a comparable result. A broader rank universe
is a separate specification needing point-in-time membership/data and approval,
not an adopted fix. See `india_research/reports/india_alpha101_003_investigation.md`.


### Alpha101_004 readiness classification

Retain #4 as an unsuccessful applicability study for the current eight-stock
top-two setup; do not silently choose a price convention, alter rank/window
definitions or run a portfolio to mask tie-dominated membership. Full finite
coverage is insufficient here: 193/209 weekly memberships are tie-dependent and
only 16 are unique. See `india_research/reports/india_alpha101_004_readiness_decision.md`
for convention/corporate-action decomposition and the explicit option-(b)
recommendation. No general economic Keep/Drop or different-universe conclusion
is implied.


### Strategy-expansion Phase 2 integration (6–10)

Developer-approved additions are `alpha101_033`, `alpha101_101`, `alpha101_054`,
`alpha101_014` and `academic_illiq`; existing factor implementations remain intact.
`src/india_phase2_factors.py::evaluate_phase2_factor` extends only isolated module
dispatch, pins original factor/base hashes, validates dependencies and retains
original NaNs, warnings and tie diagnostics. `backtest_phase2_factor` composes the
existing accounting and original Vibe IC with exact `PortfolioConfig()` and 25
prior sessions. It has run only on labelled synthetic fixtures; it supplies no
real-data approval or calendar override. Missing scores retain the established
eight-finite-name eligibility rule and deterministic ticker tie breaking.

The `academic_illiq` India exception is developer-approved research use, not PM
approval of new settings or upstream country endorsement. Original computation
is cross-sectional z-score of the 21-session mean of absolute close return /
(close × volume). Use INR adjusted close and unchanged frozen vendor-volume units
(including the twelve verified research_v4 corrections). This denominator is a
dividend-adjusted closing-price turnover proxy, not actual NSE traded value or
USD turnover. `load_illiq_basis_evidence` binds passing input-only official-record
checks to the dataset hash and close/volume matrices; absent, changed or unsupported
basis evidence rejects evaluation. Retain the dividend factor in the denominator.
Do not silently substitute nominal quantities or undo dividends. Original safe-div
regularization and sample-standard-deviation z-score remain unchanged.

At 256 sampled observations/32 dates, adjusted close × vendor volume agrees with
nominal NSE close × nominal quantity × frozen dividend ratio (maximum relative
error 2.657e-7). This supports that bounded proxy convention, not full-history
quantity certification, point-in-time validity or Reliance demerger return
normalization. The subsequently approved signal-only audit measures real-data NaNs, ties and
eligibility for 6–10; see the readiness section below.
See `india_research/reports/india_phase2_integration_review.md`. Three historical
provisional backtests remain the only completed portfolio experiments; none is
repeated or generalized by this integration.


### Expansion signal-only readiness; no portfolio approval

The separately authorized audit uses research_v4, the same 25 prior sessions and
unchanged original five modules. `src/india_phase2_readiness.py` observes raw final
numerics before JSON serialization and enumerates every W-FRI candidate's
admissible memberships. All five produce 7,920 finite evaluation scores and 209
unique eligible candidates, of which 208 have a later evaluation session. No
returns, IC, Sharpe or executions are inferred from those counts. Causal prefix
and minimal-window checks support row alignment, not historical-vintage validity.

Under the existing basis, #033/#101/#054/#014 are recommended for separately
approved provisional diagnostics; ILLIQ remains conditional on explicit acceptance
of material adjustment/proxy sensitivity. Without dividend adjustment #014 changes
five candidate pairs and ILLIQ 51; fixed terminal normalization removal changes
ILLIQ 31. The same-day ratio factors have no measured membership changes under
tested scales, although #101 retains its original non-scale-invariant 0.001 term.
Paired share price/volume conversions mostly cancel in ILLIQ's denominator;
nominal action jumps still affect its original backward-return numerator.
Price-only or quantity-only mixed-unit diagnostics are not valid replacement bases.

All 256 sampled current INR proxy checks against reparsed official records pass;
this is not certification of all daily quantities or actual exchange turnover.
No real study zero volumes occur; a hypothetical zero yields original NaNs across
the trailing 21-ratio window and must not be filled. The existing developer India
metadata exception remains separate from upstream endorsement. Preserve baseline
conventions, strict calendar flags and previous results. See
`india_research/reports/india_phase2_signal_readiness_review.md`. Any real portfolio
evaluation needs separate user approval; none is run by this audit.


### Four approved Phase 2 provisional portfolio runs completed

One separately approved run each of #033/#101/#054/#014 now completes the
signal-readiness stage, with exactly the existing research_v4 eight-name 2021–2024
baseline and 25 prior sessions. `src/india_phase2_diagnostic.py` reuses
`backtest_phase2_factor`, pins signal/data/source evidence and records only a
scoped exhaustive-calendar-inventory exception. Material calendar, quantity,
causality and cutoff gates stay active; no global flag or assumption changes.
ILLIQ is not approved for portfolio evaluation (registry ID `academic_illiq`).

All four have 208 strictly next-session executions and 207 actual execution-to-
execution rank-IC intervals. Every saved target matches its unique audited top-two
pair; every return label matches its execution-close ratio. Daily net returns,
NAV, Sharpe and signed trade legs reconcile independently. #101 keeps its fixed
0.001 term; #014's five-of-209 dividend-convention sensitivity remains disclosed.
Original formula, volume corrections, costs and benchmark conventions are intact.
See `india_research/reports/india_phase2_provisional_backtests.md` and the associated
unique immutable result directories. No prior experiment was rerun; seven archived
strategy metrics are compared with v3/v4, STREV warm-up and old tie/missingness
caveats explicit. The full 329-test suite passes. No repeats, ILLIQ run, final
Keep/Drop or publication is authorized by these completed diagnostics.


### Separately approved ILLIQ frozen-proxy diagnostic completed

A subsequent explicit user approval covers one `academic_illiq` diagnostic under
the predeclared convention; it does not expand the consumed four-factor runner.
`src/india_illiq_diagnostic.py` binds the dataset/readiness/basis hashes, confirms
25 prior sessions and unchanged settings, and passes bound INR proxy evidence to
the existing `backtest_phase2_factor`. Original factor, IC and portfolio functions
are unchanged. Higher original z-score remains the long-selection direction.

Adjusted-INR close × vendor-unit volume is a closing-price turnover proxy, not
actual exchange turnover or USD traded value. India use is a developer-approved
metadata exception; original upstream tags remain unchanged. The 51/209 dividend
and 31/209 fixed-normalization sensitivities remain explicit. No alternative basis
was adopted or portfolio-tested. All 256 current sampled proxy checks pass, without
claiming complete historical volume or point-in-time certification. Reliance and
Kotak uncertainties and the existing calendar-inventory caveat remain disclosed.

The one diagnostic completed with 208 next-session executions/491 trade legs,
207 execution-aligned IC intervals and 990 daily net returns. Saved target, label,
NAV, cost and Sharpe identities reconcile. The 353-test suite passes; all 1,036
prior files remain unchanged. See
`india_research/reports/india_ten_strategy_provisional_comparison.md`: eight
PROVISIONAL backtests are separated from two non-evaluable applicability studies.
Earlier comparisons/results are preserved. No repeat, final Keep/Drop, different
convention or publication is authorized by the consumed ILLIQ approval.
