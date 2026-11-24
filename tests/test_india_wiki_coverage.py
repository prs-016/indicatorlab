"""Offline all-company mapping dispositions and unchanged identity safeguards."""

import csv
import json
from pathlib import Path

from src.india_wikipedia_mapping import load_india_titles

ROOT = Path(__file__).resolve().parents[1]


def test_all_100_companies_have_unique_mapping_or_explicit_gap():
    with (ROOT / "config/india_wiki_coverage.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({row["symbol"] for row in rows}) == 100
    current = load_india_titles().current_titles()
    for row in rows:
        if row["en_title"]:
            assert current[row["symbol"] + ".NS"]["en"] == row["en_title"]
        else:
            assert row["en_status"].startswith("UNRESOLVED")
            assert row["notes"]
            assert row["symbol"] + ".NS" not in current
    assert sum(bool(row["en_title"]) for row in rows) == 88
    assert sum(bool(row["hi_title"]) for row in rows) == 67


def test_no_parent_redirect_or_throttled_search_is_promoted():
    evidence = json.loads((ROOT / "config/india_wiki_identity_review.json").read_text())
    checked = evidence["targeted_searches"]
    assert len(checked) == 12
    assert {row["symbol"] for row in checked if row["http_status"] == 429} == {
        "TATACAP",
        "VAML",
    }
    assert "historical attention" in evidence["scope"]
    assert all(not row.get("snippet") for item in checked for row in item["search"])


def test_unchanged_registry_retains_unknown_dates_and_historical_rows():
    records = load_india_titles().records
    assert len(records) == 167
    assert sum(row.valid_from is None for row in records) == 136
    assert sum(row.kind != "current" for row in records) == 12
