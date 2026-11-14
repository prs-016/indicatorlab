# IndicatorLab

Hong Kong local work: start with [HK_START_HERE.md](HK_START_HERE.md) for the
five-second HSI collector, five completed US/HK strategies, the separate Vibe
Trading code package, file locations and the task checklist.

IndicatorLab is a DS3 financial-market research project. Attention data
(Reddit, Wikipedia, search trends) and India equities research are both part
of the project; markets, stocks and sources live in `config.yaml`. Reddit
pipeline (Joshua): [`docs/reddit/README.md`](docs/reddit/README.md).

This branch contains the India data adapter, isolated original Vibe-Trading
factor/IC integration, Jack-inspired portfolio accounting, offline tests and a
ten-strategy review. The eight completed portfolio diagnostics are
PROVISIONAL; two other factors are non-evaluable under the fixed eight-stock
baseline.

## India submission: reviewer entry point

Start with the [portable review report](india_research/submission/india_review_v1_20261101/report.md)
and [Strategy Log](india_research/submission/india_review_v1_20261101/strategy_log.md).
The [bundle guide](india_research/submission/india_review_v1_20261101/README.md)
explains original versus review-copy hashes and excluded artifacts. Verify saved
metrics and links with standard-library Python; no external checkout or market
data is required:

```bash
python -B india_research/submission/india_review_v1_20261101/verify_package.py
```

For the offline implementation tests, use Python 3.13 and the project's dedicated
virtual environment, following the dependency setup below. Tests that use the
original factors additionally require an existing external Vibe-Trading checkout
at commit `7f6908b7e1b95d971f4151bfaf2382e2ce9485cf` from
[HKUDS/vibe-Trading](https://github.com/HKUDS/vibe-Trading).
Set its actual local path; do not copy its conflicting `src` package into this repo:

```bash
export VIBE_TRADING_ROOT=/path/to/vibe-Trading
VIBE_PYTHON="$PWD/.venv/bin/python" .venv/bin/python -B -m pytest -v -p no:cacheprovider
```

Without the external checkout or explicit VIBE_PYTHON, original-factor integration
tests skip with a reason; that is not a complete original-factor validation. The
reviewed environment ran all 353 cases without skips. No coverage percentage is
claimed. The suite uses synthetic fixtures and mocked downloads, not real-data
portfolio evaluations or market-data retrieval.

Ignored `results/` archives, raw prices and full official evidence are deliberately
not part of the portable bundle. `src.india_*_diagnostic` and Phase 4 reconciliation
entry points are historical, archive-bound workflows with consumed single-run
approvals and local runtime assumptions. They are not fresh-checkout getting-
started commands; do not run them, ingestion or new backtests to review this
submission. The portable package verifies recorded outputs, not factor/backtest
reproduction from raw data. Historical local paths in context documents describe
that original workspace; use the portable report/log for reviewer-accessible links.
See [India methodology](docs/india_backtesting_methodology.md) and
[code review](code_review.md). No commit, push, PR, merge or publication follows
from the submission-preparation checks.

A clean starter template for data science and machine learning projects at UC San Diego's DS3.

## DS3 template reference

## What this template includes

- A sensible folder structure for notebooks, source code, data, and outputs
- A Python environment file for quick setup
- A .gitignore tailored for secrets, notebooks, and generated artifacts
- A small starter package and test example

## Suggested repository structure

```text
.
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── notebooks/
│   └── README.md
├── src/
│   ├── __init__.py
│   └── example.py
├── frontend/
│   └── README.md
├── infra/
│   └── README.md
├── data/
│   ├── raw/
│   └── processed/
├── results/
├── models/
└── tests/
```

- `frontend/` is for UI/UX code and web app assets.
- `infra/` is for deployment scripts, cloud config, and infrastructure as code for AWS/GCP.

## Quick start

1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   **.env files are generally not shared on GitHub; they are included here only as an example template.**
4. Start working in notebooks or in the src package.

## Repository guidelines

- Keep notebooks for exploration and visualization.
- Put reusable logic in src so notebooks stay readable.
- Do not commit secrets, API keys, or large data files.
- Use clear filenames and short, documented functions.
- Add tests for any core logic that will be reused.

## Git and GitHub workflow for DS3 projects

Using Git and GitHub well is just as important as writing good code. A clean workflow makes collaboration easier and helps the project stay organized.

### 1. Use GitHub Issues for tracking work

Create an Issue for each task, bug, experiment, or feature request. Keep each issue focused and include:

- a short title
- a clear description of the work
- acceptance criteria if relevant
- labels such as bug, enhancement, documentation, or blocked

Example workflow:
- one issue for data cleaning
- one issue for model training
- one issue for documentation updates

### 2. Use branches to separate work

Each person or feature should usually work in its own branch. This prevents people from overwriting each other's changes.

Common branch commands:

```bash
git branch
git checkout -b feature/my-task
git checkout main
git branch -d feature/my-task
```

What they mean:
- `git branch` shows existing branches
- `git checkout -b feature/my-task` creates and switches to a new branch
- `git checkout main` switches back to the main branch
- `git branch -d feature/my-task` deletes a branch after it is merged

### 3. Use pull requests to merge code into main

When work is complete, open a Pull Request (PR) from your branch into `main`. A PR is the place to review changes, discuss issues, and confirm everything is ready.

Important rule:
- Only project managers or mentors should approve pull requests.
- Students should contribute code, but approvals should be handled by the designated maintainers.

### 4. Basic Git commands and what they mean

```bash
git clone <repo-url>
git status
git add <file>
git add .
git commit -m "Describe your change"
git push origin <branch-name>
git log
git merge <branch-name>
git rebase <branch-name>
```

What they mean:
- `git clone` copies a repository from GitHub to your local machine
- `git status` shows which files changed and what branch you are on
- `git add` stages files for commit
- `git commit` saves staged changes with a message
- `git push` uploads your local commits to GitHub
- `git log` shows recent commit history
- `git merge` combines another branch into your current branch
- `git rebase` reapplies your commits on top of another branch and can help keep history cleaner

### 5. Recommended team habits

- Pull the latest changes before starting work
- Keep commits small and descriptive
- Avoid committing large data files or secrets
- Open a PR early for feedback, not only at the end
- Resolve merge conflicts carefully and communicate with the team

### 6. Example workflow

```bash
git checkout main
git pull origin main
git checkout -b feature/data-cleaning
git status
git add .
git commit -m "Add initial data cleaning script"
git push origin feature/data-cleaning
```

Then open a Pull Request on GitHub and wait for approval from the appropriate project manager or mentor.

## Notes for DS3 projects

This template is intentionally simple so students can focus on the science instead of setup. As projects grow, teams can add:

- experiment tracking
- model checkpoints
- deployment scripts
- cloud infrastructure (AWS/GCP) in `infra/`
- frontend UI/UX code in `frontend/`
- CI checks
- docs pages
