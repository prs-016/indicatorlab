# HK native verification: fixed-fill reconciliation

**Outcome:** The saved native Sharpe (−0.048155) and research Sharpe (−0.461350) do not meet the ≤0.1 agreement rule. Their difference is now quantified: native target rebalancing retains existing holdings, while the research protocol closes/reopens weekly. The retained portfolio incurs much less turnover and friction. This reconciliation does not convert the train-ineligible research nominee into KEEP.

This is read-only accounting verification of the frozen `defensive_attention_gate` candidate. No signal generation, tuning, sizing change, data acquisition, strategy execution or native CLI rerun was performed. Accounting counterfactuals hold every executed share quantity and date fixed; they are not alternative investable strategy results.

| Frozen artifact | Research | Native |
|---|---:|---:|
| Daily observations, 2022-01-03–2026-10-30 | 1185 | 1185 |
| Annualized daily net Sharpe | -0.461350 | -0.048155 |
| Final HKD equity | 7,501,021.23 | 7,762,711.41 |
| Executed fill legs | 478 | 205 |
| Traded HKD notional | 153,868,987.62 | 39,098,530.01 |
| Fees, including stamp duty | 198,971.33 | 47,954.35 |
| Slippage cash vs identical raw opens | 153,869.02 | 39,098.58 |
| Separate dividend cash | 16,658.24 | 0.00 |

Research has 239 completed round trips. Native has 52 opens, 58 increases, 43 reductions and 52 full closes; its reported 95 trades are realized exit records (43 partial reductions plus 52 closes), not 95 independent weekly entries.

On January 3, 2022 both buy 1,000 Tencent shares. On January 10 research sells all 1,000 and buys 1,100, while native keeps the 1,000 and buys only 100. Both are out after January 17. The same pattern accounts for substantially lower native traded notional.

**Timing/data checks:** Both cover exactly the same 1,185 sessions. Held-symbol/day masks match everywhere; all actual execution prices equal that day’s frozen raw open plus/minus 10bps. There is no observed double-shift or displaced invested-day error. Quantities differ on 379 symbol-days / 318 sessions because retained target sizing and forced reopen sizing have different cash, fee and board-lot paths. Hash-verified native input CSVs match research opens/closes to CSV floating-point precision.

**Accounting identity:** Reconstructing cash plus shares at each close reproduces native equity within HKD1.9e−9 and research within HKD3.6e−8. Research fee and dividend totals match exactly. The native terminal equity advantage of HKD261,690.18 decomposes as:

- HKD151,016.98 less fees.
- HKD114,770.45 less slippage.
- HKD12,560.99 difference in gross price/quantity paths before fees, slippage and dividends.
- Minus HKD16,658.24 of dividend credits absent from native.

The four amounts sum to the equity difference. They are an exact fixed-fill cash decomposition; Sharpe effects are nonlinear. The ordered fixed-fill bridge below makes the Sharpe attribution auditable without rerunning a strategy:

| Accounting path | Sharpe | Increment |
|---|---:|---:|
| A research frozen fills, dated rounded fees and dividends | -0.461350 | — |
| B same research fills, remove dividend credits | -0.487103 | -0.025754 |
| C same research fills, remove all fees | -0.174491 | +0.312612 |
| D same research fills, remove fees and slippage | 0.066942 | +0.241434 |
| E native frozen fills, remove fees and slippage | 0.085006 | +0.018064 |
| F same native fills, retain slippage but remove fees | 0.025211 | -0.059796 |
| G native actual frozen fills and fees | -0.048155 | -0.073366 |

The increments telescope to the observed ≈+0.413194 native-minus-research Sharpe gap. This ordering is an accounting convention, not a unique causal attribution. The unfrictioned fixed-fill paths are close (+0.066942 research versus +0.085006 native), whereas the weekly research round trips pay much more friction.

**Duty/dividend conventions alone do not close the gap.** Applying native’s constant fractional 0.1% duty to the frozen research fills saves HKD10,251.01 and changes research Sharpe only to −0.445576. Applying research’s dated/whole-HKD duty to frozen native fills adds HKD3,377.47 and changes native Sharpe to −0.053308. Adding the missing dividend credits to native yields −0.022704; applying both conventions yields −0.027867, still far from −0.461350. These are fixed-quantity accounting counterfactuals; the prepared B3 duty correction was not installed in the sealed native run.

**Benchmark limit:** Native metrics explicitly use an equal-weight basket of the five supplied stocks, despite configuration naming `^HSI`. Its benchmark statistics must not be presented as the research Hang Seng Index baseline.

Both original outputs and their failed ≤0.1 numerical-agreement flag remain unchanged. The candidate was selected from train only and already marked ineligible/DROP. A future truly identical-contract validation would need to freeze the same liquidation/re-entry, fees, dividends, lots and benchmark semantics before execution; no such repeat was performed here. The existing current-lot and source-adjustment limitations remain.

Full source hashes, input checks and exact numeric decomposition are in `NATIVE_HK_RECONCILIATION.json`; the deterministic arithmetic script is `reconcile_hk_fixed_fills.py`.
