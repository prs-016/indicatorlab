"""Offline regressions for frozen WCR cooldown in matched timing controls."""

import importlib.util
import socket
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from india_week3_test_support import vibe_checkout

from src.india_week3_evaluation import random_timing_schedules


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Offline WCR test attempted a network request")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


def fixture():
    sessions = pd.bdate_range("2022-01-03", periods=100, tz="UTC") + pd.Timedelta(
        hours=20
    )
    decisions = pd.date_range(
        pd.Timestamp("2022-01-04", tz="UTC"), sessions[-1].normalize(), freq="7D"
    )
    trades = pd.DataFrame(
        {"ticker": ["A", "A"], "duration": [3, 3], "weight": [0.2, 0.2]}, index=[1, 2]
    )
    candidates = {i: list(range(1, 96, 5)) for i in trades.index}
    return sessions, decisions, trades, candidates


def test_200_wcr_schedules_preserve_four_strict_prior_decisions():
    sessions, decisions, trades, candidates = fixture()
    schedules = random_timing_schedules(
        trades,
        sessions,
        candidates,
        max_attempts=1,
        initial_entries={1: 1, 2: 26},
        mixing_sweeps=8,
        cooldown_decisions=decisions,
        cooldown_steps=4,
    )
    assert len(schedules) == 200
    for s in schedules:
        ordered = s.sort_values("entry")
        first, second = list(ordered.itertuples())
        decision = decisions[decisions < second.entry][-1]
        assert sum((decisions > first.exit) & (decisions < decision)) >= 4
        assert first.duration == second.duration == 3
        assert first.weight == second.weight == 0.2
        assert s.attrs["sampler"]["strict_prior_decision_cooldown"] == 4
        assert decision > first.exit


def test_fourth_decision_after_exit_is_not_four_strictly_prior_decisions():
    sessions, decisions, trades, candidates = fixture()
    with pytest.raises(ValueError, match="slot/ticker"):
        random_timing_schedules(
            trades,
            sessions,
            candidates,
            max_attempts=1,
            initial_entries={1: 1, 2: 21},
            mixing_sweeps=1,
            cooldown_decisions=decisions,
            cooldown_steps=4,
        )


def test_cooldown_is_per_ticker_not_portfolio_wide():
    sessions, decisions, trades, candidates = fixture()
    trades.loc[2, "ticker"] = "B"
    schedules = random_timing_schedules(
        trades,
        sessions,
        candidates,
        max_attempts=1,
        initial_entries={1: 1, 2: 1},
        mixing_sweeps=1,
        cooldown_decisions=decisions,
        cooldown_steps=4,
    )
    assert len(schedules) == 200


def test_cooldown_requires_an_auditable_clock_and_feasible_anchor():
    sessions, _, trades, candidates = fixture()
    with pytest.raises(ValueError, match="Cooldown requires"):
        random_timing_schedules(
            trades, sessions, candidates, max_attempts=1, cooldown_steps=4
        )


def test_zero_cooldown_preserves_existing_seeded_wvb_method():
    sessions, decisions, trades, candidates = fixture()
    kw = {"max_attempts": 1, "initial_entries": {1: 1, 2: 26}, "mixing_sweeps": 2}
    old = random_timing_schedules(trades, sessions, candidates, **kw)
    explicit = random_timing_schedules(
        trades,
        sessions,
        candidates,
        **kw,
        cooldown_decisions=decisions,
        cooldown_steps=0
    )
    for a, b in zip(old, explicit):
        pd.testing.assert_frame_equal(a, b)
        np.testing.assert_equal(a.attrs, b.attrs)


def test_common_wcr_evaluator_passes_and_records_original_cooldown_clock():
    from src.india_week3_wiki_strategies import (
        evaluate_wiki_run,
        wiki_random_candidates,
    )

    path = Path(__file__).with_name("test_india_week3_wiki_strategies.py")
    spec = importlib.util.spec_from_file_location("wcr_fixture", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    run, args = helper.run("WCR_v1_2")
    trades = run["result"].trades.set_index("trade_id")
    anchors = {
        t: args["close"].index.get_loc(row.entry) for t, row in trades.iterrows()
    }
    decisions = pd.DatetimeIndex(sorted(run["plans"]))
    report = evaluate_wiki_run(
        run,
        benchmark=args["close"].iloc[:, 0],
        close=args["close"],
        volume=args["volume"],
        snapshots=args["snapshots"],
        market="US",
        split="test",
        policy=args["policy"],
        ledger=args["ledger"],
        trial_prefix="wcr-fixture-cooldown",
        vibe_root=vibe_checkout(),
        random_candidates=wiki_random_candidates(run, args["close"], args["volume"]),
        max_attempts=1,
        random_initial_entries=anchors,
        random_mixing_sweeps=2,
        random_cooldown_decisions=decisions,
        random_cooldown_steps=4,
    )
    assert len(report["random"]) == 200
    records = [r for r in args["ledger"].records if r["kind"] == "random"]
    assert len(records) == 200
    assert all(r["settings"]["cooldown_steps"] == 4 for r in records)
    assert all(r["settings"]["cooldown_decisions"] for r in records)
