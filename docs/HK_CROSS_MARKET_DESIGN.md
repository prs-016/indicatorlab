# Cross-market data layer: Hong Kong section

Local issue draft for Jack, Jamal, Joshua and James. Prepared 2026-11-12 UTC.
Coordinate the shared interface with Jamal before publishing. This is a design
note, not a claim that tool B has been implemented or cloud-deployed.

## Calendar and execution clock

Use `exchange_calendars` XHKG with timezone-aware UTC timestamps at storage
boundaries and Asia/Hong_Kong for session dates. Continuous sessions are
09:30–12:00 and 13:00–16:00 HKT; opening/closing auctions need separate handling
if execution ever includes them. The local quote collector deliberately
excludes auctions. Respect holidays and shortened sessions, including
Christmas Eve and Lunar New Year arrangements. Never fabricate a lunch bar.

The task guide's generic weather-closure description needs a date qualification:
HKEX introduced severe-weather trading on 2024-09-23. Current trading continues
during Typhoon Signal 8 and black rain warnings. Historical periods before that
date may have full/partial suspensions. Do not apply a present-day weather
closure rule to either current service operation or all historical dates.
Sources: [HKEX current severe-weather arrangements](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Severe-Weather-Arrangements/Overview?sc_lang=en),
[HKEX implementation announcement](https://www.hkex.com.hk/News/Market-Communications/2024/240618news?sc_lang=en),
[exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).

Library holiday/half-day support is exercised in `tests/test_hk_live.py`.
The 2015–2025 data reconciliation found two actual full closures missing from
the installed library: [2023-09-01](https://www.hkex.com.hk/News/Market-Communications/2023/2309012news?sc_lang=en)
and [2023-09-08](https://www.hkex.com.hk/News/Market-Communications/2023/2309083news?sc_lang=en).
`src.hk.calendar` now applies those dated exceptions and the
[2023-10-09 14:00 late open](https://www.sse.com.cn/services/hkexsc/disclo/announ/c/c_20231009_5727317.shtml).
The research panel has zero unexplained missing benchmark sessions after this
correction. This is not an exhaustive audit of every historical partial-day
weather interruption; tool B needs that audit before intraday certification.
The local calendar is constructed for 2015–2027; update/test that range before
using the collector beyond it.

## FX

HKD is linked to USD with convertibility undertakings at 7.75 and 7.85 HKD/USD,
according to [HKMA](https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/how-does-the-lers-work/).
It is not exactly a fixed 7.8 rate. Fetch daily `HKD=X` (HKD per USD), store
the source date and availability timestamp, and convert HKD value to USD by
division. Use the most recent rate actually available at valuation time; a
same-day end-of-day FX close cannot price a morning decision. Do not
backfill with a later observation. Preserve local HKD P&L alongside converted
P&L. Currency-counter identity must remain explicit for RMB/USD counters;
the operational HSI roster here uses HKD counters.

## Board lots

Download [HKEX's List of Securities](https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx).
`src.hk.refresh_reference` parses HKD equities and REITs, validates positive
lots and unique symbols, and records `pulled_at`, source URL and workbook SHA256.
The current table is `config/hk_board_lots_2026-11-12.csv`. The corrected filter
includes Link REIT (0823.HK). Verify coverage against the selected roster before
passing `hk_lot_sizes` into Vibe's `GlobalEquityEngine(market="hk")`.

This snapshot proves current lots only. For 2016–2025 simulation, obtain dated
issuer lot-change notices or explicitly classify current-lot use as a research
limitation. Never assume today's table was effective in 2016. Vibe defaults
missing lots to 100 shares and reports `lot_assumptions`; reject that diagnostic
for an evaluation requiring verified sizing.

## Stamp duty and other costs

Current stock-transfer duty is **0.1% on each bought and sold note**, rounded
up to a whole HK dollar. The historical rate was 0.13% from 2021-08-01 through
2023-11-16, then 0.1% from 2023-11-17. Sources:
[IRD historical stock rates](https://www.ird.gov.hk/eng/pdf/sd_stock_rates.pdf),
[HKEX effective-date circular](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2023/ce_SEHK_CT_158_2023.pdf),
[IRD rounding example](https://www.ird.gov.hk/eng/faq/sdu.htm).
Instrument exemptions require their own evidence; do not infer taxable status
from an empty cell in a current workbook or generalize equity rules to every REIT.

Vibe's current HK engine includes bilateral duty, commission, levies,
settlement and slippage, but its defaults are constant rates. The Week 3
research adapter retains the original transaction methods and corrects the
dated duty rate and whole-dollar rounding. The other levies retain the engine's
defaults, so this is not a complete historical fee/exemption reconstruction.
Next week's tool B should finish that reconciliation. A universal 10-bps
turnover deduction alone cannot satisfy the HK requirement.

## Operational quotes and deployment handoff

The fast public Tencent request is `q=r_hk00700,r_hk00005`, not `q=hk00700`.
One request for 95 names succeeded on all 120 audit polls; batch size 100 is a
conservative implementation choice, not a tested provider maximum. Zero-based
fields: last price 3, cumulative quantity 6, exchange timestamp 30, percent
change 32. Parse provider time as HKT, store UTC; never replace it with receipt
time. Independent Google Finance spot checks are recorded separately in
`results/hk/week3/quote_comparison_summary.json`. A post-auction sample agreed
on price/change and volume within Google's display rounding, with provider
times two seconds apart. Earlier intraday snapshots disagreed at apparently
similar times; that update-clock reconciliation remains unresolved. The closing
sample validates these fields for one stock, not every intraday quote.

Local service: five-second polls, per-symbol error isolation, bounded in-memory
statistics, backoff on failed polls, atomic latest views, daily logs and minute
Parquet. No one-minute SLA is claimed: measured median last-trade age 10.63 s,
p95 86.58 s, 90.95% under 60 s across the 10-minute test.

Cloud-compatible sink exists but remains disabled. If the team later deploys,
use us-west-2, DynamoDB `indicatorlab-live-hk` keyed by four-digit `.HK` symbol,
and `s3://indicatorlab-data/raw/live/hk/date=YYYY-MM-DD/HHMM.parquet`.
Schedule by **Asia/Hong_Kong**, not a fixed US Pacific offset (DST changes).
Alarm on missing ingestion heartbeat for 60 seconds only during open sessions;
track quiet-stock last-trade age separately. The optional container, scheduler,
IAM and independent session-aware watchdog are prepared under `infra/hk_live/`;
the CloudFormation template passes cfn-lint. Docker image building, real AWS
writes, alarms and James's `/live/hk` verification remain deployment work.
The user explicitly scoped this session to local work.
