import numpy as np
import pandas as pd

from src.wiki_strategy import (
    decide,
    make_trades,
    metrics,
    random_trades,
    simulate,
    weekly_signals,
)

P = {"hold_weeks": 4, "stop_loss": 0.08, "trend_days": 5, "max_weight": 0.10, "regime_days": 5,
     "regime_exposure": 0.5, "edit_burst_ratio": 2.0, "cost_bps": 10}
DAYS = pd.bdate_range("2024-01-01", periods=80)   # starts on a Monday


def _att(spike_week, ratio):
    w = pd.Timestamp(spike_week)
    return pd.DataFrame({"week": [w, w], "ticker": ["A", "A"], "source": ["wikipedia_views", "wikipedia_edits"],
                         "spike": [True, False], "ratio": [3.0, ratio]})


def _close(path_a):
    return pd.DataFrame({"A": path_a, "B": np.linspace(50, 60, len(DAYS)), "SPY": np.linspace(100, 120, len(DAYS))},
                        index=DAYS)


def test_signal_needs_views_spike_and_edit_burst():
    assert weekly_signals(_att("2024-01-29", 2.5), 2.0)["attention"].tolist() == [True]
    assert weekly_signals(_att("2024-01-29", 1.5), 2.0)["attention"].tolist() == [False]


def test_entry_next_trading_day_and_time_exit_after_4_weeks():
    close = _close(np.linspace(100, 130, len(DAYS)))   # steady uptrend: no stop, always above trend
    t = make_trades(weekly_signals(_att("2024-01-29", 3.0), 2.0), close, P)
    assert len(t) == 1
    assert t.loc[0, "entry_date"] == pd.Timestamp("2024-02-05")   # Monday after the signal week
    assert t.loc[0, "exit_date"] == pd.Timestamp("2024-03-04") and t.loc[0, "reason"] == "time"


def test_stop_loss_exits_at_the_next_close():
    path = np.linspace(100, 130, len(DAYS))
    i = DAYS.get_loc(pd.Timestamp("2024-02-08"))
    path[i:] = path[i:] * 0.85   # 15% drop on Thursday after entry
    t = make_trades(weekly_signals(_att("2024-01-29", 3.0), 2.0), _close(path), P)
    assert t.loc[0, "exit_date"] == pd.Timestamp("2024-02-09") and t.loc[0, "reason"] == "stop_or_trend"


def test_no_entry_below_trend():
    path = np.linspace(130, 100, len(DAYS))   # downtrend: close below its 5-day average
    assert make_trades(weekly_signals(_att("2024-01-29", 3.0), 2.0), _close(path), P).empty


def test_simulate_caps_weight_and_charges_costs():
    close = _close(np.linspace(100, 130, len(DAYS)))
    trades = pd.DataFrame({"ticker": ["A"], "entry_date": [DAYS[10]], "exit_date": [DAYS[20]]})
    sim = simulate(trades, close, "SPY", P)
    assert np.isclose(sim["exposure"].iloc[11:21].max(), 0.10)   # one position, capped at 10%
    assert sim["turnover"].sum() > 0 and (sim["net"].iloc[11:21] < 0.10 * close["A"].pct_change().iloc[11:21]).all()


def test_random_trades_keep_dates_and_avoid_held_names():
    trades = pd.DataFrame({"ticker": ["A", "A"], "entry_date": [DAYS[1], DAYS[2]], "exit_date": [DAYS[10], DAYS[12]]})
    r = random_trades(trades, ["A", "B"], np.random.default_rng(0))
    assert r["entry_date"].tolist() == trades["entry_date"].tolist() and r["ticker"].nunique() == 2


def test_metrics_and_keep_drop_rule():
    m = metrics(pd.Series([0.01, -0.005] * 126))
    assert m["max_drawdown"] < 0 and m["sharpe"] > 0
    good = {"pct_random_beaten": 95, "sharpe": 1.2, "index_sharpe": 0.8}
    bad = {"pct_random_beaten": 40, "sharpe": 0.5, "index_sharpe": 0.8}
    assert decide(good, good)[0] == "Keep"
    assert decide(bad, good)[0] == "Keep on watch"
    assert decide(bad, bad)[0] == "Drop"


def test_evaluate_runs_both_periods_and_logs_config_text(monkeypatch):
    from src import wiki_strategy
    monkeypatch.setattr(wiki_strategy, "params", lambda: P)
    days = pd.bdate_range("2023-01-02", periods=300)
    rng = np.random.default_rng(0)
    close = pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0.001, 0.01, len(days))) for t in ["A", "B", "C", "SPY"]},
                         index=days)
    weeks = pd.date_range("2023-01-02", periods=60, freq="7D")
    att = pd.concat([pd.DataFrame({"week": weeks, "ticker": t, "source": s, "spike": True, "ratio": 3.0})
                     for t in ["A", "B", "C"] for s in ("wikipedia_views", "wikipedia_edits")])
    split = {"train": ["2023-01-02", "2023-06-30"], "test": ["2023-07-01", "2024-02-28"]}
    res = wiki_strategy.evaluate(att, close, ["A", "B", "C"], "SPY", split, n_random=5, seed=1)
    assert res["train"]["n_trades"] > 0 and res["test"]["n_trades"] > 0
    assert 0 <= res["test"]["pct_random_beaten"] <= 100 and res["decision"] in {"Keep", "Keep on watch", "Drop"}
    row = wiki_strategy.log_row(res, ["A", "B", "C"], split, "SPY")
    assert "4 weeks" in row["exit_rule"] and "max 10%" in row["sizing"] and row["universe_size"] == 3
