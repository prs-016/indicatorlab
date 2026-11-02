"""Wikipedia attention: daily page views, Monday-labelled weekly totals and the shared spike rule.

Titles, languages and spike parameters come from config.yaml; nothing here names a stock or
a Wikipedia language. The Wikimedia APIs require a User-Agent with a contact address, read from
the WIKIMEDIA_CONTACT environment variable (put it in .env, see .env.example).
"""
import os
from functools import lru_cache
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src import config

PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "{project}/all-access/{agent}/{title}/daily/{start}/{end}"
)
ACTION_API_URL = "https://{lang}.wikipedia.org/w/api.php"
REQUEST_TIMEOUT_S = 30
MAX_RETRIES = 5           # timeouts and 429/5xx answers are retried with exponential backoff
RETRY_BACKOFF_S = 2
ARTICLE_NAMESPACE = 0     # MediaWiki namespace of encyclopedia articles

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=MAX_RETRIES, backoff_factor=RETRY_BACKOFF_S, status_forcelist=[429, 500, 502, 503, 504])))


@lru_cache(maxsize=1)
def _load_env_once() -> None:
    load_dotenv()


def user_agent() -> dict:
    """User-Agent header with the contact address from WIKIMEDIA_CONTACT (raises if it is unset).

    .env is read once per process; a variable already set in the environment wins.
    """
    _load_env_once()
    contact = os.environ.get("WIKIMEDIA_CONTACT")
    if not contact:
        raise RuntimeError("Set WIKIMEDIA_CONTACT in .env: Wikimedia asks every client for a contact address")
    return {"User-Agent": f"DS3-IndicatorLab/1.0 ({contact})"}


def project(lang: str) -> str:
    """Wikimedia project name for a language code, e.g. 'en' -> 'en.wikipedia'."""
    return f"{lang}.wikipedia"


def pageviews(title: str, start: pd.Timestamp, end: pd.Timestamp, lang: str = "en",
              missing_ok: bool = False) -> pd.Series:
    """Return daily user pageviews for one Wikipedia page title.

    Days with zero views are filled in with 0 (the API omits them).
    Index is a daily DatetimeIndex from start to end inclusive.
    Raises requests.HTTPError on 403 (no User-Agent) or 404 (wrong title), unless
    `missing_ok` is set, in which case a 404 returns all zeros (a redirect nobody visited).
    """
    url = PAGEVIEWS_URL.format(
        project=project(lang), agent=config.load()["wikipedia"]["agent"],
        title=quote(title, safe=""), start=f"{start:%Y%m%d}", end=f"{end:%Y%m%d}",
    )
    days = pd.date_range(start, end, freq="D")
    r = SESSION.get(url, headers=user_agent(), timeout=REQUEST_TIMEOUT_S)
    if missing_ok and r.status_code == 404:
        return pd.Series(0, index=days, dtype="int64")
    r.raise_for_status()
    items = r.json()["items"]
    views = pd.Series({pd.Timestamp(i["timestamp"][:8]): i["views"] for i in items}, dtype="int64")
    return views.reindex(days, fill_value=0)


def redirects(title: str, lang: str = "en") -> list[str]:
    """Titles of the article pages that redirect to `title` (underscored, like `title`).

    Raises ValueError if `title` itself does not exist.
    """
    params = {"action": "query", "prop": "redirects", "titles": title, "rdnamespace": ARTICLE_NAMESPACE,
              "rdlimit": "max", "format": "json", "formatversion": 2}
    out = []
    while True:
        r = SESSION.get(ACTION_API_URL.format(lang=lang), params=params, headers=user_agent(),
                         timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        for page in data["query"]["pages"]:
            if page.get("missing"):
                raise ValueError(f"no {lang} Wikipedia article {title!r}")
            out += [rd["title"].replace(" ", "_") for rd in page.get("redirects", [])]
        if "continue" not in data:
            return out
        params.update(data["continue"])


def article_views(title: str, start: pd.Timestamp, end: pd.Timestamp, lang: str = "en") -> pd.Series:
    """Daily views of an article: its own title plus, if the config says so, every redirect to it.

    Page views are counted under the title a reader requested, so after a rename the old title's
    views sit under the redirect. Summing them keeps the history of renamed articles. A title with
    no views in the window (e.g. the current name before the rename) counts as zeros, but an article
    that does not exist raises ValueError.
    """
    titles = [title]
    if config.load()["wikipedia"]["include_redirects"]:
        titles += redirects(title, lang)   # also checks that `title` exists
    return sum(pageviews(t, start, end, lang, missing_ok=True) for t in titles)


def week_start(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Monday of the week containing each date (the team's week label)."""
    d = pd.DatetimeIndex(index).normalize()
    return d - pd.to_timedelta(d.dayofweek, unit="D")


def weekly(daily: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Sum daily values into Monday-labelled weeks, keeping only weeks with all 7 days present."""
    wk = week_start(daily.index)
    n_days = pd.Series(1, index=daily.index).groupby(wk).sum()
    out = daily.groupby(wk).sum()
    out.index.name = "week"
    return out[n_days.reindex(out.index) == 7]


def past_median_mad(a: pd.Series, min_history: int) -> tuple[pd.Series, pd.Series]:
    """Median and MAD of the non-missing values strictly before each position.

    Both are NaN until `min_history` earlier values exist.
    """
    vals = a.to_numpy(dtype=float)
    med = np.full(len(vals), np.nan)
    mad = np.full(len(vals), np.nan)
    for t in range(len(vals)):
        past = vals[:t][~np.isnan(vals[:t])]
        if len(past) >= min_history:
            med[t] = np.median(past)
            mad[t] = np.median(np.abs(past - med[t]))
    return pd.Series(med, index=a.index), pd.Series(mad, index=a.index)


def flag_spikes(x: pd.Series, rule: dict | None = None) -> pd.DataFrame:
    """Flag spike weeks in a weekly series for ONE ticker and source, using past weeks only.

    The shared team rule (parameters in config.yaml `spike`; `rule` overrides any of them):
        baseline = median of the previous `baseline_weeks` weeks (week t excluded)
        abnormal = log((x + offset) / (baseline + offset))
        rz       = (abnormal - med) / (mad_scale * mad), where med and mad are the median and MAD
                   of abnormal over weeks before t, once `rz_min_history` of them exist
        spike    = abnormal >= log(ratio) and rz >= rz_threshold
    Zero handling: `offset` keeps zero baselines finite (a 0 -> 3 jump gives log(4)). A zero MAD
    (most past weeks with the same abnormal value) leaves rz undefined, so that week is not flagged.
    Missing weeks must be NaN rows so `shift` and `rolling` count weeks; any undefined input gives
    spike = False. Same rule and output as Joshua's src/reddit/spike_rule.py.
    """
    r = {**config.spike_rule(), **(rule or {})}
    off = r["offset"]
    base = x.shift(1).rolling(r["baseline_weeks"], min_periods=r["baseline_weeks"]).median()
    ratio = (x + off) / (base + off)
    abnormal = np.log(ratio)
    med, mad = past_median_mad(abnormal, r["rz_min_history"])
    rz = (abnormal - med) / (r["mad_scale"] * mad.where(mad > 0))
    spike = (abnormal >= np.log(r["ratio"])) & (rz >= r["rz_threshold"])
    return pd.DataFrame({"baseline": base, "ratio": ratio, "abnormal": abnormal, "rz": rz,
                         "spike": spike.fillna(False).astype(bool)}, index=x.index)
