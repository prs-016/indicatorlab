# India Wikipedia CSV adapter

The separate [adapter](../src/india_wikipedia_mapping.py) reads the active
[four-column CSV](../config/india_wiki_titles.csv) and its existing
[evidence ledger](../config/india_nifty100_wikipedia.proposed/mapping_ledger.json).
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
  of arbitrary replacement ledgers. Keep the source checksums from the
  [activation manifest](../config/india_wiki_titles.activation.json).

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
5. Resolve the 12 English/33 Hindi gaps and entity-scope limitations listed in the
   [activation review](../india_research/reports/india_wikipedia_mapping_activation.md).

## Offline verification

```bash
.venv/bin/python -B -m pytest tests/test_india_wikipedia_adapter.py tests/test_india_wikipedia_mapping.py tests/test_config.py -q -p no:cacheprovider
```

27 tests passed (13 adapter cases, 8 registry checks, 6 configuration checks).
Tests cover YAML-shape compatibility, multilingual export, retained history,
unknown boundaries, duplicates/conflicts, malformed data, evidence mismatch
and the real local registry. Network calls are denied. Ruff, Black and whitespace
checks pass. This verifies the adapter and representation; it is not a run of
James's complete pipeline. AGENTS.md and existing configuration remain unchanged.
