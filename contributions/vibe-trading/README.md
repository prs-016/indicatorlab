# HK branch: Vibe Trading contribution for mentor review

This is the complete **code-change package** for the HK Vibe Trading
contribution. It lives in the existing IndicatorLab repository on branch
**HK**. This checkout now contains only the contribution package and its
short navigation/review documents; inherited starter/team files were removed
from this submission branch.

## What to review

| File | Contents |
|---|---|
| [01_hsi_universe.patch](01_hsi_universe.patch) | HSI Alpha Zoo universe, roster and fallback, aliases, metadata, sector/VWAP handling, API/CLI wiring and tests |
| [02_hk_quotes.patch](02_hk_quotes.patch) | HK quote service, agent/MCP tool, optional SQLite collector and tests; depends on 01 |
| [APPLY_ALL.patch](APPLY_ALL.patch) | Both scopes combined, as an alternative to applying 01 then 02 |
| [MANIFEST.json](MANIFEST.json) | Base upstream commit, all 21 destination paths, source hashes and validation scope |
| [BENCH_SUMMARY.md](BENCH_SUMMARY.md) | Actual bounded HSI Alpha101 benchmark and limitations |
| [LICENSE](LICENSE) | Upstream MIT license |

Every added and modified source/test/documentation file is included inside
the patches. No extra ZIP, full app copy, database, price archive, model file
or inspection-only duplicate is needed for applying them.

## Apply to a Vibe Trading checkout

These patches target HKUDS/Vibe-Trading base commit
`67ce0ca5c9b2a3e3d321217eff043dad913a27fa`. They apply to a compatible **Vibe
Trading checkout**, not to this IndicatorLab repository.

Apply either `APPLY_ALL.patch`, or `01_hsi_universe.patch` followed by
`02_hk_quotes.patch`. Do not apply the combined patch after the split patches.
For example, inside a clean compatible Vibe Trading checkout:

```bash
git apply --check /path/to/contributions/vibe-trading/APPLY_ALL.patch
git apply /path/to/contributions/vibe-trading/APPLY_ALL.patch
```

Both routes were independently applied to clean base files and reproduced all
21 expected destination hashes. On a newer upstream base, review any rejected
hunks and rerun the relevant tests; do not replace the entire MCP server with
a file from another checkout.

## How the HK data reaches Vibe Trading

The contribution implements retrieval of HK stock prices. Once installed in
Vibe Trading, the read-only `get_hk_quotes` agent/MCP tool fetches snapshots.
For an ongoing local archive, run this from the Vibe Trading `agent/` folder:

```bash
python -m src.hk_data --hsi-snapshot --source tencent --interval-seconds 5 --db ./data/hk_quotes.sqlite3
```

That command retrieves new observations while the process runs and stores
them at the requested database path. The HSI snapshot contains 95 stocks and
is dated 2026-11-04; it needs maintenance after index reviews. The tool exposes
provider/receipt timestamps and freshness. The archive CLI does not install
a scheduler or create a shared cloud service. A measured median last-trade
age of 10.63 seconds is not a guarantee of sub-minute freshness for every stock.

Generated price databases and historical datasets are not embedded in these
patches. Contributing the retrieval code lets the receiving installation get
future data; publishing a static price file alone does not provide that service.

## Validation and scope

The source checkout passed 91 focused HSI/quote tests and an earlier selected
1,085-test integration/purity/look-ahead suite (23 skipped, one existing
Python 3.14/Pydantic compatibility warning). This is not the entire upstream
suite or remote CI. See the manifest and benchmark note for data-vintage,
survivorship, provider and adjustment-basis limitations.

Committing/pushing this IndicatorLab HK branch submits the review package to
the mentor. An actual HKUDS/Vibe-Trading merge still requires the separate
upstream PR, real author/co-author and DCO information, review and passing CI.
