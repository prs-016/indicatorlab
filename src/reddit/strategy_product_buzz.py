"""Week 2, Step 9: the Product Buzz Lead strategy (with James) and one variant, under the new rules.

Signals are computed per stock from weekly data up to the end of week t (Sunday, UTC); a trade is
filled at the close of the next trading day (normally Monday). Everything below was fixed before the
Reddit data for the test period was looked at.

Product Buzz Lead (PDF "Attention template"), each week t, per stock:
  1 buzz       product posts rose 2 weeks in a row (p_t > p_{t-1} > p_{t-2}) and p_t >= 1.5 x median(p_{t-8..t-1})
  2 tone       product net sentiment (pct_positive - pct_negative) over weeks t-1..t is above its
               average over the 26 weeks before them
  3 confirm    Wikipedia views up week over week, or edits >= 2 x their 8-week median (James's
               weekly rows); see WIKI_PATH. Without them the run is logged as "no Wikipedia confirmation".
  4 trend      the last close of week t is above its 50-day average
  enter when all four hold.
  exit at the first of: the stock-subreddit chatter spikes (shared rule) and the next week's posts
  are lower ("peak passed"); weekly product net sentiment < 0; 6 weeks held; close 8% below entry.

Variant "Sentiment Shock, investors not yet" (mine): enter when product net sentiment over weeks
t-1..t is at least 1 standard deviation above its 26-week average, product posts are >= 1.25 x their
8-week median, the stock subreddits have NOT spiked in weeks t-1..t, and the trend filter holds.
Exit when the stock subreddits spike (investors arrive: sell into it), product net sentiment < 0,
4 weeks held, or 8% below entry.

Sizing: equal weight across open positions, at most 25% per stock; total exposure 50% while SPY is
below its 200-day average (checked at the previous close). Costs: 10 bps per unit of turnover.
A period with no trades is logged as "Insufficient data", not as a Drop.
Benchmarks: SPY, the equal-weight universe, and 200 random portfolios that keep every trade's dates
(so the same number of names, holding periods, sizing and regime) but pick a random stock not
already held. Train 2023-01-02..2024-06-30, test 2024-07-01..2025-09-30 (Reddit data starts in 2023,
so this replaces the standard 2011-2019 / 2020-2025 split). 10 stocks is a signal study, not a
stock-picking test.

    python -m src.reddit.strategy_product_buzz --note "first run"
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.market_data import load_daily_close
from src.reddit.reddit_weekly import OUT_RESEARCH
from src.reddit.utils import get_logger, utc_now_iso

log = get_logger("strategy_product_buzz", "pipeline.log")

STRAT = config.load()["strategy"]
COST_BPS = STRAT["cost_bps"]
N_RANDOM = STRAT["n_random_portfolios"]
SEED = STRAT["random_seed"]
SPLIT = {k: [pd.Timestamp(v[0], tz="UTC"), pd.Timestamp(v[1], tz="UTC")] for k, v in STRAT["reddit_split"].items()}
TRADING_DAYS = 252
KEEP_RANDOM_PCT = 90.0          # keep/drop rule: beat at least 90% of random portfolios
MAX_WEIGHT = 0.25
BEAR_EXPOSURE = 0.5
REGIME_SMA_DAYS = 200
TREND_SMA_DAYS = 50
STOP_LOSS = 0.08
BUZZ_RATIO = 1.5
BUZZ_BASE_WEEKS = 8
TONE_WEEKS = 2
TONE_BASE_WEEKS = 26
EDIT_BURST = 2.0
LEAD_MAX_WEEKS = 6
SHOCK_Z = 1.0
SHOCK_BUZZ_RATIO = 1.25
SHOCK_MAX_WEEKS = 4
WIKI_PATH = settings.ROOT / "data" / "shared" / "attention_weekly_wikipedia.csv"   # James's rows, shared format
LOG_PATH = settings.STRATEGY_LOGS / "strategy_log_week2.csv"
LOG_COLS = ["run_id", "run_utc", "who", "strategy", "signals_combined", "entry_rule", "exit_rule", "sizing",
            "regime_filter", "universe", "universe_size", "train_period", "test_period", "train_sharpe",
            "test_sharpe", "index_sharpe_train", "index_sharpe_test", "ew_sharpe_test", "pct_random_beaten_train",
            "pct_random_beaten_test", "train_cagr", "test_cagr", "train_max_drawdown", "test_max_drawdown",
            "train_turnover", "test_turnover", "n_trades_train", "n_trades_test", "decision", "why", "notes",
            "code_sha1"]


# ----------------------------------------------------------------------------- weekly signals
def weekly_features(att: pd.DataFrame, wiki: pd.DataFrame | None) -> pd.DataFrame:
    """Per (ticker, week): product posts/net sentiment, stock-subreddit posts/spike, Wikipedia views/edits."""
    a = att.copy()
    a["week"] = pd.to_datetime(a["week"], utc=True)
    a["net"] = a["pct_positive"] - a["pct_negative"]
    prod = a[a["source"] == "reddit_product"].set_index(["ticker", "week"])
    stock = a[a["source"] == "reddit_stock"].set_index(["ticker", "week"])
    f = pd.DataFrame({"p": prod["posts"], "net": prod["net"], "n_scored": prod["n_scored"]})
    f = f.join(pd.DataFrame({"s": stock["posts"], "s_spike": stock["spike"].astype(bool)}), how="outer")
    if wiki is not None and len(wiki):
        w = wiki.assign(week=pd.to_datetime(wiki["week"], utc=True)).set_index(["ticker", "week"])
        f = f.join(w[["views", "edits"]], how="left")
    else:
        f["views"], f["edits"] = np.nan, np.nan
    return f.reset_index().sort_values(["ticker", "week"])


def _per_ticker(f: pd.DataFrame, fn) -> pd.DataFrame:
    """Apply `fn` to each ticker's weekly rows (sorted by week) and stack the results."""
    parts = [fn(g.sort_values("week")) for _, g in f.groupby("ticker", sort=True)]
    return pd.concat(parts) if parts else pd.DataFrame(columns=["ticker", "week", "entry", "exit"])


def buzz_lead_signals(f: pd.DataFrame, use_wiki: bool) -> pd.DataFrame:
    """Entry and weekly exit flags of Product Buzz Lead (week t, known at the end of week t)."""
    def calc(g: pd.DataFrame) -> pd.DataFrame:
        p, net = g["p"], g["net"]
        base = p.shift(1).rolling(BUZZ_BASE_WEEKS, min_periods=BUZZ_BASE_WEEKS).median()
        buzz = (p > p.shift(1)) & (p.shift(1) > p.shift(2)) & (p >= BUZZ_RATIO * base)
        tone_now = net.rolling(TONE_WEEKS, min_periods=TONE_WEEKS).mean()
        tone_base = net.shift(TONE_WEEKS).rolling(TONE_BASE_WEEKS, min_periods=TONE_BASE_WEEKS // 2).mean()
        tone = tone_now > tone_base
        if use_wiki:
            edits_base = g["edits"].shift(1).rolling(BUZZ_BASE_WEEKS, min_periods=BUZZ_BASE_WEEKS).median()
            confirm = (g["views"] > g["views"].shift(1)) | (g["edits"] >= EDIT_BURST * edits_base)
        else:
            confirm = pd.Series(True, index=g.index)
        peak_passed = g["s_spike"].shift(1, fill_value=False) & (g["s"] < g["s"].shift(1))
        return pd.DataFrame({"ticker": g["ticker"], "week": g["week"], "entry": buzz & tone & confirm,
                             "exit": peak_passed | (net < 0)}, index=g.index)
    return _per_ticker(f, calc)


def sentiment_shock_signals(f: pd.DataFrame) -> pd.DataFrame:
    """Entry and weekly exit flags of the variant (see module docstring)."""
    def calc(g: pd.DataFrame) -> pd.DataFrame:
        p, net, sp = g["p"], g["net"], g["s_spike"]
        base = p.shift(1).rolling(BUZZ_BASE_WEEKS, min_periods=BUZZ_BASE_WEEKS).median()
        tone_now = net.rolling(TONE_WEEKS, min_periods=TONE_WEEKS).mean()
        hist = net.shift(TONE_WEEKS).rolling(TONE_BASE_WEEKS, min_periods=TONE_BASE_WEEKS // 2)
        shock = (tone_now - hist.mean()) >= SHOCK_Z * hist.std()
        investors_quiet = ~(sp | sp.shift(1, fill_value=False))
        return pd.DataFrame({"ticker": g["ticker"], "week": g["week"],
                             "entry": shock & (p >= SHOCK_BUZZ_RATIO * base) & investors_quiet,
                             "exit": sp | (net < 0)}, index=g.index)
    return _per_ticker(f, calc)


# ----------------------------------------------------------------------------- daily simulation
@dataclass
class Spec:
    name: str
    max_weeks: int
    signals: pd.DataFrame = field(repr=False)


def next_trading_day(days: pd.DatetimeIndex, after: pd.Timestamp) -> pd.Timestamp | None:
    """First trading day strictly after `after`."""
    i = days.searchsorted(after, side="right")
    return days[i] if i < len(days) else None


def make_trades(spec: Spec, close: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Entry/exit dates per trade. Weekly signals of week t fill at the first close after Sunday of week t."""
    days = close.index
    sma = close[tickers].rolling(TREND_SMA_DAYS, min_periods=TREND_SMA_DAYS).mean()
    trades = []
    for tk, g in spec.signals.groupby("ticker"):
        g = g.set_index("week").sort_index()
        week_end = {w: w + pd.Timedelta(days=7) - pd.Timedelta(seconds=1) for w in g.index}
        i_open = None
        for w in g.index:
            end = week_end[w]
            fill = next_trading_day(days, end)
            if fill is None:
                break
            if i_open is None:
                last = days[days <= end]
                if not len(last):
                    continue
                d0 = last[-1]
                trend_ok = close.at[d0, tk] > sma.at[d0, tk]
                if bool(g.at[w, "entry"]) and trend_ok and not np.isnan(close.at[fill, tk]):
                    i_open = {"ticker": tk, "entry_date": fill, "entry_price": close.at[fill, tk]}
                continue
            reason = None
            if bool(g.at[w, "exit"]):
                reason = "signal"
            elif fill >= i_open["entry_date"] + pd.Timedelta(weeks=spec.max_weeks):
                reason = "time"
            # stop-loss: any close since entry 8% below the entry price -> exit at the next close
            held = close.loc[(close.index > i_open["entry_date"]) & (close.index <= end), tk]
            hit = held[held <= (1 - STOP_LOSS) * i_open["entry_price"]]
            if len(hit):
                stop_fill = next_trading_day(days, hit.index[0]) or days[-1]
                trades.append({**i_open, "exit_date": stop_fill, "reason": "stop"})
                i_open = None
                continue
            if reason:
                trades.append({**i_open, "exit_date": fill, "reason": reason})
                i_open = None
        if i_open is not None:
            trades.append({**i_open, "exit_date": days[-1], "reason": "end"})
    return pd.DataFrame(trades, columns=["ticker", "entry_date", "entry_price", "exit_date", "reason"])


def simulate(trades: pd.DataFrame, close: pd.DataFrame, bench: str, cost_bps: float = COST_BPS) -> pd.DataFrame:
    """Daily returns of a trade list: held from the entry close to the exit close, equal weight, capped,
    regime-scaled exposure, costs on drifted-weight turnover."""
    rets = close.pct_change(fill_method=None)
    days = close.index
    held = pd.DataFrame(False, index=days, columns=close.columns)
    for t in trades.itertuples(index=False):
        held.loc[(days > t.entry_date) & (days <= t.exit_date), t.ticker] = True   # earns returns after entry
    n = held.sum(axis=1)
    sma = close[bench].rolling(REGIME_SMA_DAYS, min_periods=REGIME_SMA_DAYS).mean()
    # Bear only when SPY is known to be below its 200-day average, as of the previous close.
    bear = (close[bench] < sma).shift(1, fill_value=False).astype(bool)
    exposure = np.where(bear, BEAR_EXPOSURE, 1.0)
    w = held.astype(float).div(n.where(n > 0), axis=0).clip(upper=MAX_WEIGHT).mul(exposure, axis=0).fillna(0.0)
    gross = (w * rets.fillna(0.0)).sum(axis=1)
    drifted = (w * (1 + rets.fillna(0.0))).div(1 + gross, axis=0).shift(1).fillna(0.0)
    turnover = (w - drifted).abs().sum(axis=1)
    net = gross - turnover * cost_bps / 1e4
    return pd.DataFrame({"gross": gross, "net": net, "turnover": turnover, "n_positions": n,
                         "exposure": w.sum(axis=1)})


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
    """Same dates as `trades`, but each trade picks a random stock not already held over its window."""
    out = []
    for t in trades.sort_values("entry_date").itertuples(index=False):
        busy = {o["ticker"] for o in out if o["entry_date"] < t.exit_date and o["exit_date"] > t.entry_date}
        free = [x for x in tickers if x not in busy] or tickers
        out.append({"ticker": rng.choice(free), "entry_date": t.entry_date, "exit_date": t.exit_date,
                    "entry_price": np.nan, "reason": "random"})
    return pd.DataFrame(out, columns=trades.columns)


def _period(df: pd.DataFrame, name: str) -> pd.DataFrame:
    lo, hi = SPLIT[name]
    return df[(df.index >= lo) & (df.index <= hi)]


def evaluate(spec: Spec, close: pd.DataFrame, tickers: list[str], bench: str) -> dict:
    """Strategy, benchmarks and random portfolios for train and test, plus the keep/drop decision."""
    trades = make_trades(spec, close, tickers)
    sim = simulate(trades, close, bench)
    rets = close.pct_change(fill_method=None)
    ew = rets[tickers].mean(axis=1)
    rng = np.random.default_rng(SEED)
    rand = [simulate(random_trades(trades, tickers, rng), close, bench)["net"] for _ in range(N_RANDOM)] \
        if len(trades) else []
    res = {"trades": trades, "sim": sim}
    for p in ("train", "test"):
        s = _period(sim, p)
        m = metrics(s["net"], s["turnover"])
        rs = [metrics(_period(x.to_frame(), p)["net"])["sharpe"] for x in rand]
        beaten = 100 * np.mean([m["sharpe"] > x for x in rs if not np.isnan(x)]) if rs else np.nan
        res[p] = {**m, "index_sharpe": metrics(_period(rets[[bench]], p)[bench])["sharpe"],
                  "ew_sharpe": metrics(_period(ew.to_frame("r"), p)["r"])["sharpe"],
                  "pct_random_beaten": beaten,
                  "n_trades": int(trades["entry_date"].between(SPLIT[p][0], SPLIT[p][1]).sum())}
    if res["train"]["n_trades"] == 0 or res["test"]["n_trades"] == 0:
        empty = [p for p in ("train", "test") if res[p]["n_trades"] == 0]
        res["decision"], res["why"] = "Insufficient data", f"no trades in {' and '.join(empty)}"
    else:
        res["decision"], res["why"] = decide(res["train"], res["test"])
    return res


def decide(train: dict, test: dict) -> tuple[str, str]:
    """The PDF's keep/drop rule."""
    pass_train = train["pct_random_beaten"] >= KEEP_RANDOM_PCT
    pass_test = test["pct_random_beaten"] >= KEEP_RANDOM_PCT
    beats_index = test["sharpe"] > test["index_sharpe"]
    if pass_train and pass_test and beats_index:
        return "Keep", "beat >= 90% of random portfolios in train and test and the index Sharpe in test"
    if pass_train or pass_test:
        which = "train" if pass_train else "test"
        extra = "" if beats_index else "; did not beat the index Sharpe in test"
        return "Keep on watch", f"beat >= 90% of random portfolios in {which} only{extra}"
    return "Drop", (f"beat {train['pct_random_beaten']:.0f}% (train) and {test['pct_random_beaten']:.0f}% (test) "
                    "of random portfolios, under 90% in both")


# ----------------------------------------------------------------------------- run + log
DESCRIPTIONS = {
    "Product Buzz Lead": {
        "signals_combined": "product-subreddit buzz (2 rising weeks, >=1.5x 8w median) + product net sentiment above "
                            "26w average + Wikipedia views/edits confirmation + price above 50d average",
        "entry_rule": "all four true at the end of week t; buy at the next trading day's close",
        "exit_rule": "first of: stock-subreddit spike then lower posts next week; weekly product net sentiment < 0; "
                     "6 weeks; close 8% below entry (sold next close)"},
    "Sentiment Shock, investors not yet": {
        "signals_combined": "product net sentiment >= 1 SD above 26w average + product posts >= 1.25x 8w median + no "
                            "stock-subreddit spike in weeks t-1..t + price above 50d average",
        "entry_rule": "all true at the end of week t; buy at the next trading day's close",
        "exit_rule": "first of: stock-subreddit spike; weekly product net sentiment < 0; 4 weeks; 8% stop-loss"},
}


def append_log(rows: list[dict]) -> None:
    """Append-only week 2 strategy log (every run, every result) plus a TSV for the Google Sheet."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)[LOG_COLS]
    df.to_csv(LOG_PATH, mode="a", header=not LOG_PATH.exists(), index=False)
    pd.read_csv(LOG_PATH).to_csv(LOG_PATH.with_suffix(".tsv"), sep="\t", index=False)


def run(note: str = "", who: str = "Joshua", wiki_path: Path = WIKI_PATH) -> list[dict]:
    """Run both strategies on the research weekly table and log the results."""
    market = settings.MARKET
    tickers, bench = config.tickers(market), config.benchmark(market)
    close = load_daily_close(market)
    close = close[close.index < pd.Timestamp(settings.HOLDOUT_START, tz="UTC")]
    att = pd.read_csv(OUT_RESEARCH)
    wiki = pd.read_csv(wiki_path) if wiki_path.exists() else None
    f = weekly_features(att, wiki)
    use_wiki = wiki is not None
    specs = [Spec("Product Buzz Lead", LEAD_MAX_WEEKS, buzz_lead_signals(f, use_wiki)),
             Spec("Sentiment Shock, investors not yet", SHOCK_MAX_WEEKS, sentiment_shock_signals(f))]
    run_id = "pbl_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = settings.STRATEGY_LOGS / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:12]
    rows = []
    for spec in specs:
        res = evaluate(spec, close, tickers, bench)
        slug = spec.name.split(",")[0].lower().replace(" ", "_")
        res["trades"].to_csv(run_dir / f"{slug}_trades.csv", index=False)
        res["sim"].to_csv(run_dir / f"{slug}_daily.csv")
        notes = [note] if note else []
        if spec.name == "Product Buzz Lead" and not use_wiki:
            notes.append("no Wikipedia confirmation: James's weekly rows not found at " + str(wiki_path))
        notes.append("Reddit split (data from 2023), 10-stock signal study")
        tr, te = res["train"], res["test"]
        rows.append({"run_id": run_id, "run_utc": utc_now_iso(), "who": who, "strategy": spec.name,
                     **DESCRIPTIONS[spec.name],
                     "sizing": "equal weight across open positions, max 25% per stock",
                     "regime_filter": "50% total exposure while SPY < 200-day average",
                     "universe": " ".join(tickers), "universe_size": len(tickers),
                     "train_period": "2023-01-02..2024-06-30", "test_period": "2024-07-01..2025-09-30",
                     "train_sharpe": tr["sharpe"], "test_sharpe": te["sharpe"],
                     "index_sharpe_train": tr["index_sharpe"], "index_sharpe_test": te["index_sharpe"],
                     "ew_sharpe_test": te["ew_sharpe"], "pct_random_beaten_train": tr["pct_random_beaten"],
                     "pct_random_beaten_test": te["pct_random_beaten"], "train_cagr": tr["cagr"],
                     "test_cagr": te["cagr"], "train_max_drawdown": tr["max_drawdown"],
                     "test_max_drawdown": te["max_drawdown"], "train_turnover": tr["turnover"],
                     "test_turnover": te["turnover"], "n_trades_train": tr["n_trades"], "n_trades_test": te["n_trades"],
                     "decision": res["decision"], "why": res["why"], "notes": "; ".join(notes), "code_sha1": sha})
        log.info("%s: train Sharpe %.2f (%.0f%% random), test Sharpe %.2f (%.0f%% random) -> %s", spec.name,
                 tr["sharpe"], tr["pct_random_beaten"], te["sharpe"], te["pct_random_beaten"], res["decision"])
    (run_dir / "run_meta.json").write_text(json.dumps({"run_id": run_id, "note": note, "use_wiki": use_wiki,
                                                       "cost_bps": COST_BPS, "n_random": N_RANDOM, "seed": SEED},
                                                      indent=2))
    append_log(rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--note", default="")
    ap.add_argument("--who", default="Joshua")
    a = ap.parse_args()
    run(a.note, a.who)
