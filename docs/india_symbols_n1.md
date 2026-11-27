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
title needs verified identity or an approved proxy disposition. Use
`india_names(include_parent_proxies=True)` for approved parent and group titles. Use
`INDIA_AMBIGUOUS` for short-name checks and preserve Joshua's restriction
to ticker, cashtag, or finance-context matches for ambiguous names.

## Evidence and acceptance

The company names in PR #6's coverage table match all 100 symbols and names
in the independently downloaded November 24 NSE constituent CSV. The
adapter reuses the paired title CSV and ledger for current titles.
The [coverage registry](../config/india_wiki_coverage.csv) and N1 metadata
contain **100 unique company records**. The English mapping has 88 verified
exact-company titles, nine verified parent proxies and two verified group
proxies. Hindi has 67 verified titles. `SOLARINDS.NS` has status
`WIKIPEDIA_UNAVAILABLE`. Its Wikipedia titles are null, and its ticker,
company name, aliases and ordinary stock lookup remain available.

The acceptance test validates all 100 company records against the approved
mapping policy. The [review record](../config/india_wiki_identity_review.json)
preserves the direct-title searches and documents every proxy with company
identity, canonical page, relationship evidence, Wikidata ID and retrieval
checks. Proxy views and edits represent broader corporate attention. See
the [pipeline handoff](india_wikipedia_csv_adapter.md) for opt-in and
provenance handling.

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
