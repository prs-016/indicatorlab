> Portable submission copy packaged 2026-11-01; source-document preparation date retained below. All decisions remain preliminary.

# India Strategy Log — PM review version

**Prepared UTC:** 2026-10-29T06:10:17.071042+00:00
**Status:** Eight completed PROVISIONAL backtests and two non-evaluable applicability studies. All final PM decisions remain pending. Preliminary labels are research priorities only.

[PM report](report.md) · [full-precision CSV](strategy_log.csv) · [bundle verification](bundle_manifest.json)

## Shared notation, methodology and CSV data dictionary

- **Notation:** O/H/L/C/V = declared open/high/low/close/volume; r = one-session simple close return; R = original cross-sectional average percentile rank; Z = original cross-sectional z-score with sample standard deviation; S = original Vibe safe division with signed epsilon/nonfinite handling. `delta_n`, `corr_n`, `mean_n`, `argmax_n` and `ts_rank_n` denote original trailing operators. Formula descriptions preserve arithmetic NaN semantics; they are not replacement implementations.
- **Inputs:** `formula_inputs` lists fields actually used by the formula; `framework_required_fields` records original registry declarations. All portfolio evaluations also require close prices, volume for eligibility and separate benchmark data. In particular #003 uses O/V but declares O/V/C; #004 uses L but declares L/C.
- **Study:** eight assigned `.NS` equities; separate `^NSEI`; 990 evaluation sessions January 4, 2021–December 31, 2024. STREV uses v3 with 21 prior sessions; #001 v3 with 25; other completed factors v4 with 25. Warm-up is excluded from portfolio metrics. No post-cutoff observations, labels or executions; October 1, 2025 onward holdout remains restricted.
- **Portfolio:** last session of W-FRI period, eight finite scores, descending score/ascending ticker, top-two 50/50 long-only targets, drift and fractional weights. Strictly subsequent eligible-close execution requires positive volume on changed holdings. Initial cash earns zero; no final forced liquidation.
- **Costs:** 10 bps per unit absolute traded NAV, including entry/drift adjustments. Net daily return `(1+gross)*(1-cost_fraction)-1`. Cost-fraction sums use changing NAV bases; they are not cash totals or direct percentage-point deductions from terminal return. No spread/impact/tax/capacity model.
- **Metrics:** mean original Vibe execution-aligned Spearman IC across eight names; last unfinished label excluded, undefined correlations not filled. Daily net Sharpe = mean/sample standard deviation × √252, zero risk-free. IC, Sharpe and cumulative return are different measures. Benchmark begins at the first evaluation close with its first return zero.
- **CSV units:** all columns ending in `cumulative_return` are decimal fractions: `0.755389` means approximately `75.5389%`. `return_minus_benchmark_percentage_points` is already in percentage points; do not multiply it by 100. IC, Sharpe and Sharpe differences are unitless. `N/A` means no portfolio metric, not zero. Counts are integers; timestamps are ISO UTC. Formula lookbacks and preparation/prior-session counts are distinct.
- **Labels:** Keep = further-research shortlist; Drop = baseline-specific deprioritization; Investigate = unresolved evidence. `recommendation_basis` separates non-evaluability from observed performance. No PM-approved numerical threshold or final decision is implied.
- **Shared limits:** frozen vendor adjustments are not point-in-time; Reliance normalization and Kotak quantity uncertainty remain; calendar inventory is not exhaustively certified; fixed eight-name basket and overlapping samples limit inference; dividend-adjusted equities are compared with a price index; there is no untouched out-of-sample or multiple-testing validation. Twelve repeated closes are retained, not repaired.

## Detailed entries

### 1. `academic_strev`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Keep. **Final PM decision:** pending review.

**Signal:** `Z(-S(C-C.shift(21), C.shift(21)))` — Standardize the negative trailing 21-session close return across stocks; higher values favor recent losers.

**Formula inputs:** close. **Registry/framework-required fields:** close. **Lookback:** close; 21-session lag, 22 observed closes; metadata warm-up 21.

**Saved metrics:** mean rank IC 0.073383943 (207 valid intervals); net daily Sharpe 0.843175221; net cumulative return 75.538927%; gross 107.628643%.
**Benchmark comparison:** Net return +8.2357 percentage points vs Nifty 50; net Sharpe -0.135785 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 581 stock legs; research_v3, 21 prior sessions.

**Signal quality:** No missing/zero-volume or >20% adjusted-close-change flags in the study slice; 12 repeated closes retained. 208 executions and 207 defined IC intervals. No target skipped except the terminal candidate.

**Factor-specific limitations:** Frozen adjusted-return numerator and Reliance normalization; fixed basket/benchmark mismatch and provisional calendar exception. Original v3/21-prior-session run preserved, not migrated or rerun.

**Preliminary rationale:** Retain on the research shortlist: positive IC 0.073384 and net return above benchmark, with net Sharpe below benchmark. Independent validation is still needed.

**Saved report:** [india_strev_provisional_diagnostic.md](supporting/india_strev_provisional_diagnostic.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/academic/strev.py`.
**Portfolio:** [metrics](evidence/runs/academic_strev/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `0826a352f3d84179fcbf36906d6928c4c65e1987d13a7cf98837d0f22b519949` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/runs/academic_strev/factor_scores.csv) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `0826a352f3d84179fcbf36906d6928c4c65e1987d13a7cf98837d0f22b519949`; only selected review evidence is included.

### 2. `alpha101_001`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Investigate. **Final PM decision:** pending review.

**Signal:** `R(argmax_5(signed_power(x,2)))-0.5; x=std_20(r)*1(r<0)+C*(1-1(r<0))` — Rank the five-session location of the maximum squared conditional close/return-volatility series. Preserve the original arithmetic conditional and its NaN propagation.

**Formula inputs:** close. **Registry/framework-required fields:** close. **Lookback:** close; metadata warm-up 25 bars; 20-return volatility then five-row argmax.

**Saved metrics:** mean rank IC -0.023758766 (206 valid intervals); net daily Sharpe 0.076889467; net cumulative return -1.593235%; gross 30.682774%.
**Benchmark comparison:** Net return -68.8965 percentage points vs Nifty 50; net Sharpe -0.902071 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 698 stock legs; research_v3, 25 prior sessions.

**Signal quality:** 7,920 finite scores but daily ties on all 990 dates; 163/209 weekly cutoff ties; 162/208 executed targets depend on ticker tie breaking. March 31, 2023 all-name tie produces one undefined IC, omitted rather than set to zero.

**Factor-specific limitations:** Material ticker-rule exposure prevents attributing returns uniquely to the factor. Counterfactual tie-rule portfolio performance is unmeasured. Arithmetic conditional/argmax semantics and original v3 inputs retained.

**Preliminary rationale:** Resolve interpretability of the 162/208 tie-dependent targets before allocating more performance-testing effort; negative IC and weak net return do not isolate factor versus ticker exposure.

**Saved report:** [india_alpha101_001_provisional_diagnostic.md](supporting/india_alpha101_001_provisional_diagnostic.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_001.py`.
**Portfolio:** [metrics](evidence/runs/alpha101_001/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `c0ab1dc2b82a26db658bacf755362664f420aea9bb8a486cb553aab8bc72f7ea` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/runs/alpha101_001/factor_scores.csv) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `c0ab1dc2b82a26db658bacf755362664f420aea9bb8a486cb553aab8bc72f7ea`; only selected review evidence is included.

### 3. `alpha101_002`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Investigate. **Final PM decision:** pending review.

**Signal:** `-corr_6(R(delta_2(log V)), R((C-O)/O))` — Negative trailing correlation between ranked two-session log-volume changes and ranked intraday returns.

**Formula inputs:** open, close, volume. **Registry/framework-required fields:** open, close, volume. **Lookback:** open, close, volume; metadata warm-up 10 bars; original six-session correlation.

**Saved metrics:** mean rank IC 0.018146093 (206 valid intervals); net daily Sharpe 0.498502458; net cumulative return 38.071211%; gross 82.218034%.
**Benchmark comparison:** Net return -29.2320 percentage points vs Nifty 50; net Sharpe -0.480458 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 207 executions / 689 stock legs; research_v4, 25 prior sessions.

**Signal quality:** 7,916/7,920 finite; four constant-ranked-window NaNs: HDFC Bank Aug 9–11, 2021 and Reliance Mar 25, 2022. 208/209 weekly candidates eligible, no cutoff ties. The March 25 target is skipped; one execution-aligned interval spans ten sessions.

**Factor-specific limitations:** Volume convention matters; twelve recovered quantities are corrected in v4 using 24 anchors, but full-history nominal-volume certification, Reliance normalization and small Kotak quantity discrepancy remain unresolved. Missing signals lengthen actual IC horizons.

**Preliminary rationale:** Positive but small IC and net Sharpe below benchmark; scrutinize volume-vintage limitations, skipped-label horizon and substantial cost drag before further validation.

**Saved report:** [india_alpha101_002_provisional_diagnostic.md](supporting/india_alpha101_002_provisional_diagnostic.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_002.py`.
**Portfolio:** [metrics](evidence/runs/alpha101_002/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `9ee48ec90e003c601ada8876446b567ce8a765126ab5b5670323e09bc3ffe16d` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/runs/alpha101_002/factor_scores.csv) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `9ee48ec90e003c601ada8876446b567ce8a765126ab5b5670323e09bc3ffe16d`; only selected review evidence is included.

### 4. `alpha101_003`

**Status:** Non-evaluable under current eight-stock baseline. **Preliminary:** Drop — non-evaluable in this baseline. **Final PM decision:** pending review.

**Signal:** `-corr_10(R(O), R(V))` — Negative ten-session correlation of cross-sectional open-price and volume ranks; persistent rank order makes rolling correlations undefined.

**Formula inputs:** open, volume. **Registry/framework-required fields:** open, volume, close. **Lookback:** Formula: open, volume. Registry/framework: open, volume, close. Metadata warm-up: 10 bars..

**Portfolio metrics / benchmark-relative performance / executions:** N/A — no portfolio evaluation. The shared benchmark is context only.

**Signal quality:** 1,073/7,920 finite; 6,847 NaNs: 5,588 constant-open-rank only, 1,224 both ranks constant, 35 volume-rank only. No all-eight-eligible weekly candidate. TCS has the highest adjusted open throughout input; tested bases do not restore eligibility.

**Factor-specific limitations:** Small, price-separated basket contributes verified constant-rank windows; this is not evidence that the implementation is broken. Broader-universe validity would need independently justified point-in-time membership and separate approval.

**Preliminary rationale:** Remove from the current eight-name evaluation queue because there are no eligible weekly signals; retain the unsuccessful applicability record. This is not a universal economic rejection.

**Saved report:** [india_alpha101_003_investigation.md](supporting/india_alpha101_003_investigation.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_003.py`.
**Portfolio inventory:** N/A. The separate signal-evidence inventory below is available and verified.
**Signal evidence:** [included evidence](evidence/signals/alpha101_003/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `54a0fe0d8d3a102c439f968636596642d6373be2eafa4755d692755fde1ee264`; only selected review evidence is included.

### 5. `alpha101_004`

**Status:** Non-evaluable under current eight-stock baseline. **Preliminary:** Drop — non-evaluable in this baseline. **Final PM decision:** pending review.

**Signal:** `-ts_rank_9(R(L))` — Negative nine-session time rank of each stock’s cross-sectional low-price rank; constant ranked inputs create tied outputs.

**Formula inputs:** low. **Registry/framework-required fields:** low, close. **Lookback:** Formula: low. Registry/framework: low, close. Metadata warm-up: 9 bars..

**Portfolio metrics / benchmark-relative performance / executions:** N/A — no portfolio evaluation. The shared benchmark is context only.

**Signal quality:** 7,920 finite scores but 193/209 weekly memberships depend on ticker ties; 120 all-eight ties; only 16 unique pairs. Yahoo Close versus adjusted-low conventions change 99/209 selected pairs, with 10 disjoint and 89 overlapping admissible-pair sets.

**Factor-specific limitations:** Tie-dominated ranking and adjustment-sensitive level ranks do not support meaningful top-two evaluation here. Finite scores do not imply unique economic choices. Do not manufacture a portfolio by changing tie/price rules.

**Preliminary rationale:** Remove from the current top-two evaluation queue because only 16/209 pairs are uniquely identified; preserve the failed applicability study rather than force returns.

**Saved report:** [india_alpha101_004_readiness_decision.md](supporting/india_alpha101_004_readiness_decision.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_004.py`.
**Portfolio inventory:** N/A. The separate signal-evidence inventory below is available and verified.
**Signal evidence:** [included evidence](evidence/signals/alpha101_004/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `92560d944922a271fc987d549c5862713e3c65ddf4f92227f6f9f82adab801e3`; only selected review evidence is included.

### 6. `alpha101_033`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Keep. **Final PM decision:** pending review.

**Signal:** `R(-(1-S(O,C)))` — Rank open/close minus one: higher scores favor intraday relative losers; this is not an overnight gap signal.

**Formula inputs:** open, close. **Registry/framework-required fields:** open, close. **Lookback:** open, close; 1 bar.

**Saved metrics:** mean rank IC 0.059466299 (207 valid intervals); net daily Sharpe 0.823290332; net cumulative return 78.480471%; gross 143.663687%.
**Benchmark comparison:** Net return +11.1772 percentage points vs Nifty 50; net Sharpe -0.155670 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 725 stock legs; research_v4, 25 prior sessions.

**Signal quality:** 7,920/7,920 finite evaluation scores; 209 eligible, unique weekly pairs (208 nonterminal), no daily or weekly exact ties or weekly near-boundary ties at 1e-10. Tested adjustment scales change zero weekly memberships.

**Factor-specific limitations:** Common OHLC scaling mostly cancels in its ratio, but rounded/identical candles can tie elsewhere. Same-day close is needed; subsequent-close execution mandatory. Potential overlap with #054 is unmeasured.

**Preliminary rationale:** Retain for independently designed validation: positive IC 0.059466, complete unique signals and net return above benchmark; lower benchmark-relative Sharpe and high turnover temper the result.

**Saved report:** [india_phase2_provisional_backtests.md](supporting/india_phase2_provisional_backtests.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_033.py`.
**Portfolio:** [metrics](evidence/runs/alpha101_033/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `f5c58de1daafe0c244d3922873673d46e46e94c26c2bbbcb8ee16ab9c92657e9` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/signals/phase2/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`; only selected review evidence is included.

### 7. `alpha101_101`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Drop — observed baseline performance. **Final PM decision:** pending review.

**Signal:** `S(C-O,H-L+0.001)` — Bullish candle body divided by daily range plus the original 0.001 price-unit constant. Its mathematical sign favors intraday strength, regardless of its registry theme.

**Formula inputs:** open, high, low, close. **Registry/framework-required fields:** open, high, low, close. **Lookback:** open, high, low, close; 1 bar.

**Saved metrics:** mean rank IC -0.037382103 (207 valid intervals); net daily Sharpe -0.151835272; net cumulative return -17.915565%; gross 11.982786%.
**Benchmark comparison:** Net return -85.2188 percentage points vs Nifty 50; net Sharpe -1.130796 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 725 stock legs; research_v4, 25 prior sessions.

**Signal quality:** 7,920/7,920 finite; all 209 weekly pairs eligible and unique. Tested price scales change score magnitudes but no daily ranks/weekly memberships. No denominator problem in this sample; a valid flat candle would score zero.

**Factor-specific limitations:** Original 0.001 term is not perfectly scale invariant; no sign reversal or removal of the constant is justified by negative results. High turnover and modeled cost drag accompany the observed weak baseline.

**Preliminary rationale:** Deprioritize this exact baseline: negative IC, negative net Sharpe and -17.9156% net return despite +11.9828% gross return. Preserve evidence; do not invert or retune the formula.

**Saved report:** [india_phase2_provisional_backtests.md](supporting/india_phase2_provisional_backtests.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_101.py`.
**Portfolio:** [metrics](evidence/runs/alpha101_101/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `de28242a855ce02fe4d8579387bf557196d831164cc6a5f1d47f6ba8d538cac8` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/signals/phase2/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`; only selected review evidence is included.

### 8. `alpha101_054`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Keep. **Final PM decision:** pending review.

**Signal:** `-S((L-C)*O^5,(L-H)*C^5)` — Favors a close near the daily low, modulated by the fifth power of open/close; original denominator and powers are retained.

**Formula inputs:** open, high, low, close. **Registry/framework-required fields:** open, high, low, close. **Lookback:** open, high, low, close; 1 bar.

**Saved metrics:** mean rank IC 0.056245687 (207 valid intervals); net daily Sharpe 0.776599249; net cumulative return 69.651870%; gross 131.353003%.
**Benchmark comparison:** Net return +2.3486 percentage points vs Nifty 50; net Sharpe -0.202361 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 724 stock legs; research_v4, 25 prior sessions.

**Signal quality:** 7,920/7,920 finite; all 209 weekly pairs eligible and unique. Tested adjustment scales change zero weekly memberships. No zero/invalid denominator observed; an original flat-range denominator would remain NaN.

**Factor-specific limitations:** High powers and flat ranges can fail numerically on other data; no such sample failure is observed. Intraday candle information is only known after close. Potential overlap with #033 is unmeasured.

**Preliminary rationale:** Retain for independent validation: positive IC 0.056246, complete unique signals and slightly above-benchmark net cumulative return; lower Sharpe, costs and possible overlap require review.

**Saved report:** [india_phase2_provisional_backtests.md](supporting/india_phase2_provisional_backtests.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_054.py`.
**Portfolio:** [metrics](evidence/runs/alpha101_054/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `409567f3669aaaf5b5033ad073ccaf5b6016b53e18730cbc7253e709bf34ed43` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/signals/phase2/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`; only selected review evidence is included.

### 9. `alpha101_014`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Investigate. **Final PM decision:** pending review.

**Signal:** `-R(delta_3(r))*corr_10(O,V)` — Negative rank of the three-step change in one-session returns multiplied by the ten-session correlation of unranked open and volume.

**Formula inputs:** open, close, volume. **Registry/framework-required fields:** open, close, volume. **Lookback:** open, close, volume; metadata warm-up 10 bars.

**Saved metrics:** mean rank IC 0.048654244 (207 valid intervals); net daily Sharpe 0.382497000; net cumulative return 24.337464%; gross 66.883696%.
**Benchmark comparison:** Net return -42.9658 percentage points vs Nifty 50; net Sharpe -0.596463 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 708 stock legs; research_v4, 25 prior sessions.

**Signal quality:** 7,920/7,920 finite; all 209 weekly pairs eligible and unique; no constant raw ten-session window. 72 original warm-up NaNs occur before evaluation. Removing dividend adjustment changes 5/209 weekly pairs; reverting corrected volumes diagnostically changes two.

**Factor-specific limitations:** Five-of-209 dividend-convention sensitivity and volume units remain explicit; no convention chosen from trading returns. Constant/incomplete raw windows could create NaNs elsewhere. High turnover limits net performance.

**Preliminary rationale:** Positive IC does not translate into competitive net return/Sharpe here; investigate high turnover and five-of-209 dividend-sensitive memberships without selecting a new basis from returns.

**Saved report:** [india_phase2_provisional_backtests.md](supporting/india_phase2_provisional_backtests.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_014.py`.
**Portfolio:** [metrics](evidence/runs/alpha101_014/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `bbd3c31fb27c1de354c20a640f2e9868b9155ab18c70f90444d30d1ad08a433a` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/signals/phase2/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`; only selected review evidence is included.

### 10. `academic_illiq`

**Status:** Completed PROVISIONAL backtest. **Preliminary:** Investigate. **Final PM decision:** pending review.

**Signal:** `Z(mean_21(S(abs(S(C-C.shift(1),C.shift(1))),C*V)))` — Cross-sectional z-score of the 21-complete-observation mean of absolute adjusted-close return per adjusted-INR closing-price times vendor-volume proxy. Higher scores favor less-liquid names.

**Formula inputs:** close, volume. **Registry/framework-required fields:** close, volume. **Lookback:** close, volume; 22 bars for 21 daily ratios; 25 prior sessions supplied.

**Saved metrics:** mean rank IC -0.003105590 (207 valid intervals); net daily Sharpe 0.748968037; net cumulative return 70.490427%; gross 84.376576%.
**Benchmark comparison:** Net return +3.1872 percentage points vs Nifty 50; net Sharpe -0.229992 vs benchmark. Price-index/dividend mismatch retained.
**Activity/version:** 208 executions / 491 stock legs; research_v4, 25 prior sessions.

**Signal quality:** 7,920/7,920 finite; 209 unique eligible candidates, 208 executions; 168 warm-up NaNs only. No study-input zero volumes; original hypothetical zero invalidates a 21-ratio window. 51/209 dividend-sensitive and 31/209 fixed-normalization-sensitive pairs; 256 sampled current proxy checks pass. Kotak appears in 127/209 candidate pairs.

**Factor-specific limitations:** C*V is a dividend-adjusted INR closing-turnover proxy, not actual exchange turnover or USD turnover. Developer-approved India metadata exception, not upstream endorsement or PM approval. 51/209 dividend and 31/209 normalization sensitivity, frozen vintage, concentrated exposures, incomplete daily volume certification and Reliance/Kotak issues remain material.

**Preliminary rationale:** Net return slightly above benchmark with lower Sharpe and near-zero negative IC; material proxy/vintage sensitivity and concentrated exposure prevent a clean predictive-alpha interpretation.

**Saved report:** [india_ten_strategy_provisional_comparison.md](supporting/india_ten_strategy_provisional_comparison.md). Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/academic/illiq.py`.
**Portfolio:** [metrics](evidence/runs/academic_illiq/metrics.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `109bbb5c790b9bec944f7be8d1e7a10b36f3e8f472373909592afa1dd5d9da1c` is an identity reference, not the checksum manifest for this subset.
**Signal evidence:** [included evidence](evidence/signals/phase2/baseline_summary.json) · [bundle checksums](bundle_manifest.json). Original full-archive inventory SHA-256 `353115a4ba028970601869f4e9f61b9222d364505d07aa5838929dc431918e2b`; only selected review evidence is included.

## Provenance and supporting evidence

| Data layer | Manifest / inventory | SHA-256 / use |
|---|---|---|
| Original Yahoo snapshot | [manifest](evidence/datasets/yahoo_snapshot_manifest.json) | Raw provider files and derived adjusted OHLCV retained unchanged. |
| research_v3 | [manifest](evidence/datasets/research_v3_manifest.json) | `a99d6671002b8c15dc406d7b532556ee95cb96cb5503dd9e8555253d17e3ca42`; STREV/#001. |
| research_v4 | [manifest](evidence/datasets/research_v4_manifest.json) | `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`; #002 and five additions. |

The original Yahoo snapshot, official NSE special-session equity/index evidence, nominal-to-frozen-adjusted ledgers, January 20 recovery and calendar audits are preserved. V4 changes only twelve volume observations: Reliance ×2, HDFC ×2 and Kotak ×5, verified with share events and two exact quantity anchors each; all prices and other tokens are unchanged. No older portfolio was rerun or migrated. Vibe HEAD is `7f6908b7e1b95d971f4151bfaf2382e2ce9485cf`; each run’s source/helper/IC hashes and source snapshots fix the actual code version.

Supporting reports: [data quality](supporting/india_data_quality_report.md), [snapshot review](supporting/india_snapshot_quality_review.md), [adjustments](supporting/india_adjustment_phase4b_review.md), [January 20 recovery](supporting/india_session_phase4d_review.md), [calendar readiness](supporting/india_strev_final_readiness_review.md), [volume reconciliation](supporting/india_alpha101_002_volume_readiness_review.md), [five-factor signal readiness](supporting/india_phase2_signal_readiness_review.md), [seven-strategy results](supporting/india_phase2_provisional_backtests.md), and [ten-strategy results / ILLIQ](supporting/india_ten_strategy_provisional_comparison.md). Full original draft detail remains available in the unchanged earlier report (`india_ten_strategy_research_report_DRAFT_20261029T054748Z.md`, historical/archival record not included; see archive index) and unchanged earlier Strategy Log (`india_strategy_log_DRAFT_20261029T054748Z.md`, historical/archival record not included; see archive index).

**ILLIQ disclosure:** adjusted-INR close × vendor volume is a dividend-adjusted closing-turnover proxy, not actual exchange turnover, USD turnover or complete nominal-history reconstruction. India use despite missing `equity_in` is a developer-approved metadata exception; upstream metadata is unchanged and no upstream endorsement or explicit PM factor approval is claimed. The 51/209 dividend-sensitive and 31/209 fixed-normalization-sensitive selections were measured in earlier signal-only diagnostics; the portfolio used only the declared convention. The 256 sampled products across 32 source-hashed official dates passed at recorded float32 tolerance (maximum relative discrepancy 2.656182248594874e-7), without certifying every daily quantity or resolving Reliance adjusted-return normalization. No alternative was selected using portfolio returns.

**Authority and gates:** Vibe’s framework replacement is PM-approved. The combined portfolio settings are developer-approved; each diagnostic had separate user permission. Material calendar/clock checks passed, but exhaustive inventory certainty alone was waived within pinned diagnostic scopes. Strict manifest flags remain false; no global validation disablement or new experiment authorization follows from this review.

**Verification:** all eight portfolio inventories plus the three dedicated signal-audit inventories were checked; metrics are transcribed, not regenerated. No packages, factors, backtests or tests were run. The latest prior suite is [353 passed](evidence/recorded_test_suite.txt). The [bundle verification](bundle_manifest.json) documents file hashes, CSV checks and preservation. Stop for PM/user review; final decisions and any next work remain unapproved.
