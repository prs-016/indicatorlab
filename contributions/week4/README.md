# Week 4 HK contribution package

Authors: @Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016.

Start with the scope you are reviewing:

| Scope | Files | State |
|---|---|---|
| B2 HSI universe | [B2/README.md](B2/README.md) | Backend/frontend implemented and tested; real benchmark blocked by roster discrepancy |
| B3 HK market layer | [B3/HK_MARKET_LAYER.md](B3/HK_MARKET_LAYER.md) | HK code and tests prepared; joint India/HK PR remains a team step |
| B6 portfolio design | [B6/CROSS_MARKET_PORTFOLIO_DESIGN.md](B6/CROSS_MARKET_PORTFOLIO_DESIGN.md) | Design and local branch stacked over B3; portfolio implementation is future work |

## Applying the code

Apply inside a Vibe-Trading checkout at the exact base in each manifest.
This IndicatorLab HK branch is a mentor review package; the actual code changes
are contained in the patches, with destination paths and SHA-256 hashes.

- Preferred B2: `B2/B2_ON_NIFTY.patch`, based on Jamal's NIFTY commit
  `342259f40d04ad79f586f9585384ce44b3025058`.
- Alternate B2: `B2/01_hsi_universe_week4.patch`, based on upstream
  `1dbe5d515519565a47f0127b4e6d6fc4fbb5e4d2`. Choose one B2 route, never both.
- B3: `B3/B3_HK_MARKET_LAYER.patch`, independently based on that upstream commit.
- B6: `B6/B6_PORTFOLIO_DESIGN.patch`, applied after B3, as its manifest records.

B2+B3 coexist in an independently tested combined checkout. Their README
appends require keeping both short usage sections; source changes apply cleanly.
See `B2/COEXISTENCE_CURRENT_B3.json`. The preserved legacy combined/quote patches
in `../vibe-trading/` target an earlier base and must not be applied over this set.
Operational live-feed code for this week belongs in IndicatorLab, separately
from B2's universe PR; the existing app/collector was left unchanged.

## Validation and source limit

Preferred B2: 1,228 related backend tests passed, 23 skipped; 982 frontend tests
passed across 101 files. TypeScript and scoped Ruff passed. Its 184-test offline
subset made zero socket/DNS attempts. B3: 153 selected tests passed, including
35 new cases, with zero network attempts. Current combined B2/NIFTY/B3:
181 tests passed, zero network attempts. These overlapping suites must not be
added together and do not represent remote CI or the entire backend suite.
Exact commands and scope are in each validation file.

The real 2016-01-01–2026-10-31 HSI benchmark stopped before price/factor
calculation: Wikipedia returned85 names versus a dated 95-name official reference.
Week 4 requires strict count validation; no fallback was substituted. See
`B2/benchmark_attempt.json`. Annual loaded-name counts and performance remain
unavailable until the source/policy discrepancy is legitimately resolved.
Older85-name results are historical evidence, not this benchmark.

## Publishing handoff

The upstream commits prepared locally have Jack's sign-off and all four other
co-authors. The PR descriptions start with the five required Authors handles.
B2's draft is in `B2/PR_DESCRIPTION.md`; B3's HK draft is in
`B3/PR_DESCRIPTION.md`. Insert the actual shared design-issue link before posting.
Coordinate B3 with Jamal's India code before opening the one joint market PR.

`LOCAL_BRANCHES.json` records the local branch versions. Remote fork creation,
upstream PRs, team messages, shared-sheet posting and all AWS work remain external
steps. No remote branch, main branch, AWS service or teammate implementation was
modified during local preparation. The separate Jack research report records
strategy evaluations and config handoff; no raw inputs or full app are included here.
