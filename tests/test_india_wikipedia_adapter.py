"""Offline conversion, evidence boundaries and existing YAML-shape compatibility."""

import csv
import json
import socket

import pytest
import yaml

from src.india_wikipedia_mapping import load_india_titles


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("CSV integration attempted network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def files(tmp_path):
    rows = [
        {
            "symbol": "TEST",
            "title": "Current",
            "lang": "en",
            "valid_from": "2020-01-01T00:00:00Z",
        },
        {"symbol": "TEST", "title": "Former", "lang": "en", "valid_from": ""},
        {"symbol": "TEST", "title": "हिन्दी", "lang": "hi", "valid_from": ""},
    ]
    ledger = [
        dict(rows[0], row_kind="current", start_logid=1, valid_to=None),
        dict(
            rows[1],
            row_kind="historical_move_observed",
            valid_to="2020-01-01T00:00:00Z",
            end_logid=1,
        ),
        dict(rows[2], row_kind="current", valid_to=None),
    ]

    def write(changed_rows=None, changed_ledger=None):
        path = tmp_path / "titles.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["symbol", "title", "lang", "valid_from"]
            )
            writer.writeheader()
            writer.writerows(rows if changed_rows is None else changed_rows)
        evidence = tmp_path / "ledger.json"
        evidence.write_text(
            json.dumps(ledger if changed_ledger is None else changed_ledger)
        )
        return path, evidence

    return rows, ledger, write


def test_current_yaml_interface_and_separate_multilingual_history(files):
    _, _, write = files
    mapping = load_india_titles(*write())
    assert mapping.current_titles() == {"TEST.NS": {"en": "Current", "hi": "हिन्दी"}}
    # Exact config.stocks(...)[ticker]['wikipedia'] interface used by universe().
    stocks = {
        ticker: {"wikipedia": titles}
        for ticker, titles in mapping.current_titles().items()
    }
    restored = yaml.safe_load(yaml.safe_dump(stocks, allow_unicode=True))
    assert {
        t: dict(cfg["wikipedia"]) for t, cfg in restored.items()
    } == mapping.current_titles()
    history = mapping.title_history()["TEST.NS"]
    assert [r.title for r in history["en"]] == ["Current", "Former"]
    assert history["en"][1].valid_from is None
    assert history["en"][1].valid_to.year == 2020
    assert history["hi"][0].valid_from is None
    exported = mapping.current_titles()
    exported["TEST.NS"]["en"] = "mutated copy"
    assert mapping.current_titles()["TEST.NS"]["en"] == "Current"


def test_duplicate_csv_key_rejected_even_if_identical(files):
    rows, _, write = files
    with pytest.raises(ValueError, match="Duplicate mapping"):
        load_india_titles(*write(rows + [rows[0]]))


def test_duplicate_ledger_key_rejected(files):
    _, ledger, write = files
    with pytest.raises(ValueError, match="Duplicate ledger"):
        load_india_titles(*write(changed_ledger=ledger + [ledger[0]]))


def test_two_current_titles_for_same_language_rejected(files):
    rows, ledger, write = files
    changed = [dict(r) for r in ledger]
    changed[1].update(row_kind="current", valid_to=None)
    with pytest.raises(ValueError, match="Conflicting current"):
        load_india_titles(*write(rows, changed))


@pytest.mark.parametrize("date", ["2010-01-01T00:00:00Z", "invalid"])
def test_dates_cannot_be_invented_or_changed(files, date):
    rows, _, write = files
    changed = [dict(r) for r in rows]
    changed[1]["valid_from"] = date
    with pytest.raises(ValueError, match="matching date/title evidence"):
        load_india_titles(*write(changed))


@pytest.mark.parametrize("date", ["invalid", "2020-01-01", "2020-01-01T00:00:00+05:30"])
def test_bad_or_non_utc_boundaries_rejected(files, date):
    rows, ledger, write = files
    changed_rows = [dict(r) for r in rows]
    changed_ledger = [dict(r) for r in ledger]
    changed_rows[0]["valid_from"] = date
    changed_ledger[0]["valid_from"] = date
    with pytest.raises(ValueError):
        load_india_titles(*write(changed_rows, changed_ledger))


def test_missing_ledger_identity_and_current_mapping_rejected(files):
    rows, ledger, write = files
    with pytest.raises(ValueError, match="matching date/title evidence"):
        load_india_titles(*write(changed_ledger=ledger[:1]))
    with pytest.raises(ValueError, match="lacks a current"):
        load_india_titles(*write(rows[1:]))


def test_unbacked_start_and_reversed_interval_rejected(files):
    rows, ledger, write = files
    changed = [dict(r) for r in ledger]
    changed[0].pop("start_logid")
    with pytest.raises(ValueError, match="start lacks event"):
        load_india_titles(*write(changed_ledger=changed))
    changed = [dict(r) for r in ledger]
    changed[1].update(valid_from="2021-01-01T00:00:00Z", start_logid=2)
    changed_rows = [dict(r) for r in rows]
    changed_rows[1]["valid_from"] = changed[1]["valid_from"]
    with pytest.raises(ValueError, match="Invalid title interval"):
        load_india_titles(*write(changed_rows, changed))


def test_wrong_schema_and_extra_fields_rejected(files):
    _, _, write = files
    path, ledger = write()
    path.write_text("ticker,title,lang,valid_from\nTEST,Title,en,\n")
    with pytest.raises(ValueError, match="schema"):
        load_india_titles(path, ledger)
    path.write_text("symbol,title,lang,valid_from\nTEST,Title,en,,extra\n")
    with pytest.raises(ValueError, match="Malformed"):
        load_india_titles(path, ledger)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"lang": "hi"}, "require English"),
        ({"valid_from": "2020-01-01T00:00:00Z", "start_logid": 1}, "unknown dates"),
        ({"symbol": "TEST"}, "Conflicting current"),
    ],
)
def test_proxy_rejects_unsupported_language_dates_and_current_collisions(
    files, change, error
):
    rows, ledger, write = files
    proxy = {"symbol": "OTHER", "title": "Parent", "lang": "en", "valid_from": ""}
    proxy_evidence = dict(proxy, row_kind="parent_proxy", valid_to=None)
    proxy_evidence.update(change)
    proxy.update({k: v for k, v in change.items() if k in proxy})
    with pytest.raises(ValueError, match=error):
        load_india_titles(*write(rows + [proxy], ledger + [proxy_evidence]))


def test_real_registry_preserves_exact_titles_and_exports_only_opted_in_proxies():
    mapping = load_india_titles()
    assert len(mapping.records) == 176
    current = mapping.current_titles()
    assert len(current) == 88
    assert sum("en" in titles for titles in current.values()) == 88
    assert sum("hi" in titles for titles in current.values()) == 67
    assert "ABB.NS" not in current
    approved = mapping.current_titles(include_parent_proxies=True)
    assert approved["ABB.NS"] == {"en": "ABB"}
    assert approved["HDFCAMC.NS"] == {"en": current["HDFCBANK.NS"]["en"]}
    assert approved["ENRIN.NS"] == approved["SIEMENS.NS"] == {"en": "Siemens"}
    assert len(approved) == 97
    assert all(approved[ticker] == titles for ticker, titles in current.items())
    proxies = [row for row in mapping.records if row.kind == "parent_proxy"]
    assert len(proxies) == 9
    assert all(row.valid_from is None and row.valid_to is None for row in proxies)
    assert sum(row.kind == "historical_move_observed" for row in mapping.records) == 12
    assert sum(row.valid_from is None for row in mapping.records) == 145
    assert len(mapping.title_history()["ADANIENSOL.NS"]["en"]) == 3
