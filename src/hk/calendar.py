"""HKEX continuous sessions, holidays and half-days via exchange_calendars."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

HKT = ZoneInfo("Asia/Hong_Kong")
FULL_DAY_CLOSURES = {
    "2023-09-01": "https://www.hkex.com.hk/News/Market-Communications/2023/2309012news?sc_lang=en",
    "2023-09-08": "https://www.hkex.com.hk/News/Market-Communications/2023/2309083news?sc_lang=en",
}
LATE_OPENS_HKT = {
    "2023-10-09": (
        14,
        0,
    ),  # https://www.sse.com.cn/services/hkexsc/disclo/announ/c/c_20231009_5727317.shtml
}


@lru_cache(maxsize=1)
def calendar():
    """Return XHKG calendar with the lunch break and special-session history."""
    return xcals.get_calendar("XHKG", start="2015-01-01", end="2027-12-31")


def market_state(now: datetime) -> str:
    """Return open/lunch/closed for a timezone-aware instant, excluding auctions."""
    if now.tzinfo is None:
        raise ValueError("A timezone-aware timestamp is required")
    stamp = pd.Timestamp(now.astimezone(UTC))
    day = pd.Timestamp(now.astimezone(HKT).date())
    if str(day.date()) in FULL_DAY_CLOSURES:
        return "closed"
    delayed = LATE_OPENS_HKT.get(str(day.date()))
    local = now.astimezone(HKT)
    if delayed and (local.hour, local.minute) < delayed:
        return "closed"
    cal = calendar()
    if not cal.is_session(day):
        return "closed"
    row = cal.schedule.loc[day]
    if stamp < row["open"] or stamp >= row["close"]:
        return "closed"
    if pd.notna(row["break_start"]) and row["break_start"] <= stamp < row["break_end"]:
        return "lunch"
    return "open"


def sessions(start: str, end: str) -> pd.DatetimeIndex:
    """Return XHKG sessions with evidenced historical full-day exceptions applied."""
    result = pd.DatetimeIndex(calendar().sessions).tz_localize(None)
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    if first < pd.Timestamp("2015-01-01") or last > pd.Timestamp("2027-12-31"):
        raise ValueError("Requested dates exceed the supported HK calendar range")
    result = result[(result >= first) & (result <= last)]
    return result.difference(pd.DatetimeIndex(FULL_DAY_CLOSURES))
