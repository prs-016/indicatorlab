"""Product Buzz Lead mechanics: fill timing, stop-loss, costs, random portfolios and the keep/drop rule."""
import numpy as np
import pandas as pd
import pytest

from src.reddit import strategy_product_buzz as pb

DAYS = pd.bdate_range("2024-01-01", periods=140, tz="UTC")   # Mondays to Fridays


def _close(path_a=None):
    c = pd.DataFrame({"A": 100.0, "B": 100.0, "SPY": np.linspace(100, 140, len(DAYS))}, index=DAYS)
    c["A"] = np.linspace(80, 100, len(DAYS)) if path_a is None else path_a   # rising, so above its 50d average
    return c


def _spec(entry_weeks, exit_weeks=(), max_weeks=6, tickers=("A",)):
    weeks = pd.date_range("2024-01-01", periods=28, freq="7D", tz="UTC")
    rows = [{"ticker": t, "week": w, "entry": w in entry_weeks, "exit": w in exit_weeks} for t in tickers for w in weeks]
    return pb.Spec("test", max_weeks, pd.DataFrame(rows))


def test_signal_of_week_t_fills_at_next_monday_close_and_earns_from_tuesday():
    w = pd.Timestamp("2024-03-18", tz="UTC")                    # signal known Sunday 2024-03-24
    trades = pb.make_trades(_spec({w}), _close(), ["A"])
    t = trades.iloc[0]
    assert t["entry_date"] == pd.Timestamp("2024-03-25", tz="UTC")   # Monday after the signal week
    sim = pb.simulate(trades, _close(), "SPY", cost_bps=0)
    assert sim.loc["2024-03-25", "n_positions"] == 0 and sim.loc["2024-03-26", "n_positions"] == 1


def test_no_entry_when_price_below_50_day_average():
    falling = np.linspace(120, 80, len(DAYS))
    trades = pb.make_trades(_spec({pd.Timestamp("2024-04-01", tz="UTC")}), _close(falling), ["A"])
    assert trades.empty


def test_time_exit_after_max_weeks():
    w = pd.Timestamp("2024-03-18", tz="UTC")
    t = pb.make_trades(_spec({w}, max_weeks=6), _close(), ["A"]).iloc[0]
    assert t["reason"] == "time" and t["exit_date"] == t["entry_date"] + pd.Timedelta(weeks=6)


def test_stop_loss_exits_at_the_close_after_the_drop():
    path = np.linspace(80, 100, len(DAYS))
    entry = DAYS.get_loc(pd.Timestamp("2024-03-25", tz="UTC"))
    path[entry + 2:] = path[entry] * 0.90                        # Wednesday close 10% below entry
    t = pb.make_trades(_spec({pd.Timestamp("2024-03-18", tz="UTC")}), _close(path), ["A"]).iloc[0]
    assert t["reason"] == "stop" and t["exit_date"] == DAYS[entry + 3]   # sold at Thursday's close


def test_costs_are_10bps_per_unit_turnover_and_weight_is_capped():
    trades = pb.make_trades(_spec({pd.Timestamp("2024-03-18", tz="UTC")}), _close(), ["A"])
    sim = pb.simulate(trades, _close(), "SPY", cost_bps=10)
    assert sim["exposure"].max() == pytest.approx(pb.MAX_WEIGHT)   # one position -> 25%, rest cash
    assert np.allclose(sim["gross"] - sim["net"], sim["turnover"] * 10 / 1e4)
    assert sim["turnover"].sum() == pytest.approx(2 * pb.MAX_WEIGHT, rel=0.05)   # in and out once


def test_random_portfolios_keep_dates_and_avoid_held_stocks():
    trades = pd.DataFrame({"ticker": ["A", "A"], "entry_date": [DAYS[10], DAYS[12]], "entry_price": 1.0,
                           "exit_date": [DAYS[30], DAYS[40]], "reason": "signal"})
    r = pb.random_trades(trades, ["A", "B"], np.random.default_rng(0))
    assert (r["entry_date"].tolist(), r["exit_date"].tolist()) == (trades["entry_date"].tolist(),
                                                                  trades["exit_date"].tolist())
    assert r["ticker"].nunique() == 2                            # overlapping trades get different stocks


@pytest.mark.parametrize("train,test,beats,expected", [
    (95, 92, True, "Keep"), (95, 92, False, "Keep on watch"), (50, 95, True, "Keep on watch"), (40, 60, True, "Drop")])
def test_keep_drop_rule(train, test, beats, expected):
    tr = {"pct_random_beaten": train}
    te = {"pct_random_beaten": test, "sharpe": 1.0, "index_sharpe": 0.5 if beats else 1.5}
    assert pb.decide(tr, te)[0] == expected


def test_bear_market_halves_exposure_from_the_next_day(monkeypatch):
    spy = np.r_[np.linspace(100, 150, 110), np.linspace(150, 90, len(DAYS) - 110)]   # long rise, then a slide
    c = _close()
    c["SPY"] = spy
    trades = pd.DataFrame({"ticker": ["A"], "entry_date": [DAYS[0]], "entry_price": 80.0, "exit_date": [DAYS[-1]],
                           "reason": "end"})
    monkeypatch.setattr(pb, "REGIME_SMA_DAYS", 20)
    sim = pb.simulate(trades, c, "SPY", cost_bps=0)
    assert sim["exposure"].iloc[30] == pytest.approx(pb.MAX_WEIGHT)
    assert sim["exposure"].iloc[-1] == pytest.approx(pb.MAX_WEIGHT * pb.BEAR_EXPOSURE)
