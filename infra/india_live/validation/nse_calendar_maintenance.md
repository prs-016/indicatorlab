# NSE cash-equity calendar through December 2026

This candidate extends the November 24 deployment inputs through December 31
using the existing date-based calendar. There are 26 regular days and 12 explicit
closures. The 100-name roster and its hash are unchanged.

## Regular sessions and the closing auction

| Effective date | Closing-auction eligible cash equities | Other cash equities | Collector window for the full roster |
| --- | --- | --- | --- |
| August 3 through December 6, 2026 | Continuous 09:15–15:15 IST. Closing-auction timetable starts at 15:15, with order matching and confirmation at 15:30–15:35. | Continuous 09:15–15:30 IST. | 09:15–15:15 IST, the overlap of the continuous sessions. |
| From December 7, 2026 | Continuous 09:15–15:30 IST. Auction transition and entry run from 15:30–15:40, followed by matching and confirmation through 15:45. | Continuous 09:15–15:30 IST. | 09:15–15:30 IST. |

Phase 1 covers equity securities on which derivatives are available. NSE
publishes a CAS identifier in its equity security master. The pre-open
alignment took effect September 7, separately from the August 3 CAS launch.
The collector handles continuous cash-equity quotes. Before December 7 its
single shared window intentionally omits the noneligible stocks' last 15
continuous minutes. It does not treat the earlier cutoff as those stocks'
exchange close. The December 7 timetable makes that tradeoff unnecessary.
[NSE phase 1 FAQ](https://nsearchives.nseindia.com/web/mediaattachment/2026-10/FAQs_on_Closing_Auction_Session_CAS_in_the_CM_and_changes_in_FO_Segment_ver3_20261023220345.pdf) · [NSE phase 2 FAQ](https://nsearchives.nseindia.com/web/mediaattachment/2026-11/FAQs_for_CM_and_FO_FOR_CAS_2.0_20261109152618.pdf)

## Maintaining dated coverage

1. Use the official NSE Capital Market trading-holiday circular for the
   target year, its amendments, and dated Capital Market live-session notices.
   Check the notices again before approving a window. Settlement holidays and
   mock or simulated sessions do not establish cash-market closures or openings.
   This candidate includes the November 24 and December 25 closures from
   NSE/CMTR/71775. It stops at year-end pending an official 2027 source review.
   [2026 trading holidays](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf) · [NSE circulars](https://www.nseindia.com/resources/exchange-communication-circulars)
2. Copy the [candidate calendar](nse-sessions-2026-year-end.json) as a new
   calendar for the next review. Use one explicit ISO date entry per day.
   Store closures as `[]`. When NSE announces a live special session, replace
   that date with the published shared continuous-trading interval or intervals,
   and record the applicable notice in `source`. A live special session can
   override a regular closure. Confirm the task's start and stop window covers
   any approved session outside normal hours before considering activation.
3. Recheck the NIFTY 100 roster, set the manifest's review window to the
   verified dates, and refresh both SHA-256 values. Use a new named, dated
   operational review. Verify regular boundaries, any special intervals,
   closures, and refusal of an uncovered date. Unknown dates and expired
   review windows fail closed.

The published calendar's SHA-256 is
`0d6b1a607ead0e844407df666593053e48bc6230cd49ec523d102dbd1eb323e7`.
The accompanying local manifest remains pending operational approval.
Yahoo/Vibe's full-roster throughput limitation remains an activation blocker.
