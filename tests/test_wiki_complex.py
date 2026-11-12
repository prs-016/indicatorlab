"""Synthetic checks of the Week 3 complex-strategy simulator and evaluation (no network)."""
import numpy as np
import pandas as pd
import pytest

from src import wiki_complex as wc

TICKERS = ["AAA", "BBB", "CCC"]


def make_market(n_days=320, spy_trend=0.001, seed=0, jumps=None):
    """Random-walk prices for 3 stocks + SPY on business days, with optional {(ticker, day): return}."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-06", periods=n_days)
    r = pd.DataFrame(rng.normal(0, 0.01, (n_days, 4)), index=days, columns=TICKERS + ["SPY"])
    r["SPY"] += spy_trend
    for (t, d), x in (jumps or {}).items():
        r.loc[days[d], t] = x
    close = 100 * (1 + r).cumprod()
    volume = pd.DataFrame(1e6, index=days, columns=close.columns)
    weeks = pd.date_range(days[0], days[-1], freq="W-MON")
    zeros = pd.DataFrame(0.0, index=weeks, columns=TICKERS)
    weekly = {"abn_views": zeros + rng.normal(0, 0.1, zeros.shape), "views_ratio": zeros + 1.0,
              "spike": zeros.astype(bool), "burst": zeros.astype(bool), "revert_share": zeros,
              "news": zeros.astype(bool), "bad_news": zeros.astype(bool)}
    return wc.Market(close, volume, "SPY", TICKERS, weekly)


class Hold(wc.Strategy):
    """Holds a fixed set from a given week on."""
    name, indicators = "hold", ("regime",)

    def __init__(self, names, from_week, stop=0.0, **kw):
        super().__init__(**kw)
        self.names, self.from_week, self.stop = set(names), pd.Timestamp(from_week), stop

    def rebalance(self, m, week, fri, held, first_of_month):
        return self.names if week >= self.from_week else set()

    def signal(self, m, week, fri):
        return pd.Series(1.0, index=m.tickers)


def test_week_w_signal_is_traded_at_the_next_weeks_first_close():
    m = make_market()
    week = m.weeks.index[60]
    sig_day = m.weeks.at[week, "signal"]
    w = wc.simulate(Hold(["AAA"], week), m, cost=0)["weights"]["AAA"]
    assert w[w.index < sig_day].eq(0).all()
    assert w.loc[sig_day] > 0                          # bought at the signal day's close ...
    net = wc.simulate(Hold(["AAA"], week), m, cost=0)["net"]
    assert net.loc[sig_day] == 0                       # ... so that day's return is not earned
    nxt = m.days[m.days.get_loc(sig_day) + 1]
    assert net.loc[nxt] == pytest.approx(w.loc[sig_day] * m.ret.at[nxt, "AAA"])


def test_trailing_stop_is_seen_at_a_close_and_traded_at_the_next():
    base = make_market()
    week = base.weeks.index[60]
    entry = base.days.get_loc(base.weeks.at[week, "signal"])
    drop = entry + 2                                   # before the next weekly signal day
    m = make_market(jumps={("AAA", drop): -0.15})
    sim = wc.simulate(Hold(["AAA"], week, stop=0.10), m, cost=0)
    w = sim["weights"]["AAA"]
    assert w.iloc[drop] > 0                            # the loss on the drop day is taken
    assert w.iloc[drop + 1] == 0                       # sold at the next close
    assert sim["net"].iloc[drop] == pytest.approx(w.iloc[drop - 1] * -0.15)
    first = sim["trades"].iloc[0]
    assert (first["entry_idx"], first["exit_idx"]) == (entry, drop + 1)


def test_weights_are_capped_at_10pct_and_halved_below_spy_200d():
    up = wc.simulate(Hold(TICKERS, "2020-01-01"), make_market(spy_trend=0.003), cost=0)["weights"]
    down = wc.simulate(Hold(TICKERS, "2020-01-01"), make_market(spy_trend=-0.003), cost=0)["weights"]
    late = up.index[-1]
    assert up.loc[late].tolist() == pytest.approx([wc.MAX_WEIGHT] * 3)
    assert down.loc[late].tolist() == pytest.approx([wc.MAX_WEIGHT * wc.HALF] * 3)


def test_costs_are_charged_per_unit_of_turnover():
    m = make_market()
    week = m.weeks.index[60]
    a, b = (wc.simulate(Hold(["AAA"], week), m, cost=c) for c in (0, 0.001))
    turnover = a["weights"].diff().abs().sum(axis=1)
    assert (a["net"] - b["net"]).sum() == pytest.approx(turnover.sum() * 0.001)


def test_random_entry_baseline_is_reproducible_and_counts_runs():
    m = make_market()
    sim = wc.simulate(Hold(["AAA", "BBB"], m.weeks.index[60], stop=0.02), m, cost=0.001)
    period = (str(m.days[0].date()), str(m.days[-1].date()))
    one = wc.random_entry_sharpes(sim["trades"], m, period, 0.001, n=20, seed=1)
    assert one == wc.random_entry_sharpes(sim["trades"], m, period, 0.001, n=20, seed=1)
    assert len(one) == 20


def test_market_gate_fires_on_a_market_wide_attention_jump():
    weeks = pd.date_range("2018-01-01", periods=60, freq="W-MON")
    rng = np.random.default_rng(0)
    level = pd.DataFrame(rng.normal(0, 0.05, (60, 3)), index=weeks, columns=TICKERS)
    level.iloc[-1] = 1.0
    gate = wc.market_gate(level, level * 0 > 1)
    assert gate.iloc[-1] and not gate.iloc[:52].any()  # undefined history leaves the gate open


def test_deflated_sharpe_falls_as_trials_grow():
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.01, 1000))
    trials = list(np.random.default_rng(1).normal(0, 0.5, 30))
    assert wc.deflated_sharpe(r, trials, 5) > wc.deflated_sharpe(r, trials, 100)


def test_keep_needs_every_pass_mark():
    good = {"train": {"n_trades": 40, "sharpe": 1, "index_sharpe": 0.5, "pct_random_beaten": 95},
            "test": {"n_trades": 30, "sharpe": 1, "index_sharpe": 0.5, "pct_random_beaten": 92}}
    assert wc.decide({"periods": good})[0] == "KEEP"
    few = {**good, "train": {**good["train"], "n_trades": 12}}
    assert wc.decide({"periods": few}) == ("DROP", "only 12 train entries (< 30)")


def test_cached_prices_never_reach_the_holdout(tmp_path):
    days = pd.bdate_range("2025-09-25", "2025-10-08")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], ["AAA", "SPY"]])
    pd.DataFrame(1.0, index=days, columns=cols).to_parquet(tmp_path / "ohlcv.parquet")
    px = wc.load_ohlcv(["AAA"], "SPY", "2014-01-01", pd.Timestamp("2025-10-01"), tmp_path / "ohlcv.parquet")
    assert px["close"].index.max() < pd.Timestamp("2025-10-01")


def test_random_baseline_does_not_depend_on_trade_row_order():
    m = make_market()
    sim = wc.simulate(Hold(TICKERS, m.weeks.index[60], stop=0.02), m, cost=0.001)
    period = (str(m.days[0].date()), str(m.days[-1].date()))
    shuffled = sim["trades"].sample(frac=1, random_state=3)
    assert wc.random_entry_sharpes(shuffled, m, period, 0.001, n=10, seed=1) == \
        wc.random_entry_sharpes(sim["trades"], m, period, 0.001, n=10, seed=1)


def test_sentiment_change_uses_only_earlier_scored_weeks():
    weeks = pd.date_range("2020-01-06", periods=12, freq="7D")
    net = [0.0] * 9 + [np.nan, 0.5, -0.2]
    weekly = pd.DataFrame({"ticker": "AAA", "week": weeks, "sentiment_net": net,
                           "n_scored": [3] * 9 + [0, 3, 3]})
    chg, n = wc.sentiment_change(weekly, weeks)
    assert chg["AAA"].iloc[:8].isna().all()          # fewer than 8 earlier scored weeks
    assert np.isnan(chg["AAA"].iloc[9])              # unscored week: no value
    assert chg["AAA"].iloc[10] == pytest.approx(0.5)  # prior mean 0 over 9 scored weeks
    assert chg["AAA"].iloc[11] == pytest.approx(-0.2 - 0.5 / 10)
    assert n["AAA"].iloc[9] == 0


def test_s4_enters_on_rising_sentiment_and_exits_after_two_weaker_weeks():
    m = make_market(spy_trend=0.003)
    for k in ("sent_change", "n_scored"):
        m.weekly[k] = pd.DataFrame(np.nan, index=m.weekly["abn_views"].index, columns=["AAA"])
    weeks = m.weeks.index
    m.weekly["views_ratio"].loc[:, "AAA"] = 1.5
    m.weekly["n_scored"].loc[:, "AAA"] = 3
    m.weekly["sent_change"].loc[weeks[50], "AAA"] = 0.2
    m.weekly["sent_change"].loc[[weeks[51], weeks[53]], "AAA"] = -0.1   # week 52 unscored: counts neither way
    s = wc.SentimentConfirmedAttention()
    s.stop = 0.0                                                      # isolate the sentiment exit
    m.close.loc[:, "AAA"] = np.linspace(50, 150, len(m.days))         # always above its 50-day average
    m.__post_init__()
    w = wc.simulate(s, m, cost=0)["weights"]["AAA"]
    held = w[w > 0].index
    assert held.min() == m.weeks.at[weeks[50], "signal"]
    assert held.max() < m.weeks.at[weeks[53], "signal"]               # sold on the 2nd weak scored week
    assert w.loc[m.weeks.at[weeks[52], "signal"]] > 0
    assert "BBB" not in m.weekly["n_scored"].columns                  # only stocks with sentiment trade
