"""Offline India activation checks; post text and prices are never downloaded."""

import csv
import hashlib
import json
import socket
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src import config
from src.reddit import match_tickers as matcher

ROOT = Path(__file__).resolve().parents[2]
SURVEY = ROOT / "config/india_reddit_survey.proposed"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Offline configuration test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def tickers(text, body="", market="IN"):
    return {row["ticker"] for row in matcher.match_post(text, body, market=market)}


def test_other_markets_and_shared_settings_preserved():
    baseline = json.loads(
        (ROOT / "tests/fixtures/india_reddit_preserved_config.json").read_text()
    )
    cfg = config.load()

    def digest(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, default=str).encode()
        ).hexdigest()

    assert digest(cfg["markets"]["US"]) == baseline["US"]
    assert digest(cfg["markets"]["HK"]) == baseline["HK"]
    assert (
        digest({k: v for k, v in cfg.items() if k != "markets"}) == baseline["shared"]
    )
    assert config.spike_rule()["baseline_weeks"] == 8


def test_activated_sources_pass_saved_weekly_evidence():
    sources = config.subreddits("IN")
    assert set(sources) == {"IndianStockMarket", "IndiaInvestments", "IndianStreetBets"}
    rows = list(csv.DictReader((SURVEY / "weekly_counts_2024.csv").open(newline="")))
    for source in sources:
        weeks = [
            r for r in rows if r["subreddit"] == source and r["full_week"] == "True"
        ]
        assert len(weeks) == 52
        assert all(
            r["request_coverage"] == "complete" and int(r["archived_posts"]) >= 20
            for r in weeks
        )
    conditional = [
        r
        for r in rows
        if r["subreddit"] == "DalalStreetTalks" and r["full_week"] == "True"
    ]
    assert min(int(r["archived_posts"]) for r in conditional) == 19
    assert "DalalStreetTalks" not in sources
    assert all(
        info["type"] == "general" and info["ticker"] is None
        for info in config.subreddit_map("IN").values()
    )


def test_exact_proposed_roster_and_only_supported_rules_activated():
    proposal = yaml.safe_load((SURVEY / "matching_rules.proposed.yaml").read_text())[
        "markets"
    ]["IN"]["stocks"]
    assert len(config.stocks("IN")) == 100 and set(config.stocks("IN")) == set(proposal)
    for symbol, stock in config.stocks("IN").items():
        expected = dict(proposal[symbol]["match"])
        expected.pop("contextual_name", None)
        assert stock["match"] == expected
        assert stock["reddit"] == {"product": [], "stock": []}


@pytest.mark.parametrize("ticker", config.tickers("IN"))
def test_every_current_company_has_qualified_and_legal_name_recognition(ticker):
    # Synthetic text generated from the already recorded official current identities.
    symbol = ticker.removesuffix(".NS")
    assert tickers("Discussing " + ticker) == {ticker}
    assert tickers("Discussing NSE:" + symbol) == {ticker}
    assert ticker in tickers(config.stocks("IN")[ticker]["name"])


@pytest.mark.parametrize(
    "text",
    [
        "TCS is tax collected at source",
        "TCS shares",
        "RIL stock",
        "Reliance shares",
        "SBI shares",
        "SBI Life is not the bank",
        "SBI Cards earnings",
        "ITC input tax credit",
        "I have an IDEA",
        "BSE market breadth",
        "HAL BEL ABB LT",
        "INFY $INFY",
        "$TCS $RELIANCE",
        "DMart discounts",
        "IndiGo flight delayed",
        "prefixNSE:TCSsuffix",
        "NSE:TCSsuffix",
        "prefixTCS.NS",
    ],
)
def test_ambiguous_bare_or_unverified_aliases_not_enabled(text):
    assert tickers(text) == set()


def test_tata_passenger_company_stem_is_not_attributed_to_commercial_entity():
    assert tickers("Tata Motors passenger vehicles") == {"TMPV.NS"}


def test_distinct_tata_entities_do_not_share_a_parent_stem():
    assert tickers("Tata Motors Ltd.") == {"TMCV.NS"}
    assert tickers("Tata Motors Passenger Vehicles Ltd.") == {"TMPV.NS"}


def test_case_boundaries_urls_signatures_and_deduplication():
    assert tickers("NSE:TCS earnings", "TCS.NS share results") == {"TCS.NS"}
    assert matcher.match_post("NSE:TCS", "TCS.NS", market="IN")[0]["found_in"] == "both"
    assert tickers("nse:tcs") == set()
    assert tickers("https://example.com/NSE:TCS", "Positions: NSE:INFY") == set()
    assert tickers("Tata Consultancy Services reported earnings") == {"TCS.NS"}


def posts(market="IN", text="NSE:TCS results"):
    return pd.DataFrame(
        {
            "id": ["synthetic-post"],
            "subreddit": ["indiainvestments"],
            "subreddit_type": ["general"],
            "owner_ticker": [None],
            "market": [market],
            "created_utc": [1704153600],
            "created_dt": [pd.Timestamp("2024-01-02", tz="UTC")],
            "date": ["2024-01-02"],
            "title": [text],
            "selftext": [""],
            "score": [1],
            "num_comments": [0],
            "permalink": [""],
            "day_status": ["complete"],
            "removed_by_category": [None],
            "removed_flag": [False],
            "period": ["research"],
        }
    )


def test_existing_pipeline_routes_explicit_india_rows():
    rows = matcher.match_subreddit(posts())
    assert rows["ticker"].tolist() == ["TCS.NS"]
    assert rows["market"].tolist() == ["IN"]
    assert rows["subreddit_type"].tolist() == ["general"]
    assert matcher.match_subreddit(posts(text="No company reference here")).empty


def test_india_multi_ticker_lists_keep_existing_threshold():
    rows = matcher.match_subreddit(
        posts(text="NSE:RELIANCE NSE:TCS NSE:INFY NSE:SBIN NSE:AXISBANK")
    )
    assert len(rows) == 5 and rows["multi_ticker_list"].all()
    assert set(rows["n_tickers_in_post"]) == {5}


def test_cross_market_isolation_and_us_default():
    assert matcher.match_post("AAPL", "")[0]["ticker"] == "AAPL"
    assert tickers("NSE:TCS", market="US") == set()
    assert tickers("AAPL $AAPL") == set()
    assert tickers("NSE:TCS", market="HK") == set()


def test_mixed_or_unknown_market_rows_rejected():
    with pytest.raises(ValueError, match="One explicit market"):
        matcher.match_subreddit(
            pd.concat([posts(), posts(market="US")], ignore_index=True)
        )
    with pytest.raises(KeyError):
        matcher.match_subreddit(posts(market="UNKNOWN"))
