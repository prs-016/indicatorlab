# Final Week N1 India symbol interface

The resolver should call `src.markets.india_symbols.normalize_in(raw)` for
`market == "in"`. Catch the shared `src.markets.errors.UnknownTicker` for
the unknown-ticker response. Treat `SymbolLookupUnavailable` as a retryable
provider failure. Tracked NSE spellings resolve locally. BSE conversion and
untracked validation use yfinance, so the caller should allow provider I/O
for those cases.

Read `india_names().get(symbol)` for local metadata. The keys are yfinance
`.NS` tickers. Map `ambiguous` to `ResolvedStock.ambiguous_name` and
`wiki_en` and `wiki_hi` to the corresponding `wiki` languages. If the
symbol has no local row, use James's resolver fallback to Wikidata and
yfinance longName. Preserve unresolved local titles as null. An alternate
title needs evidence of the same listed entity before use. Use
`INDIA_AMBIGUOUS` for short-name checks and preserve Joshua's restriction
to ticker, cashtag, or finance-context matches for ambiguous names.

## Evidence and acceptance

The company names in PR #6's coverage table match all 100 symbols and names
in the independently downloaded November 24 NSE constituent CSV. The
adapter reuses the paired title CSV and ledger for current titles.
There are **88 verified English and 67 verified Hindi titles**. The strict
expected-failure test runs the full 100-title requirement and names these
12 unresolved symbols:

`ABB.NS`, `BAJAJHLDNG.NS`, `BOSCHLTD.NS`, `CUMMINSIND.NS`,
`HDFCAMC.NS`, `POWERINDIA.NS`, `SHRIRAMFIN.NS`, `ENRIN.NS`,
`SIEMENS.NS`, `SOLARINDS.NS`, `TATACAP.NS`, and `VAML.NS`.

A November 24 English Wikipedia API recheck of the exact company title
candidates found no page for eight and redirected four to Cummins, Shriram
Group, Siemens, or Tata Sons. These redirects represent broader entities.
The check does not establish that no alternative article exists. Keep
these rows open for entity-level review. [PR #6 coverage ledger](https://github.com/prs-016/indicatorlab/pull/6)

The three active `INDIA_SUBREDDITS` match PR #5: IndianStockMarket,
IndiaInvestments and IndianStreetBets. The historical DalalStreetTalks
witness remains below for reference. All four witnesses were verified via Joshua's
`ArcticShiftClient` and `posts/search`. Each witness used a bounded
one-post request and an in-range `created_utc`.

| Community | Public post ID | `created_utc` |
| --- | --- | --- |
| IndianStockMarket | `1q0rhav` | `1767227534` |
| IndiaInvestments | `1q0u51l` | `1767236456` |
| IndianStreetBets | `1q0qvqi` | `1767225657` |
| DalalStreetTalks (historical only) | `1q0vo70` | `1767241726` |

This verifies 2026 activity for N1. The separate Week 3 archive-volume
threshold and Joshua's active configuration retain their own evidence.
[Arctic Shift API](https://arctic-shift.photon-reddit.com/)
