"""Offline adapter integrity, quarantine, causal-clock and existing-engine tests."""

import hashlib
import json
import socket
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from india_week3_test_support import vibe_checkout

from src.india_week3_market_adapter import (
    MarketInputs,
    adapt_history,
    india_cost_engine,
    load_recovered_market,
    original_rank_ic,
)
from src.india_week3_strategies import UNIVERSES


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Deny network for all synthetic tests and isolated original-engine calls."""

    def denied(*a, **k):
        raise AssertionError("No provider requests permitted")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def digest(path):
    """Hash exact synthetic fixture bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, symbol="TCS.NS", *, days=230, missing=None, zero=False):
    """Build explicitly synthetic price/source/clock evidence; not exchange proof."""
    dates = pd.bdate_range("2022-01-03", periods=days)
    f = pd.DataFrame(
        {
            "open": 100 + np.arange(days) * 0.01,
            "high": 102 + np.arange(days) * 0.01,
            "low": 99 + np.arange(days) * 0.01,
            "close": 101 + np.arange(days) * 0.01,
            "volume": 1000.0,
        },
        index=dates,
    )
    if missing is not None:
        f.loc[dates[missing], "volume"] = np.nan
    if zero:
        f.loc[dates[10], "volume"] = 0
    f.index.name = "Date"
    path = tmp_path / (symbol + ".csv")
    f.to_csv(path)
    support = tmp_path / (symbol + "_source.json")
    support.write_text('{"synthetic": true}')
    closes = dates.tz_localize("Asia/Kolkata") + pd.Timedelta(hours=15, minutes=30)
    if not symbol.endswith(".NS") and symbol != "^NSEI":
        closes = dates.tz_localize("America/New_York") + pd.Timedelta(hours=16)
    evidence = {
        "symbol": symbol,
        "price_sha256": digest(path),
        "retrieval_bounds_verified": True,
        "adjustments_verified": True,
        "volume_basis_verified": True,
        "calendar_verified": True,
        "support": {"path": str(support), "sha256": digest(support)},
        "sessions": [
            {
                "Date": str(d.date()),
                "close_at": t.isoformat(),
                "published_at": (t + pd.Timedelta(minutes=5)).isoformat(),
            }
            for d, t in zip(dates, closes, strict=True)
        ],
    }
    ep = tmp_path / (symbol + "_evidence.json")
    ep.write_text(json.dumps(evidence))
    return path, ep, f


def test_values_and_missingness_are_preserved_and_quarantined(tmp_path):
    path, ep, raw = fixture(tmp_path, missing=12, zero=True)
    h = adapt_history(path, digest(path), "TCS.NS", evidence_path=ep)
    pd.testing.assert_frame_equal(h.raw, raw, check_freq=False)
    assert h.audit.accepted.sum() == len(raw) - 2
    assert "unverified_zero_volume" in h.audit.loc[raw.index[10], "reasons"]
    assert np.isnan(h.raw.volume.iloc[12])
    with pytest.raises(ValueError, match="Quarantined"):
        h.execution_bars("2022-01-03", str(raw.index[-1].date()))


def test_missing_evidence_never_assumes_clocks_or_approval(tmp_path):
    path, _ep, raw = fixture(tmp_path)
    h = adapt_history(path, digest(path), "TCS.NS")
    assert not h.audit.accepted.any()
    assert "missing_session_close_or_publication_evidence" in h.audit.reasons.iloc[0]
    with pytest.raises(ValueError):
        h.execution_bars("2022-01-03", str(raw.index[-1].date()))


def test_hash_binding_and_no_source_mutation(tmp_path):
    path, ep, _raw = fixture(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="hash"):
        adapt_history(path, "0" * 64, "TCS.NS")
    adapt_history(path, digest(path), "TCS.NS", evidence_path=ep)
    assert path.read_bytes() == before
    proof = json.loads(ep.read_text())
    proof["symbol"] = "INFY.NS"
    ep.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="binding"):
        adapt_history(path, digest(path), "TCS.NS", evidence_path=ep)


@pytest.mark.parametrize(
    "problem",
    ["support", "naive", "early_publication", "holdout_clock", "wrong_session"],
)
def test_bad_evidence_stops_before_execution(tmp_path, problem):
    path, ep, _ = fixture(tmp_path)
    proof = json.loads(ep.read_text())
    if problem == "support":
        proof["support"]["sha256"] = "0" * 64
    elif problem == "naive":
        proof["sessions"][0]["close_at"] = "2022-01-03T15:30:00"
    elif problem == "early_publication":
        proof["sessions"][0]["published_at"] = "2022-01-03T01:00:00Z"
    elif problem == "holdout_clock":
        proof["sessions"][0]["published_at"] = "2025-10-01T00:00:00Z"
    else:
        proof["sessions"][0]["close_at"] = "2022-01-02T10:00:00Z"
    ep.write_text(json.dumps(proof))
    with pytest.raises(ValueError):
        adapt_history(path, digest(path), "TCS.NS", evidence_path=ep)


def test_future_source_date_is_rejected_not_filtered(tmp_path):
    path, _, _ = fixture(tmp_path)
    f = pd.read_csv(path)
    f.loc[len(f)] = {
        "Date": "2025-10-01",
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 1,
    }
    f.to_csv(path, index=False)
    with pytest.raises(ValueError, match="pre-holdout"):
        adapt_history(path, digest(path), "TCS.NS")


def test_reference_difference_not_rebased_or_spliced(tmp_path):
    path, ep, raw = fixture(tmp_path, "INFY.NS")
    reference = raw.copy()
    reference[["open", "high", "low", "close"]] /= 0.9776
    h = adapt_history(
        path, digest(path), "INFY.NS", evidence_path=ep, reference=reference
    )
    pd.testing.assert_frame_equal(h.raw, raw, check_freq=False)
    assert h.audit.reasons.str.contains("reference_price_difference").all()
    assert not h.audit.accepted.any()


def test_known_missing_session_stays_missing(tmp_path):
    path, ep, raw = fixture(tmp_path)
    # Synthetic calendar expects an additional session; no price is inserted.
    proof = json.loads(ep.read_text())
    d = "2022-01-08"
    proof["sessions"].insert(
        5, {"Date": d, "close_at": d + "T10:00:00Z", "published_at": d + "T10:05:00Z"}
    )
    ep.write_text(json.dumps(proof))
    h = adapt_history(path, digest(path), "TCS.NS", evidence_path=ep)
    assert pd.Timestamp(d) not in h.raw.index
    assert h.audit.loc[d, "reasons"] == "missing_observation"
    with pytest.raises(ValueError):
        h.execution_bars("2022-01-03", str(raw.index[-1].date()))


def test_real_local_close_and_publication_are_retained(tmp_path):
    path, ep, raw = fixture(tmp_path, "MSFT")
    h = adapt_history(path, digest(path), "MSFT", evidence_path=ep)
    frame = h.execution_bars("2022-01-03", str(raw.index[-1].date()))
    assert frame.index[0] == pd.Timestamp("2022-01-03T21:00:00Z")
    assert frame.published_at.iloc[0] == pd.Timestamp("2022-01-03T21:05:00Z")
    assert frame.index[-1].hour == 21  # November, after DST ends
    assert frame.index[60].hour == 20
    with pytest.raises(ValueError, match="Partial"):
        h.execution_bars("2016-06-01", "2025-09-30")


def test_benchmark_does_not_require_fabricated_volume(tmp_path):
    path, ep, raw = fixture(tmp_path, "^NSEI")
    raw[["close"]].to_csv(path)
    proof = json.loads(ep.read_text())
    proof["price_sha256"] = digest(path)
    proof["volume_basis_verified"] = False
    ep.write_text(json.dumps(proof))
    h = adapt_history(path, digest(path), "^NSEI", evidence_path=ep)
    assert h.audit.accepted.all() and h.raw.volume.isna().all()


def market_fixture(tmp_path, market):
    """Build exact synthetic baskets for causal snapshot/accounting input checks."""
    histories = {}
    for s in UNIVERSES[market]:
        p, e, _ = fixture(tmp_path, s)
        proof = json.loads(e.read_text())
        proof["reference_reconciliation_verified"] = True
        e.write_text(json.dumps(proof))
        histories[s] = adapt_history(p, digest(p), s, evidence_path=e)
    benchmark = "^NSEI" if market == "IN" else "SPY"
    p, e, _ = fixture(tmp_path, benchmark)
    return MarketInputs(
        market, histories, adapt_history(p, digest(p), benchmark, evidence_path=e)
    )


@pytest.mark.parametrize("market", ["IN", "US"])
def test_full_existing_snapshot_and_accounting_boundary(tmp_path, market):
    inputs = market_fixture(tmp_path, market)
    end = str(next(iter(inputs.histories.values())).raw.index[-1].date())
    frames = inputs.accounting_inputs(start="2022-01-03", end=end)
    assert tuple(frames["close"].columns) == UNIVERSES[market]
    assert frames["close"].index.equals(frames["volume"].index)
    at = pd.Timestamp("2022-11-15T00:00:00Z")
    weekly = {
        at: pd.DataFrame(
            {
                "published_at": at - pd.Timedelta(hours=1),
                "reddit_ratio": 1.0,
                "wiki_ratio": 1.0,
                "reddit_rz": 0.0,
                "wiki_rz": 0.0,
            },
            index=UNIVERSES[market],
        )
    }
    snapshots, daily = inputs.prepare("AGM_v2", weekly, start="2022-01-03", end=end)
    features, benchmark = snapshots[at]
    assert (features.close_at < at).all() and (features.published_at < at).all()
    assert benchmark["close_at"] < at and set(daily) == set(UNIVERSES[market])
    # A separate, independently bound synthetic source changes only future bars.
    for h in inputs.histories.values():
        f = h.raw.copy()
        f.loc[f.index > "2022-11-15", ["open", "high", "low", "close"]] *= 1.01
        path = Path(h.provenance["path"])
        f.to_csv(path, index_label="Date")
        ep = tmp_path / (h.symbol + "_evidence.json")
        proof = json.loads(ep.read_text())
        proof["price_sha256"] = digest(path)
        ep.write_text(json.dumps(proof))
        inputs.histories[h.symbol] = adapt_history(
            path, digest(path), h.symbol, evidence_path=ep
        )
    again, _ = inputs.prepare("AGM_v2", weekly, start="2022-01-03", end=end)
    pd.testing.assert_frame_equal(features, again[at][0])


def test_missing_benchmark_and_wrong_market_fee_binding_fail(tmp_path):
    inputs = market_fixture(tmp_path, "US")
    inputs.benchmark = None
    with pytest.raises(ValueError, match="benchmark"):
        inputs.prepare("AGM_v2", {}, start="2022-01-03", end="2022-11-18")
    with pytest.raises(ValueError, match="US"):
        india_cost_engine(inputs, Path("/unneeded"), {})


def test_original_ic_and_cost_objects_are_reused():
    from src.india_week3_research import original_rank_ic as existing

    assert original_rank_ic is existing
    inputs = MarketInputs("IN", {})
    with india_cost_engine(inputs, vibe_checkout(), {}) as fees:
        assert fees.apply_slippage(100.0, 1) > 100.0
        assert fees.calc_commission(1.0, 100.0, 1, True) > 0


def test_recovery_inventory_is_required_and_hash_verified(tmp_path):
    (tmp_path / "artifact_hashes.json").write_text('{"artifacts":{}}')
    with pytest.raises(ValueError, match="Missing recovered"):
        load_recovered_market(tmp_path, "IN")
    with pytest.raises(ValueError, match="market"):
        load_recovered_market(tmp_path, "UNKNOWN")


def test_mutated_source_values_cannot_bypass_prior_validation(tmp_path):
    path, ep, raw = fixture(tmp_path)
    h = adapt_history(path, digest(path), "TCS.NS", evidence_path=ep)
    h.raw.loc[raw.index[0], "volume"] = 9999
    with pytest.raises(ValueError, match="changed after validation"):
        h.execution_bars("2022-01-03", str(raw.index[-1].date()))
