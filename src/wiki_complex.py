"""Complex strategies on Wikipedia attention, FinBERT edit sentiment and price/volume (James).

Rules: docs/wikipedia/week3_strategies.md (S1-S4) and docs/wikipedia/week4_strategies.md (S5-S7).

  S1  attention-gated momentum   regime + market attention gate + 12-1 momentum among 50-day uptrends
  S2  attention reversal         buy last week's losers among the most-viewed stocks (revert and volume filters)
  S3  news-tagged breakout       views spike + edit burst with earnings/product tags + 20-day high on volume
  S4  sentiment-confirmed attention  views above baseline + edit sentiment rising + 50-day uptrend
  S5  bad-news overreaction reversal  attention + negative edit tone + down week, in 200-day uptrends
  S6  positive-tone momentum, uncrowded  12-1 momentum with positive tone, no crowd, no legal/layoff news
  S7  trend with risk filters    200-day trend + 26-week return; stock and market attention/sentiment filters

Every strategy goes through the guide's full evaluation: IC, train / test Sharpe after costs vs the index,
200 random-entry-timing runs, drop-one ablation, and the deflated Sharpe.

    python -m src.wiki_complex            # US; writes results/wikipedia/week4_*.csv
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy.stats import kurtosis, skew, spearmanr

from src import config

TRADING_DAYS = 252
MOM_SKIP, MOM_LOOKBACK = 21, 252          # 12-1 momentum: close 1 month ago / close 12 months ago
TREND_DAYS, REGIME_DAYS, VOL_DAYS = 50, 200, 63
BREAKOUT_DAYS, VOLUME_BASE_DAYS = 20, 50
MAX_WEIGHT, HALF = 0.10, 0.5
GATE_Z, GATE_WEEKS, BREADTH_PCT, MIN_HISTORY_WEEKS = 1.5, 52, 0.90, 52
SENT_WEEKS, SENT_MIN_SCORED_WEEKS = 26, 8   # S4: sentiment change vs the mean of scored weeks in the prior 26
RET26_DAYS = 126                           # S7: 26-week return, in trading days
SHOCK_WEEKS, SHOCK_SD, SHOCK_MIN_STOCKS = 26, 1.0, 10   # S7: market sentiment shock (week4_strategies.md)
TRIALS_BEFORE = 21                         # James's earlier trials: 20 Vibe factor strategies + Wiki Attention Breakout
OUT_PREFIX = "week4"                       # results/wikipedia/week4_*; Week 3 runs are in pre_cutoff_20251001/


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


def sentiment_net(weekly: pd.DataFrame, weeks: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sentiment_net, n_scored) as week x ticker tables from weekly edit sentiment (src/wiki_sentiment.py).

    sentiment_net is NaN in weeks with no scored sentence (never treated as neutral); n_scored is 0 there.
    """
    w = weekly.assign(week=pd.to_datetime(weekly["week"]))
    w = w[w["n_scored"] > 0]
    net = w.pivot(index="week", columns="ticker", values="sentiment_net").reindex(weeks)
    n = w.pivot(index="week", columns="ticker", values="n_scored").reindex(weeks).fillna(0)
    return net, n


def sentiment_change(weekly: pd.DataFrame, weeks: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(change, n_scored): this week's sentiment_net minus the mean over scored weeks among the previous
    SENT_WEEKS (at least SENT_MIN_SCORED_WEEKS of them); NaN in weeks with no scored sentence.
    """
    net, n = sentiment_net(weekly, weeks)
    prior = net.shift(1).rolling(SENT_WEEKS, min_periods=SENT_MIN_SCORED_WEEKS).mean()
    return net - prior, n


def weekly_features(att: pd.DataFrame, edits: pd.DataFrame, burst_ratio: float,
                    sentiment: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """week x ticker tables from the shared attention table, the weekly edit table and edit sentiment."""
    a = att.assign(week=pd.to_datetime(att["week"]))
    v = a[a["source"] == "wikipedia_views"].pivot(index="week", columns="ticker", values=["abnormal", "ratio", "spike"])
    ed = a[a["source"] == "wikipedia_edits"].pivot(index="week", columns="ticker", values="ratio")
    w = edits.assign(week=pd.to_datetime(edits["week"]))
    piv = {c: w.pivot(index="week", columns="ticker", values=c) for c in
           ["edits", "reverts", "tag_earnings", "tag_product_launch", "tag_legal", "tag_layoff"]}
    revert_share = (piv["reverts"] / piv["edits"].where(piv["edits"] > 0)).fillna(0.0)
    out = {"abn_views": v["abnormal"].astype(float), "views_ratio": v["ratio"].astype(float),
            "spike": v["spike"].astype("boolean").fillna(False).astype(bool),
            "burst": (ed >= burst_ratio), "revert_share": revert_share,
            "news": (piv["tag_earnings"] + piv["tag_product_launch"]) > 0,
            "bad_news": (piv["tag_legal"] + piv["tag_layoff"]) > 0}
    if sentiment is not None:
        out["sent_net"], out["n_scored"] = sentiment_net(sentiment, out["abn_views"].index)
        out["sent_change"], _ = sentiment_change(sentiment, out["abn_views"].index)
    return out


def market_attention_z(abn_views: pd.DataFrame) -> pd.Series:
    """Universe-mean abnormal views of each week as a z-score against the previous GATE_WEEKS weeks."""
    level = abn_views.mean(axis=1)
    past = level.shift(1).rolling(GATE_WEEKS, min_periods=GATE_WEEKS)
    return (level - past.mean()) / past.std()


def market_sentiment_shock(net: pd.DataFrame, n_scored: pd.DataFrame) -> pd.Series:
    """True in weeks whose cross-stock mean sentiment_net is more than SHOCK_SD standard deviations below its
    mean over the previous SHOCK_WEEKS weeks (S7 layer 4). Weeks with fewer than SHOCK_MIN_STOCKS scored
    stocks have no value and never fire.
    """
    level = net.mean(axis=1).where((n_scored > 0).sum(axis=1) >= SHOCK_MIN_STOCKS)
    past = level.shift(1).rolling(SHOCK_WEEKS, min_periods=SHOCK_WEEKS)
    return (level < past.mean() - SHOCK_SD * past.std()).fillna(False)


def market_gate(abn_views: pd.DataFrame, burst: pd.DataFrame) -> pd.Series:
    """True in weeks whose market attention z-score > 1.5 or edit-burst breadth is in its top 10% (S1 layer 2)."""
    z = market_attention_z(abn_views)
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
        self.ma200 = c.rolling(REGIME_DAYS).mean()
        self.ret26 = c / c.shift(RET26_DAYS) - 1
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
        self.att_z = market_attention_z(self.weekly["abn_views"]).reindex(self.weeks.index)
        shock = (market_sentiment_shock(self.weekly["sent_net"], self.weekly["n_scored"])
                 if "sent_net" in self.weekly else pd.Series(False, index=self.weeks.index))
        self.sent_shock = shock.reindex(self.weeks.index).fillna(False).astype(bool)

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


class SentimentConfirmedAttention(Strategy):
    name = "S4 Sentiment-confirmed attention"
    indicators = ("regime", "views", "sentiment", "trend")
    stop = 0.08
    MAX_WEEKS, WEAK_WEEKS = 6, 2
    VIEWS_MIN, MIN_SCORED = (1.2, 1.2, 1.0), (3, 1, 1)     # by loosening step

    def rebalance(self, m, week, fri, held, first_of_month):
        chg, n = m.wk("sent_change", week), m.wk("n_scored", week).fillna(0)
        keep = set()
        for t, p in held.items():
            p.weeks_held += 1
            if "sentiment" not in self.off and pd.notna(chg.get(t)):   # unscored weeks count neither way
                p.weak_weeks = p.weak_weeks + 1 if chg[t] < 0 else 0
            if p.weeks_held < self.MAX_WEEKS and p.weak_weeks < self.WEAK_WEEKS:
                keep.add(t)
        ok = pd.Series(m.tickers, index=m.tickers).isin(m.weekly["n_scored"].columns)   # stocks with sentiment
        if "views" not in self.off:
            ok &= m.wk("views_ratio", week) >= self.VIEWS_MIN[self.loosen]
        if "sentiment" not in self.off:
            ok &= (chg > 0) & (n >= self.MIN_SCORED[self.loosen])
        if "trend" not in self.off:
            ok &= m.close.loc[fri, m.tickers] > m.ma50.loc[fri]
        return keep | set(ok[ok].index)

    def signal(self, m, week, fri):
        return m.wk("sent_change", week)


def recent_rows(t: pd.DataFrame, week: pd.Timestamp, n: int) -> pd.DataFrame:
    """The last `n` weekly rows of `t` up to and including `week` (never later weeks)."""
    return t.loc[:week].tail(n)


class BadNewsReversal(Strategy):
    name = "S5 Bad-news overreaction reversal"
    indicators = ("regime", "attention", "sentiment", "reversal", "long_trend")
    stop, trailing = 0.07, False
    MAX_WEEKS, MAX_NEW = 2, 5
    ATT_PCT, MIN_SCORED = (0.7, 0.7, 0.5), (2, 1, 1)     # by loosening step

    def candidates(self, m, week, fri):
        ok = pd.Series(True, index=m.tickers)
        if "attention" not in self.off:
            ok &= m.wk("abn_views", week).rank(pct=True) >= self.ATT_PCT[self.loosen]
        if "sentiment" not in self.off:
            ok &= (m.wk("sent_net", week) < 0) & (m.wk("n_scored", week).fillna(0) >= self.MIN_SCORED[self.loosen])
        if "long_trend" not in self.off:
            ok &= m.close.loc[fri, m.tickers] > m.ma200.loc[fri]
        if "reversal" not in self.off:
            ok &= m.abn_ret.loc[week].reindex(m.tickers) < 0 if week in m.abn_ret.index else False
        return ok[ok].index

    def rebalance(self, m, week, fri, held, first_of_month):
        keep = set()
        for t, p in held.items():
            p.weeks_held += 1
            if p.weeks_held < self.MAX_WEEKS:
                keep.add(t)
        names = self.candidates(m, week, fri)
        if not len(names):
            return keep
        if "reversal" in self.off:
            new = m.wk("abn_views", week)[names].nlargest(self.MAX_NEW).index
        else:
            new = m.abn_ret.loc[week, names].dropna().nsmallest(self.MAX_NEW).index
        return keep | set(new)

    def signal(self, m, week, fri):
        if week not in m.abn_ret.index:
            return pd.Series(np.nan, index=m.tickers)
        ok = (m.wk("abn_views", week).rank(pct=True) >= self.ATT_PCT[0]) & (m.wk("sent_net", week) < 0) & \
             (m.wk("n_scored", week).fillna(0) >= self.MIN_SCORED[0])
        return (-m.abn_ret.loc[week].reindex(m.tickers)).where(ok)


class PositiveToneMomentum(Strategy):
    name = "S6 Positive-tone momentum, uncrowded"
    indicators = ("regime", "momentum", "sentiment_level", "uncrowded", "no_bad_news")
    stop = 0.10
    TOP, LEVEL_WEEKS, BAD_NEWS_WEEKS, CROWD_RATIO = 10, 13, 4, 1.5
    MIN_SCORED_WEEKS = (3, 2)                            # by loosening step

    def level(self, m, week, min_weeks):
        """Mean sentiment_net over the scored weeks among weeks W-12..W; NaN with fewer than `min_weeks`."""
        net = recent_rows(m.weekly["sent_net"], week, self.LEVEL_WEEKS).reindex(columns=m.tickers)
        return net.mean().where(net.notna().sum() >= min_weeks)

    def rebalance(self, m, week, fri, held, first_of_month):
        if not first_of_month:
            return set(held)
        ok = m.close.loc[fri, m.tickers].notna()
        if "momentum" not in self.off:
            ok &= m.mom.loc[fri].notna()
        if "sentiment_level" not in self.off:
            ok &= self.level(m, week, self.MIN_SCORED_WEEKS[self.loosen]) > 0
        if "uncrowded" not in self.off:
            ok &= m.wk("views_ratio", week) < self.CROWD_RATIO
        if "no_bad_news" not in self.off:
            bad = recent_rows(m.weekly["bad_news"], week, self.BAD_NEWS_WEEKS).reindex(columns=m.tickers)
            ok &= ~bad.fillna(False).astype(bool).any()
        names = ok[ok].index
        if "momentum" in self.off:
            return set(names)
        return set(m.mom.loc[fri, names].nlargest(self.TOP).index)

    def signal(self, m, week, fri):
        return self.level(m, week, self.MIN_SCORED_WEEKS[0])


class TrendRiskFiltered(Strategy):
    name = "S7 Trend with attention/sentiment risk filters"
    indicators = ("regime", "trend200", "ret26", "stock_risk", "market_att_z", "market_sent_shock")
    stop = 0.12
    BLOCK_WEEKS = 4

    def exposure(self, m, week, fri):
        x = super().exposure(m, week, fri)
        if "market_att_z" not in self.off and m.att_z.get(week, np.nan) > GATE_Z:
            x *= HALF
        if "market_sent_shock" not in self.off and bool(m.sent_shock.get(week, False)):
            x *= HALF
        return x

    def risk_flag(self, m, week):
        """Stocks whose views spiked with negative tone in any of weeks W-3..W (excluded for 4 weeks)."""
        spike = recent_rows(m.weekly["spike"], week, self.BLOCK_WEEKS).reindex(columns=m.tickers)
        neg = recent_rows(m.weekly["sent_net"], week, self.BLOCK_WEEKS).reindex(columns=m.tickers) < 0
        return (spike.fillna(False).astype(bool) & neg).any()

    def rebalance(self, m, week, fri, held, first_of_month):
        ok = m.close.loc[fri, m.tickers].notna()
        if "trend200" not in self.off:
            ok &= m.close.loc[fri, m.tickers] > m.ma200.loc[fri]
        if "ret26" not in self.off:
            ok &= m.ret26.loc[fri] > 0
        if "stock_risk" not in self.off:
            ok &= ~self.risk_flag(m, week)
        return set(ok[ok].index)

    def signal(self, m, week, fri):
        return m.ret26.loc[fri]


STRATEGIES = (AttentionGatedMomentum, AttentionReversal, NewsTaggedBreakout, SentimentConfirmedAttention,
              BadNewsReversal, PositiveToneMomentum, TrendRiskFiltered)
MAX_LOOSEN = {AttentionReversal: 2, NewsTaggedBreakout: 3, SentimentConfirmedAttention: 2,
              BadNewsReversal: 2, PositiveToneMomentum: 1}


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


VIBE_MULTIPLE_TESTING = "agent/src/quantlib/multipletesting.py"   # in the Vibe-Trading checkout


@lru_cache(maxsize=1)
def vibe_multiple_testing():
    """Vibe-Trading's `quantlib.multipletesting` module, from the checkout at env VIBE_TRADING_ROOT (.env).

    The guide requires Vibe's own `deflated_sharpe_ratio`. The file is loaded by path because both repos
    have a top-level `src` package, so a normal import would pick up ours.
    """
    load_dotenv()
    root = os.environ.get("VIBE_TRADING_ROOT")
    if not root:
        raise RuntimeError("set VIBE_TRADING_ROOT in .env to a Vibe-Trading checkout (see .env.example)")
    spec = importlib.util.spec_from_file_location("vibe_multipletesting", Path(root).expanduser() / VIBE_MULTIPLE_TESTING)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod    # its dataclasses look the module up while it loads
    spec.loader.exec_module(mod)
    return mod


def deflated_sharpe(r: pd.Series, trial_sharpes: list[float], n_trials: int) -> float:
    """Probability the daily Sharpe of `r` beats the best of `n_trials` luck-only trials.

    Vibe's `deflated_sharpe_ratio` (Bailey & Lopez de Prado), fed per-day Sharpes: the trial Sharpes are
    annualised, so their spread is divided by sqrt(TRADING_DAYS).
    """
    r = r.dropna()
    trial_std = float(np.nanstd(np.asarray(trial_sharpes) / np.sqrt(TRADING_DAYS)))
    res = vibe_multiple_testing().deflated_sharpe_ratio(
        observed_sharpe=float(r.mean() / r.std()), n_trials=n_trials, n_observations=len(r),
        trial_sharpe_std=trial_std, skew=float(skew(r)), kurtosis=float(kurtosis(r, fisher=False)))
    return float(res.deflated_sharpe_ratio)


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
    from src.wiki_pipeline import PROCESSED, RAW, cache_tag, shared_path, universe
    holdout = pd.Timestamp(config.holdout_start())
    tickers, bench = list(universe(market)), config.benchmark(market)
    px = load_ohlcv(tickers, bench, "2014-01-01", holdout, RAW / "prices" / f"ohlcv_{market}_{cache_tag()}.parquet")
    # edit sentiment for every stock (`python -m src.wiki_sentiment strategy`), else the tracked stocks only
    sent = next((f for f in (PROCESSED / "edit_sentiment_weekly_research_strategy.csv",
                             PROCESSED / "edit_sentiment_weekly_research.csv") if f.exists()), None)
    wk = weekly_features(pd.read_csv(shared_path("research")), pd.read_csv(PROCESSED / "weekly_edits_research.csv"),
                         config.load()["wikipedia"]["edit_burst_ratio"], pd.read_csv(sent) if sent else None)
    return Market(px["close"], px["volume"], bench, [t for t in tickers if t in px["close"]], wk)


def run(market: str = "US") -> list[dict]:
    """Evaluate S1-S7 (loosening on train only when needed) and write results/wikipedia/{OUT_PREFIX}_*.csv."""
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
            if res["periods"]["train"]["n_trades"] >= 30 or loosen >= MAX_LOOSEN.get(cls, 0):
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
        n_stocks = len(m.weekly["n_scored"].columns) if r["name"].startswith("S4") else len(m.tickers)
        rows.append({"strategy": r["name"], "loosen_step": r["loosen"], "market": market.lower(), "who": "James",
                     "n_stocks": n_stocks,
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
    pd.DataFrame(rows).to_csv(out / f"{OUT_PREFIX}_strategy_log_{market.lower()}.csv", index=False)
    pd.DataFrame(ablation).to_csv(out / f"{OUT_PREFIX}_drop_one_{market.lower()}.csv", index=False)
    for r in results:
        tag = r["name"].split()[0].lower() + (f"_loosen{r['loosen']}" if r["loosen"] else "")
        r["sim"]["trades"].to_csv(out / f"{OUT_PREFIX}_{tag}_trades_{market.lower()}.csv", index=False)
        r["sim"]["weights"].to_csv(out / f"{OUT_PREFIX}_{tag}_weights_{market.lower()}.csv")
        r["sim"]["net"].rename("net").to_csv(out / f"{OUT_PREFIX}_{tag}_daily_{market.lower()}.csv")
    return results


VIBE_ENGINE = '''"""__NAME__ (__MARKET__), exported from indicatorlab src/wiki_complex.py.

Target weights come from the pre-registered rules in docs/wikipedia/week3_strategies.md (S1-S4) or
week4_strategies.md (S5-S7). They are embedded below, one row per day the targets change, and held
until the next row. Vibe shifts the signal one bar itself, so they are not shifted here.
"""
import io
from typing import Dict

import pandas as pd

WEIGHTS_CSV = """__WEIGHTS__"""


class SignalEngine:
    def generate(self, data_map) -> Dict[str, pd.Series]:
        w = pd.read_csv(io.StringIO(WEIGHTS_CSV), index_col=0, parse_dates=True)
        out = {}
        for code, df in data_map.items():
            if code in w:
                s = w[code].reindex(w.index.union(df.index)).ffill()
                out[code] = s.reindex(df.index).fillna(0.0)
        return out
'''


def export_vibe(res: dict, market: str, split: dict, runs_root: Path, cost: float) -> Path:
    """Write a Vibe-Trading run dir (config.json, code/signal_engine.py) for one strategy, in the Week 4 format.

    The target weights are embedded in the engine as a CSV string (only the days they change), and the run
    uses position_adjustment "rebalance" so Vibe resizes to every new target, as our simulator does, with the
    market's benchmark from config. Vibe fills at the next bar's open, so its numbers are a cross-check of
    ours, not a replay.

    Args:
        res: one strategy result from `run()` (needs "name", "loosen" and sim["weights"]).
        market: market code from config.yaml, e.g. "US".
        split: the wikipedia train/test split; the run covers train start to test end.
        runs_root: Vibe's runs folder, normally ~/.vibe-trading/runs.
        cost: one-way cost per unit of turnover (Vibe's slippage).

    Returns:
        The run directory.
    """
    w = res["sim"]["weights"]
    w = w.loc[:, (w != 0).any()].round(6)
    w = w[w.ne(w.shift()).any(axis=1)]   # first row, then only the days a target changes
    if market == "US":   # Vibe reads bare BRK-B as a China B share; TICKER.US is its US form
        w = w.rename(columns=lambda t: f"{t}.US")
    tag = res["name"].split()[0].lower() + (f"_loosen{res['loosen']}" if res["loosen"] else "")
    run_dir = runs_root / f"indicatorlab_wiki_{tag}_{market.lower()}"
    (run_dir / "code").mkdir(parents=True, exist_ok=True)
    engine = (VIBE_ENGINE.replace("__NAME__", res["name"]).replace("__MARKET__", market)
              .replace("__WEIGHTS__", w.to_csv(date_format="%Y-%m-%d")))
    (run_dir / "code" / "signal_engine.py").write_text(engine)
    cfg = {"codes": list(w.columns), "start_date": str(split["train"][0]), "end_date": str(split["test"][1]),
           "source": "yfinance", "interval": "1D", "engine": "daily", "position_adjustment": "rebalance",
           "benchmark": config.benchmark(market), "slippage_us": cost}
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
