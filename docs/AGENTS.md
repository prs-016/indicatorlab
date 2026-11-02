<!-- ============================================================
     👋 HUMAN-READ SECTION — read this yourself first. Delete this
     whole block (down to the divider) once you're done, or leave
     it — agents will just skip past an HTML comment either way.
     ============================================================ -->

# For DS3 Students: What Is AGENTS.md and Why Does This Repo Have One?

## The problem it solves

Every AI coding tool invented its own file for "here's context about my
project, please read this first": Cursor uses `.cursorrules`, Claude Code
uses `CLAUDE.md`, GitHub Copilot uses `.github/copilot-instructions.md`,
and so on. If you used more than one tool, you had to write the same
instructions multiple times in multiple formats.

**`AGENTS.md`** is the fix: a single, open, cross-tool standard — think of
it as **a README, but written for an AI agent instead of a human**. It was
put together by the teams behind OpenAI Codex, Cursor, Google, and others
specifically so you write your project instructions *once* and every
major coding agent (Claude Code, Cursor, Codex, Copilot, and more) reads
the same file. As of writing, tens of thousands of repos use it and
~20+ tools support it natively.

## What it's for

When an agent opens your repo, it has no idea:
- what the project actually does or who it's for
- how to install dependencies and run things
- where "real" code lives vs. scratch/exploration code
- how your team runs tests
- what conventions you follow (style, structure, docstrings...)
- what it should *never* do (touch `main` directly, commit secrets, etc.)

`AGENTS.md` answers all of that up front, once, so you don't have to
re-explain your project in every single chat with every tool. The agent
auto-discovers it just by being in the repo — you don't have to `@`
mention it (though you still can, to be explicit).

## Why DS3 wants you comfortable with this

- **It's now industry standard.** Understanding how to write good agent
  instructions — clear, specific, scoped, not overly long — is a real
  skill you'll use at any internship or job that touches AI tooling.
- **It's portable.** Whatever tool you or a future teammate prefers
  (Claude Code, Cursor, Codex, Copilot...), the same file works. You're
  not locked into one assistant.
- **It documents your project for humans too.** A well-written AGENTS.md
  is often just as useful for a new teammate joining the project as it is
  for an AI agent.
- **It's the difference between "the agent guesses" and "the agent
  knows."** Vague instructions produce vague/wrong help. Specific ones —
  "run `pytest` from the repo root," not "run tests" — get you working
  code the first time.

## Keep it alive — this is not a one-time setup step

A stale AGENTS.md is worse than none at all: it actively lies to the next
person (or agent) who trusts it. Every teammate on this project — and
every agent they work with — reads the *same* file, so it has to stay
accurate as the project actually changes.

**The rule: any time an agent (or you) adds a feature, changes how
something is run/tested, changes the structure, or adds a new
dependency/convention, AGENTS.md gets updated in the same PR.** Not
"eventually," not "someone else's job" — the same change that made the
file outdated is responsible for fixing it. See the instruction to this
effect in the template below; don't delete it.

## AGENTS.md vs. the `ds3-code-review` skill

These are two different things and both matter:
- **`AGENTS.md`** = standing context about *this whole project* (what it
  is, how to run it, conventions). The agent reads it automatically for
  *any* task in this repo.
- **`SKILL.md` files** (like `ds3-code-review`) = instructions for one
  *specific task* — in this case, running a strict read-only code review.
  You (or the agent) reach for it only when that specific job comes up.

A good mental model: AGENTS.md is "everything you need to know to work in
this repo," a skill is "here's exactly how to do this one thing well."

## How to fill this out (do this now)

This file is a **template**. Go through every `[bracketed placeholder]`
below and replace it with real info about your specific project — nobody
else can fill this in for you, since every DS3 project is different. Keep
the sections short and factual; don't write paragraphs the agent doesn't
need. If a command doesn't work, the agent will trust it and waste time —
so actually run each command yourself before writing it down.

Where this file goes: **the repo root**, named exactly `AGENTS.md`. If
your project ever splits into clearly separate sub-projects (e.g. a
`frontend/` and a `models/` pipeline that are basically unrelated), you
can also drop an additional `AGENTS.md` inside a subfolder — the agent
uses the one closest to the file it's working on.

Nothing tool-specific to install — Claude Code, Cursor, and Codex all
read `AGENTS.md` at the repo root automatically, no setup needed. (Claude
Code will also read a `CLAUDE.md` if present, and Cursor also honors
`.cursor/rules/` — but for a shared team repo, put the real content here
so it works everywhere, and keep the others as thin pointers to this file
if you need tool-specific extras.)

<!-- ============================================================
     TEMPLATE STARTS HERE — this is what the agent actually reads.
     Replace every [bracketed] placeholder below.
     ============================================================ -->


# AGENTS.md

## Project overview

Indicator Lab (DS3, UC San Diego): weekly attention data (Wikipedia page views and edits, Reddit
chatter and sentiment, search-trend alternatives) for US stocks, tested as trading signals, built so
Indian and Hong Kong stocks can be added as a config change. For the DS3 team and mentors.

**Status:** active development (Week 2)
**Primary language(s)/framework(s):** Python 3.11+, pandas, numpy, requests, yfinance, FastAPI, pytest

## Repo structure

```
.
├── README.md
├── config.yaml        # markets, stocks, subreddits, Wikipedia titles, spike rule, holdout, splits
├── .env.example
├── requirements.txt
├── pytest.ini         # puts the repo root on sys.path for `pytest`
├── notebooks/
│   └── wikipedia.ipynb   # Week 2 Wikipedia results; imports everything from src/
├── src/
│   ├── config.py          # loader for config.yaml (`from src import config`)
│   ├── wiki_attention.py  # page views (+ redirects), Monday weeks, shared spike rule `flag_spikes`
│   ├── wiki_edits.py      # revision history, weekly edits, reverts, summary keyword tags
│   ├── wiki_prices.py     # weekly returns, returns 1-4 weeks after, abnormal returns, bootstrap CIs
│   ├── wiki_pipeline.py   # pulls + caches everything, writes the shared weekly table
│   ├── wiki_analysis.py   # spike-vs-normal returns, edit timing, tags, tone, last-3-weeks table
│   ├── wiki_strategy.py   # Wikipedia-only strategy with random-portfolio baseline
│   ├── trends_compare.py  # Google Trends alternatives (GDELT, trendspy) vs Wikipedia views
│   └── api/               # FastAPI app: main.py + one router per source
├── tests/             # pytest tests for src/ (no network: HTTP calls are mocked)
├── docs/              # AGENTS.md, DesignDoc.md, codeReviewer.md, docs/wikipedia/ reports
├── data/              # git-ignored; raw/ never edited by hand
│   ├── raw/wikipedia/  # views_{research,recent}/, revisions_{research,recent}/<lang>/, prices/
│   ├── processed/wikipedia/
│   └── shared/        # attention_weekly_<source>_{research,recent}.csv in the team format
└── results/           # git-ignored outputs (tables, strategy runs)
```

## Dev environment / setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your own local values — never commit .env
```

- `WIKIMEDIA_CONTACT` in `.env` is required for any Wikipedia pull (Wikimedia rejects clients without a
  contact address in the User-Agent).
- Data is not in git. Rebuild it with the pipeline below (about 25 minutes the first time, then cached).

## Running things

- Pull/refresh Wikipedia data and rebuild the weekly tables: `python -m src.wiki_pipeline`
- Wikipedia-only strategy (train/test, 200 random portfolios): `python -m src.wiki_strategy`
- Results notebook: `jupyter lab notebooks/wikipedia.ipynb` (Restart and Run All; needs the pipeline output)
- API: `uvicorn src.api.main:app --reload --port 8000`, docs at http://localhost:8000/docs
  (`/tickers`, `/attention`, `/price`)

## Testing

- Unit tests live in `tests/` and run with:
  ```bash
  pytest                          # from the repo root
  pytest --cov=src --cov-report=term-missing
  ```
- Tests never touch the network: Wikimedia, MediaWiki and API data are mocked or built in memory.
- `notebooks/wikipedia.ipynb` asserts its data coverage (holdout split, date ranges) at the top.
- Before opening a PR: run `pytest` and `ruff check src/ tests/`, and run the `ds3-code-review` skill.

## Code style & conventions

- Follow PEP 8; lint with `ruff check src/ tests/`.
- Every public function/class in `src/` needs a docstring (what it does, params, return value).
- No magic numbers in logic: thresholds and windows live in `config.yaml` or as named constants.
- No hardcoded tickers, subreddits or Wikipedia languages inside functions: read them from `config.yaml`.
- Weeks are labelled by their Monday (Monday-Sunday weeks). Every output table has a `market` column.
- Holdout: research, spike studies and strategy tests use data before `holdout_start` (2025-10-01).
  Recent data lives in separate `*_recent` files and is only for the dashboard and spike checks.
- One spike rule for every source (`config.yaml` `spike`, past weeks only): `src/wiki_attention.flag_spikes`.

## Git / PR workflow

- One GitHub Issue per task/bug/feature.
- Work happens on your own branch (`wikipedia`, `reddit`, `india`, `jack`), never directly on `main`.
- Push with `git` from the command line (no web uploads). Small commits with clear messages,
  e.g. `wiki: fix z-score to use past weeks only`.
- Open a PR when ready; **only mentors/PMs approve and merge to `main`**
  — do not merge your own PR even if checks pass.
- Run the `ds3-code-review` skill before every push and say so in the PR description.

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
- Never commit data files, `__pycache__/`, `.xlsx` or notebook checkpoints.
- Never install packages beyond what's needed without calling it out and
  updating `requirements.txt`.
- Never use holdout data (on/after 2025-10-01) for research, spike studies or strategy tests.
- Never finish a task that changed structure/commands/conventions
  without also updating AGENTS.md — see "Keeping this file up to date"
  above.

## Useful context

- Week 2 tasks: `Indicator_Lab_Week_2_Tasks.pdf` (not in git). Wikipedia results: `docs/wikipedia/week2_report.md`.
- Page views: Wikimedia REST pageviews API (`user` agent, from 2015-07-01). An article's views include
  every redirect to it, so renamed articles keep their history.
- Known data caveat: `Meta_Platforms` only became the company's own article in late 2019; before that,
  Facebook's company attention sat on the `Facebook` article. `Alphabet_Inc.` gets far fewer views than `Google`.
- Reddit pipeline (Joshua): `docs/reddit/README.md` on the `reddit` branch.
