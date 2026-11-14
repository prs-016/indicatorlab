# Local Vibe handoff for Jack

Checkout: `/Users/jackgui/Desktop/hk/Vibe-Trading-upstream`, local branch
`feat/alpha-bench-hsi`, base `67ce0ca5c9b2a3e3d321217eff043dad913a27fa`.
The current filtered folder/ZIP is `../HSI_Vibe_Trading_Week3_Ready` (relative
to the IndicatorLab root). It has two scopes and a verified combined patch.
No fork, commit, push, PR or remote CI was performed for you.

## Scope 1: Add HSI universe to Alpha Zoo

The benchmark now accepts `hsi` via API and CLI. It parses current Wikipedia
members and records the actual page revision date, routes prices through the
shared HK provider chain and reports missing names. A dated full 95-name
fallback is explicitly degraded. 700/0700/0700.HK resolve to one instrument.
Sector labels use the SP500 90% gate; OHLC-mean VWAP is labelled a proxy;
survivorship_bias=True and price/volume provenance remain visible.

**Actual bounded run:** 2016-06-01 through 2025-09-30, 100 Alpha101 factors
tested, one skipped (alpha101_097, >95% NaN), 85/85 Wikipedia names loaded,
zero missing. Wikipedia revision 1377881667/source date 2026-10-01; sector
coverage 100%. Top reported alpha101_054 mean IC 0.0408, IC IR 0.2668.
Those are exploratory factor diagnostics, not a costed portfolio Sharpe/KEEP.
Wikipedia's 85 names lag the separate official 95-name operational snapshot.
Tencent/Eastmoney/Yahoo price providers were observed; adjustment-basis and
point-in-time limitations remain in the metadata.

Working Python entry with `PYTHONPATH=agent` from the repository root:

```python
from cli.main import main
raise SystemExit(main(["alpha", "bench", "--zoo", "alpha101", "--universe", "hsi",
                      "--period", "2016-06-01/2025-09-30", "--top", "20", "--yes"]))
```

The argparse entry worked on Python 3.14. The separate Typer module entry had
an existing unresolved `typer` annotation error; it was not patched here.
See results/hk/week3/hsi_alpha101_summary.json and hsi_alpha101_top20.csv.
Local generated HTML is ignored at data/hk_week3/hsi_alpha101_report.html.

## Scope 2: Timestamped HK quotes and optional archive

The read-only agent/MCP quote tool defaults to Tencent `r_hk` with a 60-second
age threshold and reports provider/receipt timestamps, currency and stale
state. The optional SQLite collector preserves observations. It uses the HSI
snapshot helper from scope 1, so apply 01 before 02. Lower-level explicit
`auto` retains legacy Yahoo-first behavior; choose `tencent` for this feed.
No broker order, account login or permanent shared cloud service is created.

Ten-minute audit: 95 stocks × 120 polls, 11,400 observations, zero poll errors;
median last-trade age 10.63 s, p95 86.58 s, 90.95% below one minute. This is
not an exchange publication-delay SLA. A closing Google Finance sample agreed
within display rounding, but earlier intraday clock discrepancies remain
documented. No blanket accuracy or redistribution-entitlement claim.

## Review and publishing

91 focused HSI/quote tests pass; earlier 1,085 selected integration/purity/
look-ahead tests passed, 23 skipped, one existing Python 3.14/Pydantic warning.
Scoped Ruff/Black and whitespace pass. Both split and combined patch routes
were applied to clean base files and byte-compared across all 21 targets.
These are local checks, not all upstream tests or remote CI.

Keep only the relevant patch scope in each review. Do not upload research,
raw/live prices, virtual environments, AGENTS files or this wrapper folder.
The separate IndicatorLab strategy results are not part of the Vibe patch.

PR #1303 was closed without merge; the author
[withdrew it as not ready to upstream](https://github.com/HKUDS/Vibe-Trading/pull/1303#issuecomment-5481159725).
Its combined NIFTY/process-pool proposal is not evidence of accepted structure.
Coordinate the actual shared structure with Jamal instead.

Before publishing, use real identities for Jack, Joshua, James and Jamal as
required by the task guide, and real DCO Signed-off-by trailers under upstream
CONTRIBUTING.md. No identities were fabricated. Human review remains necessary.
