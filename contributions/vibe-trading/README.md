# Vibe Trading contribution on Jack

This folder makes Jack's reviewed Vibe Trading changes visible on the
IndicatorLab **Jack** branch. It is the submission/review package, containing
code patches, tests, metadata, license and the actual benchmark summary.
The full application is maintained at https://github.com/HKUDS/Vibe-Trading;
there is no need to paste that whole application into IndicatorLab again.

## Files to review

| File | Contents |
|---|---|
| [01_hsi_universe.patch](01_hsi_universe.patch) | HSI benchmark loader, roster/fallback, symbol normalization, metadata, API/CLI wiring and tests |
| [02_hk_quotes.patch](02_hk_quotes.patch) | HK quote fetching/SQLite collector, agent/MCP integration and tests; depends on 01 |
| [APPLY_ALL.patch](APPLY_ALL.patch) | Both features together, as an alternative to applying 01 then 02 |
| [MANIFEST.json](MANIFEST.json) | Upstream base commit, 21 destination paths and file hashes |
| [BENCH_SUMMARY.md](BENCH_SUMMARY.md) | Completed bounded HSI Alpha101 benchmark and its limitations |
| [LICENSE](LICENSE) | Upstream MIT license |

All new and changed code is inside the patches. Inspection-only duplicates of
new files and ZIP files are omitted from this view. Both patch application
routes were verified against upstream base
`67ce0ca5c9b2a3e3d321217eff043dad913a27fa` and reproduced all 21 destination files.

## Where the data is

The contribution supplies the **code that retrieves and stores HK stock data**.
Once applied to a compatible Vibe Trading checkout, its operator can run this
from `agent/` as one command:

```bash
python -m src.hk_data --hsi-snapshot --source tencent --interval-seconds 5 --db ./data/hk_quotes.sqlite3
```

The collector updates a local SQLite archive while running. The agent/MCP tool
`get_hk_quotes` can fetch current snapshots. The HSI snapshot contains 95 stocks
and is dated 2026-11-04; membership needs maintenance. Observed last-trade age
is reported, with no guaranteed sub-minute feed for every stock.

The existing local dataset on Jack's Mac is separate:

- New operational quotes: `../indicatorlab-clean/data/live_hk/current/latest.json`
  and `daily/YYYY-MM-DD/observations.jsonl`, relative to the IndicatorLab root.
- Historical stock files: `research/hk_market_history/prices/` and the HSI
  benchmark under that research folder's `benchmark/`.
- Publishable reports: [results/hk/week3](../../results/hk/week3/FIVE_STRATEGY_REPORT.md).

The generated databases, price archives and local model are ignored by Git.
Publishing a static CSV would not create ongoing collection. The receiving
operator must run the collector or deploy a service. No shared cloud service
is created just by committing these files.

## Applying the contribution to Vibe Trading

In a compatible Vibe Trading checkout, apply **either** `APPLY_ALL.patch`
**or** `01_hsi_universe.patch` followed by `02_hk_quotes.patch`.
Use `git apply --check PATH/FILE.patch` before `git apply PATH/FILE.patch`.
Do not apply the combined patch after the two split patches.

This package being visible on IndicatorLab's Jack branch does not merge it into
HKUDS/Vibe-Trading. Upstream acceptance still requires the separate fork/PR,
actual DCO/co-author identities, review and CI described in the task guide.
