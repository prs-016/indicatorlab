"""Shared helpers: logging, UTC conversions, atomic file writes."""
from __future__ import annotations

import gzip
import json
import logging
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.reddit import settings

# Placeholder bodies Reddit leaves when a post is removed or deleted.
REMOVED_TEXT = {"[removed]", "[deleted]", "[removed by reddit]"}


def get_logger(name: str, logfile: str | None = None) -> logging.Logger:
    """Logger writing UTC-stamped lines to stdout and, if given, to logs/reddit/<logfile>."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%S")
    fmt.converter = lambda *a: datetime.now(timezone.utc).timetuple()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if logfile:
        settings.LOGS.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(settings.LOGS / logfile)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with microseconds and a Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def day_bounds_epoch(d: date) -> tuple[int, int]:
    """[start, end) epoch seconds for a UTC calendar day."""
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def daterange(start: date, end: date):
    """Inclusive date range."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def epoch_to_iso(ts: float) -> str:
    """Epoch seconds as an ISO-8601 UTC string (second resolution)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` through a temp file and rename, so readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json_gz(path: Path, obj) -> None:
    """Atomically write `obj` as gzip-compressed UTF-8 JSON."""
    atomic_write_bytes(path, gzip.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8"), 6))


def read_json_gz(path: Path):
    """Read a gzip-compressed JSON file written by write_json_gz."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)
