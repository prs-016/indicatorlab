"""Week 3 complex strategies on Wikipedia attention + price/volume (James). Rules: docs/wikipedia/week3_strategies.md.

  S1  attention-gated momentum   regime + market attention gate + 12-1 momentum among 50-day uptrends
  S2  attention reversal         buy last week's losers among the most-viewed stocks (revert and volume filters)
  S3  news-tagged breakout       views spike + edit burst with earnings/product tags + 20-day high on volume

Every strategy goes through the guide's full evaluation: IC, train / test Sharpe after costs vs the index,
200 random-entry-timing runs, drop-one ablation, and the deflated Sharpe.

    python -m src.wiki_complex            # US; writes results/wikipedia/week3_*.csv
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import e as EULER_E
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew, spearmanr

from src import config

TRADING_DAYS = 252
MOM_SKIP, MOM_LOOKBACK = 21, 252          # 12-1 momentum: close 1 month ago / close 12 months ago
TREND_DAYS, REGIME_DAYS, VOL_DAYS = 50, 200, 63
BREAKOUT_DAYS, VOLUME_BASE_DAYS = 20, 50
MAX_WEIGHT, HALF = 0.10, 0.5
GATE_Z, GATE_WEEKS, BREADTH_PCT, MIN_HISTORY_WEEKS = 1.5, 52, 0.90, 52
TRIALS_BEFORE = 21                         # James's earlier trials: 20 Vibe factor strategies + Wiki Attention Breakout
EULER_GAMMA = 0.5772156649015329


# ----------------------------------------------------------------------------- data
def load_ohlcv(tickers: list[str], bench: str, start: str, end: pd.Timestamp, cache: Path) -> dict[str, pd.DataFrame]:
    """Daily adjusted close and volume (Yahoo), cached; `end` is exclusive (the holdout start)."""
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        import yfinance as yf
        df = yf.download(tickers + [bench], start=start, end=end.strftime("%Y-%m-%d"), auto_adjust=True,
                         progress=False)[["Close", "Volume"]]
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache)
    df = df[df.index < end]
    return {"close": df["Close"], "volume": df["Volume"]}


def weekly_features(att: pd.DataFrame, edits: pd.DataFrame, burst_ratio: float) -> dict[str, pd.DataFrame]:
    """week x ticker tables from the shared attention table and the weekly edit table."""
    a = att.assign(week=pd.to_datetime(att["week"]))
    v = a[a["source"] == "wikipedia_views"].pivot(index="week", columns="ticker", values=["abnormal", "ratio", "spike"])
    ed = a[a["source"] == "wikipedia_edits"].pivot(index="week", columns="ticker", values="ratio")
    w = edits.assign(week=pd.to_datetime(edits["week"]))
    piv = {c: w.pivot(index="week", columns="ticker", values=c) for c in
           ["edits", "reverts", "tag_earnings", "tag_product_launch", "tag_legal", "tag_layoff"]}
    revert_share = (piv["reverts"] / piv["edits"].where(piv["edits"] > 0)).fillna(0.0)
    return {"abn_views": v["abnormal"].astype(float), "views_ratio": v["ratio"].astype(float),
            "spike": v["spike"].astype("boolean").fillna(False).astype(bool),
            "burst": (ed >= burst_ratio), "revert_share": revert_share,
            "news": (piv["tag_earnings"] + piv["tag_product_launch"]) > 0,
            "bad_news": (piv["tag_legal"] + piv["tag_layoff"]) > 0}


def market_gate(abn_views: pd.DataFrame, burst: pd.DataFrame) -> pd.Series:
    """True in weeks whose market attention z-score > 1.5 or edit-burst breadth is in its top 10% (S1 layer 2)."""
    level = abn_views.mean(axis=1)
    past = level.shift(1).rolling(GATE_WEEKS, min_periods=GATE_WEEKS)
    z = (level - past.mean()) / past.std()
    breadth = burst.where(abn_views.notna()).mean(axis=1)
    cut = breadth.shift(1).expanding(min_periods=MIN_HISTORY_WEEKS).quantile(BREADTH_PCT)
    return (z > GATE_Z) | (breadth > cut)


@dataclass
class Market:
    """Everything a strategy reads, aligned to trading days and weeks."""
    close: pd.DataFrame
    volume: pd.DataFrame
    bench: str
    tickers: list[str]
    weekly: dict[str, pd.DataFrame]
    days: pd.DatetimeIndex = field(init=False)
    weeks: pd.DataFrame = field(init=False)      # week -> friday (last close of week W) and signal day (W+1)

    def __post_init__(self):
        self.days = self.close.index
        c = self.close[self.tickers]
        self.ret = self.close.pct_change(fill_method=None)
        self.ma50 = c.rolling(TREND_DAYS).mean()
        self.spy_ma200 = self.close[self.bench].rolling(REGIME_DAYS).mean()
        self.vol63 = self.ret[self.tickers].rolling(VOL_DAYS).std()
        self.mom = c.shift(MOM_SKIP) / c.shift(MOM_LOOKBACK) - 1
        self.hi20 = c.rolling(BREAKOUT_DAYS).max()
        rows = []
        for w in self.weekly["abn_views"].index:
            fri = self.days[(self.days >= w) & (self.days < w + pd.Timedelta(days=7))]
            nxt = self.days[self.days >= w + pd.Timedelta(days=7)]
            if len(fri) and len(nxt):
                rows.append({"week": w, "friday": fri[-1], "monday": fri[0], "signal": nxt[0]})
        self.weeks = pd.DataFrame(rows).set_index("week")
        vol = self.volume[self.tickers]
        self.vol_ratio = pd.DataFrame({w: vol.loc[r.monday:r.friday].mean() /
                                       vol[vol.index < r.monday].tail(VOLUME_BASE_DAYS).mean()
                                       for w, r in self.weeks.iterrows()}).T
        prev = self.weeks["friday"].shift(1)
        wk_ret = pd.DataFrame({w: self.close.loc[r.friday] / self.close.loc[prev[w]] - 1
                               for w, r in self.weeks.iterrows() if pd.notna(prev[w])}).T
        self.abn_ret = wk_ret[self.tickers].sub(wk_ret[self.bench], axis=0)
        self.gate = market_gate(self.weekly["abn_views"], self.weekly["burst"]).reindex(self.weeks.index).fillna(False)

    def regime_up(self, friday: pd.Timestamp) -> bool:
        return bool(self.close.at[friday, self.bench] > self.spy_ma200.at[friday])

    def wk(self, name: str, week: pd.Timestamp) -> pd.Series:
        t = self.weekly[name]
        return t.loc[week].reindex(self.tickers) if week in t.index else pd.Series(np.nan, index=self.tickers)


# ----------------------------------------------------------------------------- strategies
@dataclass
class Position:
    entry_idx: int
    entry_price: float
    peak: float
    weeks_held: int = 0
    weak_weeks: int = 0


class Strategy:
    """One rule set; `off` names indicators removed for the drop-one ablation, `loosen` the loosening step."""
    name = ""
    indicators: tuple[str, ...] = ()
    stop: float = 0.0
    trailing: bool = True

    def __init__(self, off: frozenset[str] = frozenset(), loosen: int = 0):
        self.off, self.loosen = off, loosen

    def exposure(self, m: Market, week, fri) -> float:
        x = 1.0
        if "regime" not in self.off and not m.regime_up(fri):
            x *= HALF
        return x

    def rebalance(self, m: Market, week, fri, held: dict[str, Position], first_of_month: bool) -> set[str]:
        raise NotImplementedError

    def signal(self, m: Market, week, fri) -> pd.Series:
        """The score whose rank IC the evaluation reports."""
        raise NotImplementedError


class AttentionGatedMomentum(Strategy):
    name = "S1 Attention-gated momentum"
    indicators = ("regime", "att_z_gate", "burst_breadth_gate", "momentum", "trend")
    stop = 0.10

    def exposure(self, m, week, fri):
        x = super().exposure(m, week, fri)
        if "att_z_gate" in self.off and "burst_breadth_gate" in self.off:
            return x
        if "att_z_gate" in self.off or "burst_breadth_gate" in self.off:   # recompute with the remaining part
            level, burst = m.weekly["abn_views"], m.weekly["burst"]
            if "att_z_gate" in self.off:
                level = level * 0.0                                            # z never fires
            else:
                burst = burst & False                                          # breadth never fires
            on = market_gate(level, burst).get(week, False)
        else:
            on = bool(m.gate.get(week, False))
        return x * (HALF if on else 1.0)

    def rebalance(self, m, week, fri, held, first_of_month):
        if not first_of_month:
            return set(held)
        ok = m.mom.loc[fri].notna() if "momentum" not in self.off else m.close.loc[fri, m.tickers].notna()
        if "trend" not in self.off:
            ok &= m.close.loc[fri, m.tickers] > m.ma50.loc[fri]
        names = ok[ok].index
        if "momentum" in self.off:
            return set(names)
        return set(m.mom.loc[fri, names].nlargest(10).index)

    def signal(self, m, week, fri):
        return m.mom.loc[fri]


class AttentionReversal(Strategy):
    name = "S2 Attention reversal"
    indicators = ("regime", "attention", "reversal", "revert_filter", "volume")
    stop, trailing = 0.06, False
    VOLUME_MIN = (1.3, 1.0, 0.0)

    def candidates(self, m, week):
        av = m.wk("abn_views", week)
        ok = av.notna()
        if "attention" not in self.off:
            ok &= av.rank(pct=True) >= 0.7
        if "revert_filter" not in self.off:
            ok &= m.wk("revert_share", week).fillna(0) <= 0.5
        if "volume" not in self.off and self.VOLUME_MIN[self.loosen] > 0 and week in m.vol_ratio.index:
            ok &= m.vol_ratio.loc[week].reindex(m.tickers) >= self.VOLUME_MIN[self.loosen]
        return ok[ok].index

    def rebalance(self, m, week, fri, held, first_of_month):
        names = self.candidates(m, week)
        if week not in m.abn_ret.index or not len(names):
            return set()
        if "reversal" in self.off:
            return set(m.wk("abn_views", week)[names].nlargest(5).index)
        return set(m.abn_ret.loc[week, names].dropna().nsmallest(5).index)

    def signal(self, m, week, fri):
        av = m.wk("abn_views", week)
        top = av.rank(pct=True) >= 0.7
        return (-m.abn_ret.loc[week]).where(top) if week in m.abn_ret.index else av * np.nan


class NewsTaggedBreakout(Strategy):
    name = "S3 News-tagged breakout"
    indicators = ("regime", "spike", "burst", "news_tags", "breakout", "volume")
    stop = 0.08
    MAX_WEEKS, WEAK_WEEKS = 6, 2

    def rebalance(self, m, week, fri, held, first_of_month):
        keep = set()
        ratio = m.wk("views_ratio", week)
        for t, p in held.items():
            p.weeks_held += 1
            p.weak_weeks = p.weak_weeks + 1 if ratio.get(t, np.nan) <= 1 else 0
            if p.weeks_held < self.MAX_WEEKS and p.weak_weeks < self.WEAK_WEEKS:
                keep.add(t)
        ok = pd.Series(True, index=m.tickers)
        if "spike" not in self.off:
            ok &= m.wk("spike", week).fillna(False).astype(bool) | ((ratio >= 1.5) if self.loosen >= 3 else False)
        if "burst" not in self.off:
            ok &= m.wk("burst", week).fillna(False).astype(bool)
        if "news_tags" not in self.off:
            ok &= m.wk("news", week).fillna(False).astype(bool) & ~m.wk("bad_news", week).fillna(False).astype(bool)
        if "breakout" not in self.off:
            close = m.close.loc[fri, m.tickers]
            brk = close >= m.hi20.loc[fri]
            ok &= brk | (close > m.ma50.loc[fri]) if self.loosen >= 2 else brk
        if "volume" not in self.off and self.loosen < 1 and week in m.vol_ratio.index:
            ok &= m.vol_ratio.loc[week].reindex(m.tickers) >= 1.5
        return keep | set(ok[ok].index)

    def signal(self, m, week, fri):
        return m.wk("abn_views", week)


STRATEGIES = (AttentionGatedMomentum, AttentionReversal, NewsTaggedBreakout)


# ----------------------------------------------------------------------------- simulation
def simulate(strategy: Strategy, m: Market, cost: float) -> dict:
    """Daily loop: pending stop exits, then signal-day rebalance, then stop checks at the close.

    Returns end-of-day weights (days x tickers), net daily returns and the trade list.
    """
    days, close = m.days, m.close[m.tickers].to_numpy()
    sig = {r.signal: (w, r.friday) for w, r in m.weeks.iterrows()}
    idx = {t: j for j, t in enumerate(m.tickers)}
    W = np.zeros((len(days), len(m.tickers)))
    held: dict[str, Position] = {}
    pending: set[str] = set()
    trades, weights, last_month = [], {}, None
    for i, d in enumerate(days):
        for t in sorted(pending):                                  # stop seen at yesterday's close
            trades.append((t, held[t].entry_idx, i))
            del held[t]
            weights.pop(t, None)
        pending = set()
        if d in sig:
            week, fri = sig[d]
            first = d.month != last_month
            last_month = d.month
            target = strategy.rebalance(m, week, fri, held, first)
            for t in [t for t in held if t not in target]:
                trades.append((t, held[t].entry_idx, i))
                del held[t]
            for t in sorted(target - set(held)):   # sorted: set order changes between runs
                px = close[i, idx[t]]
                if np.isfinite(px):
                    held[t] = Position(i, px, px)
            inv = (1 / m.vol63.loc[fri, list(held)]).replace([np.inf], np.nan).dropna() if held else pd.Series(dtype=float)
            w = (inv / inv.sum()).clip(upper=MAX_WEIGHT) if len(inv) else inv
            weights = (w * strategy.exposure(m, week, fri)).to_dict()
        for t, wt in weights.items():
            if t in held:
                W[i, idx[t]] = wt
        for t, p in held.items():                             # stops, from the day after entry
            px = close[i, idx[t]]
            if p.entry_idx == i or not np.isfinite(px):
                continue
            p.peak = max(p.peak, px)
            ref = p.peak if strategy.trailing else p.entry_price
            if strategy.stop and px <= ref * (1 - strategy.stop):
                pending.add(t)
    trades += [(t, p.entry_idx, len(days)) for t, p in held.items()]
    Wdf = pd.DataFrame(W, index=days, columns=m.tickers)
    gross = (Wdf.shift(1) * m.ret[m.tickers].fillna(0)).sum(axis=1)
    net = gross - Wdf.diff().abs().sum(axis=1).fillna(Wdf.abs().sum(axis=1)) * cost
    tr = pd.DataFrame(trades, columns=["ticker", "entry_idx", "exit_idx"])
    tr["entry_date"] = days[tr["entry_idx"]]
    tr["days"] = tr["exit_idx"] - tr["entry_idx"]
    tr["weight"] = [W[a:b, idx[t]].mean() if b > a else 0.0 for t, a, b in tr[["ticker", "entry_idx", "exit_idx"]].itertuples(index=False)]
    return {"weights": Wdf, "net": net, "trades": tr}


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)) if len(r) > 1 and r.std() > 0 else np.nan


def cut(s: pd.Series, period: tuple) -> pd.Series:
    return s[(s.index >= pd.Timestamp(period[0])) & (s.index <= pd.Timestamp(period[1]))]


def random_entry_sharpes(trades: pd.DataFrame, m: Market, period: tuple, cost: float, n: int, seed: int) -> list[float]:
    """Sharpe of `n` portfolios that keep each trade's stock, weight and length but draw a random entry date."""
    days = m.days
    inside = np.flatnonzero((days >= pd.Timestamp(period[0])) & (days <= pd.Timestamp(period[1])))
    tr = trades[trades["entry_date"].between(pd.Timestamp(period[0]), pd.Timestamp(period[1]))]
    tr = tr.sort_values(["entry_idx", "ticker"])          # fixed draw order, so a seed gives one answer
    if tr.empty:
        return []
    R = m.ret[m.tickers].fillna(0).to_numpy()
    col = {t: j for j, t in enumerate(m.tickers)}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        W = np.zeros_like(R)
        for t, length, w in tr[["ticker", "days"]].assign(w=tr["weight"]).itertuples(index=False):
            start = rng.choice(inside[: max(1, len(inside) - length)])
            W[start:start + max(int(length), 1), col[t]] += w
        Wdf = pd.DataFrame(W, index=days)
        net = (Wdf.shift(1) * R).sum(axis=1) - Wdf.diff().abs().sum(axis=1).fillna(0) * cost
        out.append(sharpe(cut(net, period)))
    return [x for x in out if np.isfinite(x)]


def mean_ic(strategy: Strategy, m: Market, period: tuple) -> float:
    """Mean cross-sectional Spearman IC of the strategy's signal with the next period's return."""
    w = m.weeks
    w = w[(w["signal"] >= pd.Timestamp(period[0])) & (w["signal"] <= pd.Timestamp(period[1]))]
    if isinstance(strategy, AttentionGatedMomentum):            # monthly signal, monthly forward return
        w = w[w["signal"].dt.month != w["signal"].shift(1).dt.month]
    ics = []
    sig_days = list(w["signal"])
    for (week, r), nxt in zip(w.iterrows(), sig_days[1:] + [None]):
        if nxt is None:
            break
        s = strategy.signal(m, week, r.friday)
        fwd = m.close.loc[nxt, m.tickers] / m.close.loc[r.signal, m.tickers] - 1
        ok = s.notna() & fwd.notna()
        if ok.sum() >= 5:
            ics.append(spearmanr(s[ok], fwd[ok]).statistic)
    return float(np.nanmean(ics)) if ics else np.nan


def deflated_sharpe(r: pd.Series, trial_sharpes: list[float], n_trials: int) -> float:
    """Probability the (daily) Sharpe beats the best of `n_trials` luck-only trials (Bailey & Lopez de Prado)."""
    r = r.dropna()
    sr = r.mean() / r.std()
    var = np.nanvar(np.asarray(trial_sharpes) / np.sqrt(TRADING_DAYS))   # trial Sharpes are annualised
    sr0 = np.sqrt(var) * ((1 - EULER_GAMMA) * norm.ppf(1 - 1 / n_trials)
                          + EULER_GAMMA * norm.ppf(1 - 1 / (n_trials * EULER_E)))
    denom = np.sqrt(1 - skew(r) * sr + (kurtosis(r, fisher=False) - 1) / 4 * sr ** 2)
    return float(norm.cdf((sr - sr0) * np.sqrt(len(r) - 1) / denom))


# ----------------------------------------------------------------------------- evaluation
def evaluate(cls, m: Market, split: dict, cost: float, n_random: int, seed: int, loosen: int = 0) -> dict:
    """Full evaluation of one strategy: per-period metrics, random baseline, IC and drop-one."""
    s = cls(loosen=loosen)
    sim = simulate(s, m, cost)
    res = {"name": s.name, "loosen": loosen, "sim": sim, "periods": {}, "drop_one": {}}
    for p, period in split.items():
        net = cut(sim["net"], period)
        rand = random_entry_sharpes(sim["trades"], m, period, cost, n_random, seed)
        sr = sharpe(net)
        res["periods"][p] = {
            "n_trades": int(sim["trades"]["entry_date"].between(*map(pd.Timestamp, period)).sum()),
            "sharpe": sr, "index_sharpe": sharpe(cut(m.ret[m.bench], period)),
            "cagr": float((1 + net).prod() ** (TRADING_DAYS / max(len(net), 1)) - 1),
            "max_drawdown": float(((1 + net).cumprod() / (1 + net).cumprod().cummax() - 1).min()),
            "pct_random_beaten": 100 * float(np.mean([sr > x for x in rand])) if rand else np.nan,
            "random_median_sharpe": float(np.median(rand)) if rand else np.nan,
            "ic": mean_ic(s, m, period)}
    for ind in s.indicators:
        d = simulate(cls(off=frozenset({ind}), loosen=loosen), m, cost)
        res["drop_one"][ind] = {p: sharpe(cut(d["net"], period)) for p, period in split.items()}
    return res


def decide(res: dict) -> tuple[str, str]:
    """The guide's KEEP rule: beat the index Sharpe in test and >= 90% of random runs in train and test."""
    tr, te = res["periods"]["train"], res["periods"]["test"]
    fails = []
    if tr["n_trades"] < 30:
        fails.append(f"only {tr['n_trades']} train entries (< 30)")
    if not te["sharpe"] > te["index_sharpe"]:
        fails.append(f"test Sharpe {te['sharpe']:.2f} <= index {te['index_sharpe']:.2f}")
    for p in ("train", "test"):
        if not res["periods"][p]["pct_random_beaten"] >= 90:
            fails.append(f"beat {res['periods'][p]['pct_random_beaten']:.0f}% of random runs in {p}")
    return ("KEEP", "passed every pass mark") if not fails else ("DROP", "; ".join(fails))


def build_market(market: str = "US") -> Market:
    from src.wiki_pipeline import PROCESSED, RAW, shared_path, universe
    holdout = pd.Timestamp(config.holdout_start())
    tickers, bench = list(universe(market)), config.benchmark(market)
    px = load_ohlcv(tickers, bench, "2014-01-01", holdout, RAW / "prices" / f"ohlcv_{market}.parquet")
    wk = weekly_features(pd.read_csv(shared_path("research")), pd.read_csv(PROCESSED / "weekly_edits_research.csv"),
                         config.load()["wikipedia"]["edit_burst_ratio"])
    return Market(px["close"], px["volume"], bench, [t for t in tickers if t in px["close"]], wk)


def run(market: str = "US") -> list[dict]:
    """Evaluate S1-S3 (loosening on train only when needed) and write results/wikipedia/week3_*.csv."""
    from src.wiki_pipeline import ROOT
    m = build_market(market)
    split = config.load()["wikipedia"]["split"]
    s = config.load()["strategy"]
    cost = s["cost_bps"] / 1e4
    results = []
    for cls in STRATEGIES:
        loosen = 0
        while True:   # the guide: too few train entries -> loosen on train data only, logged as a new trial
            res = evaluate(cls, m, split, cost, s["n_random_portfolios"], s["random_seed"], loosen)
            results.append(res)
            max_loosen = {AttentionReversal: 2, NewsTaggedBreakout: 3}.get(cls, 0)
            if res["periods"]["train"]["n_trades"] >= 30 or loosen >= max_loosen:
                break
            loosen += 1
    n_trials = TRIALS_BEFORE + len(results)
    trial_sr = [r["periods"]["test"]["sharpe"] for r in results] + \
               [v["test"] for r in results for v in r["drop_one"].values()]
    rows, ablation = [], []
    for r in results:
        r["decision"], r["why"] = decide(r)
        r["deflated_sharpe"] = deflated_sharpe(cut(r["sim"]["net"], split["test"]), trial_sr, n_trials)
        tr, te = r["periods"]["train"], r["periods"]["test"]
        rows.append({"strategy": r["name"], "loosen_step": r["loosen"], "market": market.lower(), "who": "James",
                     "train_period": "..".join(map(str, split["train"])), "test_period": "..".join(map(str, split["test"])),
                     "sharpe_train_test": f"{tr['sharpe']:.2f} / {te['sharpe']:.2f}",
                     **{f"{k}_{p}": v for p, d in r["periods"].items() for k, v in d.items()},
                     "deflated_sharpe_prob": r["deflated_sharpe"], "n_trials": n_trials,
                     "decision": r["decision"], "why": r["why"]})
        for ind, v in r["drop_one"].items():
            ablation.append({"strategy": r["name"], "loosen_step": r["loosen"], "dropped": ind,
                             "sharpe_train": v["train"], "sharpe_test": v["test"],
                             "change_train": v["train"] - tr["sharpe"], "change_test": v["test"] - te["sharpe"]})
    out = ROOT / "results" / "wikipedia"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / f"week3_strategy_log_{market.lower()}.csv", index=False)
    pd.DataFrame(ablation).to_csv(out / f"week3_drop_one_{market.lower()}.csv", index=False)
    for r in results:
        tag = r["name"].split()[0].lower() + (f"_loosen{r['loosen']}" if r["loosen"] else "")
        r["sim"]["trades"].to_csv(out / f"week3_{tag}_trades_{market.lower()}.csv", index=False)
        r["sim"]["weights"].to_csv(out / f"week3_{tag}_weights_{market.lower()}.csv")
        r["sim"]["net"].rename("net").to_csv(out / f"week3_{tag}_daily_{market.lower()}.csv")
    return results


VIBE_ENGINE = '''"""{name} ({market}), exported from indicatorlab src/wiki_complex.py.

Target weights were computed by the pre-registered rules in docs/wikipedia/week3_strategies.md and are
read from code/weights.csv (run the runner from this directory). Vibe shifts them one bar.
"""
import pandas as pd


class SignalEngine:
    def generate(self, data_map):
        w = pd.read_csv("code/weights.csv", index_col=0, parse_dates=True)
        return {{c: w[c].reindex(df.index).ffill().fillna(0.0) for c, df in data_map.items() if c in w}}
'''


def export_vibe(res: dict, market: str, split: dict, runs_root: Path, cost: float) -> Path:
    """Write a Vibe-Trading run dir (config.json, code/signal_engine.py, code/weights.csv) for one strategy.

    Vibe trades each signal at the next bar's open and, with position_adjustment "hold", applies entries and
    exits but not resizes, so its numbers are a cross-check of ours, not a replay.
    """
    w = res["sim"]["weights"]
    w = w.loc[:, (w != 0).any()]
    if market == "US":   # Vibe reads bare BRK-B as a China B share; TICKER.US is its US form
        w = w.rename(columns=lambda t: f"{t}.US")
    tag = res["name"].split()[0].lower() + (f"_loosen{res['loosen']}" if res["loosen"] else "")
    run_dir = runs_root / f"indicatorlab_wiki_{tag}_{market.lower()}"
    (run_dir / "code").mkdir(parents=True, exist_ok=True)
    w.round(6).to_csv(run_dir / "code" / "weights.csv")
    (run_dir / "code" / "signal_engine.py").write_text(VIBE_ENGINE.format(name=res["name"], market=market))
    cfg = {"codes": list(w.columns), "start_date": str(split["train"][0]), "end_date": str(split["test"][1]),
           "source": "yfinance", "interval": "1D", "engine": "daily", "position_adjustment": "hold",
           "slippage_us": cost}
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    return run_dir


if __name__ == "__main__":
    import sys
    results = run()
    if "--vibe" in sys.argv:   # export the last (final) version of each strategy to ~/.vibe-trading/runs
        final = {r["name"]: r for r in results}
        cfg = config.load()
        for r in final.values():
            print("Vibe run dir:", export_vibe(r, "US", cfg["wikipedia"]["split"], Path.home() / ".vibe-trading" / "runs",
                                               cfg["strategy"]["cost_bps"] / 1e4))
    for r in results:
        print(f"\n{r['name']} (loosen {r['loosen']}): {r['decision']} - {r['why']}  DSR {r['deflated_sharpe']:.2f}")
        print(pd.DataFrame(r["periods"]).T.round(3).to_string())
        print("drop-one:", {k: {p: round(x, 2) for p, x in v.items()} for k, v in r["drop_one"].items()})
