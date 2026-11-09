"""Where the Reddit routes get their data: the research attention tables, from local disk or S3.

`INDICATORLAB_DATA_URI` names the folder holding the processed parquet files, either a local path
(default: data/reddit/processed) or ``s3://<bucket>/processed`` on AWS. Files are read with
`src.storage` (pyarrow), kept in memory, and re-read after CACHE_TTL_S so a new pipeline run shows up
within minutes without a restart. Only research files are loaded; holdout weeks never enter memory.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

import pandas as pd
from fastapi import HTTPException

from src import config, storage
from src.reddit import settings
from src.reddit.reddit_weekly import ATTENTION_OUT
from src.reddit.utils import get_logger

log = get_logger("api", None)

DATA_URI_ENV = "INDICATORLAB_DATA_URI"
CACHE_TTL_S = 600            # re-read the tables at most every 10 minutes
_lock = threading.Lock()
_cache: dict[str, RedditData] = {}


def data_uri() -> str:
    """The processed-data folder from the environment (local default for development and tests)."""
    return os.environ.get(DATA_URI_ENV, str(settings.PROCESSED)).rstrip("/")


def research_cutoff() -> pd.Timestamp:
    """Weeks must end before the holdout date: week (Monday) + 6 days < holdout_start."""
    return pd.Timestamp(config.holdout_start()) - pd.Timedelta(days=6)


def _read(uri: str, stem: str) -> pd.DataFrame:
    """One research table with `week` as a date, holdout weeks dropped even if a file holds them."""
    df = storage.read_parquet(f"{uri}/{stem}.parquet")
    week = pd.to_datetime(df["week"])
    df = df[week < research_cutoff()].copy()
    df["week"] = pd.to_datetime(df["week"]).dt.date
    df["market"] = df["market"].str.lower()
    return df.reset_index(drop=True)


@dataclass
class RedditData:
    """The three research tables behind /reddit/*, plus when they were loaded."""

    weekly: pd.DataFrame
    by_type: pd.DataFrame
    top_posts: pd.DataFrame
    loaded_at: float = field(default_factory=time.monotonic)

    @classmethod
    def load(cls, uri: str) -> RedditData:
        """Read reddit_weekly, reddit_weekly_by_type and reddit_top_posts from `uri`."""
        return cls(_read(uri, ATTENTION_OUT["combined"]), _read(uri, ATTENTION_OUT["by_type"]),
                   _read(uri, ATTENTION_OUT["top_posts"]))

    def tickers(self, market: str) -> set[str]:
        """Tickers with any weekly row in `market`."""
        return set(self.weekly.loc[self.weekly["market"] == market, "ticker"])


def get_reddit_data() -> RedditData:
    """FastAPI dependency: the cached tables, reloaded once they are older than CACHE_TTL_S."""
    uri = data_uri()
    with _lock:
        hit = _cache.get(uri)
        if hit is None or time.monotonic() - hit.loaded_at > CACHE_TTL_S:
            try:
                _cache[uri] = hit = RedditData.load(uri)
            except (FileNotFoundError, OSError) as e:
                if hit is None:
                    raise HTTPException(503, f"Reddit tables are not published yet at {uri}") from e
                log.warning("reload of %s failed, serving the previous copy: %s", uri, e)
                hit.loaded_at = time.monotonic()
    return hit
