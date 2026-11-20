# Proposed B4/B5 contract (awaiting team agreement)

Authors: @Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016.

This is Jack's local proposal for Monday's discussion, not an agreed schema or
an implemented B4 process runner. Joshua owns B4; Jamal and Jack share B5.
`src/hk/week4_compare.py` starts B5 with a tested consumer and JSON/Markdown
output. It does not synthesize returns or treat factor IC as a portfolio Sharpe.

An index has `schema_version: indicatorlab.cross-market-index/v0-draft`,
`zoo`, a common `period: {start, end}`, and `results` keyed by universe.
Each item is `{status: ok|error, path: relative JSON path|null, error: text|null}`.
Paths stay beneath the index directory. A failed market remains an error entry;
another market may still produce a report. Successful result files repeat the
universe, zoo and exact period and contain `factors` with unique `factor_id`s.

Metrics per factor are nullable numbers: `ic_mean_local`, `ic_ir_local`,
`sharpe_local`, `ic_mean_usd`, `ic_ir_usd`, `sharpe_usd`. The first version of
upstream factor benchmarking may provide only local IC. Missing portfolio/FX
results stay null with a capability limitation. Currency, adjustment basis,
calendar, forward-return horizon, costs, membership and data-source metadata
must travel with actual results before cross-market interpretation.

Decay is each non-US metric divided by the matching SP500 metric from the
same period/horizon. Missing or near-zero US denominators yield null. Negative
denominators need interpretation; a large ratio is not automatically good.

DSR uses Vibe's existing `agent/src/quantlib/multipletesting.py` directly.
It requires actual net daily USD portfolio returns plus a caller-attested
complete cross-market trial ledger: `complete: true`, `return_frequency: daily`,
`n_trials`, and `per_observation_sharpes` for every trial. Annualized Sharpes
must never be paired with a daily observation count. If the ledger is incomplete
or portfolio returns do not exist, the report states that DSR is unavailable.
The schema does not claim that a factor IC is a portfolio return stream.

Example invocation after the producer adopts this proposal:

```bash
python -m src.hk.week4_compare results/cross_market/index.json \
  --output results/cross_market/comparison --vibe-agent /path/to/Vibe-Trading/agent
```

Tests use explicitly synthetic fixtures. No India or US/HK empirical comparison
is being represented by those fixtures. Open decisions: exact upstream result
adapter, naming of currency-specific IC, a durable ledger location, and how the
B4 index carries the B3 FX availability and source metadata.
