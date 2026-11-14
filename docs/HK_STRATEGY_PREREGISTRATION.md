# Five-strategy local preregistration

The user's five-strategy request superseded the initial unrun three-strategy draft, preserved in `HK_STRATEGY_INITIAL_DRAFT_UNRUN.md`.

Canonical rules: `config/hk_week3_research.json`, version week3-five-v2.
Immutable local registration: `results/hk/week3/five_strategy_preregistration.json`, frozen 2026-11-12T08:56:26.740443+00:00.
Both markets' train-count-only choices: `results/hk/week3/five_strategy_selected_variants.json`.
Completed results: `results/hk/week3/FIVE_STRATEGY_REPORT.md` and `strategy_log_sheet_ready.csv`.

Every strategy uses at least four indicators across price/volume and Wikipedia, regime/entry/exit layers, observed historical FinBERT text, both markets, train entry gates and Vibe costs. The defensive strategy uses attention to scale the whole book. Weekly signals use completed Monday–Sunday UTC observations and execute at the next week's first exchange open; stops are close-triggered and fill at the next tradable open. Sizing and all train-only variant paths are in the frozen JSON.

The actual evaluations are complete; all ten market cases are DROP. No post-test rule tuning was performed. Registration was local under the user's local-only instruction; posting rules before the first run to the literal shared team sheet did not occur and cannot be retroactively claimed.
