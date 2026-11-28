"""Explicit optional Vibe checkout selection for portable offline integration tests."""

import os
from pathlib import Path

import pytest


def vibe_checkout() -> Path:
    """Return an existing configured Vibe root, or skip only its integration test."""
    value = os.environ.get("VIBE_TRADING_ROOT")
    if not value:
        pytest.skip("Set VIBE_TRADING_ROOT to run original Vibe IC/cost integration")
    path = Path(value).expanduser().resolve()
    if not (path / "agent").is_dir():
        pytest.fail("Configured VIBE_TRADING_ROOT does not contain agent/")
    return path
