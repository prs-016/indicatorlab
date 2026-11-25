"""One JSON cache for the /analyze flow: S3 on AWS, local disk for tests and laptops.

Keys follow the Shared contracts table, e.g. ``analyze/reddit_counts/us/NVDA.json``::

    from src.analyze.cache import cache_get, cache_put
    hit = cache_get(key, max_age=6 * 3600)     # None if missing or older than max_age seconds
    cache_put(key, obj)

Where entries live:
  INDICATORLAB_CACHE=local   data/analyze_cache/<key> under the repo (no AWS needed)
  otherwise                  <root>/<key>, root = INDICATORLAB_ROOT_URI, else s3://$INDICATORLAB_BUCKET,
                             else s3://indicatorlab-data (the bucket named in the contract)

Each file stores ``{"saved_at": <ISO UTC>, "obj": <the cached value>}`` so freshness is checked
without relying on S3 object timestamps.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from src import storage

CACHE_ENV = "INDICATORLAB_CACHE"
ROOT_ENV = "INDICATORLAB_ROOT_URI"       # same variables as src/reddit/pipeline.py
BUCKET_ENV = "INDICATORLAB_BUCKET"
DEFAULT_BUCKET = "indicatorlab-data"
LOCAL_ROOT = Path(__file__).resolve().parents[2] / "data" / "analyze_cache"


def cache_root() -> str:
    """Folder or bucket URI that cache keys are joined to."""
    if os.environ.get(CACHE_ENV, "").lower() == "local":
        return str(LOCAL_ROOT)
    root = os.environ.get(ROOT_ENV) or f"s3://{os.environ.get(BUCKET_ENV) or DEFAULT_BUCKET}"
    return root.rstrip("/")


def _uri(key: str) -> str:
    return f"{cache_root()}/{key.lstrip('/')}"


def cache_get(key: str, max_age: float | None):
    """The cached object for `key`, or None if missing or saved more than `max_age` seconds ago.

    `max_age=None` means the entry never expires (past spike weeks).
    """
    entry = storage.read_json(_uri(key))
    if not isinstance(entry, dict) or "obj" not in entry:
        return None
    if max_age is not None:
        try:
            saved = datetime.fromisoformat(entry["saved_at"])
        except (KeyError, TypeError, ValueError):
            return None
        if (datetime.now(UTC) - saved).total_seconds() > max_age:
            return None
    return entry["obj"]


def cache_put(key: str, obj) -> None:
    """Store `obj` (anything JSON-serialisable) under `key`, stamped with the current UTC time."""
    storage.write_json({"saved_at": datetime.now(UTC).isoformat(), "obj": obj}, _uri(key))
