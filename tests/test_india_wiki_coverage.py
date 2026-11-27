"""Offline all-company mapping dispositions and unchanged identity safeguards."""

import csv
import json
from pathlib import Path

from src.india_wikipedia_mapping import load_india_titles

PROXY_SYMBOLS = {
    "ABB",
    "BOSCHLTD",
    "CUMMINSIND",
    "ENRIN",
    "HDFCAMC",
    "POWERINDIA",
    "SIEMENS",
    "TATACAP",
    "VAML",
}
GROUP_PROXY_SYMBOLS = {"BAJAJHLDNG", "SHRIRAMFIN"}
UNAVAILABLE_SYMBOLS = {"SOLARINDS"}

ROOT = Path(__file__).resolve().parents[1]


def test_all_100_companies_have_unique_mapping_or_explicit_gap():
    with (ROOT / "config/india_wiki_coverage.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({row["symbol"] for row in rows}) == 100
    mapping = load_india_titles()
    current = mapping.current_titles(include_parent_proxies=True)
    exact = mapping.current_titles()
    for row in rows:
        if row["en_title"]:
            assert current[row["symbol"] + ".NS"]["en"] == row["en_title"]
        else:
            assert row["en_status"] == "WIKIPEDIA_UNAVAILABLE"
            assert row["notes"]
            assert row["symbol"] + ".NS" not in current
    assert len(exact) == 88
    assert sum(bool(row["en_title"]) for row in rows) == 99
    assert {row["symbol"] for row in rows if row["en_status"] == "group_proxy"} == (
        GROUP_PROXY_SYMBOLS
    )
    assert {
        row["symbol"] + ".NS"
        for row in rows
        if row["en_status"] == ("VERIFIED_CURRENT_COMPANY_PAGE")
    } == set(exact)
    assert {row["symbol"] for row in rows if row["en_status"] == "parent_proxy"} == (
        PROXY_SYMBOLS
    )
    assert {row["symbol"] for row in rows if not row["en_title"]} == UNAVAILABLE_SYMBOLS
    assert set(current) - set(exact) == {
        f"{symbol}.NS" for symbol in PROXY_SYMBOLS | GROUP_PROXY_SYMBOLS
    }
    assert sum(bool(row["hi_title"]) for row in rows) == 67


def test_review_preserves_exact_search_and_binds_proxy_retrieval_evidence():
    evidence = json.loads((ROOT / "config/india_wiki_identity_review.json").read_text())
    checked = evidence["targeted_searches"]
    assert len(checked) == 12
    assert {row["symbol"] for row in checked if row["http_status"] == 429} == {
        "TATACAP",
        "VAML",
    }
    assert "historical attention" in evidence["scope"]
    assert all(not row.get("snippet") for item in checked for row in item["search"])
    decisions = evidence["parent_proxy_review"]["decisions"]
    assert len(decisions) == 12
    assert {
        row["symbol"] for row in decisions
    } == PROXY_SYMBOLS | GROUP_PROXY_SYMBOLS | UNAVAILABLE_SYMBOLS
    followup = evidence["group_proxy_review"]["decisions"]
    assert {
        row["symbol"] for row in followup
    } == GROUP_PROXY_SYMBOLS | UNAVAILABLE_SYMBOLS
    with (ROOT / "config/india_wiki_coverage.csv").open() as stream:
        coverage = {row["symbol"]: row for row in csv.DictReader(stream)}
    records = {
        row.symbol: row
        for row in load_india_titles().records
        if row.kind in {"parent_proxy", "group_proxy"}
    }
    for row in followup:
        assert row["status"] == coverage[row["symbol"]]["en_status"]
        if row["symbol"] in UNAVAILABLE_SYMBOLS:
            assert row["reason"] == coverage[row["symbol"]]["notes"]
            assert "title" not in row
    decisions += [row for row in followup if row["status"] == "group_proxy"]
    for row in decisions:
        assert row["relationship_source"].startswith("https://")
        if row["status"] in {"parent_proxy", "group_proxy"}:
            assert row["status"] == records[row["symbol"]].kind
            assert row["title"] == records[row["symbol"]].title
            assert row["company_name"] == coverage[row["symbol"]]["company_name"]
            assert row["article_url"] == "https://en.wikipedia.org/wiki/" + row["title"]
            assert row["relationship"]
            assert row["wikidata_item"].startswith("Q")
            assert row["public_revision"]["revid"] > 0
            assert row["pageviews"]["status"] == 200
            assert row["pageviews"]["sample_days"] == 3
        else:
            assert row["status"] == "unresolved" and row["reason"]


def test_unchanged_registry_retains_unknown_dates_and_historical_rows():
    records = load_india_titles().records
    assert len(records) == 178
    assert sum(row.valid_from is None for row in records) == 147
    assert sum(row.kind == "historical_move_observed" for row in records) == 12
