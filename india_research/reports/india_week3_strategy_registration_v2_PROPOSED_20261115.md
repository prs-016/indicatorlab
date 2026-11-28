# Week 3 India strategies — proposed v2 registration package

**Status: PROPOSED / UNRUN / NOT REGISTERED.** Owner: Jamaal. No PM approval, performance result or KEEP/DROP decision is recorded. This is a separate proposed revision, not an update to the team sheet. No backtest, scoring, threshold optimization or acquisition occurred.

Originals: [v1 specification](india_week3_strategy_registration_PROPOSED_20261115T005026Z_source.txt) and [v1 registration draft](india_week3_strategy_registration_PROPOSED_20261115T005026Z.md), preserved unchanged. The original is SHA-256 `d9d54e8dd25a33a8ee1ac397617711855ddfb4d90c97a80c5f4eec229a8d3edd`.

The now-available [Week 3 pages 21–23 extract](india_week3_strategy_registration_v2_PROPOSED_20261115_guide_extract.txt) supersedes the old draft's statement that the guide could not be found. Sentiment context also uses guide pages 5–6. Companion [team rows](india_week3_strategy_registration_v2_PROPOSED_20261115_team_rows.csv) and [detailed registration rows](india_week3_strategy_registration_v2_PROPOSED_20261115_detailed.csv) are for review only. None of the earlier 15 factor studies supplies performance for these new strategies.

## Requirement check

| Proposed strategy | Indicators (more than four each) | Sources | Three layers | Attention risk filter / entry interpretation | Markets |
|---|---|---|---|---|---|
| AGM_v2 | 126–21 momentum; SMA50; benchmark SMA200; RV20; ATR20; Reddit and Wikipedia spike breadth | OHLCV, Reddit, Wikipedia | Benchmark regime; price selection; attention exposure gate and stops/time exits | Attention only scales total portfolio risk, never selection. Price-only entry is retained; Prakhar must confirm the intended risk-filter exception to the general attention+sentiment entry wording. | US + India separately |
| SCB_v2 | HH55 breakout; relative volume; ATR20; benchmark trend/RV20; two attention ratios/z; sentiment level/change | OHLCV, Reddit, Wikipedia, shared validated scorer on Reddit text | Benchmark regime; attention/sentiment/price-volume entry; low-price/sentiment/stop/time exits | Attention and sentiment select stocks | US + India separately |
| AER_v2 | Prior attention extremes/decay; sentiment level/change; five-session return; SMA20 distance; RSI14; ATR20; price recovery; benchmark regime | OHLCV, Reddit, Wikipedia, shared validated scorer on Reddit text | Benchmark regime; negative-shock/recovery entry; SMA/sentiment/stop/time exits | Attention and sentiment select stocks | US + India separately |

All three meet the indicator/source counts and three-layer structure on paper. Full compliance is **conditional on the approval decisions below**, especially AGM entry interpretation and scorer/cost/null definitions. Available configuration is not proof of complete 2016–2025 company-level data.

## Exact changes from v1

| Change | Scope and reason |
|---|---|
| IDs | AGM_v1 → AGM_v2; SCB_v1 → SCB_v2; AER_v1 → AER_v2. New trial IDs retain the originals. |
| Sentiment | SCB/AER replace VADER fractions with shared validated FinBERT mean probability net. All numeric gates, lookbacks, score directions and coefficients remain fixed; their new score-scale meaning requires approval. AGM remains sentiment-free. |
| India costs | Flat 25-bps proxy replaced by reuse of the pinned IndiaEquityEngine fee stack and separately disclosed default slippage. US stock 10-bps convention is unchanged. No duplicate cost engine proposed. |
| Random control | Attempt-count/dynamic-exit null replaced by a filled-count and held-duration matched conditional timing null, so the guide's same-trade/holding requirement is explicit. Dynamic stops are not replayed in this statistical null. |
| Acceptance | Add guide's index-relative test Sharpe and ≥90% random-run requirements. IC/ablation/DSR remain mandatory reports, not invented pass thresholds or measured results. |
| Operational semantics | Add the pending deterministic timing/missingness definitions below; they close omissions rather than silently changing v1 during implementation. |
| No opportunistic retuning | Momentum, entry/exit thresholds, attention baseline, ranking coefficients, train/test dates, basket, max positions and risk budgets are unchanged. Guide permits train-only loosening if too sparse; this package does not authorize it. Any such change is another version/trial before test. |

## Shared registration fields

| Field | Fixed specification for all three |
|---|---|
| Owner/status | Jamaal; **v2 PROPOSED—UNRUN—awaiting Prakhar approval**. New local strategy IDs, not Vibe registry entries. |
| Markets | Evaluate US and India separately, in USD and INR respectively. No combined cross-currency portfolio. |
| India universe | RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, ICICIBANK.NS, SBIN.NS, KOTAKBANK.NS, AXISBANK.NS. Benchmark: `^NSEI`. |
| US universe | Configured AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AMD, NFLX, JPM. Benchmark: SPY. These fixed, retrospectively selected baskets carry survivorship/selection limitations. |
| Train | **2016-06-01–2021-12-31**. |
| Test | **2022-01-01–2025-09-30**. |
| Warm-up | Request separately bounded history from **2015-07-01**; require every indicator’s complete warm-up before eligibility. Warm-up returns do not enter metrics. |
| Holdout | Never request or open price, attention or sentiment observations dated **2025-10-01 onward**. Use research-only files and date-bounded requests. |
| Weekly clock | Attention weeks are Monday–Sunday UTC. Decision snapshot: **Tuesday 00:00 UTC** following the completed week. Price indicators use only exchange sessions closed before that snapshot. |
| Publication safeguard | A feature must have been published by the decision snapshot. A 24-hour weekly processing allowance is a proposed assumption, **not proof of historical availability**. Missing release-time evidence prevents a point-in-time claim. |
| Execution | First eligible local close after the decision snapshot and after the price bar used for the signal. Entry orders expire after two local sessions. Daily protective exits execute at the next eligible close—not at the triggering close. |
| Portfolio | Long-only; maximum two positions; no leverage or shorting. Exact ranking ties resolve by ascending ticker. Unallocated capital earns zero. |
| Initial sizing | Let `a = ATR20 / signal close`, `d = max(0.02, 2a)`. Reject entries if `d > 0.10`. Initial target weight is `min(0.50, 0.01/d)`, before any portfolio-wide exposure multiplier. This budgets approximately 1% NAV to the initial stop distance; gaps can exceed that loss. |
| Protective stop | Initial stop = execution price × `(1−d)`. Subsequently raise—but never lower—it to the maximum of its previous level and `highest completed close since entry − 2 × entry ATR20`. Adjust consistently for corporate actions. |
| Rebalancing | Weekly entries/target review; daily protective-exit checks. Existing positions in strategies 2–3 remain until an explicit exit, rather than being replaced merely because their entry conditions disappear. |
| Missing data | Missing collection is not zero attention. No missing-price forward-fill, invented sentiment, interpolated sessions or silent anomaly removal. An unexplained missing held-position close blocks a complete performance claim. |
| Split boundaries | Start each split in cash; retain prior history for indicators only. Schedule liquidation at each split’s final eligible close, including costs. No new entries with fewer than five sessions remaining. |

**Proposed guide-aligned transaction costs:** US single stocks retain **10 bps per unit of absolute traded NAV per side**. If a liquid ETF is actually traded, use the guide's 3 bps (reference index returns are not assumed to be trades). No shorts, so the guide's 50 bps/year borrow charge is not applicable.

India replaces the flat 25-bps proxy with the existing Vibe `agent/backtest/engines/india_equity.py::IndiaEquityEngine` commission hooks, including STT, exchange/SEBI fees, GST, buy-only stamp duty and configured sell DP charge. Do not reimplement its tax formula or add the old flat charge on top. Proposed frozen source defaults: brokerage=0, STT=0.001, exchange=0.0000297, SEBI=0.000001, stamp=0.00015, GST=0.18, DP=0. Default engine slippage=0.001 is retained separately as adverse execution slippage, not another turnover commission. Pin the engine file hash/config before running. These are inspected code defaults, not independently verified historical statutory schedules; Prakhar must approve the frozen research convention or request dated parameters before registration. Use actual commission cash flows in NAV accounting and avoid double-counting slippage or fees. US accounting retains `(1+gross)*(1-cost_fraction)-1`; India must account consistently for the engine's cash charges/fills rather than treating a fixed cash fee as a constant percentage.

### Shared indicator definitions

- `C/H/L/V`: consistently adjusted close/high/low and declared comparable volume.
- `SMA_n`: mean of the latest `n` completed local sessions.
- `ATR20`: simple mean of 20 true ranges; true range uses the previous close.
- `RV20`: sample standard deviation of 20 daily simple returns × `√252`.
- `R_w`: Reddit post-count ratio; `W_w`: Wikipedia pageview ratio.
- For either attention count `x`:

  `ratio_w = (x_w + 1) / (median(x_[w−8:w−1]) + 1)`

  Use the configured past-only robust z-score: at least **26 previous valid abnormal values**, MAD scale **1.4826**. A standard spike requires **ratio ≥1.5 and robust z ≥2**. Undefined baselines or zero MAD remain unavailable.
- `S_w = mean(p_positive − p_negative)`, using deduplicated, ticker-matched English `reddit_stock` posts from the shared **validated FinBERT scorer**, or a different validated production winner explicitly approved by Prakhar. Require complete collection and **at least 20 scored posts** that week. Freeze model/tokenizer/preprocessing/text-version hashes; retain per-post probabilities and validate India sentiment on training-period labels. This replaces VADER-labelled post fractions; unchanged numeric sentiment thresholds below are newly proposed on the probability-net scale, not an equivalence claim. Scorer substitution requires another registered version.
- `ΔS_w = S_w − S_[w−1]`.

## 1. Attention-Gated Momentum — `AGM_v2`

**Hypothesis:** price momentum may remain useful while widespread unusual attention signals a need to reduce portfolio exposure. **Attention changes portfolio risk only; it does not choose stocks.**

| Registration field | Fixed rule |
|---|---|
| Sources/indicators | Market OHLCV: 126-to-21-session momentum, SMA50, benchmark SMA200, benchmark RV20, ATR20. Reddit and Wikipedia: market-wide spike breadth. |
| Price score | `M = C_[t−21] / C_[t−126] − 1`. This omits the latest month. |
| Market regime | Benchmark close above SMA200 and benchmark RV20 ≤35%. Otherwise target cash. |
| Stock eligibility | `M > 0` and stock close above SMA50. Select the two highest **price-only** momentum scores. |
| Attention filter | For each source, calculate the fraction of covered universe names exhibiting a standard spike. Require complete attention inputs for at least 80% of the fixed universe: 8/10 US names or 7/8 Indian names. |
| Exposure rule | If either Reddit or Wikipedia spike breadth is ≥40%, multiply **both selected positions’ weights by 0.5**. Otherwise multiplier =1. Missing market-level attention coverage means no new target can be certified. |
| Entry/rebalance | Review every weekly snapshot; enter eligible selected names using shared sizing and subsequent-close execution. |
| Exit | First of: no longer in the weekly top two; momentum ≤0; close below SMA50; benchmark regime fails; protective stop; **63 held sessions**. |
| Risk-filter attribution | Record ungated price targets separately from gated targets. The filter must never reorder stocks or favor individually quiet names. |
| IC score | Raw `M`. A common exposure multiplier does not improve cross-sectional ranks; evaluate the attention filter principally through its ablation and portfolio-risk effects. |


## 2. Sentiment-Confirmed Breakout — `SCB_v2`

**Hypothesis:** a breakout supported by participation, attention and improving sentiment is more credible than a price breakout alone.

| Registration field | Fixed rule |
|---|---|
| Sources/indicators | Market OHLCV: prior 55-session high, relative volume, ATR20 and benchmark trend/volatility. Reddit: attention ratio, robust z, sentiment level/change. Wikipedia: attention ratio and robust z. |
| Breakout | `C_t > max(H_[t−55:t−1])`; the current bar is excluded from the comparison range. |
| Volume confirmation | `VR = V_t / median(V_[t−20:t−1]) ≥1.5`. Require positive, comparable volumes and a positive denominator. |
| Attention confirmation | Both `R_w ≥1.5` and `W_w ≥1.5`; at least one source must also have robust z ≥2. |
| Sentiment confirmation | `S_w ≥0.20` and `ΔS_w ≥0.10`. These are mean probability-net values: a 0.10 change is 0.10 score units, not a ten-percentage-point change in VADER-labelled post counts. |
| Market regime | Benchmark close above SMA200; SMA200 above its value 20 sessions earlier; benchmark RV20 ≤30%. |
| Ranking | Descending `Q = (C_t/HH55−1)/a + ln(VR) + ln(R_w) + ln(W_w) + S_w + ΔS_w`, where `HH55` is the prior high and `a=ATR20/C_t`. All coefficients are fixed at one. |
| Entry/sizing | At each weekly snapshot, fill vacant slots with the highest-ranked qualifying names; apply shared sizing. No pyramiding. |
| Exit | First of: close below the prior 20-session low; weekly sentiment <0; benchmark regime fails; protective stop; **42 held sessions**. |
| IC score | The continuous `Q` before Boolean entry gates, across names with complete inputs. Report gated eligibility separately. |


## 3. Attention Exhaustion Reversal — `AER_v2`

**Hypothesis:** extreme attention accompanying a sell-off may precede a rebound once attention cools, sentiment improves and price confirms recovery. This is a **long-only negative-shock reversal**, not an unsupported Indian short-selling strategy.

| Registration field | Fixed rule |
|---|---|
| Sources/indicators | Reddit/Wikipedia attention extremes and decay; Reddit sentiment level/change; five-session price return; SMA20 deviation; RSI14; one-session price confirmation; ATR20; benchmark regime. |
| Prior-week event | At the previous weekly snapshot: `R_[w−1] ≥3`, Reddit robust z ≥3; `W_[w−1] ≥2`, Wikipedia robust z ≥2; `S_[w−1] ≤−0.30`. |
| Prior price shock | At that same previous snapshot: five-session return ≤−8%, close ≤`SMA20−2×ATR20`, and RSI14 ≤30. RSI uses Wilder smoothing; a flat series is neutral, not an extreme. |
| Current exhaustion | Reddit posts fall to ≤75% of the prior week, while current Reddit attention ratio remains ≥1.5. |
| Current recovery | `ΔS_w ≥0.20`, `S_w >−0.10`, RSI14 >30 and ≤50, and current completed close exceeds the previous session’s high. |
| Market regime | Benchmark close ≥90% of SMA200 and benchmark RV20 ≤40%. More severe market deterioration blocks entries. |
| Ranking | Descending `Q = ΔS_w × (−prior five-session return) / prior ATR percentage`. All components refer to the explicitly dated snapshots above. |
| Entry/sizing | Weekly entries into vacant slots; maximum two positions; shared sizing. Each prior-week shock can generate only one entry. |
| Exit | First of: close reaches/exceeds current SMA20; weekly sentiment ≥0.20; benchmark regime fails; protective stop; **20 held sessions**. |
| Re-entry | Minimum **10 local sessions** after exit, plus a new qualifying shock event. |
| IC score | Continuous recovery score `Q` before the event gates; report event-only coverage separately. |


## Evaluation fields to register before running

| Requirement | Fixed evaluation plan |
|---|---|
| Evaluable sample | **At least 30 filled training entries per strategy per market**. Count zero-to-positive position openings—not reweights or partial fills. Otherwise label **Insufficient training entries**; do not pool markets, move dates or loosen rules. |
| IC | Weekly Spearman correlation between the declared continuous score and returns from its executable close to five local sessions later. Require ≥5 valid names; report omitted/undefined observations. Censor labels crossing either split boundary. IC is diagnostic, not portfolio Sharpe. |
| Portfolio metrics | Separate net train/test Sharpe: daily mean/sample standard deviation ×√252, zero risk-free; include cash days. Also cumulative return, drawdown, turnover, costs, entries and exposure. |
| Benchmarks | Same-session SPY/`^NSEI` and equal-weight fixed-universe controls. Disclose dividend-adjusted equity versus Nifty price-index mismatch; do not silently substitute a total-return index. |
| Random entries | **200 matched-duration random-entry runs per strategy, market and split**, seeds 42–241. Keep the observed filled-entry count, ticker frequencies, entry weights and each trade’s held-session duration; randomize eligible weekly entry times, within the same predeclared benchmark-regime stratum. Enforce two slots, split boundaries, valid data and the same market costs/slippage. This conditional timing null schedules exits after the matched duration rather than replaying signal-dependent/protective exits (which could change holding times). Draw dates without using profits or future signals. If 200 feasible schedules cannot be produced, report the baseline incomplete; never silently reduce trades, shorten durations or discard losing runs. This revises v1’s attempt matching and dynamic-exit replay and needs PM approval. |
| Drop-one ablation | Predeclare and remove each predictive indicator/filter individually without retuning; report its contribution. An indicator whose removal changes no eligible signals, targets or returns is a cut candidate for a new registered revision, not silently deleted from this one. For AGM, explicitly test no attention filter, Reddit-only and Wikipedia-only filtering. Preserve execution, costs and protective risk controls in every ablation. |
| Deflated Sharpe | Record every attempted specification and ablation, including failures. Calculate DSR using sample length, skewness, kurtosis and an explicitly documented trial/dependence estimate; do not pretend there were only three trials. DSR addresses selection/non-normality, not data leakage. [Original DSR paper](https://davidhbailey.com/dhbpapers/deflated-sharpe.pdf). |
| Decision | All results **N/A / NOT EVALUATED**. For each market separately, provisional KEEP eligibility requires ≥30 filled training entries, **test net Sharpe strictly above that market’s index Sharpe**, and Sharpe beating **at least 180/200 random runs in both train and test**. Report IC, every drop-one result and DSR probability; the guide gives no extra numeric DSR/IC cutoff. Any failed stated pass mark is logged DROP after evaluation; insufficient data/sample is labelled non-evaluable, never a fabricated negative return. These are guide criteria, not a decision already earned. Final PM decisions remain pending. |

**Important:** 2022–2024 performance has already been observed in earlier India research. The requested test is a frozen temporal test for these new rules, **not an untouched out-of-sample period**.


## Proposed operational clarifications — approval required

These definitions are part of the proposed v2, not claims about existing engine behavior:

- Weekly regimes and weekly attention/sentiment decisions use the Tuesday 00:00 UTC snapshot. Daily price-stop, SMA/low-price and price-target exits use completed local bars and execute at the subsequent eligible close. No order uses its triggering close.
- Predeclared time exits (63/42/20 sessions) execute at the close of the named held session, counting the entry session as 1; they are scheduled when entering, not triggered from that close's price. Preannounced split-end liquidation is similarly allowed at the final close. Protective exits take priority when executable earlier; entry orders are cancelled at a mandatory liquidation boundary.
- Stop updates use only completed prices and become actionable on the next session; entry ATR and d are frozen from the signal snapshot. Zero/nonfinite ATR or a ranking/volume denominator makes the entry/IC score unavailable, never zero or infinity.
- Wilder RSI14 seeds average gain/loss from the first 14 complete changes, then uses alpha=1/14. No losses with gains gives 100; no gains with losses gives 0; both zero gives neutral 50. Full warm-up remains mandatory.
- Missing weekly required attention/sentiment inputs cancel uncertifiable new entry/resize orders; existing holdings remain subject to valid price-based protection and predeclared time exits. Do not impute a sentiment/regime exit from missing inputs. An unexplained held-price gap stops a defensible complete evaluation. No new order is inferred from a false Boolean caused by NaN.
- With valid observations, take the earliest eligible explicit exit; exits precede entries at a shared execution close, with costs charged on all actual trades. SCB/AER fill only vacant slots, without pyramiding. AGM stop/time exits cannot be cancelled by a new weekly target; re-entry needs a later weekly decision (AER retains its stricter ten-session/new-event rule).
- AGM's 80% coverage requirement applies independently to each source; breadth divides by valid covered names, using ceil(0.8*N) (8 US, 7 India), never the missing-as-zero fixed basket. A common exposure multiplier cannot reorder stock scores. Full target review uses current signal-close sizing; SCB/AER surviving positions drift until explicit exits.

## Decisions for Prakhar before registration or implementation

1. **AGM entry interpretation:** accept the explicit price-only attention-risk strategy as the required risk-filter case, or request a separate entry revision. Do not assert it satisfies an unqualified sentiment-at-entry rule without his confirmation.
2. **Sentiment:** approve shared FinBERT/proven validated winner and retaining the existing SCB/AER numeric thresholds on its new probability-net scale. Joshua must supply scorer validation/model and text-version evidence; a fallback is not interchangeable.
3. **Costs/execution:** approve the pinned engine parameters, default adverse slippage and historical-cost limitations; confirm the market-engine integration with cash accounting, quantity/rounding conventions and the proposed operational clarifications. No fixed research proxy is presented as historical tax certification.
4. **Random null/ablation:** approve matched filled entries/durations versus v1's dynamic-exit null, the regime-stratified feasible schedule sampler, the exact predictive-gate/ranking-term ablation matrix and DSR trial/dependence estimator. These are not implementation choices to make after seeing results.
5. **Register the frozen versions:** confirm baskets, dates, one-day publication allowance and evidence standard, then approve writing rows into the shared sheet. Approve any acceptable retrospective-vintage diagnostic scope separately. The guide's stated pass marks are already recorded; passing is N/A.
6. **Later gates:** registration does not authorize acquisition, implementation, backtests, threshold loosening, submission or publication. Dataset coverage, provider permissions, holdout-safe retrieval and executable portfolio semantics need separate review before runs.

## Present data/readiness limits

India Reddit sources, matching and market propagation now have offline support; the active Wikipedia CSV and separate adapter preserve verified identities/history. These are not certified company-week histories. Twelve English identities remain unresolved in the 100-name mapping; the strategy basket stays the original eight names. Publication times, text revisions, historical membership, post-level sentiment and complete 2015–2025 OHLCV/comparable volume remain evidence gates. The isolated unapproved 51,146-row snapshot must not be promoted to approved input. No holdout files were read.

The old equal-target/2024 backtester does not implement all these stateful, risk-sized rules or the full validation suite. FinBERT integration and India-cost reuse are proposed specifications, not completed implementations. The temporal test contains years already observed in older research; do not call it untouched out-of-sample evidence. Missing data and fewer than 30 training entries must not be fixed by fabricated observations or unregistered tuning.

## Registration and result status

All IC, train/test Sharpe, returns, filled entries, random-baseline percentiles, ablations and DSR are **N/A — NOT EVALUATED** for every strategy, market and split. KEEP/DROP is **N/A — pending evaluation and PM review**. No results from the earlier factor experiments are reused.

The seven-column CSV preserves the repository's existing team-format headers. Its Sharpe cells explicitly say `US N/A / N/A; India N/A / N/A` (train / test). The detailed CSV contains full shared rules, individual rules, operational clarifications, required evaluations and N/A slots. These are review-ready rows, not evidence they were registered in the live Google Sheet.

Verification: source/protected-file hashes, guide excerpts, three-row CSV round trips, exact ID/header alignment, N/A metrics, unchanged strategy gates and local links were checked. No automated strategy tests or backtests were run for this documentation-only revision. See the companion evidence JSON for hashes. Original specifications, drafts, source datasets, active configuration, AGENTS.md and team branches remain unchanged.
