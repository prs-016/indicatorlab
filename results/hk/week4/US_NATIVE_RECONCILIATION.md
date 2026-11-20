# US native verification: fixed-fill accounting reconciliation

Accounting-only replay of already executed fixed fill streams; no signal computation, order generation, parameter change, portfolio resizing or new strategy test. Counterfactual cash is not reinvested.

Both windows: 1212sessions, 2022-01-03 through 2026-10-30, 252annualization. First entry 2022-01-18 in both. Reconstructed cash+shares agrees with saved research/native equity within $0.000000002.

Research: 191roundtrips/382legs. Native: 246actualfills/117completed records. Native holds through repeated same-direction weekly targets; one position can remain much longer than the research weekly close/reopen schedule.

| Fixed executed quantities | Sharpe | Final equity USD | Step Sharpe change | Step equity change USD |
| --- | ---: | ---: | ---: | ---: |
| A_research_actual | 0.513963 | 1045594.00 | +0.000000 | +0.00 |
| B_study_fills_without_dividends | 0.497868 | 1044115.33 | -0.016096 | -1478.68 |
| C_study_fills_without_dividends_or_slippage | 0.804428 | 1071977.68 | +0.306560 | +27862.35 |
| D_native_fills_without_slippage | 0.802659 | 1072409.17 | -0.001769 | +431.49 |
| E_native_actual | 0.703567 | 1063303.81 | -0.099092 | -9105.35 |

Research slippage $27862.35, native $9105.35; explicit commissions are zero in both. Research dividends $1478.68. Crediting dividends on the unchanged native fills would add $1489.50 and yield Sharpe 0.719500; this is an accounting diagnostic, not a re-evaluated strategy.

Neither an extra signal shift nor a different evaluation window explains the gap. Weekly forced roundtrips in research incur much more gross turnover/slippage than native target-retention/resizing. Separate cash dividends improve research slightly; native does not credit them. The bridge isolates exact executed cash accounting and leaves the remaining gross-PnL difference to the observed distinct quantity paths, rather than claiming identical portfolios.

The raw native run succeeds, but its Sharpe is not a matching confirmation of the research portfolio (difference exceeds0.1). The candidate remains DROP/ineligible; no cost or strategy parameter was adjusted to force agreement.
