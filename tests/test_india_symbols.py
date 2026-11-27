"""Offline checks for Final Week N1 and the resolver integration contract."""

import socket
from types import SimpleNamespace

import pandas as pd
import pytest
import yfinance as yf

from src.markets import india_symbols as subject
from src.markets.errors import SymbolLookupUnavailable, UnknownTicker


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Unexpected live provider request")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(yf, "Ticker", deny)
    monkeypatch.setattr(yf, "Search", deny)


@pytest.mark.parametrize(
    "raw", ["RELIANCE", "reliance", "RELIANCE.NS", "NSE:RELIANCE", " $reliance "]
)
def test_tracked_nse_aliases_resolve_without_provider(raw):
    assert subject.normalize_in(raw) == "RELIANCE.NS"


@pytest.mark.parametrize(
    "existing,expected",
    [({"RELIANCE.NS"}, "RELIANCE.NS"), ({"RELIANCE.BO"}, "RELIANCE.BO")],
)
def test_named_bse_prefers_nse_only_with_history(monkeypatch, existing, expected):
    checked = []

    def exists(symbol):
        checked.append(symbol)
        return symbol in existing

    monkeypatch.setattr(subject, "_history_exists", exists)
    assert subject.normalize_in("RELIANCE.BO") == expected
    assert checked == (
        ["RELIANCE.NS"] if expected.endswith(".NS") else ["RELIANCE.NS", "RELIANCE.BO"]
    )


@pytest.mark.parametrize("raw", ["500325", "500325.BO", "BSE:500325"])
def test_bse_code_maps_by_yfinance_name_to_tracked_nse(monkeypatch, raw):
    monkeypatch.setattr(
        subject, "_history_exists", {"500325.BO", "RELIANCE.NS"}.__contains__
    )
    monkeypatch.setattr(
        yf,
        "Ticker",
        lambda symbol: SimpleNamespace(
            get_info=lambda: {"longName": "Reliance Industries Limited"}
        ),
    )
    assert subject.normalize_in(raw) == "RELIANCE.NS"


@pytest.mark.parametrize(
    "matches,expected",
    [
        ([{"symbol": "OTHER.NS", "longname": "Example Ltd."}], "OTHER.NS"),
        ([{"symbol": "OTHER.NS", "longname": "Different Ltd."}], "123456.BO"),
        ([{"symbol": "OTHER.BO", "longname": "Example Ltd."}], "123456.BO"),
        ([], "123456.BO"),
        (
            [
                {"symbol": s, "longname": "Example Ltd."}
                for s in ("OTHER.NS", "AMBIG.NS")
            ],
            "123456.BO",
        ),
    ],
)
def test_bse_name_lookup_handles_untracked_no_match_and_ambiguity(
    monkeypatch, matches, expected
):
    monkeypatch.setattr(
        subject, "_history_exists", {"123456.BO", "OTHER.NS"}.__contains__
    )
    monkeypatch.setattr(
        yf,
        "Ticker",
        lambda symbol: SimpleNamespace(
            get_info=lambda: {"shortName": "Example Limited"}
        ),
    )
    monkeypatch.setattr(
        yf, "Search", lambda name, **kwargs: SimpleNamespace(quotes=matches)
    )
    assert subject.normalize_in("123456") == expected


def test_bse_code_stays_bse_when_nse_name_match_has_no_history(monkeypatch):
    monkeypatch.setattr(subject, "_history_exists", {"500325.BO"}.__contains__)
    monkeypatch.setattr(
        yf,
        "Ticker",
        lambda symbol: SimpleNamespace(
            get_info=lambda: {"longName": "Reliance Industries Limited"}
        ),
    )
    assert subject.normalize_in("500325") == "500325.BO"


@pytest.mark.parametrize(
    "raw",
    ["", "garbage !", "NSE:RELIANCE.BO", "12345", "NSE:500325", "RELIANCE.US", None],
)
def test_malformed_input_uses_shared_unknown_ticker(raw):
    with pytest.raises(UnknownTicker):
        subject.normalize_in(raw)


@pytest.mark.parametrize("raw", ["RELIANCEXYZ", "123456", "RELIANCEXYZ.BO"])
def test_well_formed_but_unlisted_input_is_unknown(monkeypatch, raw):
    monkeypatch.setattr(subject, "_history_exists", lambda _: False)
    with pytest.raises(UnknownTicker):
        subject.normalize_in(raw)


def test_non_roster_nse_resolves_for_james_fallback(monkeypatch):
    monkeypatch.setattr(subject, "_history_exists", {"OUTSIDE.NS"}.__contains__)
    assert subject.normalize_in("OUTSIDE") == "OUTSIDE.NS"
    assert "OUTSIDE.NS" not in subject.india_names()


def test_history_uses_bounded_yfinance_request_and_surfaces_outage(monkeypatch):
    def history(**kwargs):
        assert kwargs["raise_errors"] and kwargs["timeout"] == 5
        return pd.DataFrame({"Close": [1.0]})

    monkeypatch.setattr(yf, "Ticker", lambda _: SimpleNamespace(history=history))
    assert subject.normalize_in("OUTSIDE") == "OUTSIDE.NS"

    def outage(**kwargs):
        raise TimeoutError

    monkeypatch.setattr(yf, "Ticker", lambda _: SimpleNamespace(history=outage))
    with pytest.raises(SymbolLookupUnavailable):
        subject.normalize_in("OUTSIDE")


def test_all_100_have_official_names_exact_contract_and_current_titles():
    names = subject.india_names()
    assert len(names) == 100
    titles = subject.load_india_titles().current_titles()
    for ticker, entry in names.items():
        assert set(entry) == {
            "name",
            "short_name",
            "aliases",
            "ambiguous",
            "wiki_en",
            "wiki_hi",
        }
        assert all(entry[k] for k in ("name", "short_name", "aliases"))
        assert entry["short_name"] in entry["aliases"]
        assert entry["wiki_en"] == titles.get(ticker, {}).get("en")
        assert entry["wiki_hi"] == titles.get(ticker, {}).get("hi")
    assert names["RELIANCE.NS"]["aliases"] == ["Reliance", "RIL"]
    assert names["INFY.NS"]["short_name"] == "Infosys"
    assert names["HDFCBANK.NS"]["short_name"] == "HDFC Bank"
    assert "Tata Consultancy" in names["TCS.NS"]["aliases"]
    assert "Zomato" in names["ETERNAL.NS"]["aliases"]
    assert {
        "Titan",
        "Trent",
        "Hero",
        "Max",
        "Eternal",
        "Bharat",
        "Indus",
    } <= subject.INDIA_AMBIGUOUS
    for symbol in ("TITAN", "TRENT", "MAXHEALTH", "ETERNAL", "BEL"):
        assert names[f"{symbol}.NS"]["ambiguous"]
    assert not names["INFY.NS"]["ambiguous"]
    names["RELIANCE.NS"]["aliases"].clear()
    assert subject.india_names()["RELIANCE.NS"]["aliases"]


@pytest.mark.xfail(
    strict=True, reason="N1 acceptance blocked: 12 English identities remain unresolved"
)
def test_n1_acceptance_every_company_has_a_verified_english_title():
    missing = [
        ticker
        for ticker, entry in subject.india_names().items()
        if not entry["wiki_en"]
    ]
    assert (
        not missing
    ), f"Missing verified English Wikipedia titles: {', '.join(missing)}"


def test_india_subreddits_match_the_enabled_reddit_communities():
    assert subject.INDIA_SUBREDDITS == (
        "IndianStockMarket",
        "IndiaInvestments",
        "IndianStreetBets",
    )
