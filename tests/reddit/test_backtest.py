
import numpy as np
import pandas as pd

from src.reddit import backtest_strategies as bt


def _prices(opens_by_week, ticker="AAPL"):
    """One Monday row per week (plus a Friday row with a different open that must be ignored)."""
    rows = []
    for i, o in enumerate(opens_by_week):
        mon = pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=i)
        rows.append({"date": mon, "ticker": ticker, "Open": o, "Close": o})
        rows.append({"date": mon + pd.Timedelta(days=4), "ticker": ticker, "Open": o * 10, "Close": o * 10})
    return pd.DataFrame(rows)


def test_forward_return_is_next_week_open_to_following_open(monkeypatch):
    monkeypatch.setattr(bt, "TICKERS", ["AAPL"])
    fwd = bt.forward_returns(_prices([100, 110, 121, 133.1]))
    # signal week 2024-01-01 -> enter open of 01-08 (110) -> exit open of 01-15 (121)
    assert np.isclose(fwd.loc["2024-01-01", "AAPL"], 121 / 110 - 1)
    assert np.isclose(fwd.loc["2024-01-08", "AAPL"], 133.1 / 121 - 1)
    assert np.isnan(fwd.loc["2024-01-15", "AAPL"])      # needs two future weeks


def test_missing_trading_week_is_not_bridged(monkeypatch):
    monkeypatch.setattr(bt, "TICKERS", ["AAPL"])
    p = _prices([100, 110, 121, 133.1])
    p = p[~p["date"].between("2024-01-08", "2024-01-14")]     # drop week 2 entirely
    fwd = bt.forward_returns(p)
    assert np.isnan(fwd.loc["2024-01-01", "AAPL"])
    assert np.isnan(fwd.loc["2023-12-25", "AAPL"]) if "2023-12-25" in fwd.index else True


def test_weights(monkeypatch):
    monkeypatch.setattr(bt, "TICKERS", ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    idx = ["w1", "w2"]
    flag = pd.DataFrame(False, index=idx, columns=bt.TICKERS)
    flag.loc["w1", ["A", "B"]] = True
    ratio = pd.DataFrame([list(range(10)), [np.nan] * 5 + list(range(5))], index=idx, columns=bt.TICKERS, dtype=float)
    w = bt.build_weights(flag, ratio, flag)
    assert w["S1"].loc["w1", "A"] == 0.5 and w["S1"].loc["w2"].abs().sum() == 0      # cash with no spike
    assert w["S2"].loc["w1", "B"] == -0.5
    assert np.isclose(w["S3"].loc["w1"].sum(), 0) and np.isclose(w["S3"].loc["w1", "A"], 0.4)
    assert w["S3"].loc["w2"].abs().sum() == 0
    s4 = w["S4"].loc["w1"]
    assert np.isclose(s4[["H", "I", "J"]], 0.5 / 3).all() and np.isclose(s4[["A", "B", "C"]], -0.5 / 3).all()
    assert w["S4"].loc["w2"].abs().sum() == 0                                          # only 5 defined ratios
    assert np.isclose(w["B0"].loc["w2"].sum(), 1)


def test_metrics_and_verdicts():
    r = pd.Series([0.01, -0.02, 0.03, 0.0])
    m = bt.metrics(r, r, pd.Series([True, True, True, False]), None)
    assert np.isclose(m["total_return_net"], 1.01 * 0.98 * 1.03 - 1)
    assert np.isclose(m["max_drawdown_net"], -0.02)
    assert np.isclose(m["hit_rate_invested"], 2 / 3)
    assert bt.verdict(m, "S1").startswith("INSUFFICIENT")
    good = {"eval_weeks": 100, "invested_weeks": 50, "sharpe_net": 0.8, "t_stat_net": 2.5}
    assert bt.verdict(good, "S1").startswith("PROMISING")
    assert bt.verdict({**good, "sharpe_net": 0.2, "t_stat_net": 1.0}, "S1") == "WEAK"
    assert bt.verdict({**good, "sharpe_net": -0.3, "t_stat_net": -1.0}, "S1") == "FAILED"
    assert bt.verdict(good, "B0") == "BENCHMARK"
