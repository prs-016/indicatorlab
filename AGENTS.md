# AGENTS.md

## Project overview

IndicatorLab is a DS3 research project focused on collecting financial-market data, developing trading indicators, and evaluating quantitative trading strategies through reproducible backtesting.

**Status:** Active development

**Primary language:** Python

**Key libraries:** pandas, NumPy, yfinance, SciPy, and scikit-learn. Verify dependencies against the repository's requirements before installing or using them.

**Research areas:** US equities, Indian equities, Hong Kong equities, and alternative attention signals.

**India research context:** `docs/india_project_context.md`

When working on India-related tasks, read `docs/india_project_context.md` before making changes. Consult the existing research reports and relevant source files to verify claims.

**Development approach:** Work incrementally, explain important implementation decisions, run appropriate tests, and stop for user review before beginning another major task.

## Repo structure

IndicatorLab follows the DS3 project template. Reusable Python logic should live in `src/`, and automated tests should live in `tests/`. Both directories already exist. Notebooks are for exploratory analysis and should import reusable logic instead of duplicating it.

Current repository structure:

```text
indicatorlab/
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── docs/
├── frontend/
├── india_research/
│   ├── data/
│   ├── reports/
│   └── weekly_plan.md
├── infra/
├── models/
├── notebooks/
├── results/
├── src/
└── tests/
```

Development conventions:

- `india_research/` contains India-specific research, source data, and reports.
- `docs/` contains team documentation and the India project context.
- `notebooks/` is for exploration and experiments.
- `results/` is for experiment outputs.
- `src/` and `tests/` contain example code plus the India data adapter, isolated Vibe bridge, historical ingestion workflow, and offline synthetic tests. Add reusable strategy implementations to `src/` and corresponding automated tests to `tests/`, following DS3 conventions.
- Preserve existing research files and never overwrite raw data without authorization.
- Before creating or reorganizing directories, inspect the relevant repository documentation and confirm the intended structure.

For India-specific work, consult `docs/india_project_context.md`.

## Dev environment / setup

IndicatorLab uses Python 3.13.11 in a WSL Ubuntu environment.

Use a dedicated Python virtual environment instead of installing project dependencies directly into Conda's base environment.

### Initial setup

Run from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Returning to the project

Activate the existing environment:

```bash
cd ~/indicatorlab
source .venv/bin/activate
```

### Dependencies

Project dependencies are maintained in `requirements.txt`, including the India research dependencies `yfinance` and `scipy`.

When adding a dependency, update `requirements.txt` and explain why it is required.

Never commit `.env` files or API credentials. Use `.env.example` to document required environment variables without exposing secrets.

Verify that the virtual environment is active before executing project scripts or installing packages.

## Running things

Activate the project's Python environment before running scripts:

```bash
source .venv/bin/activate
```

### Current implementation

- `src/example.py` contains example Python code.
- `src/india_factors.py` integrates the four unchanged original Alpha101 factors with validated adjusted OHLCV, isolated Vibe imports, missing-score/warning provenance and the same portfolio/IC baseline. `load_factor_dataset` uses a common 25 prior-session history (November 26, 2020 onward) and verifies hashes for all nine histories. Separate approved #001/#002 provisional diagnostics have completed; #003/#004 remain non-evaluable/unsuitable. See `india_research/reports/india_four_factor_integration_review.md` before real evaluation, particularly for volume-basis and cross-sectional price-rank limitations. STREV's single-run diagnostic exception does not authorize the other factors.
- `src/india_data.py` adapts in-memory lowercase close/volume histories for the eight assigned NSE stocks, keeps `^NSEI` separate, and excludes dates after December 31, 2024. Callers declare the price-adjustment basis; missing observations remain missing.
- `src/india_vibe_bridge.py` calls Vibe-Trading's unchanged STREV and next-session rank-IC functions in an isolated subprocess. It accepts an explicit checkout and Python interpreter, records source hashes, and performs no downloads or portfolio simulation. Both repositories use a package named `src`, so their imports must remain isolated.
- `src/india_vibe_bridge.py::compute_rank_ic` also evaluates execution-aligned labels through Vibe's original IC implementation. `src/india_backtest.py` supplies configurable sequential portfolio accounting, evidence-backed research-view exclusions, flags, and the composed STREV workflow. Phase 3 authorization covers implementation and offline tests, not final strategy evaluations. See `docs/india_backtesting_methodology.md` for the developer-approved 2021–2024 top-two weekly baseline and remaining risks.
- `src/india_ingestion.py` retrieves exactly the assigned eight NSE stocks and `^NSEI`, bounded by December 31, 2024 inclusive (yfinance exclusive end January 1, 2025). It reuses Vibe's symbol/date/extraction helpers in an isolated child, bypassing Vibe's normalizer because that normalizer drops missing prices and fills volume. No repair, automatic adjustment, or provider fallback is used during download.
- Ingestion creates a new snapshot directory with `raw/` provider-returned CSVs, `derived/` adjusted OHLCV CSVs, and a `manifest.json` recording settings, versions/source hashes, coverage, gaps, quality flags, and file hashes. Derived OHLC uses `Adj Close / Close`; volume is unchanged. Invalid adjustment ratios become explicitly flagged NaNs; raw values remain intact. Existing snapshots cannot be overwritten. `load_snapshot()` verifies hashes and adapts the derived histories without filling gaps. Download completion does not mean data is approved for backtesting.
- `src/india_reconciliation.py` verifies downloaded official NSE bhavcopy/index records offline and builds immutable versioned evidence datasets. It requires instrument-specific trading/publication evidence and source hashes; it never estimates equity adjustment factors. Its three-session nominal evidence is preserved in `results/india_nse_reconciliation_20261028T235724Z_a6731313/research_v1/`.
- `src/india_adjustments.py` separately audits nominal-to-adjusted conversions using official share events, pre-cutoff dividend cash/previous closes, a frozen December 31, 2024 Yahoo normalization anchor, and independent bracketing NSE price checks. Phase 4B verified 24/24 conversions to that vendor vintage and created `results/india_adjustment_phase4b_20261029T012512Z_d2f07a95/research_v2/`; it does not independently reconstruct every post-2024 Yahoo adjustment. Strict certification flags remain unchanged; the subsequently approved diagnostic uses a separate scope-bound exception. See `india_research/reports/india_adjustment_phase4b_review.md` for the verification scope, evidence, reproduction script, and unresolved global gate.
- `src/india_calendar.py` reconstructs evidence-labelled calendars and audits the unchanged 21-session clock. `src/india_phase4d.py` reuses the Phase 4B verifier/conversion procedure for January 20, 2024; run `.venv/bin/python -B -m src.india_phase4d NEW_EVIDENCE_DIRECTORY` with frozen evidence and a January 23 retrieval manifest. It refuses existing versions and does not download or backtest. Phase 4D research_v3 has 8/8 new verified conversions and zero full-period data/clock discrepancies, but exhaustive calendar-amendment coverage remains unverified; no exhaustive certified version is created; the subsequently approved single provisional diagnostic is documented separately. See `india_research/reports/india_session_phase4d_review.md`.
- Vibe-Trading is the PM-approved replacement for the unavailable India benchmarking script. The developer-approved standard India methodology combines its original factor/IC calculations with Jack-adapted portfolio simulation; the configurable portfolio parameters are not recorded as explicit PM approvals.
- Vibe-Trading is located at `/home/jampip/vibe-Trading`.
- Jack's Hong Kong implementation is a reference for backtesting and reporting.
- The original `mini_bench.py` is unavailable and is no longer required.
- The user-approved single STREV diagnostic ran with `VIBE_PYTHON=/home/jampip/indicatorlab/.venv/bin/python .venv/bin/python -B -m src.india_diagnostic --approved-diagnostic`. This pinned-dataset/review runner waives only exhaustive calendar-inventory certainty and retains all structural gates. The one approved run is complete; rerunning requires further user authorization. See `india_research/reports/india_strev_provisional_diagnostic.md`.
- Read `docs/india_project_context.md` for the required strategies and constraints.

### Notebooks

Use `jupyter lab notebooks/` for exploratory analysis.

### Historical India ingestion

From the repository root with the project virtual environment active:

```bash
python -m src.india_ingestion --start 1900-01-01 --destination results/india_history_NEW_SNAPSHOT
```

Choose a new destination for every retrieval. The start argument is an acquisition lower bound, not an approved strategy evaluation start. The illustrative 1900 lower bound requests available pre-cutoff history; no holdout price observations are requested. Yahoo may revise historical prices/adjustments using later corporate actions, so snapshots are retrieval-time vendor histories, not point-in-time data vintages. Calendar gaps are reported relative to returned sessions and the benchmark, not a verified NSE calendar. Suspicious observations require review before any strategy evaluation.

Verified October 28, 2026: `results/india_history_phase2_a6f29fdafeeb/manifest.json` records a successful nine-symbol retrieval (56,982 total rows), ending December 31, 2024 for every symbol. Raw/derived hashes and adapter loading were checked; data-quality review remains pending. A separate incomplete snapshot, `results/india_history_phase2_1a838039b3c5/`, records the sandbox DNS failure. These generated snapshots are ignored by the existing `results/*` rule and do not replace existing India research.

### Backtesting requirements

Before running a backtest, verify the strategy definitions, data sources, and historical cutoff.

Never invent execution commands or report results from tests that were not executed.

## Testing

- Unit tests live in `tests/`; `pytest.ini` sets `testpaths = tests` to avoid collecting immutable source snapshots under `results/`. Run with:
  ```bash
  pytest
  ```
- No correctness-critical validation notebooks are currently identified.
- Before opening a PR: run `pytest` and make sure it passes. New logic in
  `src/` should come with a test — either in `tests/` or a clear
  assertion-based check in the relevant notebook.

### Verified test command

Run the complete suite from the repository root with the project virtual environment active:

```bash
VIBE_PYTHON=/home/jampip/indicatorlab/.venv/bin/python .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

Verified October 28, 2026:
- Python 3.13.11
- pytest 9.2.0
- 353 tests passed: 24 ILLIQ diagnostic cases, 29 Phase 2 portfolio-diagnostic cases, 13 Phase 2 signal-readiness cases, 37 Phase 2 integration cases, 9 alpha101_004 decision cases, 6 alpha101_003 investigation cases, 17 alpha101_002 diagnostic cases, 25 volume-reconciliation cases, 16 alpha101_001 diagnostic cases, 13 signal-readiness diagnostic cases, 28 four-factor integration cases, 16 diagnostic-override cases, 14 calendar cases, 11 Phase 4D cases, 13 adjustment-audit cases, 20 official-session reconciliation cases, 26 portfolio cases, 19 India STREV cases, 16 ingestion cases, and 1 existing example test
- No failures, skips, or warnings

### Phase 1 India offline tests

`tests/test_india_strev.py` uses explicitly synthetic fixtures to test panel validation, alignment, cutoff enforcement, benchmark separation, Vibe STREV/IC calculations, and absence of look-ahead bias. It does not validate market data or portfolio performance.

Use the verified complete-suite command above. To run only the India tests, append `tests/test_india_strev.py`; that selection contains 19 cases and omits the example test.

Verified locally October 28, 2026: the project virtual environment imports `pydantic` 2.14.1 and supports the Vibe STREV/IC bridge. `VIBE_PYTHON` explicitly selects the child interpreter only; both parent and child use the project virtual environment in the verified command. Preserve the isolated child process because IndicatorLab and Vibe-Trading have conflicting `src` package names. Override `VIBE_TRADING_ROOT` in tests if the Vibe checkout is elsewhere. Integration tests skip with an explicit reason if `VIBE_PYTHON` is unset or the checkout is unavailable; adapter tests still run. The bridge itself defaults to the current interpreter and reports dependency failures rather than installing packages.

`tests/test_india_ingestion.py` adds offline synthetic checks for original CSV preservation, adjustment consistency, missing observations, anomaly reporting, cutoff/request enforcement, immutable snapshots, failure manifests, and checksum verification. Its Vibe integration test replaces only the network download with synthetic data and exercises the real isolated helper imports.

`tests/test_india_backtest.py` covers synthetic portfolio timing, holdings/drift, turnover/costs, pending-order replacement, missing-data failures, configuration/cutoff restrictions, special sessions, verified exclusions, and actual isolated Vibe factor/IC integration. These tests do not constitute real-data strategy validation.

`tests/test_india_reconciliation.py` covers synthetic instrument-specific official records, positive trading evidence, EQ/date/ISIN/OHLC validation, separate Nifty 50 verification, archive ambiguity, official-source checksums, immutable versions, and the unresolved adjustment-conversion gate. It makes no network requests.

`tests/test_india_adjustments.py` covers each recovered date's conversion, split/dividend separation, independently reconstructed cash steps, two-anchor disagreement, missing evidence, action boundaries, unknown/duplicate actions, and rejection of post-cutoff price anchors. No portfolio evaluation runs in these tests.

`tests/test_india_calendar.py` covers explicit holiday/special-session evidence, unknown dates, whole-session gaps, warm-up and 21-session offsets, next-session candidates, evidence-completeness gating, and refusal to write uncertified versions. The official record verifiers support explicitly scoped extra audit dates while preserving the historical cutoff and original three-date defaults. These tests are offline and do not run portfolio backtests.

When adding new strategy logic, add corresponding tests in `tests/`.
Do not report a strategy as validated solely because the example test passes.

## Code style & conventions

- Follow Python PEP 8 coding conventions.
- Every public function/class in `src/` must have a docstring describing its purpose, parameters, and return values.
- Avoid magic numbers. Use named constants or configuration values and document their sources.
- Keep reusable calculations in `src/`, not duplicated across notebooks.
- Add corresponding automated tests in `tests/` for new functionality.
- Use fixed random seeds when experiments involve randomness, and record those seeds.
- Save experiment configurations, date ranges, data sources, and evaluation metrics so results can be reproduced.
- Separate exploratory research from production-quality code.
- Do not introduce new linters or formatting tools without checking team conventions.

### Financial research conventions

- Prevent look-ahead bias by ensuring calculations use only information available at the prediction date.
- Respect the approved backtesting and holdout periods.
- Account for stock splits, missing observations, and suspicious prices.
- Document how IC, Sharpe ratio, and other performance metrics are calculated.
- Never fabricate financial data, experimental outcomes, or evaluation metrics.
- Clearly distinguish verified findings, assumptions, and unresolved issues.

### Research and decision-making

- Before implementing functionality, inspect relevant project
  documentation and existing implementations.
- For India backtesting, consult Jack's branch and the local
  Vibe-Trading repository.
- Reuse established approaches when applicable, but independently
  verify their correctness.
- Follow documented PM decisions without requesting approval again.
- If a material decision is unresolved, investigate existing code
  and documentation before proposing alternatives.
- Continue work that does not depend on the unresolved decision.
- Request approval before introducing assumptions that materially
  affect strategy results.
- Never present provisional results as final.
- Do not commit, push, merge, or publish without approval.

## Git / PR workflow

- One GitHub Issue per task/bug/feature.
- Work happens on a branch (`feature/your-task`), never directly on
  `main`.
- Open a PR when ready; **only mentors/PMs approve and merge to `main`**
  — do not merge your own PR even if checks pass.
- Before opening a PR, it's worth running the `ds3-code-review` skill on
  your branch to catch structure/style/testing issues yourself first.

### India branch workflow

- India research and development take place on the `india` branch.
- Verify the active branch using `git branch --show-current` before modifying project code.
- Do not commit, push, or open a pull request without explicit user approval.
- Run `python -m pytest -v` before preparing a pull request.
- Run the required `ds3-code-review` process and address applicable findings before submitting code.
- Keep weekly research reports and strategy results associated with their corresponding experiments.

## Keeping this file up to date

**This is a standing instruction, not optional:** whenever you (the
agent) make a change that affects anything described above — adding a
feature, changing/adding a run or test command, restructuring folders,
adding a dependency, changing a convention — update the relevant section
of this AGENTS.md as part of the same change, before considering the
task done. Do this even if the person didn't explicitly ask you to.

- Keep edits factual and short — update the specific section that's now
  wrong, don't rewrite the whole file.
- If you're unsure whether something is worth documenting here, prefer
  documenting it — the cost of a stale file for the next teammate/agent
  is higher than a slightly-too-detailed one.
- If your change conflicts with something already written here (e.g. you
  changed the test command), fix the existing text rather than leaving
  both the old and new versions in.
- Mention in your summary to the user that you updated AGENTS.md, so
  they can sanity-check it before it lands in the PR.

## Things the agent should never do in this repo

- Never commit or hardcode secrets, API keys, or `.env` contents.
- Never push directly to `main` or merge a PR.
- Never delete or overwrite anything in `data/raw/`.
- Never install packages beyond what's needed without calling it out and
  updating `requirements.txt`.
- Never use future market data when calculating historical trading signals.
- Never modify the approved backtesting or holdout dates without authorization.
- Never fabricate stock prices, strategy results, IC, or Sharpe ratios.
- Never overwrite existing India research data or approved experiment results without permission.
- Never change the five required strategies without user or PM approval.
- Never publish research reports as final without verifying the underlying calculations.
- Never execute Git commits, pushes, or merges without explicit user approval.
- Never finish a task that changed structure/commands/conventions
  without also updating AGENTS.md — see "Keeping this file up to date"
  above.

## Useful context

### Project documentation
- `README.md` — DS3 starter-template overview, setup, and repository guidelines.
- `docs/DesignDoc.md` — DS3 design-document guide; not a completed IndicatorLab architecture or decision record.
- `docs/codeReviewer.md` — Code-review guidance.
- `docs/india_project_context.md` — India assignment, completed research, PM decisions, and remaining work.
- `docs/india_backtesting_methodology.md` — Developer-approved combined methodology, configurable provisional assumptions, implementation details, and final-evaluation approval gate.

### India research
- Working branch: `india`.
- PM-approved framework replacement: Vibe-Trading. Developer-approved standard methodology: Vibe factor/IC functions plus Jack-adapted portfolio simulation, until instructed otherwise.
- Reference implementation: Jack's Hong Kong branch.
- Research files: `india_research/`.
- Original assigned strategies: `academic_strev`, `alpha101_001`, `alpha101_002`, `alpha101_003`, and `alpha101_004`. Preserve their completed findings. The user expanded the research scope to ten; developer-approved strategies 6–10 are integrated and tracked separately in `india_research/weekly_plan.md`; the signal-only readiness audit and four approved provisional diagnostics are complete; all separately approved diagnostics are complete; repeats remain unauthorized.
- Original backtesting cutoff: December 31, 2024.
- Team holdout starts: October 1, 2025.

### Recurring workflow
- The India assignment includes five strategy evaluations and one research report each week.
- Use `india_research/weekly_plan.md` to track weekly objectives, progress, and deliverables.
- Do not repeat completed experiments unless requested or required for validation.
- Preserve previous results and record any changes in strategy methodology.
- Stop for user review before finalizing weekly reports or submitting code.

`tests/test_india_phase4d.py` adds offline synthetic January 20 dividend-boundary, source-integrity and immutable-version regressions. Filling January 20 never establishes exhaustive calendar-amendment coverage.

Final calendar review: `india_research/reports/india_strev_final_readiness_review.md` recommends a narrowly scoped Phase 4D diagnostic pending explicit user approval; no identified material session discrepancy remains. Exhaustive certification is not claimed. Preserve existing manifests/gates until approved diagnostic handling is recorded, and keep frozen-vintage limitations separate from calendar defects. Relevant calendar/reconciliation/adjustment/Phase 4D tests: 58 passed. No backtest authorization is implied.

`src/india_diagnostic.py` records the exact approved Phase 4D dataset/final-review hashes and rejects changed scope or material calendar failures. `tests/test_india_diagnostic.py` covers its approval/validation boundary. The single approved run is complete at `results/india_strev_PROVISIONAL_20261029T021955Z_21d1a038/`; all results remain PROVISIONAL and no other factor evaluation or repeat run is authorized.

`tests/test_india_factors.py` uses synthetic fixtures and the real isolated original modules to verify four-factor formulas, warm-up, cutoff/causality, OHLCV/missingness, original warnings, source checksums, identical portfolio/benchmark settings and execution-aligned IC. No real-data portfolio run for these factors is authorized by integration.

`src/india_factor_readiness.py` supplies signal-only coverage/tie, NaN-cause,
volume-basis and convention-comparison diagnostics; its 13 offline synthetic
tests are in `tests/test_india_factor_readiness.py`. The real factor scoring audit
is `india_research/reports/india_four_factor_real_readiness_review.md`: #2 has a
verified mixed-volume-unit issue; #3 has no eight-name-eligible sessions; #4 is
price-basis/tie sensitive. No real portfolio evaluation or data repair is
authorized by that audit. Preserve STREV's archived outputs and existing factor
and portfolio definitions. Do not mistake Yahoo Close for a purely split-only
series: observed Reliance pre-July-2023 scaling is not fully explained by splits.

`src/india_alpha001_diagnostic.py` provides the separately user-approved,
dataset/readiness-review-bound #1 runner. Its one approved run is complete at
`results/india_alpha101_001_PROVISIONAL_20261029T032703Z_711fe946/`; see
`india_research/reports/india_alpha101_001_provisional_diagnostic.md` for metrics
and the 162/208 executed targets whose membership depends on ticker tie breaking.
It uses the original Vibe factor/IC, 25 prior sessions and unchanged STREV
portfolio settings; it does not generalize STREV's approval or authorize repeats.
`tests/test_india_alpha001_diagnostic.py` adds 16 offline approval/tie regressions.

`src/india_volume_reconciliation.py` verifies corporate-action share multipliers
against two exact quantity anchors and writes immutable, volume-token-only
research versions. `tests/test_india_volume_reconciliation.py` has 25 offline
synthetic cases. The twelve recovered volume-unit inconsistencies are resolved
in `results/india_alpha002_volume_reconciliation_20261029T034510Z/research_v4/`;
all previous price/data/result artifacts remain unchanged. See
`india_research/reports/india_alpha101_002_volume_readiness_review.md` for all
quantities, anchor evidence, remaining vendor-normalization limits and the
three changed weekly candidate memberships. The subsequently approved single #2 diagnostic is documented separately;
no old diagnostic override is reused and immutable dataset flags remain unchanged.

Alpha101_002 volume-package finalization completed without rebuilding
research_v4. Its outer artifact inventory now includes finalized files; the
previous inventory/report and historical error log remain preserved. Independent
checks verified 12 changes, 24 quantity anchors and 279 protected hashes; the
complete suite reran with 218 passing tests. See the finalization section of
`india_research/reports/india_alpha101_002_volume_readiness_review.md`. Recommend
a provisional #2 diagnostic only after explicit approval; existing manifest
gates and prior STREV/#1 results remain unchanged.

`src/india_alpha002_diagnostic.py` provides the separately user-approved #2
runner, bound to the finalized research_v4 package and readiness hashes. Its
one approved run is complete at
`results/india_alpha101_002_PROVISIONAL_20261029T040140Z_4784a95f/`; see
`india_research/reports/india_alpha101_002_provisional_diagnostic.md`. The 235-test
suite passed before execution, including 17 new approval/provenance boundary
cases. Four original score NaNs remain; the March 25, 2022 skipped target creates
a ten-session execution-aligned IC interval. All labels/executions remain within
2024; original data, STREV and #1 archives stay unchanged. No repeats, other
real factors or final Keep/Drop decisions are authorized by this completed run.

`src/india_alpha003_audit.py` explains the original #3 ten-session rank
correlation failures and permits labelled signal-only diagnostic input bases;
it is not a replacement production factor or a broader-universe approval.
`india_research/reports/india_alpha101_003_investigation.md` attributes all 6,847
missing cells to 5,588 open-only, 1,224 both-rank and 35 volume-only constant
windows. TCS is always the highest adjusted open in this basket. None of the
price/volume variants restores eight-name eligibility; full nominal reconstruction
before July 2023 remains unsupported. Retain a non-evaluable assigned baseline;
a point-in-time broader rank-universe study would require separate approval and
new independently justified data. Six new offline tests bring the suite to 241.

`src/india_alpha004_audit.py` provides signal-only admissible-pair/tie and
convention diagnostics. The completed #4 decision is option (b), unsuitable for
a meaningful top-two factor-ranking evaluation in this eight-stock basket:
only 16/209 weekly memberships are unique, 193 depend on ticker ordering and
120 allow all 28 pairs. See
`india_research/reports/india_alpha101_004_readiness_decision.md`. No portfolio
run, alternate price basis or production tie rule is authorized; preserve the
original finite scores and historical preliminary report. Nine synthetic tests
bring the complete suite to 250 passing cases.

Strategy-expansion Phase 2 integrates the five developer-approved candidates
6–10: `alpha101_033`, `alpha101_101`, `alpha101_054`, `alpha101_014`,
`academic_illiq` in `src/india_phase2_factors.py`. It extends isolated dispatch
without changing legacy factors/bridge, invokes pinned original modules and
retains dependency flags, original NaNs, coverage/ties and the same portfolio/IC
baseline with 25 prior sessions. `tests/test_india_phase2_factors.py` adds 37
synthetic cases. The subsequent separately approved signal-only audit is complete;
all five separately approved single-factor portfolio diagnostics are complete, as recorded below.

`academic_illiq` India use is an explicit developer research exception despite
missing upstream `equity_in` metadata, not upstream endorsement or PM approval.
Require `load_illiq_basis_evidence` and bound INR adjusted-close/vendor-volume
proxy evidence; unsupported or mismatched bases must stop. Input-only checks
pass for 256 official records across 32 dates, but do not certify all quantities,
actual traded value, point-in-time histories or Reliance return normalization.
See `india_research/reports/india_phase2_integration_review.md` and the ten-strategy
weekly plan. Preserve three prior provisional backtests and two non-evaluable/
unsuitable original assessments; integration is not empirical eligibility.

`src/india_phase2_readiness.py` adds pinned-original, isolated signal-only numerical
observation before JSON serialization, per-cell NaN/window/denominator causes and
weekly admissible top-two diagnostics. Thirteen offline synthetic regressions in
`tests/test_india_phase2_readiness.py` bring the complete suite to 300 passing cases.
See `india_research/reports/india_phase2_signal_readiness_review.md`: all five have
7,920/7,920 finite evaluation scores, 209 unique eight-name weekly candidates
(208 nonterminal), no evaluation ties/NaNs/infinities. Recommend #033/#101/#054/#014
for separately approved provisional diagnostics; ILLIQ is conditional on acceptance
of material frozen-adjusted-INR turnover-proxy sensitivity (51/209 selections differ
without dividend adjustment). Original proxy evidence reverified at 256 records;
no actual-turnover or point-in-time claim, dataset gate override or portfolio run.
Twenty real-data causality/window checks pass. Preserve all prior reports/results.

`src/india_phase2_diagnostic.py` records the separately approved one-run scopes for
#033/#101/#054/#014, pinned research_v4/readiness hashes, original Vibe sources,
25-session warm-up and the unchanged portfolio/IC baseline. Each run revalidates
calendar structure, quantity anchors and causal evidence; only exhaustive calendar
inventory certainty is waived. Certification flags remain unchanged. ILLIQ,
changed scopes and repeats after invocation are rejected. A documented preflight
serialization failure before any factor call is preserved; null optional evidence
fields now serialize correctly. Twenty-nine synthetic runner/ledger tests bring
the complete suite to 329 passing cases.

The four approved diagnostics are complete, each with 208 executions/207 valid
IC intervals and zero tie-dependent executed memberships. See
`india_research/reports/india_phase2_provisional_backtests.md` for seven-strategy
PROVISIONAL comparison, exact output paths, audit and source hashes. Preserve all
seven archives; no repeats, ILLIQ run or final Keep/Drop are approved. #101's 0.001
constant and #014's 5/209 dividend-convention selection warning remain intact.
773 prior files and all completed inventories verified unchanged. No source data,
original factor or existing accounting function changed.

`src/india_illiq_diagnostic.py` supplies the separately user-approved one-run ILLIQ
scope; the old four-factor runner remains unchanged and rejects ILLIQ. Require
pinned research_v4/readiness/basis evidence, bound INR proxy units, 51/209 dividend
and 31/209 normalization disclosures, 25 prior sessions and unchanged portfolio/IC
settings. Only exhaustive calendar inventory certainty is waived; material checks
and strict manifest flags remain intact. Repeat invocations are rejected.

The one ILLIQ diagnostic is complete at
`results/india_academic_illiq_PROVISIONAL_20261029T053314Z_128ef15c/`: mean rank IC
-0.00310559, daily net Sharpe 0.748968, cumulative net return 70.4904%, 208
executions/491 trade legs and 207 IC intervals. This tests a frozen adjusted-INR
close × vendor-volume proxy, not actual turnover or point-in-time illiquidity.
India use remains a developer metadata exception, not upstream endorsement.
Original factor/volume/price histories, 51/209 and 31/209 sensitivities and
Reliance/Kotak limitations are retained. See
`india_research/reports/india_ten_strategy_provisional_comparison.md`: eight
completed PROVISIONAL backtests and two non-evaluable applicability studies.
Twenty-four new synthetic cases in `tests/test_india_illiq_diagnostic.py` bring the
full suite to 353 passing tests. Timing/accounting and 256 proxy checks pass;
1,036 prior files and all eight inventories verify unchanged. No repeats, final
Keep/Drop, source-data changes or publication are authorized.

Review-only documentation drafts are saved at
`india_research/reports/india_ten_strategy_research_report_DRAFT_20261029T054748Z.md` and
`india_research/reports/india_strategy_log_DRAFT_20261029T054748Z.md` (plus same-stem CSV).
They synthesize existing verified evidence for all ten IDs: eight PROVISIONAL
backtests and two non-evaluable factors, with N/A unrun metrics. User-requested
Keep/Drop/Investigate labels are preliminary research priorities only; final PM
decisions remain pending. No factor scoring, backtest, test rerun, source-data or
formula change is authorized by these drafts; prior reports/results are preserved.

Current PM-facing review versions (not final PM decisions) are
`india_research/reports/india_ten_strategy_PM_review_20261029T061017Z.md` and
`india_research/reports/india_strategy_log_PM_review_20261029T061017Z.md` (plus same-stem CSV).
Original drafts stay unchanged. Formula inputs and registry-required fields are
separate for #003/#004; their Drop labels mean baseline non-evaluability, while
#101 is deprioritized for observed performance. The log retains signal-inventory
hashes, units and methods; the report includes documented assignment gaps.
No data/formula/result changes, new evaluations or publication are authorized.

Portable submission review copies are in
`india_research/submission/india_review_v1_20261101/` (`report.md`,
`strategy_log.md`, `strategy_log.csv`, selected saved evidence). Original reports,
evidence JSONs, datasets and results stay unchanged. The package is selected for local staging under the submission-preparation
authorization; its manifest hashes included copies separately from original archive
hashes. `python verify_package.py` inside that directory checks the package without
factor/backtest execution. Use `SUBMISSION_FILES.txt` as the evidence-change
allowlist, plus AGENTS.md; review wider implementation changes separately.

Submission preparation (2026-11-01): the user authorized staging the portable
155-path allowlist plus India modules/tests/dependencies and essential docs on
`india`, targeting `prs-016/indicatorlab`, but no commit/push/PR/merge. Root
`code_review.md` records the docs/codeReviewer.md review and remaining nonblocking
findings. README.md is the clean-checkout entry point; full archive-bound runners
are not getting-started commands. Only selected review-copy whitespace/guide text
and corresponding bundle checksums were corrected; original results/data/formulas
remain unchanged. Run the verified full pytest command after applicable fixes
and verify the exact staged export, not just ignored local workspace artifacts.

Submission-preparation verification: 200 changed paths selected (154 portable
evidence files, 20 India modules, 19 India test modules, 7 setup/context/review
files). All 155 evidence-allowlist paths are included. `code_review.md` records two
resolved submission blockers and three deferred nonblocking Should fix items.
The workspace suite passed 353 tests; the indexed-only export independently
passed 353 tests with the external Vibe checkout supplied. Bundle verification
and staged whitespace checks pass; original scientific/history files are intact.
This is staging approval only, not permission to commit, push, PR or merge.

### Strategies 11–15: approved Qlib158 single diagnostics

`src/india_qlib_factors.py` integrates the unchanged original Vibe
`qlib158_std20`, `qlib158_rsv20`, `qlib158_sump20`, `qlib158_wvma20` and
`qlib158_cord10`. It reuses the isolated worker protocol and India validation;
no Microsoft Qlib installation is needed. Declared warm-ups remain 20/20/20/20/10;
effective input lengths are 20/20/21/21/11 rows. The common 25 prior sessions cover
all five. Formula, direction, metadata, safe division and NaNs stay upstream.
`tests/test_india_qlib_factors.py` uses reused, explicitly synthetic fixtures for
formulas, windows, causality, dependencies, volume units, timing and scoped gates.

The current user approved one conditional PROVISIONAL diagnostic per factor on
research_v4 with unchanged portfolio settings. `src/india_qlib_diagnostic.py`
loads/verifies shared data once, computes each original real-data factor once,
saves scores, and uses the saved cache for readiness and portfolio accounting.
A material readiness failure saves an unrun/N/A outcome. The dataset/review-bound
exception waives only exhaustive calendar-inventory certainty; material calendar,
input, cutoff, all-eight eligibility and unique top-two checks remain enforced.
The first ten strategies, reports and submission package are preserved. This
approval does not permit repeats, formula tuning, final decisions or publication.

The five Qlib158 approvals are now consumed: all passed complete finite/unique
signal gates and completed one PROVISIONAL portfolio each in
`results/india_qlib158_PROVISIONAL_20261101T212235Z_dfdc1a41/`. Scores were computed
once per real-data factor and cached; do not rerun without fresh approval.
The complete suite passed 388 cases (353 prior + 35 new) in 64.79 seconds;
all 1,293 protected pre-existing files matched their before-task hashes.
See `india_research/reports/india_strategies_11_15_PROVISIONAL_20261101T212235Z.md`
and its new Strategy Log. All five underperformed the saved benchmark in net
return and Sharpe; no final decisions follow. The old ten-strategy evidence and
portable submission package remain unchanged. Only parent CSV round-trip parsing
emitted a deprecation warning; original factor numerical warnings were zero.
