# Jack final week: K0-K3 local delivery

Scope: the supplied final-week guide's shared contracts and Jack K0-K3, plus
the requested USD purchase-cost display. K4-K7 and strategy selection/evaluation
are outside this change. User handles GitHub publication; AWS stays deferred.

## What is implemented and what still needs acceptance

| Task | Local result | Remaining acceptance |
|---|---|---|
| K0 previous weeks | Root cutoff remains 2026-11-01. Actual CSVs for all 95 operational roster names contain the October 30 session, before the Saturday October 31 cutoff. Earlier research/random controls are preserved. Existing PR and delay evidence audited. | AWS/lunch alarm acceptance and actual team posting remain deferred. Existing PR 2287 combines B2/quotes/B3/design and is unmergeable at audit; no green remote CI is established. The strict B2 benchmark remains stopped at its 85-versus-95 source mismatch. |
| K1 symbols | All required ticker aliases and five-digit counters; bounded/cached history validation; all 95 English/Chinese display names, required ADR aliases, 74 verified US alias mappings, ambiguity flags. New 2026 archive checks qualify HongKong and ChinaStocks. | English Wikipedia coverage is 94/95: Laopu Gold has no verified English article. Other unverified ADR mappings remain labelled unverified. James/Joshua receipt and exception/interface agreement are not claimed. |
| K2 on-demand quotes | Shared `get_quote(symbol, market)` HK branch, HSI DynamoDB GetItem, explicit local reader for laptops, non-HSI Tencent, recorded response tests, five-second cache, correct lunch/closed/delay labels. Existing local API supports symbol queries. | The default DynamoDB branch is tested with mocks, not deployed AWS. Jamal's actual India quote implementation was not present at the named shared path; composing his branch and accepting the final shared return schema remain team steps. |
| K3 HK market layer | Actual single/composite fills and liquidation obey HK hours; one-share warned missing-lot fallback; dated duty and lot rounding; Vibe-loader daily HKD=X adapter with causal USD marking; sourced weather inventory and HSI-gap audit. Nine-file incremental patch prepared and applied locally in Forked VT. | Joint India/HK PR, remote CI and posting remain external. The stored 2016-2026 HSI daily bars now fully reconcile with the HK calendar; additional future-discovered gaps still require corroboration. Source FX completion/publication semantics must be supplied. The existing lot CSV's redistribution rights are unverified. |

This table deliberately does not mark the guide's external Done when lines as
complete merely because local unit tests pass.

## Open the USD purchase estimate

Double-click `Start HK Dashboard.command`, or open the running local dashboard
at `http://127.0.0.1:8765/live-markets/`. Search for `0700`, click Tencent's
company name, and use **What would I need in USD?** in the details dialog.

Enter shares and broker/FX charges. Blank fees stay unknown; enter zero only
when the charge does not apply. The estimate rounds to board lots and separates
share value, stamp duty, SFC/AFRC/HKEX charges, optional settlement pass-through,
broker commission/platform fees, FX spread and fixed conversion/transfer fees.
The exchange rate is HKD per USD, so HKD cash is divided by the effective rate.
Rates carry source, observation date/time and retrieval time. Stale references
are rejected rather than relabelled current. Personal US taxes are excluded,
not replaced by a guessed flat rate.

## Files to inspect

- [K0 audit and full 95-stock coverage](HK_FINAL_K0_AUDIT.json).
- [K1 implementation/metadata handoff](HK_FINAL_K1_HANDOFF.md).
- [K2 and USD estimator usage](HK_FINAL_QUOTES_AND_COSTS.md).
- `src/markets/hk_symbols.py`, `src/live/quote.py`, `src/hk/trade_costs.py`.
- `config/hk_order_cost_sources.json`: official rates, dates, source URLs and
  broker/personal-tax boundaries.
- [K3 contribution handoff](../contributions/final_week/README.md); actual fork
  code lives under `Forked VT/Vibe-Trading/agent/`.

No raw Yahoo history CSV, new HKEX workbook, credentials, login daemon or AWS
resource is added. The existing collector checkout and frozen strategies,
source hashes, research input prices and empirical results are unchanged.

## Validation

The scoped K1 selection passes 42 cases. The full staged HK/config/API selection
passes **250 cases without skips** after restoring the existing read-only legacy
Vibe dependency path in the scratch environment. The permanent checkout is
checked again before handoff. [Exact local evidence](HK_FINAL_LOCAL_VALIDATION.json)
records the separate test selections; overlapping counts are not added.

K3's 14-file compatibility selection passes 260 tests, with one inherited
Python 3.14/Pydantic-v1 warning. The existing 21 Node cases, JavaScript syntax,
scoped Ruff/format and static build pass. Browser fixture checks cover unknown
fees, platform fees, board lots, preserved input/focus, error isolation and stale
request cancellation. Real browser/API checks used all 95 quotes and an actual
dated FX reference; no page errors or mobile horizontal overflow occurred.

The independent review's FX-cache wall-clock and local-symbol-alias findings
were corrected with regressions. No empirical strategy test was rerun.

## Final historical-calendar reconciliation

[Saved audit](HK_FINAL_HSI_CALENDAR_AUDIT.json) compares the actual stored ^HSI
daily closes with the HK calendar for 2016-01-01 through 2026-10-31. It reports
no unexplained missing sessions, post-reform data gaps or unexpected benchmark
sessions. This verifies daily-session agreement, not every historical intraday
weather event or FX publication timestamp. No portfolio evaluation was run.
