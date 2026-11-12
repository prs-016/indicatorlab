"""Reproducible, append-only Yahoo history snapshots for the India assignment.

No portfolio rules or factor calculations live here. Raw means yfinance's
returned values, not the original Yahoo HTTP response or exchange tape prices.
"""

from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from src.india_data import BACKTEST_END, BENCHMARK, NSE_STOCKS, IndiaPanel, build_india_panel


SYMBOLS = (*NSE_STOCKS, BENCHMARK)
PRICE_FIELDS = ("Open", "High", "Low", "Close")
MOVE_FLAG_THRESHOLD = 0.20  # Original India data-quality assignment.
SETTINGS = {
    "interval": "1d", "auto_adjust": False, "back_adjust": False,
    "repair": False, "keepna": True, "actions": True,
    "rounding": False, "threads": False, "progress": False,
    "ignore_tz": False,
}

_DOWNLOAD_WORKER = r'''
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd

agent = Path(sys.argv[1])
sys.path.insert(0, str(agent))
request = json.load(sys.stdin)
with contextlib.redirect_stdout(sys.stderr):
    import yfinance as yf
    from backtest.loaders.yfinance_loader import (
        _to_yfinance_symbol, _to_yfinance_exclusive_end, _extract_symbol_frame,
    )
    results = {}
    for code in request['symbols']:
        symbol = _to_yfinance_symbol(code)
        data = yf.download(symbol, start=request['start'],
                           end=_to_yfinance_exclusive_end(request['end_inclusive']),
                           **request['settings'])
        results[code] = _extract_symbol_frame(data, symbol, 1).to_csv()
    source = agent / 'backtest/loaders/yfinance_loader.py'
print(json.dumps({'csv': results, 'provenance': {
    'provider': 'Yahoo Finance via yfinance', 'yfinance_version': yf.__version__,
    'vibe_loader': str(source),
    'vibe_loader_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'python_executable': sys.executable, 'python_version': sys.version,
    'pandas_version': pd.__version__,
}}))
'''


def _start_date(value: str) -> str:
    date = pd.Timestamp(value)
    if (pd.isna(date) or date.tz is not None or date != date.normalize()
            or date > BACKTEST_END):
        raise ValueError("start must be a naive session date on or before 2024-12-31")
    return date.strftime("%Y-%m-%d")


def download_yahoo_history(
    start: str, *, vibe_root: str | Path,
    python_executable: str | Path = sys.executable, timeout: float = 180,
) -> tuple[dict[str, str], dict]:
    """Fetch exactly nine symbols in an isolated Vibe-capable interpreter.

    Parameters: start is the inclusive acquisition date (not an evaluation
    start); vibe_root identifies an existing checkout; python_executable selects
    the child interpreter; timeout bounds the whole request. Returns per-symbol
    provider-frame CSV strings and loader provenance. End is fixed at the
    assignment cutoff, expressed to yfinance as exclusive 2025-01-01.
    No caches, metadata history probes, repair, or provider fallback are used.
    """
    start = _start_date(start)
    agent = Path(vibe_root).expanduser().resolve() / "agent"
    if not (agent / "backtest/loaders/yfinance_loader.py").is_file():
        raise ValueError("Vibe yfinance loader not found")
    request = {"symbols": SYMBOLS, "start": start,
               "end_inclusive": "2024-12-31", "settings": SETTINGS}
    try:
        process = subprocess.run(
            [str(python_executable), "-I", "-B", "-c", _DOWNLOAD_WORKER, str(agent)],
            input=json.dumps(request), text=True, capture_output=True,
            cwd=agent, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Historical download worker failed: {exc}") from exc
    if process.returncode:
        raise RuntimeError(f"Historical download worker failed: {process.stderr}")
    result = json.loads(process.stdout)
    provenance = result["provenance"]
    provenance["worker_stderr"] = process.stderr
    return result["csv"], provenance


def _session_index(frame: pd.DataFrame) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    # Daily timestamps are exchange-local dates. Convert before stripping TZ.
    if index.tz is not None:
        index = index.tz_convert("Asia/Kolkata").tz_localize(None)
    return index.normalize()


def transform_history(raw: pd.DataFrame) -> pd.DataFrame:
    """Return adjusted OHLCV without deleting rows, repairing, or filling gaps.

    Parameters: raw is a flat yfinance frame including Adj Close. Returns a
    session-indexed lowercase frame with OHLC multiplied by Adj Close/Close;
    volume and corporate-action fields are unscaled. Undefined/nonpositive
    ratios become NaN, with an explicit adjustment_valid column. Original
    invalid observations remain in raw and are flagged by ingestion.
    """
    frame = raw.copy()
    frame.index = _session_index(frame)
    numeric = {field: pd.to_numeric(frame[field], errors="coerce")
               if field in frame else pd.Series(np.nan, index=frame.index)
               for field in (*PRICE_FIELDS, "Adj Close", "Volume")}
    ratio = numeric["Adj Close"] / numeric["Close"]
    valid = (np.isfinite(ratio) & (ratio > 0)
             & (numeric["Close"] > 0) & (numeric["Adj Close"] > 0))
    ratio = ratio.where(valid)
    out = pd.DataFrame(index=frame.index)
    for field in PRICE_FIELDS:
        out[field.lower()] = numeric[field] * ratio
    out["volume"] = numeric["Volume"]
    out["adjustment_ratio"] = ratio
    out["adjustment_valid"] = valid
    for field in ("Dividends", "Stock Splits", "Capital Gains"):
        if field in frame:
            out[field.lower().replace(" ", "_")] = frame[field]
    return out


def _quality(raw: pd.DataFrame, derived: pd.DataFrame) -> dict:
    flags: dict[str, list[str]] = {}

    def record(name: str, mask: pd.Series) -> None:
        flags[name] = [str(date.date()) for date in derived.index[mask.fillna(False)]]

    prices = derived[list(field.lower() for field in PRICE_FIELDS)]
    for field in (*PRICE_FIELDS, "Adj Close", "Volume"):
        values = (pd.to_numeric(raw[field], errors="coerce") if field in raw
                  else pd.Series(np.nan, index=raw.index))
        values.index = derived.index
        record("missing_or_nonnumeric_" + field, values.isna())
        record("nonfinite_" + field, values.notna() & ~np.isfinite(values))
        if field != "Volume":
            record("nonpositive_" + field, values <= 0)
    record("invalid_adjustment", ~derived["adjustment_valid"])
    record("zero_volume", derived["volume"] == 0)
    record("negative_volume", derived["volume"] < 0)
    record("move_over_20pct_adjusted_close",
           derived["close"].pct_change(fill_method=None).abs() > MOVE_FLAG_THRESHOLD)
    record("repeated_adjusted_close", derived["close"].eq(derived["close"].shift()))
    record("impossible_adjusted_ohlc",
           (prices["high"] < prices[["open", "low", "close"]].max(axis=1))
           | (prices["low"] > prices[["open", "high", "close"]].min(axis=1)))
    return {
        "rows": len(raw),
        "first_session": str(derived.index.min().date()) if len(raw) else None,
        "last_session": str(derived.index.max().date()) if len(raw) else None,
        "missing_fields": [f for f in (*PRICE_FIELDS, "Adj Close", "Volume") if f not in raw],
        "flags": flags,
    }


def ingest_history(
    destination: str | Path, *, start: str, vibe_root: str | Path,
    python_executable: str | Path = sys.executable,
    fetcher: Callable[[str], tuple[Mapping[str, str], dict]] | None = None,
) -> Path:
    """Create a new snapshot containing raw CSV, derived CSV, and a manifest.

    Parameters: destination must not exist; start is the acquisition lower bound;
    vibe_root/python_executable select the isolated downloader. Optional fetcher
    accepts the validated start and supplies CSV strings/provenance for offline
    testing (label synthetic sources explicitly). Returns the manifest path.
    Errors leave an incomplete manifest and retained raw responses. Reusing an
    existing snapshot is forbidden. Suspicious rows are reported, never dropped.
    """
    start = _start_date(start)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    raw_dir = destination / "raw"
    derived_dir = destination / "derived"
    raw_dir.mkdir()
    derived_dir.mkdir()
    manifest = {
        "status": "incomplete", "retrieval_started_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": list(SYMBOLS), "start_inclusive": start,
        "end_inclusive": "2024-12-31", "yfinance_end_exclusive": "2025-01-01",
        "settings": dict(SETTINGS), "quality_move_threshold": MOVE_FLAG_THRESHOLD,
        "raw_basis": "Yahoo vendor prices with auto_adjust=False; not exchange tape or HTTP payload",
        "vendor_revision_limit": "Retrieved historical prices/adjustment factors may reflect later corporate actions or vendor revisions; not a point-in-time vintage",
        "derived_basis": "OHLC scaled by Adj Close/Close; raw volume; undefined ratios retained as NaN",
        "calendar": "union of returned session dates; not an authoritative exchange calendar",
        "date_transform": "Timezone-aware daily dates converted to Asia/Kolkata then made naive and normalized; no rows sorted, filled, or removed",
        "files_sha256": {}, "coverage": {},
        "ingestion_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    manifest_path = destination / "manifest.json"
    try:
        csvs, provenance = (fetcher(start) if fetcher else download_yahoo_history(
            start, vibe_root=vibe_root, python_executable=python_executable))
        manifest["provenance"] = provenance
        if set(csvs) != set(SYMBOLS):
            raise ValueError("Download must return exactly the eight stocks and ^NSEI")
        frames = {}
        # Preserve all returned per-symbol CSVs before any transformations.
        for symbol in SYMBOLS:
            (raw_dir / f"{symbol}.csv").write_text(csvs[symbol])
        for symbol in SYMBOLS:
            raw = pd.read_csv(StringIO(csvs[symbol]), index_col=0)
            index = _session_index(raw)
            if (index.hasnans or index.has_duplicates or not index.is_monotonic_increasing):
                raise ValueError(f"{symbol}: invalid or duplicate session dates")
            if len(index) and (index.min() < pd.Timestamp(start) or index.max() > BACKTEST_END):
                raise ValueError(f"{symbol}: provider returned dates outside requested range")
            derived = transform_history(raw)
            derived.to_csv(derived_dir / f"{symbol}.csv", index_label="Date")
            manifest["coverage"][symbol] = _quality(raw, derived)
            frames[symbol] = derived
        calendar = pd.DatetimeIndex([])
        for frame in frames.values():
            calendar = calendar.union(frame.index)
        benchmark_dates = frames[BENCHMARK].index
        for symbol, frame in frames.items():
            manifest["coverage"][symbol]["missing_sessions_vs_union"] = [
                str(d.date()) for d in calendar.difference(frame.index)]
            manifest["coverage"][symbol]["missing_sessions_vs_benchmark"] = [
                str(d.date()) for d in benchmark_dates.difference(frame.index)]
        manifest["status"] = ("downloaded_with_quality_report"
                              if all(len(f) for f in frames.values()) else "incomplete")
        manifest["validated_for_backtest"] = False
    except Exception as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        manifest["retrieval_finished_utc"] = datetime.now(timezone.utc).isoformat()
        for path in (*raw_dir.glob("*.csv"), *derived_dir.glob("*.csv")):
            manifest["files_sha256"][str(path.relative_to(destination))] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return manifest_path


def load_snapshot(manifest_path: str | Path) -> IndiaPanel:
    """Verify a completed snapshot's hashes and return its adapted stock panel.

    Parameters: manifest_path points to an ingestion manifest. Returns IndiaPanel
    using adjusted derived closes and a separate benchmark. Missing observations
    remain missing. The Phase 1 adapter rejects invalid observed prices/volumes;
    this loader never repairs them or declares a snapshot suitable for backtests.
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if (manifest["status"] != "downloaded_with_quality_report"
            or manifest["symbols"] != list(SYMBOLS)
            or manifest["end_inclusive"] != "2024-12-31"):
        raise ValueError("Snapshot is incomplete or has incompatible configuration")
    histories = {}
    for symbol in SYMBOLS:
        for kind in ("raw", "derived"):
            relative = f"{kind}/{symbol}.csv"
            path = manifest_path.parent / relative
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if manifest["files_sha256"].get(relative) != digest:
                raise ValueError(f"Snapshot checksum mismatch: {relative}")
        histories[symbol] = pd.read_csv(
            manifest_path.parent / f"derived/{symbol}.csv", index_col=0, parse_dates=True)
    return build_india_panel(histories, close_basis="adjusted")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inclusive acquisition lower bound")
    parser.add_argument("--destination", required=True, help="New snapshot directory")
    parser.add_argument("--vibe-root", default="/home/jampip/vibe-Trading")
    args = parser.parse_args()
    print(ingest_history(args.destination, start=args.start, vibe_root=args.vibe_root))
