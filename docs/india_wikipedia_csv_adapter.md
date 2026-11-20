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
history = mapping.title_history()
# history['ADANIENSOL.NS']['en'] contains current and two former records
```

James can connect it at the **India branch of `universe()`**, returning
`load_india_titles().current_titles()` as the base universe when `market == 'IN'`.
Keep his existing YAML path for US/HK. This is the proposed connection point;
no such hook has been installed by this task. If `strategy=True` adds extra
India tickers, retain his existing option semantics but review collisions:
`out.update(...)` can replace verified titles. Do not silently override a
registry identity or fabricate titles for the 12 unresolved companies.

If he needs a YAML-shaped stock fragment instead, this local conversion yields
only the expected Wikipedia field (not a replacement for full stock settings):

```python
fragment = {
    ticker: {'wikipedia': dict(titles)}
    for ticker, titles in india_titles.items()
}
```

Do not replace the full 100-stock India configuration with this 88-stock
fragment or automatically add empty title dictionaries for unresolved companies.
His current pipeline cannot safely process an empty language dictionary.

## Historical titles and unknown dates

The required CSV cannot distinguish current/former titles or store `valid_to`.
The existing ledger is therefore required, rather than selecting a title based
on CSV order or the latest nonblank date. `load_india_titles(csv_path,
ledger_path)` accepts explicit local paths and returns immutable `TitleRecord`s:
`symbol`, `title`, `lang`, `kind`, `valid_from`, `valid_to`.

- `current_titles()` selects only ledger-labelled current rows, once per
  ticker/language. Former titles never replace current titles.
- `title_history()` returns **all** records, grouped by ticker/language, retaining
  all 12 historical rows. Unknown boundaries remain `None`; this is not an
  implicit interval extending to the start/end of history.
- Starts must match CSV/ledger evidence exactly; nonblank boundaries require
  recorded event identifiers and UTC timestamps. Duplicates (even identical),
  competing current titles and reversed intervals fail rather than choosing one.
- These checks validate consistency with the saved evidence, not the authority
  of arbitrary replacement ledgers. The packaged ledger is a byte-for-byte copy of the verified mapping evidence,
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
5. Resolve the 12 English/33 Hindi gaps and entity-scope limitations identified by the mapping research. These companies remain absent rather
   than receiving fabricated titles; missing Hindi titles are simply omitted.

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
assert len(mapping.records) == 167
assert len(current) == 88
assert sum('hi' in titles for titles in current.values()) == 67
assert sum(row.kind != 'current' for row in mapping.records) == 12
print('Loaded 88 companies, 155 current titles and 12 historical titles.')
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

The ledger's complete 167 records retain only company/title identity, public
Wikipedia identifiers and URLs, observed title-event dates, query-completeness
qualifications and mapping notes. It contains no pageviews or historical article
text. The shared CSV and ledger must remain paired; do not edit dates or choose
current titles by row order.

- CSV SHA-256: `0de6ae1e3a069dc9113cb9c8dc41e7c18e43f59c7f8257c141c24c1ac69edaf0`
- Ledger SHA-256: `f4f91451ff8192f3ad67270c6f99893c64a4dc94e33d83a7d1f8d98a0df2a16f`
