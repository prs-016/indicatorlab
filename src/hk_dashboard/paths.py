"""Explicit HK inputs and bounded discovery of this workspace's existing data."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METADATA = ROOT / "config/hk_final_symbol_metadata.json"


def canonical(raw: str) -> str:
    """Normalize positive HK stock codes and reject foreign or injected symbols."""
    if not isinstance(raw, str):
        raise TypeError("HK ticker must be text")
    match = re.fullmatch(r"(?:(?:HK|HKEX):)?([0-9]{1,5})(?:\.HK)?", raw.strip().upper())
    if not match or int(match[1]) == 0:
        raise ValueError("Use an HK code such as 700 or 0700.HK")
    return f"{int(match[1]):04d}.HK"


def names() -> dict:
    """Return a new copy of the dated 95-name operational metadata."""
    result = json.loads(METADATA.read_text())["stocks"]
    return {canonical(key): value for key, value in result.items()}


def source_root() -> Path:
    """Use a configured data mount, otherwise this Mac's known HK research checkout."""
    configured = os.getenv("INDICATORLAB_HK_SOURCE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = [
        ROOT,
        ROOT.parent / "indicatorlab-Jack",
        ROOT.parent.parent / "indicatorlab-Jack",
    ]
    return next(
        (
            path
            for path in candidates
            if (path / "research/hk_market_history/coverage.csv").is_file()
        ),
        ROOT,
    )


def display_root() -> Path:
    """Return the separate ignored display cache, never the frozen research inputs."""
    value = os.getenv("INDICATORLAB_HK_DISPLAY_DIR", "").strip()
    return (
        Path(value).expanduser().resolve()
        if value
        else ROOT / "data/hk_dashboard/display"
    )


def quote_directories() -> list[Path]:
    """Candidate latest-state directories, not growing quote-history files."""
    configured = os.getenv("INDICATORLAB_LIVE_HK_DIR", "").strip()
    if configured:
        return [Path(configured).expanduser().resolve()]
    source = source_root()
    return [
        ROOT / "data/live_hk/current",
        source / "data/live_hk/current",
        source / "data/live_hk_week4",
        source.parent / "indicatorlab-clean/data/live_hk/current",
    ]
