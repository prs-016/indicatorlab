# Final-week HK handoff

The live dashboard, K1 names/resolution and K2 on-demand quote adapter belong to
IndicatorLab. They do not belong in the Vibe app's protected agent/session/
provider internals. See `docs/HK_FINAL_K0_K3_STATUS.md` in this repository.

`K3/K3_HK_INCREMENTAL.patch` contains the nine-file HK market-layer follow-up
against the user's fork head `8adb7e2fef4e98e9229861171b6800ee6e52226a`.
`K3/VALIDATION.json` records exact scoped checks and file hashes;
`K3/PR_DESCRIPTION.md` is a review-ready text draft. The same source changes
are installed locally in `Forked VT/Vibe-Trading/agent/`.

This is an incremental update to the existing mixed PR, not a new standalone
joint B3 PR or a claim of compatibility with every newer upstream change.
Combine Jamal's actual India half, resolve the current PR's base conflicts,
perform teammate review and remote CI, then publish with `git commit -s`.
No co-author or attribution trailers are inserted by this handoff.

No source lot CSV is added by this patch. Existing redistribution rights and
historical FX publication semantics still require the explicit decisions
described in `agent/backtest/HK_FINAL_K3.md`. No AWS deployment, remote push,
chat message or empirical strategy rerun was performed by this local delivery.
