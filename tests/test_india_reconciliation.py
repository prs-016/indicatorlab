"""OFFLINE SYNTHETIC NSE record fixtures; no genuine market prices or network."""

from io import BytesIO
import hashlib
import json
from zipfile import ZipFile

import pandas as pd
import pytest

from src.india_data import NSE_STOCKS, BENCHMARK
from src.india_ingestion import ingest_history
from src.india_reconciliation import (
    SESSION_DATES, build_reconciliation, read_bhavcopy,
    verify_equities, verify_nifty50,
)


def synthetic_equities(session):
    return pd.DataFrame([{
        "SYMBOL": symbol.removesuffix(".NS"), "SERIES": "EQ",
        "TIMESTAMP": pd.Timestamp(session).strftime("%d-%b-%Y").upper(),
        "ISIN": f"INE{i:03d}A01011", "OPEN": 100., "HIGH": 110.,
        "LOW": 90., "CLOSE": 105., "LAST": 106., "PREVCLOSE": 99.,
        "TOTTRDQTY": 1000., "TOTTRDVAL": 105000., "TOTALTRADES": 50.,
    } for i, symbol in enumerate(NSE_STOCKS)])


def synthetic_index(session):
    return pd.DataFrame([{
        "Index Name": "Nifty 50", "Index Date": pd.Timestamp(session).strftime("%d-%m-%Y"),
        "Open Index Value": 1000., "High Index Value": 1100.,
        "Low Index Value": 900., "Closing Index Value": 1050., "Volume": 10000,
    }])


def test_each_equity_requires_actual_trading_and_uses_close_not_last():
    quotes, issues = verify_equities(synthetic_equities(SESSION_DATES[0]), SESSION_DATES[0])
    assert len(quotes) == 8 and not issues
    assert quotes.close.eq(105).all()
    assert quotes.adjusted_close.isna().all()
    assert quotes.trades.gt(0).all()
    assert quotes.integration_status.str.startswith("blocked").all()


@pytest.mark.parametrize("column,value", [
    ("TOTTRDQTY", 0), ("TOTALTRADES", 0), ("TOTALTRADES", .5),
    ("TOTTRDVAL", 0), ("CLOSE", 0), ("CLOSE", float("nan")),
    ("HIGH", 95), ("ISIN", ""), ("TIMESTAMP", "13-NOV-2023"),
])
def test_invalid_equity_rejected_per_symbol(column, value):
    frame = synthetic_equities(SESSION_DATES[0])
    frame.loc[0, column] = value
    quotes, issues = verify_equities(frame, SESSION_DATES[0])
    assert len(quotes) == 7
    assert issues[0]["symbol"] == NSE_STOCKS[0]


def test_no_series_substitution_or_duplicate_selection():
    frame = synthetic_equities(SESSION_DATES[0])
    frame.loc[0, "SERIES"] = "BE"
    quotes, issues = verify_equities(frame, SESSION_DATES[0])
    assert len(quotes) == 7 and len(issues) == 1
    frame = synthetic_equities(SESSION_DATES[0])
    _, issues = verify_equities(pd.concat([frame, frame.iloc[:1]]), SESSION_DATES[0])
    assert len(issues) == 1


def test_index_verified_separately_not_inferred_from_equity_session():
    frame = synthetic_index(SESSION_DATES[0])
    quote = verify_nifty50(frame, SESSION_DATES[0])
    assert quote["symbol"] == BENCHMARK
    assert quote["close"] == 1050
    assert "trades" not in quote
    assert "not_an_EQ_trade" in quote["verification"]
    frame.loc[0, "Index Name"] = "Nifty 50 Total Returns Index"
    with pytest.raises(ValueError, match="price-index record"):
        verify_nifty50(frame, SESSION_DATES[0])


def test_wrong_index_date_and_missing_publication_fail():
    frame = synthetic_index(SESSION_DATES[0])
    frame.loc[0, "Index Date"] = "13-11-2023"
    with pytest.raises(ValueError, match="Index date"):
        verify_nifty50(frame, SESSION_DATES[0])
    with pytest.raises(ValueError, match="Missing or duplicate"):
        verify_nifty50(frame.iloc[:0], SESSION_DATES[0])


def test_zip_member_ambiguity_fails():
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr("one.csv", "test\n1\n")
        z.writestr("two.csv", "test\n2\n")
    with pytest.raises(ValueError, match="exactly one"):
        read_bhavcopy(stream.getvalue())


def make_sources(tmp_path):
    root = tmp_path / "official"
    root.mkdir()
    entries = []
    for session in SESSION_DATES:
        date = pd.Timestamp(session)
        month = {3: "MAR", 5: "MAY", 11: "NOV"}[date.month]
        name = f"cm{date.day:02d}{month}{date.year}bhav.csv.zip"
        with ZipFile(root / name, "w") as z:
            z.writestr(name.removesuffix(".zip"), synthetic_equities(session).to_csv(index=False))
        index_name = f"ind_close_all_{date.strftime('%d%m%Y')}.csv"
        (root / index_name).write_text(synthetic_index(session).to_csv(index=False))
        for filename, url in [
            (name, f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{date.year}/{month}/{name}"),
            (index_name, f"https://nsearchives.nseindia.com/content/indices/{index_name}"),
        ]:
            entries.append({"file": filename, "url": url, "status": 200,
                            "sha256": hashlib.sha256((root / filename).read_bytes()).hexdigest()})
    path = root / "retrieval_manifest.json"
    path.write_text(json.dumps(entries))
    dates = pd.to_datetime(["2023-11-10", "2023-11-13", "2024-03-01",
                            "2024-03-04", "2024-05-17", "2024-05-21"])
    raw = pd.DataFrame({"Open": 100., "High": 110., "Low": 90., "Close": 105.,
                        "Adj Close": 50., "Volume": 1000.}, index=dates)
    parent = ingest_history(tmp_path / "parent", start="2023-11-10", vibe_root=tmp_path,
                            fetcher=lambda _: ({s: raw.to_csv() for s in (*NSE_STOCKS, BENCHMARK)},
                                               {"provider": "SYNTHETIC TEST FIXTURE"}))
    return path, parent


def test_versioned_evidence_dataset_never_guesses_equity_adjustments(tmp_path):
    retrieval, parent = make_sources(tmp_path)
    old = parent.read_bytes()
    path = build_reconciliation(retrieval, parent, tmp_path / "research_v1")
    manifest = json.loads(path.read_text())
    assert manifest["verified_record_count"] == 27
    assert manifest["missing_authoritative_records"] == []
    assert manifest["backtest_ready"] is False
    quotes = pd.read_csv(path.parent / "official_quotes.csv")
    assert quotes.adjusted_close.isna().all()
    benchmark = pd.read_csv(path.parent / "benchmark_price_index_view.csv", index_col=0)
    assert len(benchmark) == 9
    assert parent.read_bytes() == old
    with pytest.raises(FileExistsError):
        build_reconciliation(retrieval, parent, tmp_path / "research_v1")


def test_source_tampering_is_reported_not_used(tmp_path):
    retrieval, parent = make_sources(tmp_path)
    records = json.loads(retrieval.read_text())
    (retrieval.parent / records[0]["file"]).write_bytes(b"not the original ZIP")
    path = build_reconciliation(retrieval, parent, tmp_path / "research")
    manifest = json.loads(path.read_text())
    assert manifest["verified_record_count"] == 19
    assert manifest["verification_issue_count"] == 8
    assert all("checksum mismatch" in issue["reason"] for issue in manifest["missing_authoritative_records"])


def test_nonofficial_source_is_not_accepted(tmp_path):
    retrieval, parent = make_sources(tmp_path)
    records = json.loads(retrieval.read_text())
    records[1]["url"] = "https://example.org/other-exchange.csv"
    retrieval.write_text(json.dumps(records))
    path = build_reconciliation(retrieval, parent, tmp_path / "research")
    manifest = json.loads(path.read_text())
    assert manifest["verified_record_count"] == 26
    assert manifest["missing_authoritative_records"][0]["symbol"] == BENCHMARK


@pytest.mark.parametrize("date", ["2025-10-01", "2024-12-31", "2023-11-12T12:00"])
def test_unrequested_or_post_cutoff_date_rejected(date):
    with pytest.raises(ValueError):
        verify_equities(synthetic_equities(SESSION_DATES[0]), date)
