"""Locate existing local quote snapshots for either API entry point."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_SNAPSHOT_BYTES = 2_000_000
FUTURE_TOLERANCE_SECONDS = 5


def dashboard_profile(root: Path = ROOT) -> str:
    """Identify this checkout's public runtime configuration without exposing paths."""
    settings = {
        name: os.getenv(name, "").strip()
        for name in (
            "INDICATORLAB_LIVE_SOURCE",
            "INDICATORLAB_LIVE_HK_DIR",
            "INDICATORLAB_HSI_ROSTER",
            "INDICATORLAB_LIVE_HK_TABLE",
            "AWS_REGION",
            "INDICATORLAB_API_BASE_URL",
            "INDICATORLAB_CORS_ORIGINS",
            "INDICATORLAB_ATTENTION_ENABLED",
        )
    }
    value = json.dumps([str(root.resolve()), settings], sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def local_quote_directory(root: Path = ROOT) -> Path:
    """Respect an explicit directory, otherwise use the newest valid local feed.

    Args:
        root: Project root, overridden by offline tests.

    Returns:
        The quote directory. A fresh installation defaults to the normal local
        collector output, so a later first poll can be read without reconfiguration.
    """
    configured = os.getenv("INDICATORLAB_LIVE_HK_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else root / path
    candidates = [
        root / "data/live_hk_week4",
        root / "data/live_hk/current",
        root.parent / "indicatorlab-clean/data/live_hk/current",
    ]
    observed = []
    existing = []
    now = datetime.now(UTC)
    for directory in candidates:
        path = directory / "latest.json"
        if not path.is_file():
            continue
        existing.append(directory)
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_SNAPSHOT_BYTES + 1)
            if len(raw) > MAX_SNAPSHOT_BYTES:
                continue
            rows = json.loads(raw)
            if not isinstance(rows, list):
                continue
            times = []
            for row in rows:
                try:
                    stamp = datetime.fromisoformat(row["ts_received"])
                    if stamp.tzinfo is not None and stamp <= now + timedelta(
                        seconds=FUTURE_TOLERANCE_SECONDS
                    ):
                        times.append(stamp.astimezone(UTC))
                except (KeyError, TypeError, ValueError):
                    continue
            if times:
                observed.append((max(times), directory))
        except (OSError, TypeError, ValueError):
            continue
    if observed:
        return max(observed, key=lambda item: item[0])[1]
    return existing[0] if existing else candidates[1]
