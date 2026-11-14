# HK submission: Vibe Trading contribution

This branch contains only the Vibe Trading contribution prepared for mentor
review. Open **[contributions/vibe-trading](contributions/vibe-trading/README.md)**.

The package includes the HSI benchmark-universe changes, HK quote retrieval
and optional collector, integration/tests, file manifest, benchmark evidence
and upstream license. All 21 changed/new Vibe Trading target files are inside
the patches. Use 01 then 02, or the combined APPLY_ALL patch, as documented.

The patches apply to a compatible Vibe Trading checkout. This repository is
the mentor handoff, not the installed/running app or a price database.
Generated data is retrieved by the collector when it runs after installation.

Inherited starter files, HTML dashboards and unrelated team research were
removed from this HK submission branch. Full research remains in the separate
Jack checkout; main and its Git history are preserved. This submission-only
cleanup is not a change intended to merge into IndicatorLab main.

See [code_review.md](code_review.md) for the packaging review and the package
README for application instructions, validation scope and remaining upstream
acceptance steps.
