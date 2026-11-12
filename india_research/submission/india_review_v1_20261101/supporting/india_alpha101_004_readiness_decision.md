> Review copy: machine-local paths sanitized; excluded full-archive records remain provenance references, not bundled evidence. Original retained unchanged.

# Alpha101_004 pre-backtest readiness decision

**Recommendation (b): classify alpha101_004 as unsuitable for a meaningful factor-ranking evaluation under the current eight-stock, top-two setup. Do not proceed to its portfolio backtest under this specification.**

The formula is computable and its data coverage is complete. The issue is that it provides little uniquely discriminating membership information in this basket: 193 of 209 weekly candidates depend on ticker ordering, and 120 permit every possible pair. This is a signal-applicability/readiness decision, not a claim about negative returns, a general economic Keep/Drop decision, or a defective original implementation. No price convention is chosen by historical trading returns.

This completes and supersedes the earlier **conditional** #4 recommendation in `india_four_factor_real_readiness_review.md`. That historical report remains unchanged because it is preserved input evidence for previous approved experiments. This dedicated decision and the current research/context addenda provide the updated conclusion.

## Original definition, inputs and what was preserved

Original source: `https://github.com/HKUDS/vibe-Trading/blob/7f6908b7e1b95d971f4151bfaf2382e2ce9485cf/agent/src/factors/zoo/alpha101/alpha_004.py::compute`:

```text
- Ts_Rank(rank(low), 9)
```

`src/factors/base.py::rank` ranks the stocks' low prices cross-sectionally on each date, using average percentile ranks. `ts_rank` ranks today's cross-sectional rank within its own nine-session history, again with average ranks for ties and full valid windows. Thus the factor reacts to changes in relative low-price ordering, not simply to a stock's own price falling.

A constant nine-value rank series has average tied rank 5 out of 9 and therefore score **-5/9**. Unlike #3's zero-variance correlation, this constant window gives a valid but non-discriminating number. A different score must come from relative rank dynamics; changing the sign, window, low-to-return input, tie method or missing-score behavior would change the factor definition and is not proposed.

The baseline uses the **predeclared frozen adjusted-price convention** from research_v3. Research_v4 has the same exact low-price tokens; its twelve volume corrections do not enter #4. The existing original Vibe baseline and two previously completed convention score files were reused, not recalculated as new experiments. Their original source hashes were checked. Five additional labelled input-scale diagnostics invoked only the unchanged original #4 through the isolated bridge; none writes a research dataset or changes production settings.

Primary dataset reference: `archive:india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/` (manifest SHA-256 `9a913ab88927ee35fd43a96b76d548e949a40d14815119e2b315a5ccb7dfd3b1`). The eight assigned stocks, 25 prior sessions and January 4, 2021–December 31, 2024 evaluation remain fixed. No signal date beyond the cutoff or October 2025 holdout observation is used. Outputs: `archive:india_alpha004_readiness_20261029T042224Z/`.

## Tie frequency and influence under the fixed convention

- All **7,920 evaluation cells** are finite, across 990 sessions; ties occur on every day.
- **6,864 cells (86.67%)** come from constant nine-session low-rank windows, despite changing unranked adjusted lows. Each has score -5/9.
- **563 days** have identical scores across all eight stocks. In every such day, all eight nine-session low-rank windows are constant; these are not unexplained coincidences or missing-score fills.
- **193 of 209 weekly candidates (92.34%)** have a tie across the top-two membership boundary. Only **16 (7.66%)** have a unique top-two membership.
- **120 weekly candidates (57.42%)** have all eight stocks tied, allowing any of the **28 possible two-stock pairs** before a tie rule is applied.
- Of the 208 nonterminal candidates with a later evaluation session, **192** have ambiguous membership. The extra December 31 candidate cannot trade after the cutoff and is reported separately.

Weekly admissible-pair counts are 28 pairs on 120 dates, 6 pairs on 70 dates, 5 pairs on 2 dates, 2 pairs on 1 date and 1 pair on 16 dates. These are exact equal-score choices; the diagnostic does not create alternative scores or round near-scores into ties.

Reversing **only ticker ordering inside exact score ties**, as a candidate-only diagnostic, changes membership on **193 of 209 dates**. It does not reverse the factor score ranking. Under the existing ascending-ticker rule, AXISBANK appears in 175 candidates and HDFCBANK in 170, while TCS appears in none. Under the diagnostic descending-ticker rule, TCS appears in 192, SBIN in 125, AXISBANK in 26 and HDFCBANK in 32. All 120 all-name ties select AXISBANK/HDFCBANK under the existing rule and SBIN/TCS under the reversed diagnostic rule.

These counts establish a large effect on candidate membership. **No alternative tie-break portfolio or return comparison was run**, so no share of performance is attributed to that rule. The original production ticker rule remains unchanged. A mechanically valid simulation would mostly evaluate that tie policy's chosen membership rather than a uniquely ordered factor signal.

## Understanding the 99-of-209 adjusted-price differences

The earlier comparison removed the saved cash-dividend adjustment ratio from lows, reproducing **Yahoo Close basis**, with vendor split and other corporate-action transformations retained. It is not a pure split-only or nominal price series, particularly before Reliance's July 2023 demerger.

The existing ascending-ticker rule yields different pairs on **99 of 209 weekly dates** (all 99 are nonterminal). That number is real, but does not mean 99 uniquely identified preferences reversed:

- On **10 dates**, the two conventions' admissible membership sets are disjoint: every permitted tie-break must produce different pairs across those bases.
- On the other **89 changed dates**, at least one pair is admissible under both conventions. The predeclared deterministic selections still differ, but the contrast is not robust to how the ties are resolved.
- Across all weekly dates, the full set of admissible memberships changes on **118 dates**; only **one** changed date has a unique pair under both conventions.

The 89 overlapping cases must not be dismissed as no change or attributed exclusively to alphabetical order. The input convention can change rank constraints and tie pools even when they retain a common admissible pair. This decomposition distinguishes deterministic choice sensitivity from unavoidable score-preference incompatibility.

Removing cash adjustments alone leaves 198 weekly cutoff ambiguities and 118 all-name ties. The other existing diagnostic—Yahoo Close basis in 2024-end share units—changes 98 chosen pairs, has 9 disjoint admissible sets and 195 weekly cutoff ambiguities. Neither is a demonstrated cure for the underlying lack of discrimination.

## Corporate-action and normalization diagnostics

Stock-specific scale factors can change cross-sectional price ranks even when they are constant through time for a stock. A common scale applied to all eight on a date would preserve rankings; these company-specific corporate-action conventions do not.

The independently documented share events are Reliance's 1:1 bonus on October 28, 2024, HDFC Bank's 1:1 bonus on August 26, 2025 and Kotak Bank's five-for-one subdivision on January 14, 2026. `corporate_action_scale_evidence.json` retains the exact saved official descriptions, ex-dates, factors and source hashes. Later events are frozen-vintage metadata, not later price observations or new trading signals.

The following are **controlled input diagnostics**, not alternative datasets adopted for trading. OHLC fields are scaled together in memory to preserve bounds, while volumes and portfolio settings remain unchanged. Each #4 calculation is the original unchanged function. No prices are repaired or coefficients fitted.

| Diagnostic vs predeclared baseline | Weekly chosen-pair changes | Disjoint admissible sets | Weekly cutoff ambiguities remaining |
|---|---:|---:|---:|
| Remove cash-dividend OHLC ratio (existing Yahoo Close basis) | 99 | 10 | 198 |
| Same, also normalize post-2024 share units (existing comparison) | 98 | 9 | 195 |
| Reverse only HDFC's known post-2024 twofold share scale; retain cash adjustments | 46 | 8 | 191 |
| Reverse only Kotak's known post-2024 fivefold share scale; retain cash adjustments | 16 | 0 | 191 |
| Reverse both post-2024 share scales; retain cash adjustments | 60 | 8 | 188 |
| Remove only Reliance's 2024 bonus back-adjustment before its ex-date | 18 | 2 | 200 |
| Remove only each stock's fixed terminal Adj Close/Close normalization | 70 | 14 | 193 |

The last diagnostic divides each stock's full adjusted OHLC path by its own frozen December 31, 2024 Adj Close/Close ratio. It isolates sensitivity to the inherited terminal normalization; it does **not** independently reconstruct every post-2024 dividend or point-in-time prices. The Reliance diagnostic reverses only its documented share adjustment, not its separate cash/de-merger transformations; it is not a full nominal-price reconstruction.

These effects are not additive. They include changed crossing dates, different tie pools and rolling propagation through nine sessions. The 99 changes cannot be assigned one-for-one to nearby ex-dividend dates: vendor back-adjustment acts on earlier history, and static company-specific factors can change relative price levels long before an ex-date. The available action table is evidence for the documented changes, not a complete pre-2023 action inventory or proof of a unique cause for every historical crossing.

Removing known future share scaling produces 60 changes even while cash adjustments remain. That confirms that later corporate-action units embedded in a retrieved price vintage can materially affect this price-level rank factor. This is part of its **non-point-in-time historical-vintage limitation**, not a claim that future prices were fed into the trailing calculation. No future observation was used in the factor windows; the input-price vintage itself is retrospective.

The full 2021–2024 nominal low-price history is not independently reconstructed because Reliance's additional pre-demerger normalization remains unresolved. None of these diagnostics should be relabelled as nominal or historically point-in-time evidence. The small Kotak volume discrepancy and the twelve volume conversions do not enter #4's formula, and none was altered by this study.

## Decision rationale and boundaries

The predeclared adjusted-price convention is a reproducible research convention, and all scores are calculable. Nevertheless, under **this basket and top-two rule**, most candidates have no unique factor-selected pair and over half contain no cross-stock score discrimination at all. The original ordinal signal is dominated by long stable low-price ordering and large tie pools, with meaningful exposure to retrospective company-specific price units.

**Choose (b), unsuitable under the current eight-stock universe for the intended factor-ranking evaluation.** Preserve the complete signal audit as an unsuccessful applicability experiment. Do not run a portfolio merely to generate a Sharpe dominated by the arbitrary fixed ticker tie rule. This decision is made from signal geometry and input conventions, not trading returns. It is not a general Keep/Drop verdict about the original formula in another universe.

No alternative convention is selected because it improves coverage, reduces ties or might trade better; even the variants retain severe ambiguity. A future independently justified broader-universe or point-in-time input study would be a separate proposal requiring approval and data validation. Do not introduce noise, new tie rules, price normalization, changed rank/window definitions or an eligibility change as a silent rescue. If the user later explicitly requests a purely mechanical diagnostic of the fixed tie policy anyway, that would require a new scoped approval and must not be described as unambiguous factor evidence.

## Tests, artifacts and integrity

New `src/india_alpha004_audit.py` computes candidate tie pools, all admissible pairs, weekly comparisons and low-rank window evidence; it does not change any production factor or simulator. `tests/test_india_alpha004_audit.py` adds **nine offline synthetic cases**: 28 all-tied pairs, unique membership despite ties among both winners, partial cutoff pools, preserved missing values, overlapping versus disjoint convention choices, terminal candidate handling, constant ranks with changing prices, and original Vibe's finite -5/9 plateau.

The complete suite passed **250 tests in 21.79 seconds**, zero failures/skips:

```bash
VIBE_PYTHON=.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

Saved evidence includes baseline daily/weekly tie geometry and admissible pairs, every nine-session low-rank window, seven convention-comparison tables, exact new diagnostic scale matrices and original scores, official corporate-action references, source snapshots/hashes, test and execution logs, decision and provenance. The original baseline and completed two convention calculations were reused; only new input-scale sensitivities were calculated. No returns, IC, portfolio backtest or performance metrics were computed or used to choose a convention. Existing datasets, original factor code and every prior strategy result remain unchanged. No package installation, commit, push or publication. Stop for user review.
