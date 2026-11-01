"""Offline verification of official NSE special-session records.

Nominal equity quotes are evidence, not automatically compatible replacements
for retrospectively adjusted Yahoo prices. This module never estimates factors.
"""

from io import BytesIO, StringIO
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd

from src.india_data import BACKTEST_END, BENCHMARK, NSE_STOCKS
from src.india_ingestion import load_snapshot


SESSION_DATES = ("2023-11-12", "2024-03-02", "2024-05-18")
EQUITY_FIELDS = {
    "SYMBOL", "SERIES", "TIMESTAMP", "ISIN", "OPEN", "HIGH", "LOW",
    "CLOSE", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL", "TOTALTRADES",
}
INDEX_FIELDS = {
    "Index Name", "Index Date", "Open Index Value", "High Index Value",
    "Low Index Value", "Closing Index Value", "Volume",
}


def read_bhavcopy(content: bytes) -> pd.DataFrame:
    """Read one official ZIP's sole CSV without extracting files to disk.

    Parameters: content is original downloaded ZIP bytes. Returns the raw CSV
    frame; ambiguous ZIP contents fail instead of choosing an arbitrary member.
    """
    with ZipFile(BytesIO(content)) as archive:
        csvs = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError("Expected exactly one bhavcopy CSV member")
        return pd.read_csv(archive.open(csvs[0]))


def _date(value: str, allowed_sessions: tuple[str, ...] = SESSION_DATES) -> pd.Timestamp:
    date = pd.Timestamp(value)
    if str(date.date()) not in allowed_sessions or date != date.normalize() or date.tz is not None:
        raise ValueError("Only explicitly requested pre-cutoff sessions are permitted")
    if date > BACKTEST_END:
        raise ValueError("Historical cutoff exceeded")
    return date


def _prices(values: list) -> list[float]:
    prices = [float(value) for value in values]
    if not np.isfinite(prices).all() or min(prices) <= 0:
        raise ValueError("Invalid/nonpositive OHLC")
    open_, high, low, close = prices
    if high < max(open_, low, close) or low > min(open_, high, close):
        raise ValueError("Impossible OHLC range")
    return prices


def verify_equities(
    frame: pd.DataFrame, session: str,
    *, allowed_sessions: tuple[str, ...] = SESSION_DATES,
) -> tuple[pd.DataFrame, list[dict]]:
    """Verify each assigned stock separately in an NSE cash-equity bhavcopy.

    Parameters: frame is an official bhavcopy and session is its expected date.
    allowed_sessions explicitly scopes additional calendar-audit dates; the
    historical cutoff still applies. Returns verified rows plus failures. Require one EQ
    row per ticker, matching date, populated ISIN, valid OHLC/previous close, and
    positive quantity, turnover and integral trade count. Never use LAST as CLOSE
    or substitute BE/BSE records. Historical ISIN is retained, not replaced by a
    current constituent snapshot's potentially different post-action ISIN.
    """
    date = _date(session, allowed_sessions)
    if not EQUITY_FIELDS <= set(frame.columns):
        raise ValueError("Missing official equity fields")
    records, issues = [], []
    for symbol in NSE_STOCKS:
        try:
            matches = frame.loc[
                frame["SYMBOL"].eq(symbol.removesuffix(".NS"))
                & frame["SERIES"].eq("EQ")]
            if len(matches) != 1:
                raise ValueError("Missing or duplicate EQ record")
            row = matches.iloc[0]
            if pd.to_datetime(row["TIMESTAMP"], format="%d-%b-%Y") != date:
                raise ValueError("Record date does not match requested session")
            isin = str(row["ISIN"])
            if pd.isna(row["ISIN"]) or len(isin) != 12 or not isin.startswith("INE"):
                raise ValueError("Missing or malformed historical equity ISIN")
            prices = _prices([row[k] for k in ("OPEN", "HIGH", "LOW", "CLOSE")])
            quantity, turnover, trades, previous = [float(row[k]) for k in (
                "TOTTRDQTY", "TOTTRDVAL", "TOTALTRADES", "PREVCLOSE")]
            if (not np.isfinite([quantity, turnover, trades, previous]).all()
                    or min(quantity, turnover, trades, previous) <= 0
                    or not quantity.is_integer() or not trades.is_integer()):
                raise ValueError("No verified positive trading evidence/previous close")
            records.append({
                "date": session, "symbol": symbol, "series": "EQ", "isin": isin,
                "open": prices[0], "high": prices[1], "low": prices[2],
                "close": prices[3], "previous_close": previous,
                "volume": quantity, "turnover_inr": turnover, "trades": trades,
                "price_basis": "NSE nominal equity session OHLC; unconverted",
                "verification": "actual_equity_trading_and_close_verified",
                "adjusted_close": None,
                "integration_status": "blocked_unverified_adjustment_conversion",
            })
        except (ValueError, TypeError, OverflowError) as exc:
            issues.append({"date": session, "symbol": symbol, "reason": str(exc)})
    return pd.DataFrame(records), issues


def verify_nifty50(
    frame: pd.DataFrame, session: str,
    *, allowed_sessions: tuple[str, ...] = SESSION_DATES,
) -> dict:
    """Verify the published Nifty 50 index close independently of equity trading.

    Parameters: frame is NSE's daily all-index CSV; session is the expected date.
    allowed_sessions explicitly scopes additional audit dates within the cutoff.
    Returns OHLC/volume and price-index basis. The index is not a traded EQ
    security; stock trade counts are neither invented nor required for it.
    """
    date = _date(session, allowed_sessions)
    if not INDEX_FIELDS <= set(frame.columns):
        raise ValueError("Missing official index fields")
    rows = frame.loc[frame["Index Name"].str.strip().str.upper().eq("NIFTY 50")]
    if len(rows) != 1:
        raise ValueError("Missing or duplicate Nifty 50 price-index record")
    row = rows.iloc[0]
    if pd.to_datetime(row["Index Date"], format="%d-%m-%Y") != date:
        raise ValueError("Index date does not match requested session")
    prices = _prices([row[k] for k in (
        "Open Index Value", "High Index Value", "Low Index Value", "Closing Index Value")])
    volume = float(row["Volume"])
    if not np.isfinite(volume) or volume <= 0:
        raise ValueError("Missing positive reported index constituent volume")
    return {
        "date": session, "symbol": BENCHMARK, "index_name": "Nifty 50",
        "open": prices[0], "high": prices[1], "low": prices[2], "close": prices[3],
        "volume": volume, "price_basis": "Nifty 50 price-index points; not total return",
        "verification": "official_index_publication_verified_not_an_EQ_trade",
        "adjusted_close": None,
        "integration_status": "verified_price_index_points_not_stock_adjustment",
    }


def build_reconciliation(
    retrieval_manifest: str | Path, original_manifest: str | Path,
    destination: str | Path,
) -> Path:
    """Create an immutable versioned official-record dataset and audit manifest.

    Parameters: retrieval_manifest records official URLs, HTTP statuses and byte
    hashes; original_manifest identifies the unchanged Yahoo parent snapshot;
    destination must be new. Returns research manifest path. Verify records
    separately, preserve original files, and retain a blocked integration gate
    until equity adjustment conventions are independently resolved. This is an
    evidence dataset, not a mixed-basis executable portfolio panel.
    """
    retrieval_manifest, original_manifest = Path(retrieval_manifest), Path(original_manifest)
    panel = load_snapshot(original_manifest)  # Also verifies all parent CSV hashes.
    retrievals = json.loads(retrieval_manifest.read_text())
    records, issues = [], []
    for session in SESSION_DATES:
        date = pd.Timestamp(session)
        month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG",
                 "SEP", "OCT", "NOV", "DEC")[date.month - 1]
        equity_name = f"cm{date.day:02d}{month}{date.year}bhav.csv.zip"
        index_name = f"ind_close_all_{date.strftime('%d%m%Y')}.csv"
        for name, symbols in ((equity_name, NSE_STOCKS), (index_name, (BENCHMARK,))):
            try:
                candidates = [r for r in retrievals if Path(r["file"]).name == name]
                if len(candidates) != 1:
                    raise ValueError("Missing or ambiguous retrieval record")
                source = candidates[0]
                relative = Path(source["file"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Invalid source path")
                expected_url = (
                    f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{date.year}/{month}/{name}"
                    if len(symbols) > 1 else
                    f"https://nsearchives.nseindia.com/content/indices/{name}")
                if (source.get("status") != 200 or source["url"] != expected_url
                        or source.get("final_url", source["url"]) != expected_url):
                    raise ValueError("Unverified official source or HTTP response")
                content = (retrieval_manifest.parent / relative).read_bytes()
                if hashlib.sha256(content).hexdigest() != source["sha256"]:
                    raise ValueError("Official source checksum mismatch")
                if len(symbols) > 1:
                    quotes, failures = verify_equities(read_bhavcopy(content), session)
                    issues.extend(failures)
                    parsed = quotes.to_dict("records")
                else:
                    parsed = [verify_nifty50(pd.read_csv(StringIO(content.decode("utf-8-sig"))), session)]
                for quote in parsed:
                    quote.update(source_url=source["url"], source_sha256=source["sha256"],
                                 source_file=source["file"])
                records.extend(parsed)
            except (ValueError, KeyError, OSError, UnicodeError, BadZipFile) as exc:
                issues.extend({"date": session, "symbol": s, "reason": str(exc)} for s in symbols)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    quotes = pd.DataFrame(records)
    quotes.to_csv(destination / "official_quotes.csv", index=False)
    (destination / "verification_issues.json").write_text(json.dumps(issues, indent=2) + "\n")
    benchmark = panel.benchmark.copy()
    for quote in records:
        if quote["symbol"] == BENCHMARK:
            day = pd.Timestamp(quote["date"])
            if day in benchmark.index:
                raise ValueError("Refusing to overwrite an existing benchmark date")
            benchmark.loc[day] = quote["close"]
    benchmark.sort_index().to_csv(destination / "benchmark_price_index_view.csv", index_label="Date")
    manifest = {
        "schema_version": 1,
        "status": ("official_verification_incomplete" if issues else
                   "verified_official_quotes_adjustment_integration_blocked"),
        "parent_snapshot": str(original_manifest.resolve()),
        "parent_manifest_sha256": hashlib.sha256(original_manifest.read_bytes()).hexdigest(),
        "retrieval_manifest": str(retrieval_manifest.resolve()),
        "retrieval_manifest_sha256": hashlib.sha256(retrieval_manifest.read_bytes()).hexdigest(),
        "parser_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "session_dates": SESSION_DATES, "verified_record_count": len(records),
        "expected_records": 27, "verification_issue_count": len(issues),
        "missing_authoritative_records": issues,
        "equity_adjusted_conversion_verified": False, "backtest_ready": False,
        "adjustment_convention": "Official equities are nominal INR session prices, not Yahoo adjusted history. No adjustment factors were inferred, interpolated, forward-filled or applied. adjusted_close remains missing. Index additions are independently verified Nifty 50 price-index points.",
        "original_data_modified": False,
        "files_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                         for f in destination.iterdir() if f.is_file()},
    }
    manifest_path = destination / "research_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path
