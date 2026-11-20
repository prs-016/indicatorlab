Authors: @Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016.

Design issue: DESIGN_ISSUE_URL (replace with the agreed posted issue).

Add the HK portion of the cross-market market layer: sourced HKEX weather
schedule corrections, lunch/holiday handling, explicit previous-available FX-close
valuation, a dated95-name HKEX lot snapshot, and dated bilateral whole-HKD stamp
duty in actual equity execution. Composite fee dispatch now carries the execution
timestamp while preserving India's existing state-aware T+1/price-band routing.

This is the HK side of the planned joint B3 PR. Combine Jamal's reviewed India
calendar/FX/cost pieces before publishing the shared PR. The FX helper consumes
observations with explicit close and availability timestamps; it does not ship a
certified historical FX dataset. The lot reference is current, not historical.
Known weather overrides are sourced but not an exhaustive historical inventory.
Severe-weather trading continues under the post-2024 policy. Stamp exemptions
and full dated fees outside the declared ordinary HKD equity scope need separate
support. No live quote, dashboard, parallel runner or multicurrency portfolio
mode is included.

Validation:153 selected tests passed, including35new cases; socket/DNS guard
recordedzero attempts. Exact command and counts are in VALIDATION.json. Scoped
Ruff on6 changed/new Python files and Black on3 new files passed. Both B3 and
B6 patches reconstruct all10targetfiles byte-for-byte. This is local selected
validation, not remote CI. B2+NIFTY+B3 current coexistence:181 focused tests passed;
only the shared README append needed reconciliation.
