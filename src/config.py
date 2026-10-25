"""Load the shared Indicator Lab config (``config.yaml`` at the repo root).

Every market, stock, subreddit, Wikipedia title and benchmark lives in that file, so adding
India or Hong Kong is a config change. Typical use::

    from src import config
    config.tickers("US")                  # ['AAPL', 'MSFT', ...]
    config.subreddit_map("US")["iphone"]  # {'market': 'US', 'type': 'product', 'ticker': 'AAPL', ...}
    config.holdout_start()                # date(2025, 10, 1)
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

# Subreddit types: product/stock subreddits belong to one company; general/sector ones are text-matched.
STOCK_SUBREDDIT_TYPES = ("product", "stock")
SHARED_SUBREDDIT_TYPES = ("general", "sector")


@lru_cache(maxsize=None)
def load(path: Path = CONFIG_PATH) -> dict:
    """Parse the YAML config once and cache it."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def holdout_start() -> date:
    """First holdout day; research data must be strictly earlier."""
    return load()["holdout_start"]


def markets() -> list[str]:
    """Market codes in config order, e.g. ['US', 'IN', 'HK']."""
    return list(load()["markets"])


def market(code: str) -> dict:
    """The config block of one market (raises KeyError for an unknown code)."""
    return load()["markets"][code]


def stocks(code: str = "US") -> dict[str, dict]:
    """Ticker -> stock config for one market."""
    return market(code).get("stocks") or {}


def tickers(code: str = "US") -> list[str]:
    """Tracked tickers of one market, in config order."""
    return list(stocks(code))


def benchmark(code: str = "US") -> str:
    """Yahoo symbol of the market index used as benchmark (SPY, ^NSEI, ^HSI)."""
    return market(code)["benchmark"]


def spike_rule() -> dict:
    """Parameters of the shared spike rule (see the `spike` block in config.yaml)."""
    return dict(load()["spike"])


def subreddit_map(code: str = "US") -> dict[str, dict]:
    """Lower-cased subreddit name -> {market, subreddit, type, ticker} for one market.

    `ticker` is None for general and sector subreddits, whose posts are matched by text.
    A subreddit listed twice raises ValueError, because each post must have one owner.
    """
    out: dict[str, dict] = {}

    def add(name: str, kind: str, ticker: str | None) -> None:
        key = name.lower()
        if key in out:
            raise ValueError(f"r/{name} is listed twice in config.yaml ({out[key]['type']} and {kind})")
        out[key] = {"market": code, "subreddit": name, "type": kind, "ticker": ticker}

    shared = market(code).get("reddit") or {}
    for kind in SHARED_SUBREDDIT_TYPES:
        for name in shared.get(kind) or []:
            add(name, kind, None)
    for ticker, cfg in stocks(code).items():
        for kind in STOCK_SUBREDDIT_TYPES:
            for name in (cfg.get("reddit") or {}).get(kind) or []:
                add(name, kind, ticker)
    return out


def subreddits(code: str = "US", kinds: tuple[str, ...] | None = None) -> list[str]:
    """Subreddit names of one market, optionally only some types (general, sector, product, stock)."""
    return [v["subreddit"] for v in subreddit_map(code).values() if kinds is None or v["type"] in kinds]
