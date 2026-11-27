# India Reddit configuration activation

Local configuration and matching integration, 2026-11-15. No collection,
attention calculation, sentiment scoring or backtest was run. The original
[inactive survey](../../config/india_reddit_survey.proposed/README.md) and its
matching proposals remain unchanged as historical evidence; this report records
which subset is now active in [config.yaml](../../config.yaml).

## Activated sources

Week 3 page 17 requires Arctic Shift representation and at least 20 posts/week
in 2024. These three general communities satisfy both the existing configured
annual-average interpretation and the stricter every-full-week interpretation:

| Community | Archived 2024 posts | Full-week median | Full-week minimum | Full weeks >=20 |
|---|---:|---:|---:|---:|
| IndianStockMarket | 50,563 | 997.5 | 404 | 52/52 |
| IndiaInvestments | 13,821 | 271 | 176 | 52/52 |
| IndianStreetBets | 28,590 | 517.5 | 379 | 52/52 |

Evidence: [source comparison](../../config/india_reddit_survey.proposed/source_comparison.csv)
and [weekly counts](../../config/india_reddit_survey.proposed/weekly_counts_2024.csv).
All three have verified Arctic Shift metadata identities and 366 successfully
counted days, without final failed months. The 52 full weeks are Monday–Sunday
UTC; December 30–31 is a separate partial bucket. These are archive-observed
submission counts, not proof of archive completeness, usable text or company-level
attention coverage. No survey queries were repeated.

IndiaInvestments is newly added; the two existing India general communities
are retained. DalalStreetTalks remains inactive: the week beginning December 23
has 19 posts (51/52 full weeks pass), despite passing the annual average.
US, HK, shared settings and the eight-week attention baseline are unchanged.

## Active matching behavior

All 100 current constituent identities from the saved official NSE roster have
configuration-driven qualified NSE identifiers and source-backed company-name
patterns. The existing matcher accepts `match_post(title, body, market="IN")`
and routes `match_subreddit` using each batch's explicit `market` column.
Omitting the market preserves the existing US default; unknown or mixed-market
batches are rejected. No separate India pipeline or stock names in code were added.

The activated rules are copied from the
[matching proposal](../../config/india_reddit_survey.proposed/matching_rules.proposed.yaml),
except the unvalidated contextual RIL/TCS/SBI aliases are omitted. Qualified
`NSE:TCS` and `TCS.NS` work; bare `TCS`, `SBI`, `INFY` and bare cashtags do not.
Company-name matching uses the recorded legal names and multiword stems, including
Tata Consultancy Services. TMCV and TMPV remain distinct: the short Tata Motors
parent stem is not enabled for TMCV. DMart/IndiGo brand aliases and Hindi/Hinglish
aliases are not enabled without supporting matching evidence.

Existing URL/signature stripping, word boundaries, method provenance, one row
per post/security and the five-ticker list flag remain in use. General-source
posts require text matches and are never automatically attributed to all stocks.
The roster source SHA-256 is
`0a53ad14c15e9ec258dc72117a8c0699546ec25f2d283c47d53412e2de8a06fc`;
see the preserved [proposal](../../config/india_reddit_survey.proposed/matching_rules.proposed.yaml).

## Remaining limits and coordination

- Source-backed names and synthetic recognition tests do not establish real-post
  precision/recall. Joshua should label positives/negatives and review subsidiary,
  group and acronym collisions before operational attention or strategy use.
- The current roster is not historical NIFTY 100 membership. ETERNAL/Zomato,
  LTM/LTIMindtree, MOTHERSON and Tata identity changes require dated security/ISIN
  intervals before historical attribution. No old names or dates were invented.
- The survey only establishes 2024 source activity. IndianStreetBets did not
  exist throughout the requested 2016–2021 training period; other communities'
  creation dates do not prove continuous company-level coverage either.
- Post-building now accepts explicit `--market IN`, derives market identity from
  configured communities and rebuilds incorrectly tagged cached posts. The shared
  matcher processes the recorded market while retaining US defaults and preserving
  unrelated market outputs. This is offline pipeline compatibility, not evidence of
  operational India collection or complete historical coverage.
- No Wikipedia mapping was activated. AGENTS.md, prior proposals, historical
  datasets, strategy results and other markets were preserved.

## Offline verification

```bash
.venv/bin/python -B -m pytest tests/test_config.py tests/reddit/test_matching.py tests/reddit/test_india_matching.py tests/reddit/test_reddit_weekly.py tests/reddit/test_spike_rule.py tests/reddit/test_spikes.py -q -p no:cacheprovider
```

Result: **163 passed in 1.60s**. This includes all 100 current company identifiers
and legal names, ambiguous aliases, market routing/isolation, configuration
preservation and existing weekly/spike regressions. New tests deny network access.
An initial incorrect negative-test expectation for the legitimate TMPV name stem
was corrected; the rerun has no failures.

Ruff and Black checks on the two changed Python files pass. Equivalent regex
flag names and the cache decorator were updated to satisfy Ruff; Black formatted
the matcher. No dependencies were added. Preservation checks confirm unchanged
AGENTS.md and all saved proposal files. These tests establish local configuration
and matching behavior, not production readiness or historical data completeness.

## Publication verification — 2026-11-23

Reconciled with shared main `13c58bcf`: only the India config block changed;
US/HK settings, shared sentiment settings, the eight-week baseline and the newer
`holdout_start: 2026-11-01` remain unchanged. Frozen Week 3 studies retain their
original dates separately. The full selected configuration/matching/weekly suite
passed **174 tests in 1.71 seconds**. Historical test counts above describe the
earlier activation, not this fresh run. Publication includes compact count/proposal
evidence; raw archived posts and private acquisition records remain local.
