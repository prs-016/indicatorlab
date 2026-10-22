"""Wikipedia attention data helpers."""
import pandas as pd
import requests
from urllib.parse import quote
import numpy as np

SPIKE_RATIO = 1.5        # at least 1.5x the baseline
SPIKE_RZ = 2.0           # robust z-score threshold
BASELINE_WEEKS = 8       # rolling median window
RZ_MAD_SCALE = 1.4826    # makes MAD comparable to a std dev

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



def flag_spikes(views: pd.Series) -> pd.DataFrame:
    """Flag spike weeks in a weekly series for ONE ticker.

    baseline = median of the previous BASELINE_WEEKS weeks (excludes week t).
    abnormal = log(views / baseline).
    rz = robust z-score of abnormal vs its own history (median/MAD).
    spike = abnormal >= log(SPIKE_RATIO) and rz >= SPIKE_RZ.
    The first BASELINE_WEEKS weeks have no baseline and are never flagged.
    """
    base = views.shift(1).rolling(BASELINE_WEEKS).median()
    abnormal = np.log(views / base)
    med = abnormal.median()
    mad = (abnormal - med).abs().median()
    rz = (abnormal - med) / (RZ_MAD_SCALE * mad)
    spike = (abnormal >= np.log(SPIKE_RATIO)) & (rz >= SPIKE_RZ)
    return pd.DataFrame(
        {"views": views, "baseline": base, "abnormal": abnormal, "rz": rz, "spike": spike}
    )