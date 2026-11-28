"""Offline constrained-timing regressions; no historical strategy evaluation."""

import socket

import numpy as np
import pandas as pd
import pytest

from src.india_week3_evaluation import random_timing_schedules
from src.india_week3_portfolio import AccountingPolicy
from src.india_week3_research import price_random_comparisons, price_timing_schedule


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Deny acquisition while exercising scheduling and actual accounting."""

    def denied(*args, **kwargs):
        pytest.fail("Offline randomization attempted network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def inputs():
    sessions = pd.date_range("2022-01-03", periods=20, tz="UTC")
    trades = pd.DataFrame(
        {"ticker": ["A", "B", "C", "D"], "duration": [5] * 4, "weight": [0.2] * 4},
        index=[10, 11, 12, 13],
    )
    initial = dict(zip(trades.index, [0, 0, 4, 4]))
    allowed = {t: [0, 4, 8, 12] for t in trades.index}
    return sessions, trades, initial, allowed


def test_exit_close_releases_slot_before_different_ticker_entry():
    sessions, trades, initial, _ = inputs()
    schedules = random_timing_schedules(
        trades, sessions, {t: [i] for t, i in initial.items()}, max_attempts=1
    )
    assert len(schedules) == 200
    # Four execution endpoints meet at close4; only two post-close holdings.
    assert sum(schedules[0].entry == sessions[4]) == 2
    assert sum(schedules[0].exit == sessions[4]) == 2


def test_same_ticker_shared_endpoint_is_still_rejected():
    sessions, trades, initial, _ = inputs()
    trades.loc[12, "ticker"] = "A"
    with pytest.raises(ValueError, match="slot/ticker"):
        random_timing_schedules(
            trades,
            sessions,
            {t: [i] for t, i in initial.items()},
            max_attempts=1,
            initial_entries=initial,
            mixing_sweeps=2,
        )


def test_replacement_close_replays_sales_before_buys_without_extra_holdings():
    sessions, trades, initial, _ = inputs()
    schedule = random_timing_schedules(
        trades,
        sessions,
        {t: [i] for t, i in initial.items()},
        max_attempts=1,
        initial_entries=initial,
        mixing_sweeps=1,
    )[0]
    close = pd.DataFrame(100.0, index=sessions, columns=list("ABCD"))
    result = price_timing_schedule(
        schedule,
        close,
        close * 100,
        accounting={
            "market": "US",
            "split": "test",
            "policy": AccountingPolicy(
                100000, "fractional", "pretrade_nav_fee_inclusive_budget"
            ),
        },
    )
    assert result.metrics["filled_entries"] == 4
    assert result.trades.duration.tolist() == [5] * 4
    assert (result.quantities > 0).sum(axis=1).max() == 2
    fills = result.fills[result.fills.execution_at == sessions[4]]
    assert fills.buy.tolist() == [False, False, True, True]


def test_seeded_chains_preserve_constraints_and_randomize_dense_schedules():
    sessions, trades, initial, allowed = inputs()
    args = {"max_attempts": 1, "initial_entries": initial, "mixing_sweeps": 8}
    frames = random_timing_schedules(trades, sessions, allowed, **args)
    repeat = random_timing_schedules(trades, sessions, allowed, **args)
    assert len(frames) == 200
    signatures = set()
    for frame, other in zip(frames, repeat):
        pd.testing.assert_frame_equal(frame, other)
        occupancy = np.zeros(len(sessions), int)
        own = {}
        assert frame.trade_id.tolist() == trades.index.tolist()
        for r in frame.itertuples():
            start, end = sessions.get_loc(r.entry), sessions.get_loc(r.exit)
            assert start in allowed[r.trade_id] and end - start + 1 == r.duration == 5
            assert r.weight == trades.at[r.trade_id, "weight"]
            occupancy[start:end] += 1
            used = own.setdefault(r.ticker, set())
            assert not used.intersection(range(start, end + 1))
            used.update(range(start, end + 1))
        assert occupancy.max() <= 2
        signatures.add(tuple(frame.entry))
    assert len(signatures) > 50
    pd.testing.assert_frame_equal(trades, inputs()[1])


def test_anchored_method_rejects_invalid_initial_support():
    sessions, trades, initial, allowed = inputs()
    initial[10] = 1
    with pytest.raises(ValueError, match="initial placement"):
        random_timing_schedules(
            trades,
            sessions,
            allowed,
            max_attempts=1,
            initial_entries=initial,
            mixing_sweeps=2,
        )


def test_small_symmetric_chain_explores_both_feasible_states():
    sessions, trades, _, _ = inputs()
    trades = trades.iloc[:1]
    frames = random_timing_schedules(
        trades,
        sessions,
        {10: [0, 8]},
        max_attempts=1,
        initial_entries={10: 0},
        mixing_sweeps=8,
    )
    counts = pd.Series([x.entry.iloc[0] for x in frames]).value_counts()
    assert len(counts) == 2 and counts.min() > 65


def test_200_real_ledger_replays_preserve_counts_resizes_costs_and_timing():
    sessions, trades, initial, allowed = inputs()
    trades = trades.iloc[:2].copy()
    initial = {k: initial[k] for k in trades.index}
    allowed = {k: allowed[k] for k in trades.index}
    trades["resize_path"] = [[(2, 0.15)], [(1, 0.1)]]
    close = pd.DataFrame(100.0, index=sessions, columns=["A", "B"])
    volume = close * 100
    null = price_random_comparisons(
        trades,
        close,
        volume,
        allowed,
        max_attempts=1,
        initial_entries=initial,
        mixing_sweeps=4,
        accounting={
            "market": "US",
            "split": "test",
            "policy": AccountingPolicy(
                100000, "fractional", "pretrade_nav_fee_inclusive_budget"
            ),
        },
    )
    assert len(null["results"]) == 200
    for result in null["results"]:
        assert result.metrics["filled_entries"] == 2
        assert result.trades.duration.tolist() == [5, 5]
        assert (result.fills.decision_at < result.fills.execution_at).all()
        np.testing.assert_allclose(
            result.fills.commission,
            result.fills.quantity * result.fills["close"] * 0.001,
        )
        assert result.daily.cash.min() >= -1e-8
        assert (result.quantities > 0).sum(axis=1).max() <= 2
