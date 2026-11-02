"""Wikipedia-only strategy, "Wiki Attention Breakout", under the Week 2 rules (James step 11).

Rules, fixed before the first run (parameters in config.yaml `wikipedia.strategy`):
  signals   1 views spike: the shared spike rule on weekly article views (wikipedia_views rows)
            2 edit burst: edits >= 2x their 8-week median, as (edits + 1) / (median + 1) >= 2
              (the `ratio` of the wikipedia_edits rows, so weeks with a zero median stay defined)
            3 trend: the last close of week t is above its 50-day average
  entry     all three at the end of week t (Sunday); buy at the next trading day's close
  exit      first of: 4 weeks held; a close 8% below entry; a close below the 50-day average.
            Daily exits are seen at a close and traded at the next day's close.
  sizing    equal weight across open positions, at most 10% per stock, rest in cash
  regime    50% of that exposure while SPY closed below its 200-day average the day before
  costs     10 bps per unit of turnover (config `strategy.cost_bps`)
Test: research data only, train 2016-2019 and test 2020 to Sep 2025 (Wikipedia starts Jul 2015).
Benchmarks: SPY, the equal-weight universe, and 200 random portfolios that keep every trade's dates
(same number of names, holding periods, sizing and regime) but pick a random stock not already held.

    python -m src.wiki_strategy
"""
import numpy as np
import pandas as pd

from src import config

TRADING_DAYS = 252
KEEP_RANDOM_PCT = 90.0   # keep/drop rule: beat at least 90% of random portfolios


def params() -> dict:
    """Strategy parameters from config.yaml."""
    return {**config.load()["wikipedia"]["strategy"], "edit_burst_ratio": config.load()["wikipedia"]["edit_burst_ratio"],
            "cost_bps": config.load()["strategy"]["cost_bps"]}


def description(p: dict, bench: str) -> dict:
    """Strategy Log text columns, built from the parameters actually used."""
    return {
        "strategy": "Wiki Attention Breakout",
        "signals_combined": f"Wikipedia views spike (shared rule) + edit burst (>={p['edit_burst_ratio']:g}x 8w median)"
                            f" + price above {p['trend_days']}d average",
        "entry_rule": "all three at the end of week t; buy at the next trading day's close",
        "exit_rule": f"first of: {p['hold_weeks']} weeks; close {p['stop_loss']:.0%} below entry; "
                     f"close below {p['trend_days']}d average (sold at the next close)",
        "sizing": f"equal weight across open positions, max {p['max_weight']:.0%} per stock",
        "regime_filter": f"{p['regime_exposure']:.0%} exposure while {bench} < {p['regime_days']}-day average",
    }


def weekly_signals(att: pd.DataFrame, edit_burst_ratio: float) -> pd.DataFrame:
    """Per (ticker, week): views spike and edit burst, from shared-format Wikipedia rows."""
    a = att.assign(week=pd.to_datetime(att["week"]))
    views = a[a["source"] == "wikipedia_views"].set_index(["ticker", "week"])["spike"].astype(bool)
    edits = a[a["source"] == "wikipedia_edits"].set_index(["ticker", "week"])["ratio"]
    out = pd.DataFrame({"views_spike": views, "edit_burst": edits >= edit_burst_ratio})
    out["attention"] = out["views_spike"] & out["edit_burst"].fillna(False)
    return out.reset_index()


def _next_day(days: pd.DatetimeIndex, after: pd.Timestamp) -> pd.Timestamp | None:
    i = days.searchsorted(after, side="right")
    return days[i] if i < len(days) else None


def make_trades(sig: pd.DataFrame, close: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Entry and exit dates of every trade (one open trade per stock at a time)."""
    days = close.index
    sma = close.rolling(p["trend_days"], min_periods=p["trend_days"]).mean()
    trades = []
    for tk, g in sig[sig["attention"]].groupby("ticker"):
        if tk not in close:
            continue
        busy_until = None
        for w in sorted(g["week"]):
            week_end = w + pd.Timedelta(days=6)
            last = days[days <= week_end]
            if not len(last) or (busy_until is not None and last[-1] < busy_until):
                continue
            d0 = last[-1]
            entry = _next_day(days, week_end)
            if entry is None or not close.at[d0, tk] > sma.at[d0, tk] or np.isnan(close.at[entry, tk]):
                continue
            px = close.at[entry, tk]
            after = close.loc[days > entry, tk]
            limit = after.index[after.index >= entry + pd.Timedelta(weeks=p["hold_weeks"])]
            stop = after.index[(after <= (1 - p["stop_loss"]) * px) | (after < sma.loc[after.index, tk])]
            exit_ = limit[0] if len(limit) else days[-1]
            reason = "time"
            if len(stop) and stop[0] < exit_:
                nxt = _next_day(days, stop[0]) or days[-1]
                if nxt <= exit_:
                    exit_, reason = nxt, "stop_or_trend"
            trades.append({"ticker": tk, "signal_week": w, "entry_date": entry, "entry_price": px,
                           "exit_date": exit_, "reason": reason})
            busy_until = exit_
    return pd.DataFrame(trades, columns=["ticker", "signal_week", "entry_date", "entry_price", "exit_date", "reason"])


def simulate(trades: pd.DataFrame, close: pd.DataFrame, bench: str, p: dict) -> pd.DataFrame:
    """Daily net returns: held from the entry close to the exit close, capped equal weight, regime-scaled, costs."""
    rets = close.pct_change(fill_method=None).fillna(0.0)
    days = close.index
    held = pd.DataFrame(False, index=days, columns=close.columns)
    for t in trades.itertuples(index=False):
        held.loc[(days > t.entry_date) & (days <= t.exit_date), t.ticker] = True
    n = held.sum(axis=1)
    sma = close[bench].rolling(p["regime_days"], min_periods=p["regime_days"]).mean()
    bear = (close[bench] < sma).shift(1, fill_value=False).astype(bool)
    exposure = np.where(bear, p["regime_exposure"], 1.0)
    w = held.astype(float).div(n.where(n > 0), axis=0).clip(upper=p["max_weight"]).mul(exposure, axis=0).fillna(0.0)
    gross = (w * rets).sum(axis=1)
    drifted = (w * (1 + rets)).div(1 + gross, axis=0).shift(1).fillna(0.0)
    turnover = (w - drifted).abs().sum(axis=1)
    return pd.DataFrame({"net": gross - turnover * p["cost_bps"] / 1e4, "turnover": turnover,
                         "n_positions": n, "exposure": w.sum(axis=1)})


def metrics(r: pd.Series, turnover: pd.Series | None = None) -> dict:
    """CAGR, annualised Sharpe (rf = 0), max drawdown and annual turnover of daily returns."""
    r = r.dropna()
    if len(r) < 2:
        return {"cagr": np.nan, "sharpe": np.nan, "max_drawdown": np.nan, "turnover": np.nan}
    growth = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    sd = r.std()
    return {"cagr": growth.iloc[-1] ** (1 / years) - 1,
            "sharpe": r.mean() / sd * np.sqrt(TRADING_DAYS) if sd > 0 else np.nan,
            "max_drawdown": (growth / growth.cummax() - 1).min(),
            "turnover": turnover.loc[r.index].sum() / years if turnover is not None else np.nan}


def random_trades(trades: pd.DataFrame, tickers: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """Same dates as `trades`, each with a random stock not already held over its window."""
    out = []
    for t in trades.sort_values("entry_date").itertuples(index=False):
        busy = {o["ticker"] for o in out if o["entry_date"] < t.exit_date and o["exit_date"] > t.entry_date}
        free = [x for x in tickers if x not in busy] or tickers
        out.append({"ticker": rng.choice(free), "entry_date": t.entry_date, "exit_date": t.exit_date})
    return pd.DataFrame(out, columns=["ticker", "entry_date", "exit_date"])


def decide(train: dict, test: dict) -> tuple[str, str]:
    """The PDF's keep/drop rule."""
    pass_train = train["pct_random_beaten"] >= KEEP_RANDOM_PCT
    pass_test = test["pct_random_beaten"] >= KEEP_RANDOM_PCT
    beats_index = test["sharpe"] > test["index_sharpe"]
    if pass_train and pass_test and beats_index:
        return "Keep", "beat >= 90% of random portfolios in train and test and the index Sharpe in test"
    if pass_train or pass_test:
        which = "train" if pass_train else "test"
        return "Keep on watch", f"beat >= 90% of random portfolios in {which} only" + \
            ("" if beats_index else "; did not beat the index Sharpe in test")
    return "Drop", (f"beat {train['pct_random_beaten']:.0f}% (train) and {test['pct_random_beaten']:.0f}% (test) "
                    "of random portfolios, under 90% in both")


def evaluate(att: pd.DataFrame, close: pd.DataFrame, tickers: list[str], bench: str,
             split: dict, n_random: int, seed: int) -> dict:
    """Strategy, SPY, equal weight and random portfolios in train and test, plus the keep/drop decision."""
    p = params()
    trades = make_trades(weekly_signals(att, p["edit_burst_ratio"]), close[tickers + [bench]], p)
    sim = simulate(trades, close, bench, p)
    rets = close.pct_change(fill_method=None)
    rng = np.random.default_rng(seed)
    rand = [simulate(random_trades(trades, tickers, rng), close, bench, p)["net"] for _ in range(n_random)] \
        if len(trades) else []
    res = {"trades": trades, "sim": sim}
    for name, (lo, hi) in split.items():
        def cut(s: pd.Series, lo=lo, hi=hi) -> pd.Series:
            return s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
        m = metrics(cut(sim["net"]), sim["turnover"])
        rs = [metrics(cut(x))["sharpe"] for x in rand]
        rs = [x for x in rs if not np.isnan(x)]
        res[name] = {**m, "index_sharpe": metrics(cut(rets[bench]))["sharpe"],
                     "ew_sharpe": metrics(cut(rets[tickers].mean(axis=1)))["sharpe"],
                     "ew_cagr": metrics(cut(rets[tickers].mean(axis=1)))["cagr"],
                     "index_cagr": metrics(cut(rets[bench]))["cagr"],
                     "pct_random_beaten": 100 * np.mean([m["sharpe"] > x for x in rs]) if rs else np.nan,
                     "random_median_sharpe": float(np.median(rs)) if rs else np.nan,
                     "n_trades": int(trades["entry_date"].between(pd.Timestamp(lo), pd.Timestamp(hi)).sum())}
    if min(res[k]["n_trades"] for k in split) == 0:
        res["decision"], res["why"] = "Insufficient data", "no trades in a period"
    else:
        res["decision"], res["why"] = decide(res["train"], res["test"])
    return res


def log_row(res: dict, tickers: list[str], split: dict, bench: str) -> dict:
    """One Strategy Log row with the PDF's new columns."""
    tr, te = res["train"], res["test"]
    return {**description(params(), bench), "who": "James", "universe_size": len(tickers),
            "train_period": "..".join(str(d) for d in split["train"]),
            "test_period": "..".join(str(d) for d in split["test"]),
            "train_sharpe": tr["sharpe"], "test_sharpe": te["sharpe"], "index_sharpe_train": tr["index_sharpe"],
            "index_sharpe_test": te["index_sharpe"], "pct_random_beaten_train": tr["pct_random_beaten"],
            "pct_random_beaten_test": te["pct_random_beaten"], "train_cagr": tr["cagr"], "test_cagr": te["cagr"],
            "train_max_drawdown": tr["max_drawdown"], "test_max_drawdown": te["max_drawdown"],
            "train_turnover": tr["turnover"], "test_turnover": te["turnover"], "n_trades_train": tr["n_trades"],
            "n_trades_test": te["n_trades"], "decision": res["decision"], "why": res["why"]}


def run(market: str = "US") -> dict:
    """Run on the research data and write trades, daily returns and the log row to results/wikipedia/."""
    from src.wiki_pipeline import RAW, ROOT, shared_path, universe
    holdout = pd.Timestamp(config.holdout_start())
    tickers, bench = list(universe(market)), config.benchmark(market)
    close = pd.read_csv(RAW / "prices" / f"daily_close_{market}.csv", index_col=0, parse_dates=True)
    close = close[close.index < holdout]
    att = pd.read_csv(shared_path("research"))
    split = config.load()["wikipedia"]["split"]
    s = config.load()["strategy"]
    res = evaluate(att, close, tickers, bench, split, s["n_random_portfolios"], s["random_seed"])
    out = ROOT / "results" / "wikipedia"
    out.mkdir(parents=True, exist_ok=True)
    res["trades"].to_csv(out / "wiki_breakout_trades.csv", index=False)
    res["sim"].to_csv(out / "wiki_breakout_daily.csv")
    row = log_row(res, tickers, split, bench)
    pd.DataFrame([row]).to_csv(out / "strategy_log_rows.tsv", sep="\t", index=False)
    return res


if __name__ == "__main__":
    r = run()
    for k in ("train", "test"):
        print(k, {m: round(v, 3) if isinstance(v, float) else v for m, v in r[k].items()})
    print(r["decision"], "-", r["why"])
