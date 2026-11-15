# HK contribution package v2

This is the contribution-only mentor handoff on branch **HK**. The full Vibe
Trading app, raw datasets, generated database/model and unrelated templates are
kept outside this checkout.

**Start with [ALIGNMENT_REVIEW.md](ALIGNMENT_REVIEW.md)** for the five teammate
questions, confirmed data limitations, read-only India inspection, shared contract
proposal and a suggested reply. No team message was sent.

| File | Purpose |
|---|---|
| [01_hsi_universe.patch](01_hsi_universe.patch) | Standalone HSI universe, symbol/provenance reconciliation, availability identity and tests |
| [02_hk_quotes.patch](02_hk_quotes.patch) | Live quotes, MCP and optional SQLite archive; stacked on 01 |
| [APPLY_ALL.patch](APPLY_ALL.patch) | Both scopes as an alternative to 01 then 02 |
| [MANIFEST.json](MANIFEST.json) | Versioned base, 25 target-file hashes, checks and compatibility boundaries |
| [BENCH_SUMMARY.md](BENCH_SUMMARY.md) | Preserved older 85-name exploratory benchmark; no v2 performance rerun |
| [LICENSE](LICENSE) | Upstream MIT license |

## Apply

Base: `19c83de9c4f53ff1609e266c3102badd0d034876`. Apply inside a clean compatible **Vibe Trading**
checkout, not this IndicatorLab handoff repository:

```bash
git apply --check /path/to/contributions/vibe-trading/APPLY_ALL.patch
git apply /path/to/contributions/vibe-trading/APPLY_ALL.patch
```

Alternatively apply 01 then 02; do not also apply the combined patch. Both routes
were reconstructed from the pinned base and byte-matched all 25 targets. The
HSI-only patch passed 51 checks without the quote package. Publish the universe
PR separately; the quote PR depends on it through the roster helper.

## Data and validation

Wikipedia remains primary per assignment, compared against a dated official
95-name reference. It currently has 85 names and is flagged degraded. This does
not silently change membership or certify either source as indefinitely current.
Prices/volume are provider-native with explicit adjustment/unit warnings; no new
universal corporate-action, volume or PIT normalization is claimed.

After installation, run from Vibe Trading's `agent/` directory:

```bash
python -m src.hk_data --hsi-snapshot --source tencent --interval-seconds 5 --db ./data/hk_quotes.sqlite3
```

The operator must keep collection running. This does not create a shared cloud
service or guarantee sub-minute freshness. The 95-name operational snapshot is
dated 2026-11-04 and needs maintenance after reviews.

Version 2 passed 141 focused checks plus 1,078 broader bench/purity/look-ahead
checks (23 skipped; existing Python compatibility warning). Scoped Ruff/Black and
patch reconstruction passed. Full upstream suite, remote CI and actual NIFTY
joint compatibility were not established. The supplied India research branch was
read-only and unchanged; its actual standalone NIFTY code is still needed.

Committing this HK review branch does not itself merge changes into HKUDS/Vibe-
Trading. Upstream acceptance still needs the actual fork/PR, real DCO/coauthor
identities, review and CI. No commit, push, deployment or strategy rerun was done
by this coordination update.
