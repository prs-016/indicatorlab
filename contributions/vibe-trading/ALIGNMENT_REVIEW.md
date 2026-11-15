# HK / NIFTY 100 coordination review

Reviewed 2026-11-14 (America/Los_Angeles). HK submission package v2.

The five questions concern reproducibility and integration: both markets need
comparable definitions, and their independent changes must coexist in the same
upstream infrastructure. They identify real issues worth resolving before review.

## 1. Why 85 benchmark names but 95 operational names?

The parser did not lose ten downloaded stocks. The actual Wikipedia table has
85 rows and all 85 were loaded by the recorded benchmark. Fresh retrieval still
returned Wikipedia revision 1377881667, page modified 2026-10-01T18:43:56Z.
That page edit date is not a verified membership effective date.

The official [21 August HSI review](https://www.hsi.com.hk/static/uploads/contents/en/news/pressRelease/20260821T174500.pdf) increased membership from 93 to
95, effective 2026-09-07. Its Appendix 1's 95 stock codes exactly match the local
frozen 2026-11-04 operational snapshot. The official
[October factsheet](https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsie.pdf)
also reported 95, with data as of 2026-10-30.

There are 84 shared names: Wikipedia misses **11** official-reference names and
includes **one** obsolete name, giving a net difference of ten. Missing:
0728.HK, 1347.HK, 1519.HK, 1801.HK, 2338.HK, 2600.HK, 3750.HK, 3993.HK, 6160.HK, 6181.HK, 9901.HK. Unexpected: **0881.HK**.

Current submission policy: keep **Wikipedia primary**, as the assignment
specifies, with the dated full 95-name fallback when fetching fails. Version 2
also compares sets with the dated official reference, marks mismatch degraded,
and records missing/extra names separately from provider price failures.
It does not silently change the returned universe to 95. A future mismatch
can mean the frozen reference is old, so neither count is hard-coded as a
permanent assertion about the market. An official-primary loader is a possible
policy change to agree with the team/mentor, not an unannounced alteration here.

## 2. Price, volume, missing observations and membership

Actual upstream behavior is **provider-native**, not a uniformly adjusted panel.
The shared [registry](https://github.com/HKUDS/Vibe-Trading/blob/19c83de9c4f53ff1609e266c3102badd0d034876/agent/backtest/loaders/registry.py)
explicitly labels Tencent HK prices raw; other sources can declare split/dividend
adjustment. The loader does not invent corporate-action factors or transform
one basis into another. Per-stock `adjustment`, `volume_unit`, source and any
alias conflict are now visible under canonical four-digit `.HK` keys, alongside
the untouched raw metadata. Mixed/unknown bases have explicit warnings.

Tencent/Eastmoney/Yahoo/yfinance declare HK historical volume in shares; other
adapters may be undeclared. These are provider declarations, not certification
of every historical quantity. No blanket ×100 multiplier or board-lot-size
conversion is applied. Board lots govern order sizing, not a universal data unit.

The HSI wide-panel step outer-joins observed dates without filling NaN cells.
However, shared upstream adapters can already drop incomplete OHLC rows or
replace missing volume with zero. Version 2 discloses that inherited behavior;
it does not claim original missingness can be recovered afterwards. Entirely
unavailable stocks remain in `missing_instruments`; the roster differences are
in distinct `constituent_reference_*` fields. No complete session-gap audit is
claimed by simply reporting missing symbols.

Membership and sector labels are current snapshots, not historical constituent
masks: `survivorship_bias=True`, `pit_membership=False`. The HSI table's Sub-index
labels are coarser than GICS or NSE classifications and are not a common global
sector taxonomy. Coverage uses the SP500 90% gate; VWAP remains an explicitly
labelled OHLC-mean proxy, not true traded VWAP.

`degraded` is a source/ambiguity flag, not a full certification flag. Always read
missing names, warnings, adjustment/quantity declarations and availability
statuses too. The separate frozen Week 3 portfolio research has different Yahoo
cash-dividend/lot assumptions; it is not interchangeable with this factor panel.

## 3. What compatibility was actually tested?

The original package pinned 67ce0ca5c9b2a3e3d321217eff043dad913a27fa. Against fresh upstream
[19c83de9](https://github.com/HKUDS/Vibe-Trading/commit/19c83de9c4f53ff1609e266c3102badd0d034876),
the HSI patch applied cleanly. The old combined package failed in two shared
files: `agent/mcp_server.py` and `agent/tests/test_mcp_json_string_args.py`.
Those changes were rebased as small additions, preserving newer options and
calculation-workspace behavior instead of replacing whole files.

The new split and combined routes apply to that base and byte-match all 25
destination files. Checks: **141 focused tests passed**, **1,078 broader
benchmark/purity/look-ahead tests passed, 23 skipped**. PR 1 alone also passes
**51 tests without the live-quote package**. There is one existing Python
3.14/LangChain Pydantic-v1 compatibility warning. This is not all upstream tests
or GitHub CI. No price/strategy/factor-performance backtest was rerun.

The supplied [India snapshot](https://github.com/prs-016/indicatorlab/tree/02625ce32dee742f75e923cd0177dbaba4fd2944)
was inspected read-only. It contains India research/adapters and an STREV/rank-IC
bridge, but no standalone NIFTY 100 loader, benchmark patch or fork/PR link.
Therefore **actual HSI plus NIFTY compatibility is still unverified**. The missing
input is the Vibe Trading fork/PR/commit containing the teammate's contribution.
No India branch, source file or remote was modified.

Once supplied, test both change sets on one pinned upstream base in a temporary
integration checkout. Keep both entries in universe/tag maps, API validators,
CLI choices and availability adapters. Test each universe independently and a
combined API/CLI import, preserving each provider chain. A textual patch check
alone is not an integration test.

## 4. Two PRs

PR 1 (`01_hsi_universe.patch`) is the standalone HSI universe, metadata,
availability adapter and tests. PR 2 (`02_hk_quotes.patch`) is the quote/MCP/archive
feature, stacked on PR 1 because its snapshot option reuses the HSI roster helper.
Submit PR 1 first; base PR 2 on it or wait for merge. `APPLY_ALL.patch` is a local
combined convenience, not a reason to submit one broad PR. NIFTY stays a separate
universe PR. Actual co-author identities and DCO sign-offs remain human inputs.

## 5. Proposed shared contract and responsibilities

These rows separate implemented HK facts from coordination work still proposed.

| Topic | HK now | Proposed common convention / remaining work |
|---|---|---|
| Identity | HSI adapter: equity, XHKG, HKD, Asia/Hong_Kong, XHKG; canonical 0700.HK | Each universe registers venue/currency/timezone/calendar in existing availability v1; confirm NIFTY's actual symbol convention in its code |
| Availability | Unknown historical membership, assumed/unverified bar timing remain non-PIT | `verified` only with evidence; current membership never becomes PIT-safe just from adding an adapter |
| Price basis | Provider-native per-stock adjustment, mixed/unknown warnings | Agree adjusted-return basis or reject/partition noncomparable series; preserve source, corporate-action/volume basis and date |
| Volume | Native quantities and declared units; no implicit lot multiplier | Require known units for volume/turnover comparisons; audit source declarations rather than guessing |
| Missing data | Observed-date union/NaNs at HSI layer; inherited fills disclosed | Agree explicit provider missingness policy and session-gap inventory; do not manufacture holiday/suspension trading bars |
| Membership | Current Wikipedia or dated degraded fallback; dated set comparison | Current-survivor benchmarks only labelled exploratory; genuine PIT comparisons require effective-dated memberships |
| Sector/VWAP | Source labels/90% gate, OHLC proxy VWAP | Keep native taxonomies labelled; agree a common mapping/proxy before pooling markets |
| Calendar | HK identity is registered; loader does not reindex/enforce sessions | Use each venue's real open/lunch/holiday/half-day schedule for execution; treat historical weather dates separately |
| FX | HSI panel stays HKD; no implicit conversion | Keep native P&L and convert portfolio valuation separately to USD using only rates known then; HKD=X is HKD per USD, so divide |
| Costs | Factor IC loader does not simulate portfolio costs | Portfolio comparisons require venue-specific fees, lots and dated taxes through the market engines |
| Cache | HSI metadata v2 avoids legacy cache records | Cache pins a snapshot; refresh after index reviews and record source/as-of/hash, rather than silently presenting stale membership as live |

HKEX continuous sessions are 09:30–12:00 and 13:00–16:00 HKT. Current severe-weather
trading differs from historical suspensions; the separate HK design note records
two 2023 full closures and a late open. Native daily session labels and UTC event
timestamps serve different purposes. Correct timezone metadata alone does not
implement a calendar engine or prove timestamps available before an entry.
Sources: [HKEX weather policy](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Severe-Weather-Arrangements/Overview?sc_lang=en),
[HKMA currency system](https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/how-does-the-lers-work/).

Suggested coordination: HK owns the fixes delivered here; the teammate provides
the actual NIFTY Vibe code and confirms its price/volume policy. Together, review
the contract above and run the joint integration fixture. Present Prakhar with
the evidence, the two scoped contributions, and only unresolved choices such as
official-primary membership or a strict common adjusted-data requirement. These
are proposals for agreement, not claims that cross-market comparison is finished.

## Suggested reply to the teammate

Thanks for checking these together. The 85/95 difference is a real roster-source
mismatch: the Wikipedia table has 85 names, all loaded successfully, while the
dated official snapshot has 95. It misses 11 reference names and includes one old
name. I have kept Wikipedia primary to match the assignment, added a dated
official-reference comparison and marked that mismatch degraded, without changing
the old benchmark's universe or numbers.

The HK panel currently retains provider-native adjustment and quantity bases;
Tencent HK is raw, so I cannot call the whole panel adjusted or PIT-safe. I have
made canonical per-symbol provenance/conflicts, native units, inherited missing
data behavior and current membership explicit. We should agree a strict common
adjustment/volume/membership convention before interpreting cross-market results.

I rebased the HK package on upstream 19c83de9 and fixed the two
MCP conflicts. The HSI loader is PR 1 and works standalone; live quotes are PR 2
stacked on it. I also registered the HK availability identity without upgrading
unknown timestamps or membership to verified/PIT-safe.

The IndicatorLab india branch you linked contains the research bridge rather
than the standalone NIFTY loader. Please share the actual Vibe fork/PR/commit;
then we can test both contributions on one base without changing your branch.
The draft contract above covers metadata, calendars, native currency and separate
FX valuation. I suggest we resolve the joint test and data conventions together
before presenting the remaining policy decisions to Prakhar.
