# PROVISIONAL Strategy Log — India strategies 11–15

Companion [report](india_strategies_11_15_PROVISIONAL_20261101T212235Z.md) and [full-precision CSV](india_strategy_log_11_15_PROVISIONAL_20261101T212235Z.csv). All five are completed single diagnostics; all final PM decisions remain pending. Earlier ten-strategy logs/reports remain unchanged.

## Notation, units and conventions

O/H/L/C/V mean aligned adjusted-INR OHLC and research_v4 vendor-unit volume. `S(a,b)=a/(b+1e-12*sign(b))`, with original nonfinite-to-NaN behavior. `[-1]` is the immediately preceding **session**; mean/std/min/max/sum/corr are trailing per-stock windows, min_periods equal to the stated window. Std uses sample ddof=1; corr is Pearson within the time window, while reported IC is cross-sectional Spearman. Positive change is `diff.where(diff>0,0)`; its missing-input behavior is determined by the original complete denominator window. No cross-sectional rank or z-score is added to the original signals.

CSV `*_return_decimal` fields are decimal compounded returns (0.10 = 10%); `_pp` is a percentage-point difference (10 = 10 pp). IC and Sharpe are unitless. Turnover sums are absolute traded NAV units; cost-fraction sums are sums of 0.001×turnover over changing NAV bases, not a direct final-return deduction. `stock_trade_legs` counts nonzero stock changes; executions count portfolio rebalances including drift-only trades. Every run has 990 evaluation sessions, 25 prior sessions, eight-stock eligibility, 208 executions and 207 defined IC labels.

Execution/cost rules are final W-FRI session signals, strictly subsequent eligible-close execution, long-only equal 50% top-two targets, drift between rebalances and unchanged 10-bps absolute-turnover costs. Original descending scores and ticker tie-break are retained; no observed weekly tie needs that rule. IC labels start at the actual execution close, ending at next execution close, never after 2024-12-31. Net Sharpe uses sample daily std ×sqrt252 with zero risk-free; initial cash is included and there is no terminal liquidation.

| # | Registry ID | Mean rank IC | Net Sharpe | Net cumulative return | Minus Nifty 50 (pp) | Cost-fraction sum | Trade legs |
|---|---|---:|---:|---:|---:|---:|---:|
| 11 | `qlib158_std20` | 0.008742 | 0.501045 | 38.2745% | -29.0287 | 0.166326 | 580 |
| 12 | `qlib158_rsv20` | -0.055441 | -0.236678 | -23.6375% | -90.9408 | 0.216736 | 631 |
| 13 | `qlib158_sump20` | -0.061997 | -0.033481 | -9.9512% | -77.2544 | 0.151167 | 565 |
| 14 | `qlib158_wvma20` | -0.008857 | 0.596890 | 45.4276% | -21.8756 | 0.144001 | 557 |
| 15 | `qlib158_cord10` | -0.088912 | -0.052153 | -11.5646% | -78.8678 | 0.234068 | 648 |


## 11. `qlib158_std20`

**Signal:** Twenty-session sample standard deviation of closing price divided by current close; higher scores favor greater relative price-level variability. Formula: `S(std_20(C,ddof=1),C)`.

**Dependencies:** formula/declared fields close; the common India adapter requires full aligned OHLCV and separate benchmark. Declared metadata warm-up 20; effective input length 20; 25 prior sessions supplied. Original theme `['momentum']` and all metadata/direction are preserved; every original registry entry explicitly includes `equity_in` (no metadata exception).

**Status/rationale:** Complete continuous signals and small positive IC support interpretable diagnostics; net performance trails the benchmark and does not establish alpha. No final Keep/Drop recommendation is assigned; **PM decision pending**.

**Quality:** 7,920 finite evaluation scores; 209 eligible/unique pairs; no exact daily or weekly boundary ties, no near-boundary ties at 1e-10; no evaluation NaNs/infinities. Known frozen-vintage, Reliance/Kotak, calendar and benchmark limitations in the main report apply. Volume-unit caveats additionally apply to WVMA/CORD; no alternative real-data basis was scored.

**Saved evidence:** [metrics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/metrics.json), [scores](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/factor_scores.csv), [readiness](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/signal_readiness.json), [weekly selections](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/weekly_candidates.json), [original metadata/numerics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/original_metadata_and_numerics.json), [configuration](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/configuration.json), [provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/provenance.json), [execution log](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/order_log.json), [trades](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/trades.csv), [returns/costs](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/daily_returns_nav.csv), [IC](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/execution_aligned_ic.csv), [warnings](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/warnings.json), [inventory](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/artifact_hashes.json).

Inventory SHA-256: `182990ddc5baae423d15f25ac1b739663062437ea3664f66b7ea76afa8958da5`. Score-cache SHA-256: `997d9a86c4b39d8023244f5fcc87e2a74803a6184d87e52a47f1ba35e69d7ece`.

- Original Vibe `src/factors/zoo/qlib158/std20.py`: `8abed102785febbc178930c99a954f207fe1fa066147d6328b41e842f9862724`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/source_snapshot/src/factors/zoo/qlib158/std20.py).
- Original Vibe `src/factors/base.py`: `5b4bd3ae72d8fcd19f0734c7949a40804fdc16b7a8f939c80255d824f0f27291`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/source_snapshot/src/factors/base.py).
- Original Vibe `src/factors/factor_analysis_core.py`: `7d39b4220b477f3a5de9051b8c19e56dd1ae55fd11c1d276fc5ea4c099a2a940`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_std20/source_snapshot/src/factors/factor_analysis_core.py).

## 12. `qlib158_rsv20`

**Signal:** Current close position within the trailing twenty-session high/low range; higher scores favor closes near the upper range. Formula: `S(C-min_20(L),max_20(H)-min_20(L))`.

**Dependencies:** formula/declared fields high, low, close; the common India adapter requires full aligned OHLCV and separate benchmark. Declared metadata warm-up 20; effective input length 20; 25 prior sessions supplied. Original theme `['momentum']` and all metadata/direction are preserved; every original registry entry explicitly includes `equity_in` (no metadata exception).

**Status/rationale:** Complete unique signals permit evaluation; negative IC and net return describe this original high-RSV direction without justifying inversion. No final Keep/Drop recommendation is assigned; **PM decision pending**.

**Quality:** 7,920 finite evaluation scores; 209 eligible/unique pairs; no exact daily or weekly boundary ties, no near-boundary ties at 1e-10; no evaluation NaNs/infinities. Known frozen-vintage, Reliance/Kotak, calendar and benchmark limitations in the main report apply. Volume-unit caveats additionally apply to WVMA/CORD; no alternative real-data basis was scored.

**Saved evidence:** [metrics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/metrics.json), [scores](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/factor_scores.csv), [readiness](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/signal_readiness.json), [weekly selections](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/weekly_candidates.json), [original metadata/numerics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/original_metadata_and_numerics.json), [configuration](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/configuration.json), [provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/provenance.json), [execution log](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/order_log.json), [trades](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/trades.csv), [returns/costs](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/daily_returns_nav.csv), [IC](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/execution_aligned_ic.csv), [warnings](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/warnings.json), [inventory](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/artifact_hashes.json).

Inventory SHA-256: `4177cffcfcc007ccdb835aec407d9c88b42d687057cfe285a83ee9fe0df8dc23`. Score-cache SHA-256: `7ecf636682702ed216f040a27848c22d04637a050996c1fa608f6896911e386f`.

- Original Vibe `src/factors/zoo/qlib158/rsv20.py`: `904103606d9251c095a2af3474b83ef638411816e5f4f6d381927708c8d96c8b`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/source_snapshot/src/factors/zoo/qlib158/rsv20.py).
- Original Vibe `src/factors/base.py`: `5b4bd3ae72d8fcd19f0734c7949a40804fdc16b7a8f939c80255d824f0f27291`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/source_snapshot/src/factors/base.py).
- Original Vibe `src/factors/factor_analysis_core.py`: `7d39b4220b477f3a5de9051b8c19e56dd1ae55fd11c1d276fc5ea4c099a2a940`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_rsv20/source_snapshot/src/factors/factor_analysis_core.py).

## 13. `qlib158_sump20`

**Signal:** Trailing twenty-session positive close-change magnitude divided by total absolute close changes; higher scores favor stronger upward price movement. Formula: `S(sum_20(positive(C-C[-1])),sum_20(abs(C-C[-1])))`.

**Dependencies:** formula/declared fields close; the common India adapter requires full aligned OHLCV and separate benchmark. Declared metadata warm-up 20; effective input length 21; 25 prior sessions supplied. Original theme `['reversal']` and all metadata/direction are preserved; every original registry entry explicitly includes `equity_in` (no metadata exception).

**Status/rationale:** Complete unique signals permit evaluation; negative IC and net return are retained without changing the upstream reversal tag or score direction. No final Keep/Drop recommendation is assigned; **PM decision pending**.

**Quality:** 7,920 finite evaluation scores; 209 eligible/unique pairs; no exact daily or weekly boundary ties, no near-boundary ties at 1e-10; no evaluation NaNs/infinities. Known frozen-vintage, Reliance/Kotak, calendar and benchmark limitations in the main report apply. Volume-unit caveats additionally apply to WVMA/CORD; no alternative real-data basis was scored.

**Saved evidence:** [metrics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/metrics.json), [scores](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/factor_scores.csv), [readiness](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/signal_readiness.json), [weekly selections](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/weekly_candidates.json), [original metadata/numerics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/original_metadata_and_numerics.json), [configuration](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/configuration.json), [provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/provenance.json), [execution log](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/order_log.json), [trades](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/trades.csv), [returns/costs](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/daily_returns_nav.csv), [IC](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/execution_aligned_ic.csv), [warnings](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/warnings.json), [inventory](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/artifact_hashes.json).

Inventory SHA-256: `38bbb2e55b0cdcaeeaf47a08134212cd2229cf0015875e10b0e6bddf44bfbf58`. Score-cache SHA-256: `4d1b61f9888334ad4efb2e9f2f71a6ca99a24c3a52db59cdfe1d0ab40dda75ed`.

- Original Vibe `src/factors/zoo/qlib158/sump20.py`: `346cfbcd3cfef020cd577326af042e158656e65e0498babd93dee88157af5dcc`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/source_snapshot/src/factors/zoo/qlib158/sump20.py).
- Original Vibe `src/factors/base.py`: `5b4bd3ae72d8fcd19f0734c7949a40804fdc16b7a8f939c80255d824f0f27291`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/source_snapshot/src/factors/base.py).
- Original Vibe `src/factors/factor_analysis_core.py`: `7d39b4220b477f3a5de9051b8c19e56dd1ae55fd11c1d276fc5ea4c099a2a940`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_sump20/source_snapshot/src/factors/factor_analysis_core.py).

## 14. `qlib158_wvma20`

**Signal:** Trailing twenty-session coefficient of variation of absolute close returns multiplied by vendor volume; higher scores favor more variable return-volume products. Formula: `S(std_20(abs(S(C,C[-1])-1)*V,ddof=1),mean_20(abs(S(C,C[-1])-1)*V))`.

**Dependencies:** formula/declared fields close, volume; the common India adapter requires full aligned OHLCV and separate benchmark. Declared metadata warm-up 20; effective input length 21; 25 prior sessions supplied. Original theme `['volume', 'volatility']` and all metadata/direction are preserved; every original registry entry explicitly includes `equity_in` (no metadata exception).

**Status/rationale:** Complete unique signals and positive net return permit interpretation, but slightly negative IC and volume-vintage uncertainty limit any predictive claim. No final Keep/Drop recommendation is assigned; **PM decision pending**.

**Quality:** 7,920 finite evaluation scores; 209 eligible/unique pairs; no exact daily or weekly boundary ties, no near-boundary ties at 1e-10; no evaluation NaNs/infinities. Known frozen-vintage, Reliance/Kotak, calendar and benchmark limitations in the main report apply. Volume-unit caveats additionally apply to WVMA/CORD; no alternative real-data basis was scored.

**Saved evidence:** [metrics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/metrics.json), [scores](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/factor_scores.csv), [readiness](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/signal_readiness.json), [weekly selections](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/weekly_candidates.json), [original metadata/numerics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/original_metadata_and_numerics.json), [configuration](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/configuration.json), [provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/provenance.json), [execution log](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/order_log.json), [trades](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/trades.csv), [returns/costs](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/daily_returns_nav.csv), [IC](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/execution_aligned_ic.csv), [warnings](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/warnings.json), [inventory](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/artifact_hashes.json).

Inventory SHA-256: `9d9b499c1d0c67a00c1c12f47db832e95e68798c92ef4388050ab2311ecb04d1`. Score-cache SHA-256: `b6d18779d0ffebc488c1bfb001a5246e7e376b0a08ae5660b55a01390fb22f0b`.

- Original Vibe `src/factors/zoo/qlib158/wvma20.py`: `6a593c8d752eefe97d86cf1e66ac8cfe7e7838e0903decd1079bcc60e716ed94`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/source_snapshot/src/factors/zoo/qlib158/wvma20.py).
- Original Vibe `src/factors/base.py`: `5b4bd3ae72d8fcd19f0734c7949a40804fdc16b7a8f939c80255d824f0f27291`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/source_snapshot/src/factors/base.py).
- Original Vibe `src/factors/factor_analysis_core.py`: `7d39b4220b477f3a5de9051b8c19e56dd1ae55fd11c1d276fc5ea4c099a2a940`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_wvma20/source_snapshot/src/factors/factor_analysis_core.py).

## 15. `qlib158_cord10`

**Signal:** Trailing ten-session correlation of gross close ratios with log consecutive volume ratios using the original volume +1 constant; higher scores favor stronger positive price-volume association. Formula: `corr_10(S(C,C[-1]),log(S(V+1,V[-1]+1)))`.

**Dependencies:** formula/declared fields close, volume; the common India adapter requires full aligned OHLCV and separate benchmark. Declared metadata warm-up 10; effective input length 11; 25 prior sessions supplied. Original theme `['volume', 'microstructure']` and all metadata/direction are preserved; every original registry entry explicitly includes `equity_in` (no metadata exception).

**Status/rationale:** Complete unique signals permit evaluation; negative IC and net return accompany volume-unit and frozen-vintage limitations, with the +1 constant retained. No final Keep/Drop recommendation is assigned; **PM decision pending**.

**Quality:** 7,920 finite evaluation scores; 209 eligible/unique pairs; no exact daily or weekly boundary ties, no near-boundary ties at 1e-10; no evaluation NaNs/infinities. Known frozen-vintage, Reliance/Kotak, calendar and benchmark limitations in the main report apply. Volume-unit caveats additionally apply to WVMA/CORD; no alternative real-data basis was scored.

**Saved evidence:** [metrics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/metrics.json), [scores](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/factor_scores.csv), [readiness](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/signal_readiness.json), [weekly selections](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/weekly_candidates.json), [original metadata/numerics](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/original_metadata_and_numerics.json), [configuration](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/configuration.json), [provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/provenance.json), [execution log](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/order_log.json), [trades](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/trades.csv), [returns/costs](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/daily_returns_nav.csv), [IC](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/execution_aligned_ic.csv), [warnings](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/warnings.json), [inventory](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/artifact_hashes.json).

Inventory SHA-256: `86e68db213c9f622cfff679346d15edded2ae695eab78bcad7a54a22e8fc5cd0`. Score-cache SHA-256: `5704e102ebd3cf0923c4ab933890a1e2fc967e34ca5b4818fb341db07cc780f5`.

- Original Vibe `src/factors/zoo/qlib158/cord10.py`: `e8b0efc6705f8c4c35ec58d520a9798360c1bee7a99509e88b8cba486d8d3803`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/source_snapshot/src/factors/zoo/qlib158/cord10.py).
- Original Vibe `src/factors/base.py`: `5b4bd3ae72d8fcd19f0734c7949a40804fdc16b7a8f939c80255d824f0f27291`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/source_snapshot/src/factors/base.py).
- Original Vibe `src/factors/factor_analysis_core.py`: `7d39b4220b477f3a5de9051b8c19e56dd1ae55fd11c1d276fc5ea4c099a2a940`; [frozen source](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/qlib158_cord10/source_snapshot/src/factors/factor_analysis_core.py).

## Shared provenance and remaining evidence limits

Dataset: `results/india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/research_manifest.json`; manifest SHA-256 `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`. The [copied manifest](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/dataset_manifest.json) records each of nine history hashes; it is unchanged original evidence and can contain local historical paths. [Shared provenance](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/provenance.json) records Vibe HEAD `7f6908b7e1b95d971f4151bfaf2382e2ce9485cf`, IndicatorLab HEAD, package versions, cached benchmark hash and data files. Individual source snapshots/hashes are stronger than HEAD alone because new integration files are uncommitted. [Shared local source snapshots](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/source_snapshot/indicatorlab/india_qlib_factors.py) and the batch runner record exact execution code. [Volume/calendar verification](../../results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/shared_preflight.json) reuses existing evidence without rebuilding v4.

The new result directories are local ignored experiment outputs, not a newly prepared portable Git submission. Full research data remain external to the previously frozen submission package; that package and all earlier evidence are preserved. Publication/submission requires separate review and approval. These five results do not resolve the original assignment's outstanding PM/code-review/submission requirements.
