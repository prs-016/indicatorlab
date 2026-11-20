"""Week4-only daily HK weather reconciliation; historical Week3 code is untouched."""

import pandas as pd

from src.hk.calendar import sessions as base_sessions

# Exchange notices confirm these full-day closures. Libraries differ by vintage;
# applying set subtraction is idempotent when the library already includes one.
WEATHER_CLOSURES = {
    "2016-08-02": "https://www.hkex.com.hk/News/Market-Communications/2016/1608022news?sc_lang=en",
    "2016-10-21": "https://www.hkex.com.hk/News/Market-Communications/2016/1610212news?sc_lang=en",
    "2017-08-23": "https://www.hkex.com.hk/News/Market-Communications/2017/1708232news?sc_lang=en",
    "2023-07-17": "https://www.hkex.com.hk/News/Market-Communications/2023/2307172news?sc_lang=en",
}


def sessions(start, end):
    """Actual sessions after evidenced weather closures, with no fabricated prices."""
    return base_sessions(start, end).difference(pd.DatetimeIndex(WEATHER_CLOSURES))
