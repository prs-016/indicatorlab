"""Google Trends alternatives (Week 2, James step 7): pull GDELT news volume and compare it with page views.

GDELT DOC 2.0 (free, no key) covers Jan 2017 onward and asks for at most one request every 5 seconds.
`gdelt_daily` returns raw article counts per day for a query; `tracking_correlation` compares any
weekly series with weekly Wikipedia views on levels and on week-over-week log changes.
"""
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from src.wiki_attention import user_agent, weekly

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_RETRY_WAITS_S = [6, 30, 90]   # GDELT asks for one request every 5 seconds; back off when refused
REQUEST_TIMEOUT_S = 60


def gdelt_daily(query: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Daily number of news articles GDELT matched to `query` (timelinevolraw), start..end inclusive."""
    params = {"query": query, "mode": "timelinevolraw", "format": "json", "timelinesmooth": 0,
              "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959"}
    for wait in [0, *GDELT_RETRY_WAITS_S]:
        time.sleep(wait)
        r = requests.get(GDELT_URL, params=params, headers=user_agent(), timeout=REQUEST_TIMEOUT_S)
        if r.status_code != 429 and r.text.lstrip().startswith("{"):   # else: "please limit requests"
            break
    else:
        raise RuntimeError(f"GDELT kept refusing: HTTP {r.status_code} {r.text[:120]}")
    r.raise_for_status()
    points = r.json()["timeline"][0]["data"]
    s = pd.Series({pd.Timestamp(p["date"][:8]): p["value"] for p in points}, dtype=float)
    return s.reindex(pd.date_range(start, end, freq="D"), fill_value=0.0)


def tracking_correlation(other_weekly: pd.Series, views_daily: pd.Series) -> dict:
    """Pearson correlation of a weekly series with weekly views: levels, and week-over-week log changes."""
    both = pd.concat([other_weekly.rename("x"), weekly(views_daily).rename("v")], axis=1, join="inner").dropna()
    both = both[(both > 0).all(axis=1)]
    dl = np.log(both).diff().dropna()
    return {"weeks": len(both), "corr_level": both["x"].corr(both["v"]), "corr_change": dl["x"].corr(dl["v"]),
            "corr_level_spearman": both["x"].corr(both["v"], method="spearman")}


def cached_series(path: Path, pull: Callable[[], pd.Series]) -> pd.Series:
    """Read a date-indexed series from `path`, or call `pull()` and save its result there first."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pull().rename_axis("date").to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]


def trendspy_weekly(term: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Google Trends weekly interest (0-100) via the unofficial trendspy scraper, relabelled to Mondays.

    Google weeks run Sunday-Saturday; each is labelled by the Monday after its first day. Exploring
    only: trendspy scrapes Google's website and must never feed final results.
    """
    from trendspy import Trends
    df = Trends().interest_over_time([term], timeframe=f"{start:%Y-%m-%d} {end:%Y-%m-%d}")
    s = df.iloc[:, 0].astype(float)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None) + pd.Timedelta(days=1)
    return s
