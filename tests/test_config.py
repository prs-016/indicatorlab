"""The shared config loads, covers three markets and gives every subreddit exactly one owner."""
from datetime import date

import pytest

from src import config


def test_three_markets_with_benchmarks():
    assert config.markets() == ["US", "IN", "HK"]
    assert [config.benchmark(m) for m in config.markets()] == ["SPY", "^NSEI", "^HSI"]


def test_cutoff_and_team_split_are_the_week_4_values():
    assert config.holdout_start() == date(2026, 11, 1)          # research data runs through 2026-10-31
    split = config.load()["strategy"]["split"]
    assert split["train"] == [date(2016, 6, 1), date(2021, 12, 31)]
    assert split["test"] == [date(2022, 1, 1), date(2026, 10, 31)]
    assert split["test"][1] < config.holdout_start()            # the test window never reaches the cutoff


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
