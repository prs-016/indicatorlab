"""Backtest five Reddit-chatter strategies and append EVERY result to the Strategy Log.

Nothing is filtered: each run appends one row per strategy (plus the benchmark) to
results/strategy_logs/strategy_log.csv, whatever the outcome. Earlier runs are never
overwritten. Per-run weekly returns and weights go to results/strategy_logs/runs/<run_id>/.

Timing (no look-ahead)
----------------------
Reddit week s covers Mon 00:00 UTC .. Sun 23:59 UTC (= Sunday ~19:59 New York time).
The signal for week s is therefore known before Monday's U.S. open of week s+1.
Positions are entered at the first adjusted OPEN of week s+1 and held until the first
adjusted OPEN of week s+2 (open-to-open), so no post written after the entry price is
used. Prices: yfinance daily, auto_adjust=True.

Strategies (universe = the 10 tracked stocks; weights sum of |w| = 1 unless noted)
---------------------------------------------------------------------------------
S1 spike_momentum     long, equal-weight, every ticker with a combined post spike (>=2x); else cash
S2 spike_contrarian   short, equal-weight, every ticker with a combined post spike; else cash
S3 spike_vs_universe  long spiked tickers, short the equal-weight 10-stock basket (market-neutral)
S4 attention_rank_ls  long the 3 highest post spike ratios, short the 3 lowest (needs >=6 defined)
S5 wsb_spike_fade     short, equal-weight, tickers with an r/wallstreetbets-only post spike
B0 equal_weight_hold  benchmark: always long the equal-weight 10-stock basket

Costs: net returns deduct `cost_bps` per unit of turnover (sum of |weight changes|).
Verdict rule (fixed before running): <52 evaluation weeks -> INSUFFICIENT DATA; else
net Sharpe >= 0.5 and |t| >= 2 with positive mean -> PROMISING (needs out-of-sample check);
net Sharpe > 0 -> WEAK; otherwise FAILED. Five strategies are tested at once, so a single
"promising" result is still exposed to multiple-testing luck.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from src.reddit import settings
from src.reddit.utils import get_logger, utc_now_iso
from src.reddit.weekly_metrics import week_start

log = get_logger("backtest_strategies", "pipeline.log")

LOG_PATH = settings.STRATEGY_LOGS / "strategy_log.csv"
RUNS = settings.STRATEGY_LOGS / "runs"
PRICES_PATH = settings.RAW_PRICES / "tickers_daily_yfinance.csv"
TICKERS = list(settings.TICKERS)
MIN_WEEKS = 52

STRATEGIES = {
    "S1": ("spike_momentum", "Chatter spikes precede continued gains.",
           "Long equal-weight all tickers with combined posts_spike_flag in week s; cash otherwise."),
    "S2": ("spike_contrarian", "Chatter spikes mark short-term tops (attention overshoot reverses).",
           "Short equal-weight all tickers with combined posts_spike_flag in week s; cash otherwise."),
    "S3": ("spike_vs_universe", "Spiking stocks outperform their peers regardless of market direction.",
           "Long spiked tickers, short the equal-weight 10-stock basket (dollar neutral)."),
    "S4": ("attention_rank_ls", "Relative attention surges predict relative returns.",
           "Long top-3, short bottom-3 tickers by posts_spike_ratio (requires >= 6 defined ratios)."),
    "S5": ("wsb_spike_fade", "Retail frenzy on r/wallstreetbets reverses.",
           "Short equal-weight tickers with an r/wallstreetbets posts_spike_flag; cash otherwise."),
    "B0": ("equal_weight_hold", "Benchmark (not a Reddit signal).",
           "Always long the equal-weight 10-stock basket, open-to-open weekly."),
}

LOG_FIELDS = ["run_id", "run_timestamp_utc", "source", "strategy_id", "strategy_name", "hypothesis", "rule",
              "universe", "eval_start_week", "eval_end_week", "eval_weeks", "invested_weeks", "position_weeks",
              "cost_bps", "total_return_gross", "total_return_net", "ann_return_net", "ann_vol_net",
              "sharpe_net", "sharpe_gross", "t_stat_net", "max_drawdown_net", "hit_rate_invested",
              "mean_weekly_return_invested", "excess_ann_return_vs_B0", "avg_weekly_turnover",
              "ic_mean", "ic_std", "ir", "verdict", "data_snapshot", "code_sha1", "details_path", "notes"]


# ----------------------------------------------------------------------------- data
def load_prices(refresh: bool = False) -> pd.DataFrame:
    if refresh or not PRICES_PATH.exists():
        df = yf.download(TICKERS, start="2022-10-01", auto_adjust=True, progress=False, actions=False, group_by="column")
        if df.empty:
            raise RuntimeError("yfinance returned no data")
        long = df.stack(level=1, future_stack=True).reset_index()
        long.columns = [str(c) for c in long.columns]
        long = long.rename(columns={"Date": "date", "Ticker": "ticker"})
        long = long[["date", "ticker", "Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "Close"])
        settings.RAW_PRICES.mkdir(parents=True, exist_ok=True)
        long.to_csv(PRICES_PATH, index=False)
        (PRICES_PATH.with_suffix(".meta.json")).write_text(json.dumps({
            "tickers": TICKERS, "source": "yfinance", "yfinance_version": yf.__version__, "auto_adjust": True,
            "retrieved_at_utc": utc_now_iso(), "rows": len(long),
            "first_date": str(long["date"].min())[:10], "last_date": str(long["date"].max())[:10]}, indent=2))
        log.info("downloaded %d price rows -> %s", len(long), PRICES_PATH)
    p = pd.read_csv(PRICES_PATH, parse_dates=["date"])
    missing = set(TICKERS) - set(p["ticker"])
    if missing:
        raise RuntimeError(f"no prices for {missing}")
    return p


def forward_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """ret_fwd[s, ticker] = first open of week s+2 / first open of week s+1 - 1 (index: signal week s)."""
    p = prices.sort_values("date").copy()
    p["week_start"] = week_start(p["date"].dt.strftime("%Y-%m-%d"))
    first_open = p.groupby(["week_start", "ticker"])["Open"].first().unstack("ticker")
    weeks = pd.date_range(first_open.index.min(), first_open.index.max(), freq="7D", tz="UTC")
    first_open = first_open.reindex(weeks)   # a week without trading stays NaN, never bridged
    entry = first_open.shift(-1)              # open of week s+1
    exit_ = first_open.shift(-2)              # open of week s+2
    fwd = exit_ / entry - 1
    fwd.index = fwd.index.strftime("%Y-%m-%d")
    return fwd[TICKERS]


def signals():
    w = pd.read_csv(settings.PROCESSED / "reddit_weekly.csv")
    ws = pd.read_csv(settings.PROCESSED / "reddit_weekly_by_subreddit.csv")
    wsb = ws[ws["subreddit"] == "wallstreetbets"]
    flag = w.pivot(index="week_start", columns="ticker", values="posts_spike_flag").reindex(columns=TICKERS).astype(bool)
    ratio = w.pivot(index="week_start", columns="ticker", values="posts_spike_ratio").reindex(columns=TICKERS)
    complete = w.groupby("week_start")["coverage_complete"].all()
    wsb_flag = wsb.pivot(index="week_start", columns="ticker", values="posts_spike_flag").reindex(columns=TICKERS).astype(bool)
    wsb_complete = wsb.groupby("week_start")["coverage_complete"].all()
    # a week is tradable only when the current week AND its full 4-week baseline are defined
    defined = w.groupby("week_start")["posts_median_4w"].apply(lambda s: s.notna().all())
    wsb_defined = wsb.groupby("week_start")["posts_median_4w"].apply(lambda s: s.notna().all())
    return flag, ratio, complete & defined, wsb_flag, wsb_complete & wsb_defined


# ----------------------------------------------------------------------------- strategies
def _ew(mask: pd.DataFrame, sign: float) -> pd.DataFrame:
    k = mask.sum(axis=1)
    return mask.astype(float).div(k.where(k > 0), axis=0).fillna(0.0) * sign


def build_weights(flag, ratio, wsb_flag) -> dict[str, pd.DataFrame]:
    ew_all = pd.DataFrame(1 / len(TICKERS), index=flag.index, columns=TICKERS)
    s1 = _ew(flag, +1)
    s3 = (s1 - ew_all).where(flag.any(axis=1), 0.0, axis=0)
    top = ratio.rank(axis=1, ascending=False, method="first") <= 3
    bot = ratio.rank(axis=1, ascending=True, method="first") <= 3
    enough = ratio.notna().sum(axis=1) >= 6
    s4 = (_ew(top, +0.5) + _ew(bot, -0.5)).where(enough, 0.0, axis=0)
    return {"S1": s1, "S2": _ew(flag, -1), "S3": s3, "S4": s4, "S5": _ew(wsb_flag, -1), "B0": ew_all}


def metrics(r: pd.Series, gross: pd.Series, invested: pd.Series, b0: pd.Series | None) -> dict:
    n = len(r)
    out = {"eval_weeks": n, "invested_weeks": int(invested.sum())}
    if n == 0:
        return out
    eq = (1 + r).cumprod()
    mu, sd = r.mean(), r.std(ddof=1)
    out.update({
        "total_return_gross": float((1 + gross).prod() - 1),
        "total_return_net": float(eq.iloc[-1] - 1),
        "ann_return_net": float(eq.iloc[-1] ** (52 / n) - 1),
        "ann_vol_net": float(sd * np.sqrt(52)) if n > 1 else np.nan,
        "sharpe_net": float(mu / sd * np.sqrt(52)) if n > 1 and sd > 0 else np.nan,
        "sharpe_gross": float(gross.mean() / gross.std(ddof=1) * np.sqrt(52)) if n > 1 and gross.std(ddof=1) > 0 else np.nan,
        "t_stat_net": float(mu / (sd / np.sqrt(n))) if n > 1 and sd > 0 else np.nan,
        "max_drawdown_net": float((eq / eq.cummax() - 1).min()),
        "hit_rate_invested": float((r[invested] > 0).mean()) if invested.any() else np.nan,
        "mean_weekly_return_invested": float(r[invested].mean()) if invested.any() else np.nan,
    })
    if b0 is not None:
        out["excess_ann_return_vs_B0"] = out["ann_return_net"] - float((1 + b0).prod() ** (52 / n) - 1)
    return out


def verdict(m: dict, sid: str) -> str:
    if sid == "B0":
        return "BENCHMARK"
    if m["eval_weeks"] < MIN_WEEKS:
        return f"INSUFFICIENT DATA (<{MIN_WEEKS} evaluation weeks)"
    if m.get("invested_weeks", 0) == 0:
        return "FAILED (never traded)"
    s, t = m.get("sharpe_net", np.nan), m.get("t_stat_net", np.nan)
    if s >= 0.5 and abs(t) >= 2 and t > 0:
        return "PROMISING (needs out-of-sample check)"
    if s > 0:
        return "WEAK"
    return "FAILED"


# ----------------------------------------------------------------------------- run
def append_log(rows: list[dict]) -> None:
    settings.STRATEGY_LOGS.mkdir(parents=True, exist_ok=True)
    new = not LOG_PATH.exists()
    df = pd.DataFrame(rows).reindex(columns=LOG_FIELDS)
    df.to_csv(LOG_PATH, mode="a", header=new, index=False)


def import_alpha101() -> int:
    """Register the Vibe-Trading Alpha101 benchmark runs in the Strategy Log (idempotent per source log)."""
    src = settings.STRATEGY_LOGS / "alpha101_comparison.csv"
    if not src.exists():
        return 0
    a = pd.read_csv(src)
    existing = pd.read_csv(LOG_PATH) if LOG_PATH.exists() else pd.DataFrame(columns=LOG_FIELDS)
    a = a[~a["source_log"].isin(existing.get("details_path", pd.Series(dtype=str)).astype(str).str.split("/").str[-1])]
    if a.empty:
        return 0
    run_id = a["source_log"].iloc[0].replace("alpha_compare_", "vt_").replace(".log", "")
    ts = datetime.strptime(run_id[3:], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{
        "run_id": run_id, "run_timestamp_utc": ts, "source": "vibe-trading alpha compare (benchmark, not Reddit)",
        "strategy_id": r["id"], "strategy_name": r["id"], "hypothesis": "Kakushadze (2015) formulaic alpha",
        "rule": r.get("formula (Kakushadze 2015)", ""), "universe": f"{r['universe']} (current constituents)",
        "eval_start_week": str(r["period"]).split("-")[0], "eval_end_week": str(r["period"]).split("-")[-1],
        "eval_weeks": np.nan, "ic_mean": r["ic_mean"], "ic_std": r["ic_std"], "ir": r["ir"],
        "verdict": "FAILED (IR < 0)" if r["ir"] < 0 else ("WEAK (IR < 0.1)" if r["ir"] < 0.1 else "OK"),
        "data_snapshot": f"{int(r['ic_count'])} daily IC observations; {int(r['failed_ticker_downloads'])} tickers failed to download",
        "details_path": f"results/strategy_logs/{r['source_log']}",
        "notes": f"rank {int(r['rank'])}/5 by IR; metrics are daily rank IC vs next-day return, no Sharpe/drawdown produced",
    } for _, r in a.iterrows()]
    append_log(rows)
    return len(rows)


def write_markdown() -> None:
    df = pd.read_csv(LOG_PATH)
    lines = ["# Strategy Log", "",
             "Append-only record of every strategy test, including failures. Generated from `strategy_log.csv`.", ""]
    for run_id, g in df.groupby("run_id", sort=False):
        r0 = g.iloc[0]
        lines += [f"## {run_id} — {r0['source']}", "",
                  f"Run at {r0['run_timestamp_utc']} · evaluation {r0['eval_start_week']} → {r0['eval_end_week']} · {r0['data_snapshot']}", ""]
        if str(r0["source"]).startswith("vibe"):
            lines += ["| alpha | IC mean | IC std | IR | verdict |", "|---|---|---|---|---|"]
            lines += [f"| {r.strategy_id} | {r.ic_mean:.4f} | {r.ic_std:.4f} | {r.ir:.4f} | {r.verdict} |" for r in g.itertuples()]
        else:
            lines += ["| id | strategy | weeks (invested) | total net | ann. net | Sharpe net | t | max DD | hit rate | verdict |",
                      "|---|---|---|---|---|---|---|---|---|---|"]
            f = lambda x, p=True: "—" if pd.isna(x) else (f"{x * 100:+.1f}%" if p else f"{x:.2f}")
            lines += [f"| {r.strategy_id} | {r.strategy_name} | {int(r.eval_weeks)} ({int(r.invested_weeks)}) | "
                      f"{f(r.total_return_net)} | {f(r.ann_return_net)} | {f(r.sharpe_net, False)} | {f(r.t_stat_net, False)} | "
                      f"{f(r.max_drawdown_net)} | {'—' if pd.isna(r.hit_rate_invested) else f'{r.hit_rate_invested:.0%}'} | {r.verdict} |" for r in g.itertuples()]
        lines.append("")
    (settings.STRATEGY_LOGS / "strategy_log.md").write_text("\n".join(lines))


def run(cost_bps: float = 10.0, refresh_prices: bool = False, note: str = "") -> pd.DataFrame:
    import_alpha101()
    fwd = forward_returns(load_prices(refresh_prices))
    flag, ratio, ok, wsb_flag, wsb_ok = signals()
    weights = build_weights(flag, ratio, wsb_flag)

    run_id = "reddit_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    code_sha1 = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:12]
    manifest = pd.read_csv(settings.MANIFEST)
    done = manifest.drop_duplicates(["subreddit", "date"], keep="last")
    pct = (done["status"] == "complete").sum() / (3 * len(pd.date_range(settings.START_DATE, settings.default_end_date())))

    results, weekly = {}, {}
    for sid, w in weights.items():
        valid = (wsb_ok if sid == "S5" else ok).reindex(w.index).fillna(False)
        if sid == "B0":
            valid = ok.reindex(w.index).fillna(False)
        weeks = [s for s in w.index if valid.get(s, False) and s in fwd.index and fwd.loc[s].notna().all()]
        W = w.loc[weeks]
        R = fwd.loc[weeks]
        gross = (W * R).sum(axis=1)
        turnover = W.diff().abs().sum(axis=1)
        if len(W):
            turnover.iloc[0] = W.iloc[0].abs().sum()
        net = gross - turnover * cost_bps / 1e4
        invested = W.abs().sum(axis=1) > 0
        weekly[sid] = pd.DataFrame({"gross": gross, "net": net, "turnover": turnover, "invested": invested,
                                    "n_long": (W > 0).sum(axis=1), "n_short": (W < 0).sum(axis=1),
                                    "positions": W.apply(lambda row: " ".join(f"{t}:{v:+.2f}" for t, v in row.items() if v), axis=1)})
        results[sid] = (net, gross, invested, turnover, W)

    b0_net = results["B0"][0]
    rows = []
    for sid, (net, gross, invested, turnover, W) in results.items():
        m = metrics(net, gross, invested, b0_net.reindex(net.index).fillna(0) if sid != "B0" else None)
        name, hyp, rule = STRATEGIES[sid]
        rows.append({
            "run_id": run_id, "run_timestamp_utc": utc_now_iso()[:19] + "Z", "source": "reddit indicator backtest",
            "strategy_id": sid, "strategy_name": name, "hypothesis": hyp, "rule": rule,
            "universe": "AAPL MSFT NVDA TSLA AMZN META GOOGL AMD NFLX JPM",
            "eval_start_week": net.index.min() if len(net) else "", "eval_end_week": net.index.max() if len(net) else "",
            "position_weeks": int((W != 0).sum().sum()), "cost_bps": cost_bps,
            "avg_weekly_turnover": float(turnover.mean()) if len(turnover) else np.nan,
            **m, "verdict": verdict(m, sid),
            "data_snapshot": f"Reddit collection {pct:.1%} complete; {len(net)} evaluable signal weeks",
            "code_sha1": code_sha1, "details_path": f"results/strategy_logs/runs/{run_id}", "notes": note,
        })
        weekly[sid].to_csv(run_dir / f"{sid}_{name}_weekly.csv", index_label="signal_week")
    append_log(rows)
    (run_dir / "run_meta.json").write_text(json.dumps({
        "run_id": run_id, "cost_bps": cost_bps, "code_sha1": code_sha1, "collection_complete_fraction": pct,
        "timing": "signal week s (Mon-Sun UTC) -> enter first open of week s+1 -> exit first open of week s+2",
        "prices": str(PRICES_PATH.relative_to(settings.ROOT)), "strategies": STRATEGIES}, indent=2))
    write_markdown()
    out = pd.DataFrame(rows)
    log.info("run %s logged:\n%s", run_id, out[["strategy_id", "strategy_name", "eval_weeks", "invested_weeks",
                                                "total_return_net", "sharpe_net", "max_drawdown_net", "verdict"]].to_string(index=False))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--refresh-prices", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    run(a.cost_bps, a.refresh_prices, a.note)
