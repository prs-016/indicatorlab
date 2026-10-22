"""Wikipedia attention data helpers."""
import pandas as pd
import requests
from urllib.parse import quote

PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{title}/daily/{start}/{end}"
)
USER_AGENT = {"User-Agent": "DS3-IndicatorLab/1.0 (your-email@example.com)"}
REQUEST_TIMEOUT_S = 30


def pageviews(title: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Return daily user pageviews for an English Wikipedia article.

    Days with zero views are filled in with 0 (the API omits them).
    Index is a daily DatetimeIndex from start to end inclusive.
    Raises requests.HTTPError on 403 (no User-Agent) or 404 (wrong title).
    """
    url = PAGEVIEWS_URL.format(
        title=quote(title, safe=""), start=f"{start:%Y%m%d}", end=f"{end:%Y%m%d}"
    )
    r = requests.get(url, headers=USER_AGENT, timeout=REQUEST_TIMEOUT_S)
    r.raise_for_status()
    items = r.json()["items"]
    views = pd.Series({pd.Timestamp(i["timestamp"][:8]): i["views"] for i in items})
    return views.reindex(pd.date_range(start, end, freq="D"), fill_value=0)