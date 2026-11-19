"""Week 4 strategies S1-S3 (rules fixed in docs/reddit/week4_strategies.md) with the full evaluation.

    python -m src.reddit.strategies_week4 prices      # download/cache daily OHLCV (yfinance) once
    python -m src.reddit.strategies_week4 run         # train + test once, random baselines, ablation, log

Timing: week W runs Monday 00:00 to Sunday 23:59 UTC. Every indicator for W uses data through W only
(past-only rolling windows). A target weight set from week W becomes effective on the first trading day
of W+1 and, like the Vibe-Trading engine, earns returns from the next bar on (weight on day d times the
return of d+1), so a weekend headline never trades before it is known.

Evaluation (Week 4 guide): train 2016-06-01..2021-12-31, test 2022-01-01..2026-10-31 (`strategy.split`),
10 bps per unit of turnover, 50 bps/yr borrow on shorts, >= 30 entries in train, 200 random runs with the
same trades' holding times, sides and sizes but random stocks and start weeks, drop-one ablation (each
indicator shuffled across rows, seeded), SPY Sharpe, and the deflated Sharpe from Vibe-Trading's
`agent/src/quantlib/multipletesting.py`, counting every trial in every strategy log. Every run is appended
to results/reddit/strategy_logs/strategy_log_week4.csv; nothing is overwritten or filtered.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.utils import get_logger, utc_now_iso

log = get_logger("strategies_week4", "pipeline.log")

STRAT = config.load()["strategy"]
SPLIT = {k: (pd.Timestamp(v[0]), pd.Timestamp(v[1])) for k, v in STRAT["split"].items()}
COST_BPS = STRAT["cost_bps"]
BORROW_BPS_YR = 50
N_RANDOM = STRAT["n_random_portfolios"]
SEED = STRAT["random_seed"]
TRADING_DAYS = 252
MIN_TRAIN_ENTRIES = 30
KEEP_RANDOM_PCT = 90.0
BASELINE_WEEKS = config.spike_rule()["baseline_weeks"]
SPIKE_LOG = float(np.log(config.spike_rule()["ratio"]))   # log(1.5)
PRICE_START = "2015-01-01"   # room for the 200-day and 52-week windows before the train start
PRICES = settings.RAW_PRICES / "daily_ohlcv_week4.parquet"
WEEKLY_BY_TYPE = settings.PROCESSED / "reddit_weekly_by_type.parquet"
LOG_PATH = settings.STRATEGY_LOGS / "strategy_log_week4.csv"
OTHER_LOGS = [settings.STRATEGY_LOGS / "strategy_log.csv", settings.STRATEGY_LOGS / "strategy_log_week2.csv"]
VIBE_ROOT = settings.ROOT.parent / "vibe-trading-fork"
MULTITEST = VIBE_ROOT / "agent" / "src" / "quantlib" / "multipletesting.py"

# Rule constants (docs/reddit/week4_strategies.md)
S1_TOP_ATT = 0.7            # top 30% of `att`
S1_ABN_VOL = 1.5
S1_SENT_FLOOR = -0.15
S1_NET_CAP = 0.2            # |net exposure| <= 20% of capital
NAME_CAP_S1 = 0.25
RISK_Z = 1.5                # market-wide attention z that halves exposure
S2_TOP, S2_KEEP_RANK, S2_MAX_WEEKS, S2_MIN_SCORED, S2_NAME_CAP = 3, 5, 4, 20, 0.40
S3_MAX_NAMES, S3_WEIGHT, S3_WEEKS, S3_EXIT_JUMP = 4, 0.25, 4, 0.10


# ----------------------------------------------------------------------------- data
def load_prices(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily adjusted close and volume (date x ticker, plus the benchmark), cached as parquet."""
    tickers, bench = config.tickers("US"), config.benchmark("US")
    if refresh or not PRICES.exists():
        import yfinance as yf
        end = (pd.Timestamp(settings.HOLDOUT_START)).strftime("%Y-%m-%d")   # yfinance end is exclusive
        raw = yf.download([*tickers, bench], start=PRICE_START, end=end, auto_adjust=True, progress=False)
        df = pd.concat({"close": raw["Close"], "volume": raw["Volume"]}, axis=1)
        PRICES.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(PRICES)
        PRICES.with_suffix(".meta.json").write_text(json.dumps(
            {"source": "yfinance auto_adjust=True", "retrieved_utc": utc_now_iso(), "start": PRICE_START,
             "end_exclusive": end, "symbols": [*tickers, bench]}, indent=2))
    df = pd.read_parquet(PRICES)
    close, volume = df["close"], df["volume"]
    keep = close.index < pd.Timestamp(settings.HOLDOUT_START)
    return close[keep], volume[keep]


def load_attention() -> pd.DataFrame:
    """Weekly Reddit attention per (week, ticker, subreddit_type) from the published research table."""
    df = pd.read_parquet(WEEKLY_BY_TYPE)
    df["week"] = pd.to_datetime(df["week"]).dt.tz_localize(None)
    return df[df["market"].str.lower() == "us"]


# ----------------------------------------------------------------------------- features
def _weekly_prices(close: pd.DataFrame, volume: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Week-end close (labelled by the week's Monday) and week volume."""
    wk_close = close.resample("W-SUN").last()
    wk_vol = volume.resample("W-SUN").sum(min_count=1)
    for f in (wk_close, wk_vol):
        f.index = f.index - pd.Timedelta(days=6)
    return {"close": wk_close, "volume": wk_vol}


def _past_median(x: pd.DataFrame, n: int) -> pd.DataFrame:
    return x.shift(1).rolling(n, min_periods=n).median()


def build_features(close: pd.DataFrame, volume: pd.DataFrame, att: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Every indicator as a (week Monday x ticker) frame, or a week Series for market-level ones."""
    tickers, bench = config.tickers("US"), config.benchmark("US")
    wp = _weekly_prices(close, volume)
    wc, wv = wp["close"], wp["volume"]
    weeks = wc.index

    def pivot(kind: str, col: str) -> pd.DataFrame:
        sub = att[att["subreddit_type"] == kind]
        return sub.pivot_table(index="week", columns="ticker", values=col, aggfunc="sum").reindex(
            index=weeks, columns=tickers)

    m_inv, m_prod = pivot("investor", "value").fillna(0), pivot("product", "value").fillna(0)
    net_inv = pivot("investor", "sentiment_pos") - pivot("investor", "sentiment_neg")
    net_prod = pivot("product", "sentiment_pos") - pivot("product", "sentiment_neg")
    has_reddit = att.groupby("week").size().reindex(weeks).fillna(0) > 0   # weeks the corpus covers

    f: dict[str, pd.DataFrame | pd.Series] = {}
    f["att"] = np.log((m_inv + 1) / (_past_median(m_inv, BASELINE_WEEKS) + 1)).where(has_reddit, np.nan)
    f["att_prod"] = np.log((m_prod + 1) / (_past_median(m_prod, BASELINE_WEEKS) + 1)).where(has_reddit, np.nan)
    recent = net_inv.rolling(4, min_periods=2).mean()
    base = net_inv.shift(4).rolling(26, min_periods=13).mean()
    f["sent_dev"] = recent - base
    f["prod_net"] = net_prod
    f["n_scored"] = pivot("investor", "n_scored").fillna(0)
    rets = wc[tickers].pct_change(fill_method=None)
    f["ret_1w"] = rets
    f["mom_12_1"] = wc[tickers].shift(1) / wc[tickers].shift(12) - 1
    f["abn_vol"] = wv[tickers] / _past_median(wv[tickers], 20)
    f["vol12"] = rets.rolling(12, min_periods=8).std()
    d20 = close.pct_change(20, fill_method=None).resample("W-SUN").last()
    d20.index = d20.index - pd.Timedelta(days=6)
    f["rel20"] = d20[tickers].sub(d20[bench], axis=0).reindex(weeks)
    mkt = f["att"].mean(axis=1)
    f["mkt_att_z"] = (mkt - mkt.shift(1).rolling(52, min_periods=26).mean()) / mkt.shift(1).rolling(52, min_periods=26).std()
    f["regime_40w"] = (wc[bench] > wc[bench].rolling(40, min_periods=40).mean()).astype(float)
    sma200 = close[bench].rolling(200, min_periods=200).mean().resample("W-SUN").last()
    sma200.index = sma200.index - pd.Timedelta(days=6)
    f["regime_200d"] = (wc[bench] > sma200.reindex(weeks)).astype(float)
    return f


# ----------------------------------------------------------------------------- strategies -> weekly weights
def _pct_rank(x: pd.DataFrame) -> pd.DataFrame:
    return x.rank(axis=1, pct=True)


def s1_weights(f: dict) -> pd.DataFrame:
    """Attention-gated reversal: long attention-heavy losers, short attention-heavy winners, one week."""
    hot = (_pct_rank(f["att"]) >= S1_TOP_ATT) & (f["abn_vol"] > S1_ABN_VOL)
    r = _pct_rank(f["ret_1w"])
    longs = hot & (r <= 1 / 3) & ~(f["sent_dev"] < S1_SENT_FLOOR)
    shorts = hot & (r >= 2 / 3)
    w = pd.DataFrame(0.0, index=f["att"].index, columns=f["att"].columns)
    for wk in w.index:
        L, S = longs.loc[wk][longs.loc[wk]].index, shorts.loc[wk][shorts.loc[wk]].index
        if len(L) and len(S):
            gl, gs = 0.5, 0.5
        else:
            gl, gs = (S1_NET_CAP if len(L) else 0.0), (S1_NET_CAP if len(S) else 0.0)
        if len(L):
            w.loc[wk, L] = min(gl / len(L), NAME_CAP_S1)
        if len(S):
            w.loc[wk, S] = -min(gs / len(S), NAME_CAP_S1)
    scale = np.where(f["regime_40w"] == 1, 1.0, 0.5) * np.where(f["mkt_att_z"] > RISK_Z, 0.5, 1.0)
    return w.mul(scale, axis=0)


def s2_weights(f: dict) -> pd.DataFrame:
    """Sentiment momentum, attention-capped: top 3 by sentiment change + momentum, up to 4 weeks."""
    score = (_pct_rank(f["sent_dev"]) + _pct_rank(f["mom_12_1"])) / 2
    rank = score.rank(axis=1, ascending=False)
    ok = (f["att"] > 0) & (f["n_scored"] >= S2_MIN_SCORED) & score.notna()
    w = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    held: dict[str, int] = {}
    for wk in w.index:
        exited = set()
        for tk in list(held):
            held[tk] += 1
            if held[tk] > S2_MAX_WEEKS or f["sent_dev"].at[wk, tk] < 0 or not rank.at[wk, tk] <= S2_KEEP_RANK:
                del held[tk]
                exited.add(tk)   # sits out at least one week, so a hold never exceeds S2_MAX_WEEKS
        cands = rank.loc[wk][ok.loc[wk]].sort_values()
        for tk in [t for t in cands.index[:S2_TOP] if t not in exited]:
            if len(held) >= S2_TOP:
                break
            held.setdefault(tk, 1)
        if held:
            inv = 1 / f["vol12"].loc[wk, list(held)].replace(0, np.nan)
            inv = inv.fillna(inv.mean() if inv.notna().any() else 1.0)
            w.loc[wk, list(held)] = (inv / inv.sum()).clip(upper=S2_NAME_CAP).to_numpy()
    scale = np.where(f["regime_200d"] == 1, 1.0, 0.5) * np.where(f["mkt_att_z"] > RISK_Z, 0.5, 1.0)
    return w.mul(scale, axis=0)


def s3_weights(f: dict) -> pd.DataFrame:
    """Product-buzz lead: product spike with positive tone, investors not yet, price lagging SPY."""
    sig = (f["att_prod"] >= SPIKE_LOG) & (f["prod_net"] > 0) & (f["att"] < SPIKE_LOG) & (f["rel20"] < 0)
    jump = (f["att"] >= SPIKE_LOG) & (f["ret_1w"] > S3_EXIT_JUMP)
    w = pd.DataFrame(0.0, index=sig.index, columns=sig.columns)
    held: dict[str, int] = {}
    for wk in w.index:
        exited = set()
        for tk in list(held):
            held[tk] += 1
            if held[tk] > S3_WEEKS or jump.at[wk, tk]:
                del held[tk]
                exited.add(tk)
        for tk in [t for t in sig.loc[wk][sig.loc[wk]].index if t not in exited]:
            if len(held) >= S3_MAX_NAMES:
                break
            held.setdefault(tk, 1)
        w.loc[wk, list(held)] = S3_WEIGHT
    return w.mul(np.where(f["regime_200d"] == 1, 1.0, 0.5), axis=0)


@dataclass(frozen=True)
class Strategy:
    sid: str
    name: str
    weights: Callable[[dict], pd.DataFrame]
    indicators: tuple[str, ...]


STRATEGIES = [
    Strategy("S1", "Attention-gated reversal", s1_weights, ("att", "ret_1w", "abn_vol", "sent_dev", "mkt_att_z")),
    Strategy("S2", "Sentiment momentum, attention-capped", s2_weights,
             ("sent_dev", "mom_12_1", "att", "n_scored", "mkt_att_z")),
    Strategy("S3", "Product-buzz lead", s3_weights, ("att_prod", "prod_net", "att", "rel20", "ret_1w")),
]


# ----------------------------------------------------------------------------- simulation
def daily_weights(weekly: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Weekly targets -> daily weights: week W's row applies from the first trading day after W's Sunday."""
    eff = days[np.minimum(days.searchsorted(weekly.index + pd.Timedelta(days=7)), len(days) - 1)]
    keep = weekly.index + pd.Timedelta(days=7) <= days[-1]
    w = weekly[keep].copy()
    w.index = eff[keep]
    w = w[~w.index.duplicated(keep="last")]
    return w.reindex(days, method="ffill").fillna(0.0)


def simulate(weekly: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Daily net returns: weight on day d earns the return of d+1; costs on weight changes, borrow on shorts."""
    tickers = list(weekly.columns)
    w = daily_weights(weekly, close.index)
    nxt = close[tickers].pct_change(fill_method=None).shift(-1).fillna(0.0)
    gross = (w * nxt).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    borrow = w.clip(upper=0).abs().sum(axis=1) * BORROW_BPS_YR / 1e4 / TRADING_DAYS
    net = gross - turnover * COST_BPS / 1e4 - borrow
    return pd.DataFrame({"net": net, "turnover": turnover, "gross_exposure": w.abs().sum(axis=1)})


def trades_of(weekly: pd.DataFrame) -> pd.DataFrame:
    """Runs of consecutive same-sign weights per ticker: (ticker, start week, n weeks, side, mean size)."""
    out = []
    for tk in weekly.columns:
        s = np.sign(weekly[tk].fillna(0.0)).to_numpy()
        i = 0
        while i < len(s):
            if s[i] == 0:
                i += 1
                continue
            j = i
            while j + 1 < len(s) and s[j + 1] == s[i]:
                j += 1
            out.append({"ticker": tk, "start": weekly.index[i], "weeks": j - i + 1, "side": s[i],
                        "size": float(weekly[tk].iloc[i:j + 1].abs().mean())})
            i = j + 1
    return pd.DataFrame(out, columns=["ticker", "start", "weeks", "side", "size"])


def random_weekly(trades: pd.DataFrame, index: pd.DatetimeIndex, tickers: list[str], window: tuple,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Same holding lengths, sides and sizes as `trades`, random stocks and start weeks inside `window`."""
    w = pd.DataFrame(0.0, index=index, columns=tickers)
    pos = np.flatnonzero((index >= window[0]) & (index <= window[1]))
    for t in trades.itertuples(index=False):
        if not len(pos):
            break
        start = rng.integers(pos[0], max(pos[0] + 1, pos[-1] - t.weeks + 2))
        w.iloc[start:start + t.weeks, rng.integers(len(tickers))] += t.side * t.size
    return w


def metrics(r: pd.Series) -> dict:
    """Annualised Sharpe (rf = 0), CAGR, max drawdown, plus per-day moments for the deflated Sharpe."""
    r = r.dropna()
    if len(r) < 2 or r.std() == 0:
        return {"sharpe": np.nan, "cagr": np.nan, "max_drawdown": np.nan, "n_days": len(r), "skew": 0.0,
                "kurtosis": 3.0, "sharpe_daily": np.nan}
    growth = (1 + r).cumprod()
    return {"sharpe": r.mean() / r.std() * np.sqrt(TRADING_DAYS),
            "cagr": growth.iloc[-1] ** (TRADING_DAYS / len(r)) - 1,
            "max_drawdown": float((growth / growth.cummax() - 1).min()), "n_days": len(r),
            "skew": float(r.skew()), "kurtosis": float(r.kurt() + 3), "sharpe_daily": r.mean() / r.std()}


def _window(s: pd.Series | pd.DataFrame, name: str):
    lo, hi = SPLIT[name]
    return s[(s.index >= lo) & (s.index <= hi)]


def evaluate(weekly: pd.DataFrame, close: pd.DataFrame, n_random: int = N_RANDOM, seed: int = SEED) -> dict:
    """Train and test metrics, entries, SPY Sharpe and the random-baseline percentile."""
    bench = config.benchmark("US")
    sim = simulate(weekly, close)
    tr = trades_of(weekly)
    spy = close[bench].pct_change(fill_method=None).shift(-1)
    out = {}
    rng = np.random.default_rng(seed)
    for p in ("train", "test"):
        lo, hi = SPLIT[p]
        m = metrics(_window(sim["net"], p))
        mine = tr[(tr["start"] >= lo) & (tr["start"] <= hi)]
        rand = []
        for _ in range(n_random if len(mine) else 0):
            rw = random_weekly(mine, weekly.index, list(weekly.columns), (lo, hi), rng)
            rand.append(metrics(_window(simulate(rw, close)["net"], p))["sharpe"])
        rand = [x for x in rand if np.isfinite(x)]
        out[p] = {**m, "entries": len(mine), "index_sharpe": metrics(_window(spy, p))["sharpe"],
                  "pct_random_beaten": 100 * float(np.mean([m["sharpe"] > x for x in rand])) if rand else np.nan,
                  "turnover_yr": float(_window(sim["turnover"], p).sum() / max(1, m["n_days"]) * TRADING_DAYS)}
    return out


def decide(res: dict) -> tuple[str, str]:
    """KEEP only if it beats >= 90% of random runs in train and test and SPY's Sharpe in test."""
    tr, te = res["train"], res["test"]
    if tr["entries"] < MIN_TRAIN_ENTRIES:
        return "Insufficient trades", f"{tr['entries']} entries in train (< {MIN_TRAIN_ENTRIES})"
    ok = tr["pct_random_beaten"] >= KEEP_RANDOM_PCT and te["pct_random_beaten"] >= KEEP_RANDOM_PCT
    if ok and te["sharpe"] > te["index_sharpe"]:
        return "Keep", "beat >= 90% of random runs in train and test and SPY's Sharpe in test"
    return "Drop", (f"random runs beaten {tr['pct_random_beaten']:.0f}% train / {te['pct_random_beaten']:.0f}% test; "
                    f"test Sharpe {te['sharpe']:.2f} vs SPY {te['index_sharpe']:.2f}")


def ablate(strategy: Strategy, f: dict, close: pd.DataFrame, seed: int = SEED) -> list[dict]:
    """Drop-one ablation: each indicator shuffled across rows (seeded), train Sharpe only."""
    rows = []
    for ind in strategy.indicators:
        g = dict(f)
        x = f[ind]
        rng = np.random.default_rng(seed)
        if isinstance(x, pd.DataFrame):
            vals = x.to_numpy().ravel().copy()
            rng.shuffle(vals)
            g[ind] = pd.DataFrame(vals.reshape(x.shape), index=x.index, columns=x.columns)
        else:
            g[ind] = pd.Series(rng.permutation(x.to_numpy()), index=x.index)
        sim = simulate(strategy.weights(g), close)
        rows.append({"indicator": ind, "train_sharpe": metrics(_window(sim["net"], "train"))["sharpe"]})
    return rows


# ----------------------------------------------------------------------------- multiple testing + log
def _deflated_sharpe_fn():
    """Vibe-Trading's deflated_sharpe_ratio, loaded from the local clone (module has no Vibe imports)."""
    spec = importlib.util.spec_from_file_location("vibe_multipletesting", MULTITEST)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod     # its dataclasses look themselves up there
    spec.loader.exec_module(mod)
    return mod.deflated_sharpe_ratio


def logged_trial_sharpes() -> list[float]:
    """Annualised train Sharpe of every trial in every strategy log (Week 1, 2 and 4)."""
    vals = []
    for p in [*OTHER_LOGS, LOG_PATH]:
        if p.exists():
            d = pd.read_csv(p)
            col = next((c for c in ("train_sharpe", "sharpe_net", "net_sharpe", "sharpe") if c in d), None)
            if col:
                vals += pd.to_numeric(d[col], errors="coerce").dropna().tolist()
    return vals


def deflated(test: dict, trial_sharpes: list[float]) -> dict:
    """Deflated Sharpe of the test result given every logged trial (per-day units)."""
    if not np.isfinite(test["sharpe_daily"]) or len(trial_sharpes) < 2:
        return {"dsr": np.nan, "n_trials": len(trial_sharpes)}
    res = _deflated_sharpe_fn()(observed_sharpe=float(test["sharpe_daily"]), n_trials=len(trial_sharpes),
                                n_observations=int(test["n_days"]),
                                trial_sharpe_std=float(np.std(trial_sharpes, ddof=1) / np.sqrt(TRADING_DAYS)),
                                skew=test["skew"], kurtosis=test["kurtosis"])
    return {"dsr": res.deflated_sharpe_ratio, "n_trials": res.n_trials, "survives": bool(res.survives)}


def _code_sha() -> str:
    return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:10]


def append_log(rows: list[dict]) -> None:
    """Append-only Week 4 log plus a TSV copy for the shared sheet."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    old = pd.read_csv(LOG_PATH) if LOG_PATH.exists() else pd.DataFrame()
    full = pd.concat([old, df], ignore_index=True)
    full.to_csv(LOG_PATH, index=False)
    full.to_csv(LOG_PATH.with_suffix(".tsv"), sep="\t", index=False)


def run(note: str = "", n_random: int = N_RANDOM, only: list[str] | None = None) -> list[dict]:
    """Every strategy once on train and test; logs one row per strategy and one per ablation variant."""
    close, volume = load_prices()
    att = load_attention()
    first = att["week"].min()
    if pd.isna(first) or first > SPLIT["train"][0] + pd.Timedelta(days=28):
        raise SystemExit(f"Reddit weekly data starts {first}; the train window starts {SPLIT['train'][0].date()}. "
                         "Finish the backfill and rebuild reddit_weekly_by_type.parquet first.")
    f = build_features(close, volume, att)
    run_id = utc_now_iso().replace(":", "")
    rows, tests = [], {}
    for s in [x for x in STRATEGIES if not only or x.sid in only]:
        res = evaluate(s.weights(f), close, n_random)
        tests[s.sid] = res["test"]
        decision, why = decide(res)
        abl = ablate(s, f, close)
        base = res["train"]["sharpe"]
        abl_txt = "; ".join(f"-{a['indicator']}: {a['train_sharpe']:.2f}" for a in abl)
        common = {"run_id": run_id, "run_utc": utc_now_iso(), "who": "Joshua", "code_sha1": _code_sha(),
                  "train_period": f"{SPLIT['train'][0].date()}..{SPLIT['train'][1].date()}",
                  "test_period": f"{SPLIT['test'][0].date()}..{SPLIT['test'][1].date()}", "notes": note}
        rows.append({**common, "strategy": f"{s.sid} {s.name}", "variant": "full",
                     "train_sharpe": base, "test_sharpe": res["test"]["sharpe"],
                     "sharpe_train_test": f"{base:.2f} / {res['test']['sharpe']:.2f}",
                     "spy_sharpe_test": res["test"]["index_sharpe"],
                     "pct_random_beaten_train": res["train"]["pct_random_beaten"],
                     "pct_random_beaten_test": res["test"]["pct_random_beaten"],
                     "test_max_drawdown": res["test"]["max_drawdown"], "entries_train": res["train"]["entries"],
                     "entries_test": res["test"]["entries"], "turnover_yr_train": res["train"]["turnover_yr"],
                     "ablation_train_sharpe": abl_txt, "decision": decision, "why": why})
        for a in abl:
            rows.append({**common, "strategy": f"{s.sid} {s.name}", "variant": f"ablation -{a['indicator']}",
                         "train_sharpe": a["train_sharpe"], "decision": "Ablation trial",
                         "why": f"train Sharpe {a['train_sharpe']:.2f} vs {base:.2f} with every indicator"})
    trials = logged_trial_sharpes() + [r["train_sharpe"] for r in rows if np.isfinite(r["train_sharpe"])]
    for r in rows:
        if r["variant"] == "full":
            r.update({f"deflated_{k}": v for k, v in deflated(tests[r['strategy'].split()[0]], trials).items()})
    append_log(rows)
    log.info("week 4 strategies logged to %s (%d rows)", LOG_PATH, len(rows))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prices", "run"])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--only", nargs="*", choices=[s.sid for s in STRATEGIES])
    a = ap.parse_args()
    if a.cmd == "prices":
        close, _ = load_prices(refresh=a.refresh)
        print(close.index.min().date(), "..", close.index.max().date(), close.shape)
    else:
        for r in run(a.note, only=a.only):
            if r["variant"] == "full":
                print(r["strategy"], r["sharpe_train_test"], r["decision"], "-", r["why"])


if __name__ == "__main__":
    main()
