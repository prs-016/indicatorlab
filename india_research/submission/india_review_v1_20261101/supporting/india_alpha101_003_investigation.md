> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# Alpha101_003: undefined-signal investigation

**Recommendation: retain this as a documented unsuccessful/non-evaluable experiment under the assigned eight-stock baseline. Do not manufacture scores or run a cash-only portfolio as evidence of factor performance.** A separately approved, predeclared broader rank universe is a defensible future research hypothesis, not a demonstrated rescue or replacement of the current experiment.

No portfolio backtest, returns, IC, Sharpe, configuration search on performance, source-data repair or real-universe change was executed. Original Vibe factor definitions and all prior strategy results remain unchanged.

## Original definition and exact calculation

Inspected `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_003.py::compute`, `src/factors/base.py::rank` and `src/factors/base.py::ts_corr`.

The unchanged expression is:

```text
- correlation(rank(open), rank(volume), 10)
```

It first ranks all stocks **across the same date** (average percentile ranks, NaNs kept). Then it computes **a separate rolling ten-session Pearson correlation for each stock**, between that stock's two rank series. The window includes today and the previous nine sessions; all ten pairs are required. It is not today's cross-sectional open/volume correlation, and it is not a rolling rank of raw prices. The factor declares open, volume and close; only open and volume enter compute. Close supports framework/accounting. Metadata warm-up is ten bars; `decay_horizon=5` is metadata, not permission to change the hard-coded ten-session correlation.

For each stock/window, the correlation denominator contains the product of ranked-open and ranked-volume standard deviations. Either zero variance makes the correlation undefined. The original helper preserves NaNs and converts any correlation infinities to NaN. No epsilon, zero correlation, jitter or substitute price-return factor is justified by that definition.

The [original paper](https://arxiv.org/pdf/1601.00991), Appendix A, gives the same #3 expression; its operator definitions specify cross-sectional ranking and time-series correlation. This verifies the two-stage interpretation, not a particular India universe, adjustment convention or portfolio design.

## Data and reproducibility

Primary input: verified research_v4 at `archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/`. Its manifest hash remains `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`. It has the same prices as research_v3 and twelve volume-unit corrections. The original Vibe #3 was recalculated through the isolated bridge and its scores equal the earlier research_v3 audit numerically: **1,073 finite and 6,847 undefined out of 7,920 evaluation cells**.

Input includes 25 prior sessions from November 26, 2020 through January 1, 2021, followed by 990 evaluation sessions January 4, 2021–December 31, 2024. No missing source open/volume cells, zero volumes, insufficient evaluation warm-up or post-cutoff dates explain these NaNs. The nine leading-window warm-up rows are outside the evaluation count.

New evidence directory: `archive:india_alpha003_investigation_20261029T041207Z/`. It contains every stock/date's original score status, actual rank values, rank ranges, pair counts and unranked open range, per-stock cause totals, all constant-rank runs, original scores, diagnostic convention scores, sampled official nominal checks, protected hashes and source versions. No transformed research dataset was written.

## Precisely why 6,847 evaluation scores are undefined

| Mutually exclusive cause | Undefined cells |
|---|---:|
| Only open rank constant in the ten-session window | **5,588** |
| Both open and volume ranks constant | **1,224** |
| Only volume rank constant | **35** |
| Missing pairs, insufficient warm-up or unexplained numerical failure | **0** |
| Total | **6,847** |

Thus **6,812** undefined cells have constant open ranks; in every one, the **unranked adjusted open varies inside the window**. The input-price changes are real observations, but cross-sectional ranking discards their magnitude when no stock changes relative position. In the artifact, `raw_open_range_10` means the unranked input open—not an assertion that those values are nominal, unadjusted NSE opens. No finite output has a zero-variance ranked input; no undefined evaluation output remains unattributed.

| Stock | Finite | Open rank only constant | Both ranks constant | Volume rank only constant | Undefined total |
|---|---:|---:|---:|---:|---:|
| AXISBANK.NS | 314 | 665 | 11 | 0 | 676 |
| HDFCBANK.NS | 239 | 631 | 95 | 25 | 751 |
| ICICIBANK.NS | 247 | 743 | 0 | 0 | 743 |
| INFY.NS | 76 | 673 | 240 | 1 | 914 |
| KOTAKBANK.NS | 21 | 969 | 0 | 0 | 969 |
| RELIANCE.NS | 96 | 894 | 0 | 0 | 894 |
| SBIN.NS | 80 | 862 | 39 | 9 | 910 |
| TCS.NS | 0 | 151 | 839 | 0 | 990 |

TCS has percentile open rank **1.0 in every one of the 1,015 input sessions**. Its open changes, but remains above the other seven adjusted opens. Each evaluation window therefore has zero ranked-open variance. Its 990 missing cells comprise 151 open-only and 839 both-rank-constant windows. This one stock alone makes the baseline's all-eight-finite requirement impossible throughout the period.

Other long constant-price-rank runs reinforce the problem: Kotak has 807 consecutive sessions at rank 0.125 (September 30, 2021–December 31, 2024); INFY and Reliance each have 608-session runs beginning November 26, 2020; HDFC Bank has a 394-session run. All run boundaries and ranks are saved; these are observed run statistics, not periods selected for performance.

On 544 evaluation days every score is undefined. Finite-name counts across the 990 dates are 0:544, 1:12, 2:323, 3:41, 4:61, 5:6, 6:3. The maximum is six, so even reducing the minimum from eight to seven would not create eligible signals. Across 209 weekly dates, counts are 0:121, 1:3, 2:60, 3:9, 4:13, 5:2, 6:1. No portfolio was run for any alternative eligibility threshold.

## Does the eight-stock universe contribute?

**Yes, through sparse and persistent cross-sectional price ordering.** With eight valid names and no tie, rank moves on an eighth-of-universe grid. A stock's own price/volume can change every day while its ordinal position remains unchanged. Widely separated share-price levels make crossovers uncommon; this small basket leaves TCS permanently at the top and other names in long-lived slots. The failure concerns rank dynamics, not a lack of underlying price observations.

The diagnosis is not that eight observations are mathematically insufficient: the correlation uses ten dates per stock, not eight stocks as its sample size. Nor is broadening automatically sufficient. Synthetic regressions call the **unchanged original Vibe module** on the same eight invented price paths, first alone, then with eight predetermined crossing-price neighbors. The original eight remain all NaN in the small cross-section but become finite after warm-up with crossing neighbors. Adding eight distant-price neighbors instead leaves them all NaN. The fixtures are explicitly synthetic, use no real future prices/returns, and demonstrate a mechanism only. They are not replacement market data, a real expanded-universe experiment or evidence that a particular Nifty universe will work.

Changes to rank denominator from missing stocks or membership churn can also create rank variation without economically meaningful price crossovers. More finite scores alone would not establish useful signal quality.

## Adjusted versus nominal opens and volume conventions

All variants below invoke the unchanged original #3 compute; volumes/prices are copied in memory. No baseline data or portfolio settings are changed. The approved frozen input is not historically point-in-time.

### Full-period, non-nominal price bases

| Diagnostic basis, 2021–2024 | Finite scores / 7,920 | All-eight-finite days / weekly dates |
|---|---:|---:|
| Approved adjusted prices, corrected frozen-vendor volumes | **1,073** | **0 / 0** |
| Yahoo Close price basis (cash-dividend adjustment removed) | **1,161** | **0 / 0** |
| Yahoo Close price basis in December 31, 2024 share units | **914** | **0 / 0** |

Yahoo Close is **not nominal or purely split-only history**: it retains vendor split and other corporate-action transformations. The third diagnostic additionally undoes the known post-2024 HDFC/Kotak share scaling, while retaining pre-cutoff adjustments. These differences show that stock-specific adjustment scales affect cross-sectional level ranks and the locations of missing scores; neither basis restores baseline eligibility. No convention is recommended because its finite count is larger.

### Restricted nominal-open/nominal-volume proxy check

A full 2021–2024 independently verified nominal reconstruction is **not available** from the current evidence, because the exact additional Reliance vendor scaling before its July 20, 2023 demerger remains unexplained. No ratio is invented to reverse it.

For the known post-demerger portion, remove the saved cash-dividend OHLC ratio and multiply prices by the documented later share multipliers, using their dates. Nominal-volume proxies divide corrected frozen-vendor quantities by those multipliers. This is a diagnostic reconstruction from saved data/metadata, not a new nominal dataset or a claim of historical point-in-time vintage. It also retains the known small vendor quantity discrepancy.

The derived opens were compared with **208 primary NSE instrument/date records on 26 sampled dates**: every open agrees within the established eight-float32-epsilon tolerance; maximum relative error is **4.76e-8**. Nominal-volume proxies match those nominal quantities except for Kotak March 1, 2024, which is lower by one nominal share (the previously documented five-vendor-share difference). This sampled validation is not verification of every daily nominal record. No nominal price/quantity was fabricated, rounded to force a match or inserted into a production dataset.

July 20, 2023 onward supplies the first ten valid sessions; the fair comparison is **August 2, 2023–December 31, 2024: 351 evaluation sessions, 2,808 cells**.

| Diagnostic inputs on those same dates | Finite / 2,808 | All-eight-finite days |
|---|---:|---:|
| Approved adjusted open, frozen-vendor volume | **406** | **0** |
| Nominal-open proxy, frozen-vendor volume | **361** | **0** |
| Adjusted open, nominal-volume proxy | **427** | **0** |
| Nominal-open and nominal-volume proxies | **371** | **0** |

These are measured input sensitivities, not claims that the conventions are mathematically equivalent. Nominal prices can change ranks abruptly at actual splits/bonuses; that is a separate input-convention effect, not a license to choose whichever retrospectively maximizes validity.

**The twelve corrected volume observations do not solve #3:** research_v4 scores equal the earlier research_v3 scores. In the inspected windows, the previously mixed-volume unit problem was not the cause of this factor's undefined scores. Volume ranking still causes 35 price-nonconstant failures and contributes to 1,224 both-constant windows. The broader normalization limitations remain disclosed.

## Legitimate future configurations and look-ahead safeguards

There is no documented production switch that makes a zero-variance correlation defined while preserving the formula. Do not fill NaNs with zero, add jitter, rank returns instead of open levels, replace this with Alpha #6, or alter the fixed ten-session window. Additional warm-up cannot create variation in a permanently constant rank. A common positive price scale applied to every stock on a date leaves ranks unchanged; it cannot fix this problem. Original sample-versus-population variance choices likewise cannot make a constant series nonconstant.

Lowering the eight-name signal threshold changes the approved portfolio eligibility, not the factor's signal validity. It may let a sparse and selection-dependent subset trade, but leaves the mathematical degeneracy intact and would no longer be a comparable baseline. This investigation does not recommend or implement it. Changing the correlation window is a factor-definition change, not merely a harmless configuration adjustment.

A **separately approved broader cross-sectional rank universe** is independently defensible. The factor is defined over cross-sectional ranks rather than a mandated eight-stock sample. The paper discusses broad liquid-stock portfolios as context; that is not evidence that its original #3 universe was Nifty 100 or any fixed size. [NSE Indices defines Nifty 100](https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-100) as a diversified broad-market index combining Nifty 50 and Nifty Next 50, making it a reasonable externally defined India research candidate. The repo's original Nifty 100 loader/research objective provides additional project context.

A defensible future proposal would predeclare **one** universe/input policy before any return evaluation, for example as-of-date Nifty 100 membership, and preserve the exact original rank/correlation formula. It would require:

1. Independently reconstruct membership announcements/effective dates known at each signal date, including removals, ticker/ISIN changes and delistings. Do not backfill today's constituents into 2021.
2. Obtain causal OHLCV and at least ten prior sessions for original formula windows, define warm-up/new-entry and missing-observation rules without padding stocks into dates before they were eligible, and validate volume/price corporate-action conventions. Avoid retroactive future share-unit adjustments if claiming point-in-time validity.
3. Decide explicitly whether the broader universe determines ranks only while the eight assigned stocks remain tradable, or whether the trading universe changes too. Both are new research specifications requiring approval; neither is the current assignment unchanged.
4. First audit raw coverage, rank stability and valid correlations with no P&L-based configuration selection. Broader ranks may help, but persistent extremes or data gaps may still prevent full eligibility. Do not add names chosen because they crossed these eight stocks retrospectively.

`docs/india_project_context.md` confirms the existing 100-name CSV is a snapshot, not historical membership, and that completeness of a 2021–2024 reconstruction has not been established. Therefore the required broader real-data experiment cannot currently be justified or executed from that file alone. No new universe or price data was downloaded during this task.

## Decision and validation

Keep the assigned experiment recorded as **non-evaluable under the unchanged eight-stock/eight-finite-score baseline**, with the exact 1,073/7,920 coverage and zero eligible weekly dates. This is an unsuccessful signal-applicability result, not a negative Sharpe, a fabricated zero-return strategy, or a final economic Keep/Drop judgment about the formula in all universes.

Recommend requesting approval only if the team wants a **separate, predeclared point-in-time broader-universe signal-validity study**. The current evidence supports its rationale, not its success; do not adopt nominal prices, another universe or a relaxed minimum simply because one diagnostic has more finite cells.

New `src/india_alpha003_audit.py` supplies the exact per-window cause/run audit and a labelled diagnostic-only boundary to the unchanged original worker. Production eight-stock integration, approved portfolio settings and existing runners/factor files are unchanged. `tests/test_india_alpha003_audit.py` adds **six offline synthetic regressions** for mutually exclusive causes, changing prices with fixed ranks, missing pairs, alignment, controlled small/broad/distant universes, common-scale rank invariance and cutoff/basis enforcement. Complete suite: **241 passed in 21.41 seconds**, zero failures/skips:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

Original dataset and every prior strategy/evidence artifact were hash-verified unchanged before and after. Saved scores and all convention diagnostics retain original NaNs; no return/performance calculations or portfolio simulations were run. Code/source/runtime provenance, scripts, exact cause tables, nominal checks, tests and decision are saved with artifact hashes. No package installation, commit, push or publication. Stop for user review.
