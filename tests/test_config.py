"""The shared config loads, covers three markets and gives every subreddit exactly one owner."""
from datetime import date

import pytest

from src import config


def test_three_markets_with_benchmarks():
    assert config.markets() == ["US", "IN", "HK"]
    assert [config.benchmark(m) for m in config.markets()] == ["SPY", "^NSEI", "^HSI"]


def test_holdout_is_oct_1_2025():
    assert config.holdout_start() == date(2025, 10, 1)


def test_us_stocks_have_name_match_rules_and_wikipedia_title():
    assert len(config.tickers("US")) == 10
    for ticker, cfg in config.stocks("US").items():
        assert cfg["name"] and cfg["wikipedia"]["en"], ticker
        assert ticker in cfg["match"]["symbols"], ticker


def test_subreddit_map_types_and_owners():
    sm = config.subreddit_map("US")
    assert sm["iphone"] == {"market": "US", "subreddit": "iphone", "type": "product", "ticker": "AAPL"}
    assert sm["wallstreetbets"]["type"] == "general" and sm["wallstreetbets"]["ticker"] is None
    assert sm["hardware"]["type"] == "sector"   # covers NVDA, AMD and others, so text-matched
    assert set(config.subreddits("US", ("general",))) == {"stocks", "investing", "wallstreetbets"}


def test_duplicate_subreddit_is_rejected(monkeypatch):
    cfg = {"markets": {"US": {"reddit": {"general": ["stocks"]},
                              "stocks": {"AAPL": {"reddit": {"product": ["Stocks"]}}}}}}
    monkeypatch.setattr(config, "load", lambda: cfg)
    with pytest.raises(ValueError, match="listed twice"):
        config.subreddit_map("US")


def test_spike_rule_parameters():
    rule = config.spike_rule()
    assert rule["ratio"] == 1.5 and rule["rz_threshold"] == 2.0 and rule["baseline_weeks"] == 8
