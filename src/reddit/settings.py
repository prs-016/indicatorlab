"""Reddit pipeline settings: data/result paths plus Reddit values read from config.yaml.

All paths are under the repository root so every module runs as
``python -m src.reddit.<module>`` from the repo root. ``data/``, ``results/`` and
``logs/`` are git-ignored; raw archives stay local.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src import config

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data" / "reddit"
RAW = DATA / "raw"
RAW_ARCTIC = RAW / "arctic_shift"
RAW_COVERAGE = RAW / "coverage"
RAW_PRICES = RAW / "prices"
PROCESSED = DATA / "processed"
POSTS = PROCESSED / "posts"   # one parquet file per subreddit
VALIDATION = DATA / "validation"
RESULTS = ROOT / "results" / "reddit"
CHARTS = RESULTS / "charts"
TABLES = RESULTS / "tables"
STRATEGY_LOGS = RESULTS / "strategy_logs"
LOGS = ROOT / "logs" / "reddit"
DASHBOARD = ROOT / "frontend" / "reddit_dashboard"

MANIFEST = RAW / "manifest.csv"

MARKET = "US"
_REDDIT = config.load()["reddit"]
_ARCTIC = _REDDIT["arctic_shift"]

ARCTIC_BASE_URL = _ARCTIC["base_url"]
ARCTIC_MIN_INTERVAL_S = _ARCTIC["min_interval_s"]
ARCTIC_RETRY_WAIT_S = tuple(_ARCTIC["retry_wait_s"])
ARCTIC_MAX_RETRIES = _ARCTIC["max_retries"]

# Week 1 investor subreddits (text-matched); Week 2 adds product/stock/sector ones via config.subreddit_map.
SUBREDDITS = config.subreddits(MARKET, kinds=("general",))

START_DATE = _REDDIT["collect_start"]
HOLDOUT_START = config.holdout_start()


def default_end_date() -> date:
    """Last *complete* UTC calendar day (yesterday in UTC)."""
    return datetime.now(timezone.utc).date() - timedelta(days=1)


# Ticker -> company display name. Matching patterns live in config.yaml (markets.<m>.stocks.<t>.match).
TICKERS = {t: cfg["name"] for t, cfg in config.stocks(MARKET).items()}

# Week 1 spike rule (2x the median of the previous 4 weeks), kept so Week 1 results reproduce.
# Week 2 analyses use the shared rule in config.yaml (`spike`).
SPIKE_THRESHOLD = 2.0
SPIKE_WINDOW = 4
