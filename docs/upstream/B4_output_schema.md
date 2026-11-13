# B4 output schema (proposal for Mon Nov 16, 2026)

For Jamal and Jack. B4 is the parallel runner; B5 (your comparison report) reads what it writes. Please check this before I build on it. Status: draft, nothing here is merged upstream.

```
vibe-trading alpha bench --universe sp500,nifty100,hsi --zoo alpha101 --period 2020-2025 --out-dir runs/demo
```

A run with two or more universes writes one folder:

```
<out_dir>/index.json        one per run, read this first
<out_dir>/<universe>.json   one per universe, e.g. sp500.json
<out_dir>/<universe>.log    that worker's console output, for debugging
```

A run with a single universe is unchanged from today: the envelope is printed to stdout and no folder is written.

## 1. `<universe>.json`

Exactly the JSON that `alpha bench --universe <one>` prints to stdout today (`cmd_alpha_bench` in `agent/src/factors/cli_handlers.py`). No keys added, renamed or removed.

| Key | Type | Present |
|---|---|---|
| `status` | `"ok"` or `"error"` | always |
| `zoo`, `universe`, `period` | string (`zoo` is null when every zoo is benched) | always |
| `error` | string | only when `status` is `"error"`; then the four keys above are the whole file |
| `n_alphas_tested`, `n_skipped` | int | ok |
| `top` | list of rows, best `ir` first, cut to `--top` (default 20) | ok |
| `wall_seconds` | float, bench loop only | ok |
| `horizon`, `forward_return_sampling` | int, `"daily"` or `"non_overlapping"` | ok |
| `universe_excluded` | list of alpha ids | only when some alphas cannot run on this universe |
| `meta` | object: loader facts (`survivorship_bias`, `constituent_source`, ...) plus `data_availability` and `research` | ok |
| `report_path` | string, the HTML report | ok, when the report was written |
| `strict`, `confirmed_alive`, `train_only`, `reversed_strict`, `noise`, `oos_split`, `training_cutoff` | bool, ints, dates | only with `--strict` |

Each row in `top`: `id`, `zoo`, `theme` (list), `formula_latex`, `ic_mean`, `ic_std`, `ir`, `ic_positive_ratio`, `ic_count`, `category` (`alive`, `reversed` or `dead`). With `--strict` a row also has `alpha_t_full`, `alpha_t_train`, `alpha_t_test`, `random_ic_mean`.

```json
{
  "status": "ok",
  "zoo": "alpha101",
  "universe": "sp500",
  "period": "2020-2025",
  "n_alphas_tested": 98,
  "n_skipped": 3,
  "top": [
    {"id": "alpha101_012", "zoo": "alpha101", "theme": ["reversal"], "formula_latex": "...",
     "ic_mean": 0.0312, "ic_std": 0.1104, "ir": 0.2826, "ic_positive_ratio": 0.6012,
     "ic_count": 1507, "category": "alive"}
  ],
  "wall_seconds": 201.3,
  "horizon": 1,
  "forward_return_sampling": "daily",
  "meta": {"universe": "sp500", "survivorship_bias": true, "data_availability": {}, "research": {}},
  "report_path": "/Users/me/.vibe-trading/reports/alpha_bench_sp500_20261116T180321Z.html"
}
```

## 2. `index.json`

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | int | `1`; goes up if a key changes meaning |
| `zoo`, `period` | string | the same for every universe in the run |
| `started_utc`, `finished_utc` | string | ISO 8601, UTC, e.g. `2026-11-16T18:00:02Z` |
| `wall_seconds` | float | whole run |
| `concurrency` | object | `max_parallel` (universes running at once), `bench_workers` (per-alpha workers each universe was allowed) |
| `universes` | object | one entry per universe, in the order given on the command line |

Each entry in `universes`:

| Key | Type | Meaning |
|---|---|---|
| `path` | string or null | the `<universe>.json` file, relative to the folder holding `index.json`; null when the worker died before writing one |
| `status` | `"ok"` or `"error"` | |
| `error` | null or string | the message when `status` is `"error"` |
| `wall_seconds` | float | this universe's worker from start to exit (longer than the envelope's own `wall_seconds`, which leaves out data loading) |
| `n_alphas_tested` | int or null | null when `status` is `"error"` |
| `log_path` | string | the `<universe>.log` file, relative like `path` |

```json
{
  "schema_version": 1,
  "zoo": "alpha101",
  "period": "2020-2025",
  "started_utc": "2026-11-16T18:00:02Z",
  "finished_utc": "2026-11-16T18:07:43Z",
  "wall_seconds": 461.2,
  "concurrency": {"max_parallel": 3, "bench_workers": 2},
  "universes": {
    "sp500":    {"path": "sp500.json", "status": "ok", "error": null,
                 "wall_seconds": 214.8, "n_alphas_tested": 98, "log_path": "sp500.log"},
    "nifty100": {"path": "nifty100.json", "status": "ok", "error": null,
                 "wall_seconds": 380.1, "n_alphas_tested": 95, "log_path": "nifty100.log"},
    "hsi":      {"path": "hsi.json", "status": "error",
                 "error": "universe load failed: universe 'hsi' produced empty panel for 2020-01-01..2025-12-31; check network / token / date range",
                 "wall_seconds": 41.6, "n_alphas_tested": null, "log_path": "hsi.log"}
  }
}
```

Rules for B5: read `index.json`; for each universe open `path` only when `status` is `"ok"`; show `error` otherwise. One market failing never stops the others. The command exits 0 only when every universe is ok, and writes `index.json` either way.

## 3. Open questions for Jamal and Jack

1. **Local currency vs USD (B3).** Where do the two sets of metrics sit? My suggestion: extra keys on each `top` row with a suffix, for example `ic_mean_usd`, `ir_usd`, and the unsuffixed keys stay local currency, so sp500 files do not change. The other option is a second file per universe (`hsi.usd.json`).
2. **Long-short Sharpe.** B5 needs it, but today's rows only carry IC numbers (`ic_mean`, `ic_std`, `ir`, `ic_positive_ratio`, `ic_count`). Which piece adds it, and under what key (`ls_sharpe`, `ls_sharpe_usd`)?
3. **`--top` cuts the rows.** The file holds only the best `--top` alphas by `ir` (default 20), and a different 20 in each market. For a per-factor comparison B5 has to run with `--top` at least the zoo size (for example `--top 1000`). Is that fine, or should B4 always write every row?
4. **Default `out_dir`.** Proposed: `~/.vibe-trading/reports/alpha_bench_<UTC timestamp>/` (same root as the HTML reports), with `--out-dir` to choose. Does B5 take the `index.json` path as its argument?
5. **Shape of `universes`.** An object keyed by universe name (above) or a list of entries with a `universe` key? And are relative paths fine, so a run folder can be zipped and shared?
6. **Universe names.** B4 validates names against `_UNIVERSE_CHOICES`. I am assuming the exact spellings `nifty100` (B1) and `hsi` (B2); tell me if yours differ.
7. **Exit code.** Non-zero when any universe fails. If B5 is run in the same script as B4, is that what you want, or should partial success exit 0?
