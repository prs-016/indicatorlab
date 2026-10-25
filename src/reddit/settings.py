"""Reddit pipeline settings: data/result paths, subreddits, date range, tracked tickers.

All paths are under the repository root so every module runs as
``python -m src.reddit.<module>`` from the repo root. ``data/``, ``results/`` and
``logs/`` are git-ignored; raw archives stay local.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data" / "reddit"
RAW = DATA / "raw"
RAW_ARCTIC = RAW / "arctic_shift"
RAW_COVERAGE = RAW / "coverage"
RAW_PRICES = RAW / "prices"
PROCESSED = DATA / "processed"
VALIDATION = DATA / "validation"
RESULTS = ROOT / "results" / "reddit"
CHARTS = RESULTS / "charts"
TABLES = RESULTS / "tables"
STRATEGY_LOGS = RESULTS / "strategy_logs"
LOGS = ROOT / "logs" / "reddit"
DASHBOARD = ROOT / "frontend" / "reddit_dashboard"

MANIFEST = RAW / "manifest.csv"

ARCTIC_BASE_URL = "https://arctic-shift.photon-reddit.com/api"

SUBREDDITS = ["stocks", "investing", "wallstreetbets"]

START_DATE = date(2023, 1, 1)


def default_end_date() -> date:
    """Last *complete* UTC calendar day (yesterday in UTC)."""
    return datetime.now(timezone.utc).date() - timedelta(days=1)


# Ticker -> company display name. Matching rules live in src/reddit/match_tickers.py.
TICKERS = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "GOOGL": "Alphabet / Google",
    "AMD": "Advanced Micro Devices",
    "NFLX": "Netflix",
    "JPM": "JPMorgan Chase",
}

SPIKE_THRESHOLD = 2.0
SPIKE_WINDOW = 4
