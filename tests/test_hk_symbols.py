"""HK lookup contract, isolated provider failures and display-name provenance."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import requests

from src.markets import hk_symbols as hk
from src.markets.errors import SymbolLookupUnavailable, UnknownTicker

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("700", "0700.HK"),
        ("0700", "0700.HK"),
        ("00700", "0700.HK"),
        ("0700.HK", "0700.HK"),
        ("700.HK", "0700.HK"),
        ("HK:700", "0700.HK"),
        ("HKEX:0700", "0700.HK"),
        ("9988", "9988.HK"),
        ("80737", "80737.HK"),
        ("  hkex:00700.hk  ", "0700.HK"),
    ],
)
def test_normalization_contract_requires_price_history(raw, expected):
    requested = []

    def history(symbol):
        requested.append(symbol)
        return True

    assert hk.normalize_hk(raw, history_check=history) == expected
    assert requested == [expected]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        700,
        "",
        "00000",
        "0",
        "100000",
        "ABC",
        "700.US",
        "７００",
        "HK:7 00",
        "../700",
        "-700",
        "7.00",
    ],
)
def test_garbage_never_reaches_history_provider(raw):
    def history(_):
        pytest.fail("Garbage ticker must fail before any provider request")

    with pytest.raises(UnknownTicker):
        hk.normalize_hk(raw, history_check=history)


def test_confirmed_missing_history_is_unknown_but_outage_is_not():
    with pytest.raises(UnknownTicker, match="99999.HK"):
        hk.normalize_hk("99999", history_check=lambda _: False)

    def outage(_):
        raise SymbolLookupUnavailable("rate limited")

    with pytest.raises(SymbolLookupUnavailable, match="rate limited"):
        hk.normalize_hk("0700", history_check=outage)
    with pytest.raises(SymbolLookupUnavailable, match="invalid result"):
        hk.normalize_hk("0700", history_check=lambda _: None)


def test_syntax_only_and_tencent_conversion_never_need_the_provider(monkeypatch):
    monkeypatch.setattr(
        hk, "_history_exists", lambda _: pytest.fail("unexpected network")
    )
    assert hk.canonical_hk("00700") == "0700.HK"
    assert hk.normalize_hk("700", validate=False) == "0700.HK"
    assert hk.tencent_code("700.HK") == "hk00700"
    assert hk.tencent_code("80737.HK") == "hk80737"


def test_production_cache_expires_and_never_caches_outages(monkeypatch):
    monkeypatch.setattr(hk, "_HISTORY_CACHE", {})
    clock = [100.0]
    calls = []
    monkeypatch.setattr(hk.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        hk, "_history_exists", lambda symbol: calls.append(symbol) or True
    )
    assert hk.normalize_hk("700") == hk.normalize_hk("00700")
    assert calls == ["0700.HK"]
    clock[0] += hk.HISTORY_CACHE_SECONDS + 1
    hk.normalize_hk("700")
    assert len(calls) == 2

    def outage(_):
        raise SymbolLookupUnavailable("offline")

    monkeypatch.setattr(hk, "_history_exists", outage)
    with pytest.raises(SymbolLookupUnavailable):
        hk.normalize_hk("9988")
    assert "9988.HK" not in hk._HISTORY_CACHE


def test_confirmed_unknown_cache_has_short_lifetime(monkeypatch):
    monkeypatch.setattr(hk, "_HISTORY_CACHE", {})
    clock = [0.0]
    calls = []
    monkeypatch.setattr(hk.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        hk, "_history_exists", lambda symbol: calls.append(symbol) or False
    )
    for _ in range(2):
        with pytest.raises(UnknownTicker):
            hk.normalize_hk("99999")
    assert len(calls) == 1
    clock[0] = hk.UNKNOWN_CACHE_SECONDS + 1
    with pytest.raises(UnknownTicker):
        hk.normalize_hk("99999")
    assert len(calls) == 2


class FakeResponse:
    def __init__(self, payload, status=200, chunks=None):
        self.payload, self.status_code, self.chunks = payload, status, chunks

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, **_):
        return iter(self.chunks or [json.dumps(self.payload).encode()])


def history_payload(symbol="0700.HK", closes=None):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": symbol},
                    "indicators": {
                        "quote": [
                            {"close": closes if closes is not None else [None, 500]}
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_yahoo_history_uses_bounded_monthly_all_history_request(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(history_payload())

    monkeypatch.setattr(hk.requests, "get", get)
    assert hk._history_exists("0700.HK")
    assert calls[0][0].endswith("/0700.HK")
    assert calls[0][1]["params"] == {"range": "max", "interval": "1mo"}
    assert calls[0][1]["timeout"] == hk.HISTORY_TIMEOUT_SECONDS
    assert calls[0][1]["stream"]


@pytest.mark.parametrize(
    "response, missing",
    [
        (FakeResponse({}, 404), True),
        (
            FakeResponse({"chart": {"result": None, "error": {"code": "Not Found"}}}),
            True,
        ),
        (FakeResponse(history_payload(closes=[None, 0, -1])), True),
        (FakeResponse({}, 429), False),
        (FakeResponse({}, 503), False),
        (FakeResponse({"chart": {"result": None, "error": None}}), False),
        (FakeResponse(history_payload(symbol="9988.HK")), False),
        (FakeResponse({"unexpected": "HTML proxy converted to JSON"}), False),
    ],
)
def test_history_response_distinguishes_absence_from_service_failure(
    monkeypatch, response, missing
):
    monkeypatch.setattr(hk.requests, "get", lambda *_a, **_kw: response)
    if missing:
        assert hk._history_exists("0700.HK") is False
    else:
        with pytest.raises(SymbolLookupUnavailable):
            hk._history_exists("0700.HK")


def test_yahoo_response_size_is_bounded(monkeypatch):
    response = FakeResponse({}, chunks=[b"x" * (hk.MAX_HISTORY_BYTES + 1)])
    monkeypatch.setattr(hk.requests, "get", lambda *_a, **_kw: response)
    with pytest.raises(SymbolLookupUnavailable, match="too large"):
        hk._history_exists("0700.HK")


def test_names_cover_dated_roster_and_keep_the_real_english_article_gap():
    with (ROOT / "config/hsi_constituents_2026-11-04.csv").open() as handle:
        expected = {row["yahoo_ticker"] for row in csv.DictReader(handle)}
    names = hk.hk_names()
    assert set(names) == expected and len(names) == 95
    for symbol, record in names.items():
        assert record["name"] and record["short_name"] and record["name_zh"]
        assert record["name_zh"] in record["aliases"]
        assert record["wiki_zh"]
        assert record["metadata_sources"]
        if symbol != "6181.HK":
            assert record["wiki_en"]
    assert names["6181.HK"]["wiki_en"] is None
    assert names["6181.HK"]["wiki_status"] == "missing_english_article"
    assert "404" in names["6181.HK"]["wiki_note"]


def test_required_adr_aliases_and_ambiguous_common_words_are_explicit():
    names = hk.hk_names()
    for symbol, ticker in [
        ("0700.HK", "TCEHY"),
        ("9988.HK", "BABA"),
        ("9618.HK", "JD"),
        ("9888.HK", "BIDU"),
    ]:
        assert ticker in names[symbol]["aliases"]
        assert ticker in names[symbol]["adr_aliases"]
    assert {"Link", "Galaxy", "Sands"} <= hk.HK_AMBIGUOUS
    assert all(
        names[symbol]["ambiguous"] for symbol in ["0823.HK", "0027.HK", "1928.HK"]
    )


def test_name_consumers_cannot_mutate_the_shared_metadata():
    names = hk.hk_names()
    names["0700.HK"]["aliases"].append("bad injection")
    assert "bad injection" not in hk.hk_names()["0700.HK"]["aliases"]


def test_subreddits_only_include_exact_2026_evidence_matches():
    evidence = json.loads(hk.SUBREDDIT_EVIDENCE.read_text())
    selected = {
        row["candidate"]
        for row in evidence["candidates"]
        if row["exists"] and row["has_2026_posts"] and row["qualified"]
    }
    assert set(hk.HK_SUBREDDITS) == selected == set(evidence["selected"])
    assert set(hk.HK_SUBREDDITS) == {"HongKong", "ChinaStocks"}
