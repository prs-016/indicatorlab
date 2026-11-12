# Code Review — indicatorlab, Wikipedia + Week 3 API (branch `wikipedia`, after merging `main`)
Reviewed: 2026-11-11
Files reviewed: 41
- 17 in `src/`: `wiki_*.py`, `sentiment/`, `trends_compare.py`, and `api/` except `reddit.py`.
- 18 in `tests/`: the Wikipedia, API and FinBERT tests, plus the 6 files in `tests/fixtures/api/`.
- `notebooks/wikipedia.ipynb`.
- 5 docs and config: `docs/AGENTS.md`, `docs/wikipedia/`, the Wikipedia section of `README.md`, and the
  `wikipedia:` and `api:` blocks of `config.yaml`.

Reddit (`src/reddit/`, `src/api/reddit.py`) and India files came from `main` and were not reviewed.
Jamal's India review stays in `code_review.md`.

## Summary
The Wikipedia work is in good shape. Logic lives in `src/` and the notebook imports it, every config
value lives in `config.yaml`, all 83 in-scope tests pass, and `ruff` is clean on these files. Coverage of
the in-scope modules is about 82%.

The new Week 3 code has three issues to fix before deploying:
1. The FinBERT cache records the wrong model version on a machine that hasn't downloaded the model yet,
   so the second run rescores everything.
2. `/hot` (and `/live`) will return HTTP 500 on AWS until the DynamoDB live tables exist.
3. `AttentionRecord.spike` is a required `bool`, so one missing spike flag in Joshua's Reddit table
   fails the whole `/attention` response.

Structure follows the DS3 template. `infra/` has only a README so far, and the API has no deploy files
yet; that is expected at this stage but blocks "API deployed".

## Repo Structure
| Expected | Present? | Notes |
|---|---|---|
| `README.md` | yes | Explains the Wikipedia pipeline, the commands and the API. The merge doubled the intro; now fixed (uncommitted). |
| `.env.example` | yes | Variable names only: `WIKIMEDIA_CONTACT`, `INDICATORLAB_DATA`, `VIBE_API_URL/KEY`, and so on. No values. |
| `.gitignore` | yes | Ignores `data/*` and `results/*`. No `.env` or data is committed. |
| `requirements.txt` | yes | Lists `pyarrow` and `boto3` for the new code. `huggingface_hub` and `botocore` come in through `transformers` and `boto3`. |
| `notebooks/` | yes | `wikipedia.ipynb` imports from `src/` and asserts coverage at the top. |
| `src/` + `__init__.py` | yes | `src/sentiment/__init__.py` added. |
| `tests/` | yes | Fixture tables in `tests/fixtures/api/`, small (<10 KB each), with `make_fixtures.py` to rebuild them. |
| `data/raw`, `data/processed` | yes (git-ignored) | |
| `results/` | yes (git-ignored) | |
| `models/` | yes (empty) | FinBERT comes from the Hugging Face cache, which is fine. |
| `frontend/` | partial | Joshua's Reddit pages only; dashboard v1 is not started. |
| `infra/` | partial | README only. The API, the scheduled Wikipedia pull and App Runner have no SAM/CDK or Dockerfile yet. |

There are no secrets in source. `_vibe` reads `VIBE_API_KEY` from the environment, and
`tests/test_api_dashboard.py` checks that the key never appears in a response.

## Test Coverage
- Ran `pytest --cov=src` on the in-scope tests: 83 passed. In-scope modules: 1,306 statements, 236
  missed, about 82%.
- High (≥ 90%): `wiki_prices` (100%), `wiki_attention` (99%), `dashboard` (94%), `wiki_analysis`
  (92%), `api/wikipedia.py` (91%), `wiki_titles` (90%).
- Lowest:
  - `api/storage.py` 56%: every S3 and DynamoDB branch is untested.
  - `wiki_export.py` 60%: `build()` is untested.
  - `wiki_sentiment.py` 68%: `build()` and `analyse()` are untested.
  - `sentiment/finbert_scorer.py` 69%: model loading and `revision()` are untested. Mocking the model is
    the right call; `revision()` is not, see Findings.
  - `wiki_pipeline.py` 74%: `build()` and `load_prices()` are untested.
- The `build()`/`run()` functions are I/O orchestration over already-tested pieces, so they are lower
  priority. The S3/DynamoDB branches of `storage.py` are what will run in production, and nothing
  exercises them.
- The notebook has explicit assertions (coverage, holdout split) and ran top to bottom with no errors.

## Findings

### `src/sentiment/finbert_scorer.py` (lines 49-53, 90)
**Issue:** Bug Risk
**Severity:** Should fix

```python
    path = try_to_load_from_cache(model, "config.json")
    return Path(path).parent.name if isinstance(path, str) else "local"
...
    rev = f"{model}@{revision(model)}"   # no model load when everything is cached
```

`revision()` runs before `probabilities()` downloads the model. On a fresh machine (a teammate, a
container, App Runner) it returns `"local"`, and every score is cached as `ProsusAI/finbert@local`. On
the next run the snapshot hash exists, the cache key no longer matches, and the whole corpus is rescored.
The docstring's "'local' for a model folder" also doesn't describe this case. Resolve the revision after
the model is available, or whenever new texts need scoring, and add a test where the first call has no
cached snapshot.

### `src/api/storage.py` (lines 85-97) and `src/api/dashboard.py` (line 279)
**Issue:** Bug Risk
**Severity:** Should fix

```python
    change = {q["symbol"]: q.get("change_pct") for m in ("india", "hk") for q in storage.live(m)}
```

In S3 mode, `live()` scans DynamoDB. `/hot` always scans both live tables, so until Jamal's and Jack's
tables exist (or if one is deleted or renamed), `ResourceNotFoundException` turns `/hot` into HTTP 500.
`/hot` is a "Done when" endpoint and is supposed to work before the live feeds do. A missing live table
should give no price change, not an error. A test with a mocked boto3 table that raises would catch it.

### `src/api/dashboard.py` (lines 41-56, 186-194)
**Issue:** Bug Risk
**Severity:** Should fix

```python
class AttentionRecord(BaseModel):
    ...
    spike: bool
```

`_rows` turns NaN into `None`. A single `None` spike in a table that has gaps fails response validation,
and the whole `/attention` call returns 500. That would happen with Reddit weeks before a full baseline,
since Joshua's table schema isn't confirmed. Normalise `spike` to a bool when reading the weekly tables,
as `/spikes` already does on line 231, or make the field tolerant. Add a fixture row with a missing spike.

### `src/api/storage.py` (whole file)
**Issue:** No Test Coverage
**Severity:** Should fix

```python
    def _bucket_key(self, key: str) -> tuple[str, str]:
        bucket, _, prefix = self.root[len("s3://"):].partition("/")
        return bucket, f"{prefix.rstrip('/')}/{key}".lstrip("/")
```

Every S3 and DynamoDB path is untested: bucket/prefix splitting, listing keys under a prefix, a missing
object giving an empty table, DynamoDB pagination, and the `Decimal` to `float` conversion. These are the
code paths the deployed API will take. Mock the boto3 client and resource (or use `moto`), so a wrong
prefix or a `Decimal` leaking into JSON is caught before the deploy, not after.

### `src/api/storage.py` (line 87) and `src/api/dashboard.py` (line 279)
**Issue:** Bad Practice
**Severity:** Nit

```python
        if self.is_s3:
            import boto3
            name = config.load()["api"]["live_tables"][market]
```

Where live quotes come from is tied to where the tables are. With S3 tables you always get DynamoDB, and
locally you always get JSON. That stops you pointing the local API at real live tables to debug. Also,
`/hot` does two full table scans per request with no cache. That's fine for 100–150 symbols, but worth a
comment or a short TTL.

### `src/api/dashboard.py` (lines 148-153)
**Issue:** Missing Docstring
**Severity:** Nit

```python
def weekly(storage: Storage, source: str) -> pd.DataFrame:
    return research_weeks(storage.table(f"processed/{TABLE_PREFIX[source]}_weekly.parquet"))
```

`weekly()` and `current()` are public, unprefixed helpers with no docstring. `weekly()` silently drops
holdout weeks and `current()` doesn't, and that difference is exactly what a reader needs to know.

### `src/api/dashboard.py` (line 224) and `src/api/main.py`
**Issue:** Structure
**Severity:** Should fix (coordination, not code)

```python
@router.get("/spikes", response_model=list[Spike])
```

In the merged app, Joshua's Week 2 router owns `GET /spikes` (with `?ticker=`) and is mounted first.
The dashboard's `/spikes?week=` is unreachable, and FastAPI warns "Duplicate Operation ID
spikes_spikes_get". The comment in `main.py` documents it, but `/spikes` is a "Done when" endpoint.
Agree with Joshua to move his Week 2 routes under `/reddit/` before deploying.

### `src/api/wikipedia.py` (line 105) and `src/api/dashboard.py` (line 178)
**Issue:** Structure
**Severity:** Nit

```python
@router.get("/attention")              # Week 2: ?ticker=&start=&end=, shared-table rows
@router.get("/attention/{ticker}")     # Week 3: attention records
```

Two attention endpoints now return different shapes: the shared-table rows and the attention record.
The dashboard should use one. Mark the Week 2 route as deprecated in its docstring and README, or
remove it once nothing calls it.

### `src/api/dashboard.py` (lines 244-251)
**Issue:** Bug Risk
**Severity:** Nit

```python
        a = _num(p["abn_ret"].get(r.ticker)) if "abn_ret" in p else None
```

`p` is indexed by ticker alone. If `prices_weekly.parquet` ever holds the same ticker twice in one week
(two markets, or a duplicated row), `.get` returns a Series and `_num` fails. Index on (ticker, market)
or de-duplicate when loading.

### `docs/wikipedia/week3_report.md` (line 94)
**Issue:** Style (stale doc)
**Severity:** Nit

```markdown
Tests: `tests/test_api_dashboard.py` runs 10 TestClient tests on fixture tables in `tests/fixtures/api/`.
```

The file now has 11 tests (the router-mounting test was added), and the dashboard tests now run the
router on its own app. Say why: the merged app's `/spikes` belongs to Joshua's router for now.

## Checklist for the student
Fixed on 2026-11-11 (`tests/test_api_storage.py`, plus new tests in the dashboard and FinBERT files):
455 passed, 66 skipped; `storage.py` coverage is now 99%. Nits also fixed: docstrings for `weekly()` and
`current()`, `/spikes` prices keyed by (ticker, market), the Week 2 `/attention` route marked as the
older format, and the report's test count.

- [x] `finbert_scorer.revision()`: resolve the model revision after the model is downloaded, so a fresh
      machine doesn't cache scores under `@local` and rescore everything on the next run; add a test.
- [x] `/hot` and `/live`: treat a missing or unreachable DynamoDB live table as "no quotes" instead of
      HTTP 500; add a test.
- [x] `/attention`: normalise `spike` (and `edits_spike`) to bool when reading the tables, or make the
      model tolerant; add a fixture row with a missing spike.
- [x] `src/api/storage.py`: test the S3 and DynamoDB branches with a mocked boto3 (prefix handling,
      missing object, pagination, `Decimal` conversion).
- [ ] Agree with Joshua on moving his Week 2 `/spikes` and `/sentiment` under `/reddit/`, so the dashboard
      `/spikes` is reachable before deploying.
