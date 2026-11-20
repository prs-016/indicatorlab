# Code Review — indicatorlab, Wikipedia Week 4 (branch `wikipedia`, before push)
Reviewed: 2026-11-19
Files reviewed: 21
- 7 in `src/`: `wiki_complex.py`, `wiki_pipeline.py`, `wiki_sentiment.py`, `wiki_export.py`,
  `wiki_strategy.py`, `wiki_sp500.py`, `api/dashboard.py`. `api/main.py` was also read for one finding.
- 6 in `tests/`: `test_wiki_complex.py`, `test_wiki_pipeline.py`, `test_wiki_sentiment.py`,
  `test_wiki_sp500.py`, `test_api_dashboard.py`, `test_config.py`.
- 8 more: `frontend/dashboard/index.html`, `config.yaml` (the `wikipedia:` block),
  `config/us_sp500_wiki_titles.csv`, `.env.example`, `docs/AGENTS.md`, `README.md`,
  `docs/wikipedia/week4_strategies.md`, `docs/wikipedia/week4_report.md`.
- Out of scope: Reddit (Joshua) and India (Jamal) files.

The previous review (2026-11-11, Week 3) is in this file's git history.

## Summary
The Week 4 changes are in good shape:
- ruff is clean on every in-scope file;
- the 113 in-scope tests pass;
- the new logic has offline tests: S5–S7, the cutoff-named caches, the seeded diff cache, and the
  Vibe deflated Sharpe, which is checked against the published formula;
- no secrets or hardcoded absolute paths.

The one functional bug to fix first: in the real app, **`GET /spikes` is served by the Week 2 Reddit
router**, so dashboard page 3 never reaches its own handler.

After that:
- the Vibe-Trading export still writes the Week 3 run format, not the one the Week 4 guide asks for;
- the S1–S3 thresholds are inline literals, while S4–S7 use named constants.

The branch follows DS3 conventions: logic in `src/`, tests in `tests/`, data and results gitignored.

## Repo Structure
| Expected | Present? | Notes |
|---|---|---|
| `README.md`, `.env.example`, `.gitignore`, `requirements.txt` | yes | `.env.example` documents `VIBE_TRADING_ROOT` without a value |
| `src/` with `__init__.py` | yes | |
| `tests/` | yes | Network is mocked; the Vibe tests skip without a checkout |
| `notebooks/` | yes | Not touched this week |
| `data/raw`, `data/processed`, `results/` | yes (gitignored) | Pre-cutoff copies are in `pre_cutoff_20251001/` folders, also ignored |
| `config/` | yes (new) | Holds only the 60 KB S&P 500 title map, in line with the "titles in config" rule |
| `frontend/` | yes | |
| `infra/` | partial | Only `README.md`: the API and Wikipedia pipeline deployment files don't exist yet |

The untracked files that must stay out of the commit are `.claude/` and the three task PDFs. Neither
is in `.gitignore`, so a careless `git add .` would include them.

## Test Coverage
`pytest --cov` over the in-scope modules gives **113 passed**, and line coverage of:

| Module | Coverage |
|---|---|
| `api/dashboard.py` | 93% |
| `wiki_strategy.py` | 82% |
| `wiki_pipeline.py` | 75% |
| `wiki_sentiment.py` | 68% |
| `wiki_complex.py` | 66% |
| `wiki_export.py` | 59% |
| `wiki_sp500.py` | 59% |
| **Total** | **73%** |

**Covered:**
- S1–S7 entry and exit rules, on synthetic markets;
- the market sentiment shock (10-stock minimum);
- S6 ignoring a legal/layoff tag from a later week;
- S7's 0.25 exposure floor and its 4-week stock block;
- sentiment change from earlier weeks only;
- random-entry determinism;
- the deflated Sharpe against the hand formula;
- cutoff-named caches that leave the old caches alone;
- the API cutoff guard.

**Not covered:** the I/O orchestration (`build_market`, `run`, the `--vibe` path), `export_vibe`,
`wiki_export`'s parquet writers and `wiki_sp500`'s network fetchers. Most of that is plumbing. But
`export_vibe` produces the candidate's Vibe confirmation, so it's worth a test (see Findings).

`notebooks/wikipedia.ipynb` still asserts its data coverage at the top. It wasn't rerun for this review.

## Findings

### `src/api/main.py` (lines 21-23)
**Issue:** Bug Risk
**Severity:** Must fix

```python
app.include_router(reddit.router)
app.include_router(wikipedia.router)
app.include_router(dashboard.router)
```

`reddit.router` and `dashboard.router` both declare `GET /spikes` at the root. FastAPI keeps the first
match, so the app's OpenAPI lists `/spikes` once, as the Reddit route. The dashboard's page 3 calls
`/spikes?week=&market=` and gets the Week 2 Reddit handler. `tests/test_api_dashboard.py` misses it
because it builds an app with only the dashboard router. Joshua's PR #4, now merged into `main`,
provides the `/reddit/*` router. Merge `main`, mount Reddit under `/reddit`, and add a test that runs
`/spikes` through `src.api.main.app`.

### `src/wiki_complex.py` (lines 721-740)
**Issue:** Bad Practice / No Test Coverage
**Severity:** Should fix

```python
w.round(6).to_csv(run_dir / "code" / "weights.csv")
cfg = {"codes": list(w.columns), ...,
       "source": "yfinance", "interval": "1D", "engine": "daily", "position_adjustment": "hold",
```

The Week 4 guide's Vibe run format asks for:
- `position_adjustment: "rebalance"`;
- a `benchmark`;
- target weights embedded in `signal_engine.py` as a CSV string, with no file reads.

This export uses `"hold"` (no resizes), has no benchmark, and reads `code/weights.csv`. The S7
confirmation (Sharpe within 0.03) was run in that older format. Update the export to the guide's format
and add a test that checks the written `config.json` and engine. Then rerun the S7 check before
nominating it.

### `src/wiki_complex.py` (lines 244-307)
**Issue:** Magic Number
**Severity:** Should fix

```python
return set(m.mom.loc[fri, names].nlargest(10).index)
ok &= av.rank(pct=True) >= 0.7
ok &= m.wk("revert_share", week).fillna(0) <= 0.5
return set(m.abn_ret.loc[week, names].dropna().nsmallest(5).index)
ok &= m.vol_ratio.loc[week].reindex(m.tickers) >= 1.5
```

S1–S3 keep their thresholds as inline literals: top 10, 70th percentile, 50% revert share, 5 losers,
1.5× volume. S4–S7 use named class constants (`VIEWS_MIN`, `ATT_PCT`, `TOP`, `CROWD_RATIO`...). The
values are pre-registered, so they must not change. But naming them, with a pointer to
`week3_strategies.md`, makes a reader check them against the rules instead of guessing.
`AttentionReversal.signal` repeats the 0.7 on line 277, so the two copies could drift apart.

### `src/wiki_complex.py` (lines 520-526, 644)
**Issue:** Missing Docstring
**Severity:** Should fix

```python
def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 1 and r.std() > 0 else np.nan

def cut(s: pd.Series, period: tuple) -> pd.Series:
```

These three public functions have no docstring:
- `sharpe`: annualised with 252 days, NaN for fewer than 2 points or zero spread;
- `cut`: inclusive on both ends;
- `build_market`: which files it reads, and that prices stop at `holdout_start`.

The seven strategy classes (lines 215-424) also lack class docstrings. Their `name` attribute helps,
but a one-line pointer to the rules file and section would match the project convention.

### `src/wiki_strategy.py` (lines 169-170)
**Issue:** Bad Practice (duplication)
**Severity:** Nit

```python
def cut(s: pd.Series, lo=lo, hi=hi) -> pd.Series:
    return s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
```

This is the same inclusive date filter as `wiki_complex.cut`, redefined in a loop. One shared helper
keeps the two strategy harnesses from disagreeing on period edges.

### `src/wiki_sentiment.py` (line 253)
**Issue:** Bad Practice (print in library code)
**Severity:** Nit

```python
frames.append(week_sentences(tk, r, weeks[weeks >= starts[key]], cache, lang, seed))
print(tk, title, len(frames[-1]), "rows", flush=True)
```

`build()` is called by other modules as well as the CLI, so this progress line prints on every import
path. Use `logging`, as `wiki_pipeline` does. The other `print` calls are in `__main__` blocks and are
fine.

### `src/wiki_complex.py` (lines 39-56)
**Issue:** Bug Risk (environment dependency)
**Severity:** Nit

```python
root = os.environ.get("VIBE_TRADING_ROOT")
if not root:
    raise RuntimeError("set VIBE_TRADING_ROOT in .env to a Vibe-Trading checkout (see .env.example)")
```

The guide requires Vibe's own `deflated_sharpe_ratio`, so depending on a checkout is correct, and the
error is clear. But on a fresh clone without the variable, the two deflated Sharpe tests *skip*
silently and `python -m src.wiki_complex` stops at the end of the run. The skip reason shows only with
`pytest -rs`. Say in the PR description that these tests need `VIBE_TRADING_ROOT`.

### `docs/AGENTS.md` (line "Status")
**Issue:** Style (stale doc)
**Severity:** Nit

```markdown
**Status:** active development (Week 2)
```

It's Week 4. The rest of the file was updated this week: the run commands, `VIBE_TRADING_ROOT` and
the cutoff.

### `src/api/dashboard.py` (lines 63-125)
**Issue:** Missing Docstring
**Severity:** Nit

```python
class SentimentWeek(BaseModel):
```

The response models (`SentimentWeek`, `Spike`, `PriceWeek`, `EditSummary`, `HotRow`, `Quote`,
`LiveMarket`) have no docstrings, so `/docs` shows no schema descriptions. A one-line docstring each
would document the API for the dashboard and for Joshua's routes.

## Checklist for the student
- [x] Mount Joshua's Reddit router under `/reddit` (merge `main`, which has PR #4) so `/spikes` reaches
      the dashboard handler; add a test through `src.api.main.app`. (Done by the merge `f7ad23c`.)
- [x] Update `export_vibe` to the Week 4 Vibe format (`rebalance`, `benchmark`, weights embedded as a
      CSV string), add a test for it, and rerun the S7 Vibe confirmation. (Done in `5f2b6d4`.)
- [ ] Name the S1–S3 thresholds as constants (values unchanged), including the duplicated 0.7.
- [ ] Add docstrings to `sharpe`, `cut`, `build_market` and one-liners to the strategy classes.

## Follow-up review, 2026-11-19: AWS pieces
Files: `src/wiki_daily.py` (new), `src/api/dashboard.py` (`/runs` key from SSM), `tests/test_wiki_daily.py`
(new, 6 tests), `tests/test_api_dashboard.py` (+1), `infra/api/` and `infra/wikipedia/` (Dockerfiles),
`requirements-api.txt`, `config.yaml` (`wikipedia.title_maps`, `api.vibe_key_param`),
`config/hk_wiki_titles.csv` (Jack's, copied from `origin/Jack` unchanged), `infra/README.md`, `docs/AGENTS.md`.

- ruff is clean on the changed Python files. The full suite: 568 passed, 0 failed.
- A real run against Wikimedia (written to a scratch folder, not S3) pulled 146 stocks (51 US, 95 HK) in
  about 4 minutes with no failures and no 429s.
- **Fixed during review:**
  - Pulling every redirect took over 10 minutes (Apple_Inc. has 103), so the job reads each article's own
    title.
  - The "published" check accepted a half-filled day (66 of 146 stocks had Nov 19 views at 03:40 UTC). It
    now needs the day's market total to be at least half its 7-day median (`PUBLISHED_MIN_SHARE`).
  - A blind `except Exception` was narrowed (ruff BLE001).
- **Not verified here:** the two Docker images were not built, since Docker Desktop wasn't running. Their
  dependencies were checked by importing both entry points in a clean Python 3.12 venv with only
  `requirements-api.txt`.
- **Known limit (documented in the module):** without redirects, an article renamed inside the 36-week
  window shows low views before the rename.

- [ ] Build both images and test-invoke the Lambdas (infra/README.md steps 3–8).
