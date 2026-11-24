# Week 3 complex strategies — portable review package

This package delivers completed **US** WATM_v1_2, WVB_v1_2 and WCR_v1_2 research.
It does not rerun historical studies, register strategies or approve quarantined
India observations. All original local datasets, results and frozen versions
remain unchanged. No raw Tiingo prices, Wikipedia histories, Reddit text,
credentials, pickles or per-fill licensed prices are included.

## Actual evaluation

Train 2016-06-01–2021-12-31; test 2022-01-01–2025-09-30; USD100,000 fresh capital
per split. The exact ten-stock US basket and SPY are in the frozen rules.

| Strategy | Entries train/test | Rank IC train/test | Net Sharpe train/test | Null percentile train/test | Research outcome |
|---|---:|---:|---:|---:|---|
| WATM_v1_2 | 202 / 119 | .017471 / -.026014 | 1.817279 / .368955 | 98.5% / 33.5% | DROP |
| WVB_v1_2 | 15 / 15 | -.012638 / -.007608 | .369312 / -.159678 | 62% / 29% | INSUFFICIENT TRADES |
| WCR_v1_2 | 3 / 5 | .007204 / -.012214 | -.565819 / 1.178539 | 1.5% / 97.5% | INSUFFICIENT TRADES |

SPY Sharpe: .997686 train / .655867 test. Each strategy has 200 completed matched
timing comparisons per split. WATM fails the test benchmark and random gate;
WVB/WCR fail the 30-training-entry requirement and cannot qualify for KEEP. All
four/six/seven frozen drop-one variants respectively were evaluated in each split.
Inert variants are disclosed, not retroactively deleted from frozen strategies.

Full precision, fees, compounded returns and explicit India N/A rows are in
[market_results.csv](market_results.csv) and [results_summary.json](results_summary.json).
Returns ending `_fraction` or `net_cumulative_return` are fractions (1.0 = 100%);
random percentiles are percentages; fees are USD cash amounts. Sharpe is daily
net mean/sample standard deviation times sqrt(252), zero risk-free, including
cash days. Both splits use the same session-aligned adjusted-close SPY baseline.
US costs are 10 bps per absolute traded notional; India bindings call the original
Vibe engine. Fractional holdings, fee-inclusive cash constraints, later-session
execution, protective exits and explicit split-end liquidation are preserved.

Original Vibe Spearman rank IC uses finite pre-entry-gate scores and next-five-
session execution-aligned returns, omitting undefined/incomplete intervals. IC
sample counts differ from trade counts. Historical publication receipts are not
invented: the accepted session-close information boundary and one-day Wikipedia
lag remain documented assumptions, not provider first-release certification.

## Frozen definitions and complexity

The unchanged [v1_2 frozen rules](../../reports/week3_wiki_frozen_20261117_v1_2/rules.json)
and their [original checksum file](../../reports/week3_wiki_frozen_20261117_v1_2/checksums.json)
remain authoritative. Rules SHA-256:
`c44d9adf372c069a064fdcbec25ee5fce35640b99b390cd03ed58dab9f273c33`.

- WATM: benchmark SMA200 regime, momentum/SMA50 selection, ATR risk and a market-
  wide Wikipedia attention/coverage risk gate. Attention scales the portfolio.
- WVB: benchmark regime, breakout20, relative volume, Wikipedia confirmation,
  ATR risk and low10/expiry exits; vacant-slot entries rather than rebalancing.
- WCR: benchmark regime, Wikipedia shock/cooling, SMA20, RSI14, price recovery,
  ATR risk, exits and stock-specific cooldown/event-consumption controls.

Each has at least four indicators, market OHLCV plus Wikipedia as independent
sources, and regime/entry/exit-risk layers. The supplied Prakhar clarification
recorded in the freeze allows these two sources without Reddit/FinBERT in every
strategy; this is separate from the original guide's attention-plus-sentiment
example. No new rule or threshold is introduced by this publication.

The original freeze's NOT REGISTERED/NOT EVALUATED text is its historical state,
not today's results. [Registration status](registration_status.json) distinguishes
WATM's user-confirmed prior entry (exact sheet timestamp unknown) from WVB/WCR's
explicit execution waiver and unverified shared-sheet entry. Do not backdate.

## Evidence and trial accounting

- [WATM original baseline](WATM_v1_2/baseline_original.json) deliberately preserves
  its initial failed null attempt; use the later [corrected null summary](WATM_v1_2/random_summary.json)
  and [protocol](WATM_v1_2/random_protocol.json) for completed random comparisons.
- [WVB evaluation](WVB_v1_2/evaluation.json) and [WCR evaluation](WCR_v1_2/evaluation.json)
  retain full numerical outputs. Each strategy directory includes its ablation
  table and two 200-row random metric tables.
- [Trial audit projection](trial_ledger.csv) contains all 1,653 saved current
  records from three ledgers: successful evaluations plus failed schedules,
  earlier unrun null attempts and unavailable DSR. Original ledger/settings
  hashes are retained. This scalar projection omits repeated private input
  structures; it is not a byte-identical serialization of the full local ledgers.
- [Input provenance](input_provenance.json) preserves actual Tiingo/Wikipedia
  manifest hashes, accepted timing assumptions and independent replay checks.
- [Source artifact index](source_artifacts.json) records original hashes and
  public review-copy transformations. Original `results/` paths in metadata are
  local archive identifiers, not promises that ignored files are in this commit.

**DSR is N/A for all three:** the complete global prior attempted-trial history
and effective independence/dependence assumptions remain uncertified. Counting
only these three strategies or treating timing-null draws as independent alpha
trials would invent a probability. The random sampler preserves realized counts,
durations, weights/resize paths, cash and costs, with symmetric relocation/swaps;
64-sweep mixing and global connectedness are unproved. Percentiles are conditional
empirical diagnostics, not exact-uniform p-values. Original frozen definitions
and baseline performance are unchanged.

## India evaluation — blocked, not a failed portfolio

[2025 decision](india_2025_decision.json) and [per-stock counts](india_2025_per_symbol.csv)
retain the existing 0 accepted / 1,496 quarantined observations. Eight March 18
rows have zero volume and flat previous-close prices. No quarantined row is
promoted, repaired or deleted. Required safeguards remain original retrieval
bounds, adjustment vintage, comparable volumes, evidenced sessions/closes and
causal availability. v4 ends in 2024 and supplies no independent 2025 anchors.

The eight fixed stocks require a validated 2025-01-01–2025-09-30 extension;
`^NSEI` requires validated benchmark/session coverage through the same cutoff.
The earlier coverage report also identifies six unverified/missing benchmark
closes before 2025. Retained official 2025 corporate-action events do not alone
reconstruct vendor normalization or missing observations. Existing rejection
criteria were not weakened and exhausted providers were not retried. US results
must not be presented as US-versus-India evidence; India remains N/A.

## Delivery and reproducibility

[Exact seven-column Strategy Log import](strategy_log_import.tsv) is ready for
the official sheet. No authenticated sheet URL/interface was available in the
inspected repository/guide, so no sheet update is claimed. Import the actual
outcomes and preserve the registration qualifications above.

[Publication manifest](publication_manifest.json) verifies included artifacts and
current framework files, distinct from historical execution hashes and the
unchanged frozen rule hashes. The legacy common-runner parameter/specification
dependencies are included unchanged; their archived narrative references may
refer to local-only historical drafts. They are not new registration claims.

See [execution and offline test instructions](../../../docs/india_week3_research.md).
Licensed source datasets are intentionally absent; a reviewer needs authorized
matching inputs to replay historical returns. Missing inputs fail rather than
triggering acquisition or synthetic substitution. Existing original reports and
raw evidence remain local; this is a separate review package.
