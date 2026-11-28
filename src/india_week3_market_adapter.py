"""Offline, provenance-bound Vibe history adapter for frozen Week 3 strategies.

Reads recovered CSVs only. No Vibe package import, provider fallback, price repair,
volume filling, clock guessing, strategy execution or automatic data approval.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.india_week3_costs import OriginalIndiaCosts
from src.india_week3_research import original_rank_ic
from src.india_week3_runner import prepare_snapshots
from src.india_week3_strategies import UNIVERSES

FIELDS = ["open", "high", "low", "close", "volume"]
LOWER = pd.Timestamp("2015-07-01")
UPPER = pd.Timestamp("2025-09-30")
# Existing diagnostic tolerance, not a trading/acceptance threshold or rebasing rule.
REFERENCE_RELATIVE_TOLERANCE = 1e-6
KNOWN_SESSIONS = (
    "2016-10-30",
    "2020-02-01",
    "2023-11-12",
    "2024-01-20",
    "2024-03-02",
    "2024-05-18",
)
REQUIRED_EVIDENCE = (
    "retrieval_bounds_verified",
    "adjustments_verified",
    "volume_basis_verified",
    "calendar_verified",
)
BENCHMARKS = {"US": "SPY", "IN": "^NSEI"}
__all__ = [
    "AdaptedHistory",
    "MarketInputs",
    "adapt_history",
    "india_cost_engine",
    "load_recovered_market",
    "original_rank_ic",
]


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _values_digest(frame):
    return hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    ).hexdigest()


def _dates(values):
    index = pd.DatetimeIndex(pd.to_datetime(values, errors="raise"))
    if (
        index.tz is not None
        or not index.is_unique
        or index.hasnans
        or not index.is_monotonic_increasing
        or not index.equals(index.normalize())
        or len(index) == 0
        or index.min() < LOWER
        or index.max() > UPPER
    ):
        raise ValueError("Require unique sorted pre-holdout session dates")
    return index


def _read_prices(path, expected_hash, benchmark=False):
    if _digest(path) != expected_hash:
        raise ValueError("Price source hash mismatch")
    header = pd.read_csv(path, nrows=0)
    if (not benchmark and list(header.columns) != ["Date", *FIELDS]) or (
        benchmark
        and (
            "Date" not in header
            or "close" not in header
            or not set(header) <= {"Date", *FIELDS}
        )
    ):
        raise ValueError("Require original Date/open/high/low/close/volume schema")
    # Check dates before parsing price values; do not filter forbidden observations.
    dates = _dates(pd.read_csv(path, usecols=["Date"]).Date)
    frame = pd.read_csv(path).set_index("Date").reindex(columns=FIELDS)
    frame.index = dates
    return frame


def _evidence(path, symbol, price_hash):
    if path is None:
        return {}, pd.DataFrame(), {}
    path = Path(path)
    evidence = json.loads(path.read_text())
    if evidence.get("symbol") != symbol or evidence.get("price_sha256") != price_hash:
        raise ValueError("Evidence symbol/price binding mismatch")
    support = evidence.get("support", {})
    source = Path(support.get("path", ""))
    if not source.is_file() or _digest(source) != support.get("sha256"):
        raise ValueError("Evidence support hash mismatch")
    clock = pd.DataFrame(evidence.get("sessions", []))
    if not clock.empty:
        if set(clock) != {"Date", "close_at", "published_at"}:
            raise ValueError("Unexpected evidence session schema")
        clock.index = _dates(clock.pop("Date"))
        for field in ["close_at", "published_at"]:
            # Never silently localize a naive timestamp to UTC.
            if any(pd.Timestamp(v).tzinfo is None for v in clock[field]):
                raise ValueError("Evidence needs timezone-aware timestamps")
            clock[field] = pd.to_datetime(clock[field], utc=True)
            if (clock[field] >= pd.Timestamp("2025-10-01", tz="UTC")).any():
                raise ValueError("Evidence observation reaches holdout")
        if (clock.published_at < clock.close_at).any():
            raise ValueError("Price publication precedes close")
        zone = (
            "Asia/Kolkata"
            if symbol.endswith(".NS") or symbol == "^NSEI"
            else "America/New_York"
        )
        local_days = (
            clock.close_at.dt.tz_convert(zone).dt.tz_localize(None).dt.normalize()
        )
        if list(local_days) != list(clock.index):
            raise ValueError("Close timestamp disagrees with local session date")
    return (
        evidence,
        clock,
        {"evidence_sha256": _digest(path), "support_sha256": support["sha256"]},
    )


@dataclass
class AdaptedHistory:
    """Original dated prices, separate row decisions and bound timing evidence."""

    symbol: str
    raw: pd.DataFrame
    audit: pd.DataFrame
    clock: pd.DataFrame
    provenance: dict

    def execution_bars(self, start: str, end: str):
        """Return ready UTC close bars for an explicit window, or fail closed.

        Bounds select existing history; no incomplete/quarantined row is silently
        removed. Calendar evidence must describe every session in the window.
        Original dates stay in session_date; publication comes only from evidence.
        """
        if (
            _digest(self.provenance["path"]) != self.provenance["price_sha256"]
            or _values_digest(self.raw) != self.provenance["values_sha256"]
        ):
            raise ValueError("Price values changed after validation")
        a, b = pd.Timestamp(start), pd.Timestamp(end)
        if not LOWER <= a <= b <= UPPER:
            raise ValueError("Invalid execution input window")
        if self.raw.index.min() > a or self.raw.index.max() < b:
            raise ValueError("Partial dataset does not cover requested window")
        decisions = self.audit.loc[a:b]
        if decisions.empty or not decisions.accepted.all():
            raise ValueError("Quarantined or missing market observations")
        expected = self.clock.loc[a:b]
        observed = self.raw.loc[a:b]
        if not len(expected) or not observed.index.equals(expected.index):
            raise ValueError("Unverified or incomplete exchange session coverage")
        frame = observed.copy(deep=True)
        frame["session_date"] = frame.index
        frame["published_at"] = expected.published_at.to_numpy()
        frame.index = pd.DatetimeIndex(expected.close_at)
        frame.index.name = "close_at"
        return frame


@dataclass
class MarketInputs:
    """Exact fixed stock basket, optional benchmark, and truthful partial coverage."""

    market: str
    histories: dict[str, AdaptedHistory]
    benchmark: AdaptedHistory | None = None

    def prepare(self, strategy, weekly, *, start, end):
        """Delegate ready data to existing snapshot preparation; never backtest.

        Args: strategy/weekly follow the frozen runner; start/end explicitly scope
            the input history, including warm-up. Returns existing snapshots and
            daily features, failing before signal preparation if inputs are unsafe.
        """
        if self.benchmark is None:
            raise ValueError(f"Missing benchmark {BENCHMARKS[self.market]}")
        bars = {s: h.execution_bars(start, end) for s, h in self.histories.items()}
        benchmark = self.benchmark.execution_bars(start, end)
        if any(not f.index.equals(benchmark.index) for f in bars.values()):
            raise ValueError("Benchmark and stock calendars disagree")
        return prepare_snapshots(strategy, self.market, bars, benchmark, weekly)

    def accounting_inputs(self, *, start, end):
        """Return aligned close/volume frames for the existing accounting runner.

        No costs, quantities, orders or performance are invented. This method
        enforces the same stock/benchmark and observation safeguards as prepare.
        """
        if self.benchmark is None:
            raise ValueError("Missing benchmark")
        reference = self.benchmark.execution_bars(start, end)
        bars = {s: h.execution_bars(start, end) for s, h in self.histories.items()}
        if any(not f.index.equals(reference.index) for f in bars.values()):
            raise ValueError("Benchmark and stock calendars disagree")
        return {
            "close": pd.DataFrame({s: f.close for s, f in bars.items()}),
            "volume": pd.DataFrame({s: f.volume for s, f in bars.items()}),
        }


def adapt_history(path, expected_hash, symbol, *, evidence_path=None, reference=None):
    """Read one hash-pinned candidate and quarantine unsupported observations.

    Args: path/hash bind recovered CSV bytes; symbol is fixed; optional evidence
        binds reviewed retrieval/adjustment/volume/calendar facts and actual clocks
        to those bytes. reference is a hash-verified v4 frame, never a splice input.
    Returns: Original values plus explicit acceptance/reconciliation audit. Evidence
        claims must be backed by their cited source; hashing does not certify truth.
    """
    benchmark = symbol in BENCHMARKS.values()
    raw = _read_prices(path, expected_hash, benchmark=benchmark)
    evidence, clock, proof = _evidence(evidence_path, symbol, expected_hash)
    dates = raw.index.union(clock.index)
    if symbol.endswith(".NS"):
        dates = dates.union(
            pd.to_datetime(
                [
                    d
                    for d in KNOWN_SESSIONS
                    if raw.index.min() <= pd.Timestamp(d) <= raw.index.max()
                ]
            )
        )
    reasons = {d: [] for d in dates}
    for key in REQUIRED_EVIDENCE:
        if benchmark and key == "volume_basis_verified":
            continue
        if evidence.get(key) is not True:
            for d in dates:
                reasons[d].append("unverified_" + key.removesuffix("_verified"))
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    for day in dates:
        if day not in raw.index:
            reasons[day].append("missing_observation")
            continue
        row = numeric.loc[day]
        if not np.isfinite(row[["close"]] if benchmark else row).all():
            reasons[day].append("missing_or_nonfinite_ohlcv")
        if (row[["close"]] if benchmark else row[FIELDS[:4]]).le(0).any() or (
            not benchmark and row.volume < 0
        ):
            reasons[day].append("invalid_price_or_volume")
        if not benchmark and (
            row.high < row[FIELDS[:4]].max() or row.low > row[FIELDS[:4]].min()
        ):
            reasons[day].append("inconsistent_ohlc")
        if row.volume == 0 and not benchmark:
            reasons[day].append("unverified_zero_volume")
        if day not in clock.index:
            reasons[day].append("missing_session_close_or_publication_evidence")
        if (
            symbol == "KOTAKBANK.NS"
            and day == pd.Timestamp("2024-03-01")
            and evidence.get("reference_reconciliation_verified") is not True
        ):
            reasons[day].append("unresolved_Kotak_quantity")
        if (
            symbol == "RELIANCE.NS"
            and day < pd.Timestamp("2023-07-20")
            and evidence.get("reference_reconciliation_verified") is not True
        ):
            reasons[day].append("unresolved_Reliance_normalization")
    audit = pd.DataFrame(index=dates)
    audit.index.name = "Date"
    audit["source_present"] = dates.isin(raw.index)
    audit["reference_present"] = False
    audit["reference_price_ratio"] = np.nan
    audit["reference_volume_equal"] = pd.NA
    if reference is not None:
        for day in raw.index.intersection(reference.index):
            r = reference.loc[day]
            audit.at[day, "reference_present"] = True
            audit.at[day, "reference_price_ratio"] = raw.loc[day, "close"] / r.close
            equal_volume = bool(raw.loc[day, "volume"] == r.volume)
            audit.at[day, "reference_volume_equal"] = equal_volume
            # Comparison flags only; never use a ratio to change prices/quantities.
            equal_price = np.isclose(
                numeric.loc[day, FIELDS[:4]],
                r[FIELDS[:4]].astype(float),
                rtol=REFERENCE_RELATIVE_TOLERANCE,
                atol=0,
                equal_nan=True,
            ).all()
            if evidence.get("reference_reconciliation_verified") is not True:
                if not equal_price:
                    reasons[day].append("unreconciled_reference_price_difference")
                if not equal_volume:
                    reasons[day].append("unreconciled_reference_volume_difference")
    audit["reasons"] = [";".join(reasons[d]) for d in dates]
    audit["accepted"] = audit.reasons.eq("")
    audit["numerical_quality_pass"] = [
        d in raw.index
        and not any(
            r in reasons[d]
            for r in [
                "missing_or_nonfinite_ohlcv",
                "invalid_price_or_volume",
                "inconsistent_ohlc",
                "unverified_zero_volume",
            ]
        )
        for d in dates
    ]
    return AdaptedHistory(
        symbol,
        raw,
        audit,
        clock,
        {
            "path": str(Path(path)),
            "price_sha256": expected_hash,
            "values_sha256": _values_digest(raw),
            "basis": "Preserved Vibe split/dividend-adjusted OHLC and vendor volume; no rebasing",
            "support": proof,
            "full_frozen_period": raw.index.min() <= LOWER and raw.index.max() >= UPPER,
        },
    )


def load_recovered_market(
    audit_directory,
    market,
    *,
    evidence_paths=None,
    v4_directory=None,
    benchmark_path=None,
    benchmark_sha256=None,
):
    """Load the exact recovered basket through an isolated file/hash boundary.

    Args: audit_directory contains previous recovery's immutable exports/inventory;
        market is US/IN; optional evidence/benchmark files carry actual safeguards.
        v4_directory provides independently hash-verified references only.
    Returns: MarketInputs retaining partial periods and quarantines; no network,
        Vibe imports, benchmark substitution or mutation of original files occurs.
    """
    if market not in UNIVERSES:
        raise ValueError("Unknown frozen market")
    directory = Path(audit_directory)
    inventory = json.loads((directory / "artifact_hashes.json").read_text())[
        "artifacts"
    ]
    evidence_paths = evidence_paths or {}
    references = {}
    if v4_directory is not None:
        v4 = Path(v4_directory)
        manifest = json.loads((v4 / "research_manifest.json").read_text())
        for symbol in UNIVERSES[market]:
            key = f"derived/{symbol}.csv"
            if key in manifest["files_sha256"]:
                if _digest(v4 / key) != manifest["files_sha256"][key]:
                    raise ValueError("v4 reference hash mismatch")
                references[symbol] = pd.read_csv(
                    v4 / key, index_col=0, parse_dates=True
                ).loc[LOWER:UPPER]
    histories = {}
    for symbol in UNIVERSES[market]:
        key = f"cache_exports/{symbol}.csv"
        if key not in inventory:
            raise ValueError(f"Missing recovered source {symbol}")
        histories[symbol] = adapt_history(
            directory / key,
            inventory[key],
            symbol,
            evidence_path=evidence_paths.get(symbol),
            reference=references.get(symbol),
        )
    benchmark = None
    if benchmark_path is not None:
        benchmark = adapt_history(
            benchmark_path,
            benchmark_sha256,
            BENCHMARKS[market],
            evidence_path=evidence_paths.get(BENCHMARKS[market]),
        )
    return MarketInputs(market, histories, benchmark)


def india_cost_engine(inputs: MarketInputs, vibe_root, config, **kwargs):
    """Return the existing isolated India fee engine for an IN bundle only.

    Arguments/config follow OriginalIndiaCosts; no fee or execution assumptions
    are added. Original IC is likewise reused via the imported original_rank_ic.
    """
    if inputs.market != "IN":
        raise ValueError("India cost engine cannot price US trades")
    return OriginalIndiaCosts(Path(vibe_root), config, **kwargs)
