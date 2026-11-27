# India Wikipedia CSV adapter

The separate [adapter](../src/india_wikipedia_mapping.py) reads the active
[four-column CSV](../config/india_wiki_titles.csv) and its existing
[evidence ledger](../config/india_wiki_mapping_ledger.json).
It performs no requests, changes no configuration and does not activate collection.
James's pipeline and branches are unchanged.

## Interface and connection point

Read-only review of `origin/wikipedia`, commit
`38ec62f02f1f040bbc71177ff4edfd4dbc439938`, confirms that
`src/wiki_pipeline.py::universe(market, strategy)` returns:

```python
{ticker: dict(stock_config['wikipedia'])}
# e.g. {'TCS.NS': {'en': 'Tata_Consultancy_Services', 'hi': '…'}}
```

The adapter provides that exact output shape, with official bare symbols
qualified as `.NS` tickers and original UTF-8 title strings retained:

```python
from src.india_wikipedia_mapping import load_india_titles

mapping = load_india_titles()  # local files only; defaults are repo-relative
india_titles = mapping.current_titles()
# 88 tickers: 88 English and 67 Hindi current titles
approved_titles = mapping.current_titles(include_parent_proxies=True)
# 99 tickers with an English title: 88 exact, 9 parent proxies, 2 group proxies
history = mapping.title_history()
# history['ADANIENSOL.NS']['en'] contains current and two former records
```

James can connect it at the **India branch of `universe()`**, returning
`load_india_titles().current_titles()` as the base universe when `market == 'IN'`.
Keep his existing YAML path for US/HK. This is the proposed connection point;
the hook remains with James. For an approved proxy-enabled run, pass
`include_parent_proxies=True` in the India-only branch. If `strategy=True` adds extra
India tickers, retain his existing option semantics but review collisions:
`out.update(...)` can replace verified titles. Retain registry dispositions when merging strategy entries.

If he needs a YAML-shaped stock fragment instead, this local conversion yields
only the expected Wikipedia field (not a replacement for full stock settings):

```python
fragment = {
    ticker: {'wikipedia': dict(titles)}
    for ticker, titles in india_titles.items()
}
```

The Wikipedia fragment covers 88 exact or 99 approved tickers, depending on
opt-in. Retain the full stock configuration and omit empty title dictionaries.
His current pipeline cannot safely process an empty language dictionary.

## Historical titles and unknown dates

The required CSV cannot distinguish current/former titles or store `valid_to`.
The existing ledger is therefore required, rather than selecting a title based
on CSV order or the latest nonblank date. `load_india_titles(csv_path,
ledger_path)` accepts explicit local paths and returns immutable `TitleRecord`s:
`symbol`, `title`, `lang`, `kind`, `valid_from`, `valid_to`.

- `current_titles()` selects exact current rows. The optional
  `include_parent_proxies=True` includes ledger-labelled `parent_proxy` and
  `group_proxy` rows.
  Each ticker/language has at most one exportable title.
- `title_history()` returns **all** records, grouped by ticker/language, retaining
  all 12 historical rows. Consumers must check `kind` before using a record. Unknown boundaries remain `None`; this is not an
  implicit interval extending to the start/end of history.
- Starts must match CSV/ledger evidence exactly; nonblank boundaries require
  recorded event identifiers and UTC timestamps. Duplicates (even identical),
  competing current titles and reversed intervals fail rather than choosing one.
- These checks validate consistency with the saved evidence, not the authority
  of arbitrary replacement ledgers. The packaged ledger preserves the original exact and historical records,
  retaining public Wikipedia page/revision/log IDs, uncertainty and entity-scope
  notes. Its SHA-256 is recorded below; no research dataset is required.

Current export is **not point-in-time history**. Known title events do not
establish continuous article availability, corporate identity or historical
NIFTY membership. James must explicitly decide how to use interval evidence
and approved aliases before historical aggregation. This adapter neither sums
redirects nor issues a date-qualified title selection.

## What remains with James

1. Review/install the India `universe()` hook while retaining US/HK behavior
   and deciding how strategy-universe extras interact with verified titles.
2. Review Hindi use and language aggregation: the existing loader sums languages,
   which is an analysis convention beyond title identity.
3. Handle historical intervals and approve any redirect aggregation. The existing
   `include_redirects` path discovers current redirects and does not enforce these
   ledger boundaries. Do not pass every historical title to it and sum blindly.
4. Enforce acquisition bounds before running collection. The reviewed pipeline
   builds both research and recent/holdout windows by default; this task has not
   made that execution safe for India historical research.
5. Keep the unavailable Solar Industries title out of the pipeline universe.
   Preserve the complete stock metadata row and omit the 33 missing Hindi titles.

## Standalone checkout and offline verification

The runtime package consists of exactly four files:

- `src/india_wikipedia_mapping.py`
- `config/india_wiki_titles.csv`
- `config/india_wiki_mapping_ledger.json`
- `docs/india_wikipedia_csv_adapter.md`

No proposal directory, activation manifest, historical dataset, credentials or
network access is needed to load it. The adapter uses the Python standard
library. From the checkout root, run:

```bash
python -B - <<'PYTHON'
from src.india_wikipedia_mapping import load_india_titles
mapping = load_india_titles()
current = mapping.current_titles()
assert len(mapping.records) == 178
assert len(current) == 88
assert sum('hi' in titles for titles in current.values()) == 67
assert len(mapping.current_titles(include_parent_proxies=True)) == 99
assert sum(row.kind == 'historical_move_observed' for row in mapping.records) == 12
print('Loaded 155 exact current, 9 parent proxy, 2 group proxy and 12 historical titles.')
PYTHON
```

Defaults are anchored to the module's repository directory, not the caller's
working directory. Explicit local CSV/ledger paths remain supported. Missing or
inconsistent evidence fails closed; unknown effective dates remain unknown.

The original project's 27 mapping/adapter/configuration tests additionally use
local audit fixtures and the full project configuration; those are not runtime
dependencies and are intentionally outside this small sharing branch. Existing
adapter regressions and focused packaging checks can also run against an export
of only these committed files, without the original project present.

### Evidence checksums

The ledger's complete 178 records retain only company/title identity, public
Wikipedia identifiers and URLs, observed title-event dates, query-completeness
qualifications and mapping notes. It contains no pageviews or historical article
text. The shared CSV and ledger must remain paired; do not edit dates or choose
current titles by row order.

- CSV SHA-256: `711096f50fb5308740bef872e850a3e6c6bc137ca732c0d55ff120aec502ab4f`
- Ledger SHA-256: `83c9d45702f82020db836387d950dfa4ba60bd59065f75452906c211c10137fc`

## All-constituent disposition review — 2026-11-23

[Coverage](../config/india_wiki_coverage.csv) records all 100 frozen official
constituent identities, including 12 explicit unresolved English and 33 Hindi
gaps. A bounded [identity metadata recheck](../config/india_wiki_identity_review.json)
queried only the unresolved English companies. Direct-title checks found missing
pages or redirects to parents/groups; successful searches did not establish
separate listed-company identities. TATACAP and VAML search requests returned
HTTP 429 and were not retried. These are unresolved mappings, not claims that
articles cannot exist. Parent/group pages are not substituted for listed entities.

All 88 English, 67 Hindi and 12 historical mappings remain unchanged. Unknown
valid_from dates stay blank. This current identity review provides no historical
pageview/text coverage or eligibility claim. James can inspect the complete
coverage file alongside the existing current_titles()/title_history() interface;
no pipeline hook or historical redirect aggregation is enabled here.

## Approved parent proxies — 2026-11-27

Prakhar's approval, as reported by the requester, applies to verified
parent-company articles for the unresolved English titles. The
[review record](../config/india_wiki_identity_review.json) records decisions for
all 12, issuer evidence, canonical page and Wikidata IDs, revisions and
pageview retrieval samples. Nine qualified. BAJAJHLDNG, SHRIRAMFIN and SOLARINDS
lacked a suitable controlling corporate parent article at this stage. The
follow-up below records their final dispositions.

Parent page views and edits measure broader corporate attention and do not
establish attention specific to the Indian-listed company. ENRIN and SIEMENS
share the Siemens page. HDFCAMC shares the HDFC Bank page with the exact
HDFCBANK entry. Treat each shared page as one underlying signal when
aggregating across stocks. The review validates current ownership and sample
retrieval only. Parent proxy dates stay blank and must not be interpreted as
historical eligibility. Recheck ENRIN on any announced change of control.

The adapter and `india_names(include_parent_proxies=True)` retain James's
existing dictionary structures. Read `TitleRecord.kind` or the coverage
registry for `parent_proxy` and `group_proxy` provenance, outside the pipeline's language/title
pairs and weekly output columns. James's current weekly schema carries no
proxy flag. Keep this provenance alongside proxy-enabled output and keep
historical or exact-identity runs on the default export. This PR does not
enable a pipeline hook or run collection.

## Group proxies and unavailable Wikipedia data

`BAJAJHLDNG` maps to Bajaj Group because Bajaj Holdings & Investment is the
group’s flagship holding company. `SHRIRAMFIN` maps to Shriram Group because
Shriram Finance is part of that conglomerate. The registry uses `group_proxy`
in the existing classification field to describe group affiliation.
Views and edits measure broader corporate attention across each group.
The [review record](../config/india_wiki_identity_review.json) contains
canonical URLs, legal company names, Wikidata IDs, issuer sources and
successful pageview and revision checks for both groups and all nine parents.

`SOLARINDS` has an explicit `WIKIPEDIA_UNAVAILABLE` coverage row with blank
titles. Its normal stock lookup continues to use the original company metadata.
Solar Defence and Aerospace Limited is its wholly owned subsidiary. James’s
Wikipedia universe omits the unavailable ticker and receives no empty language
dictionary. Keep the null titles in resolver metadata and resolve other
sources independently.
