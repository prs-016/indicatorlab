"""Team-format strategy sheet (Who / Strategy / What it does / IC / Sharpe / Keep or drop / Why).

Built from results/strategy_logs/strategy_log.csv: the Vibe-Trading Alpha101 benchmark rows and
the latest Reddit-indicator backtest run. Writes strategy_sheet.csv and a paste-ready .tsv.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.reddit import settings

WHAT = {
    "alpha101_012": "Bets yesterday's price move reverses when volume rose (buys volume-backed drops, sells volume-backed jumps)",
    "alpha101_002": "Bets against stocks where rising volume lines up with strong open-to-close gains over 6 days",
    "alpha101_013": "Shorts stocks whose price and volume rankings move together over 5 days",
    "alpha101_003": "Shorts stocks whose opening-price and volume rankings move together over 10 days",
    "alpha101_006": "Shorts stocks whose raw opening price and volume move together over 10 days",
    "S1": "Buys any of the 10 stocks whose Reddit posts hit 2x their 4-week median, holds one week",
    "S2": "Shorts stocks whose Reddit posts spiked 2x, betting the hype reverses",
    "S3": "Buys spiked stocks and shorts an equal mix of all 10, so market direction cancels out",
    "S4": "Buys the 3 stocks with the biggest chatter jump and shorts the 3 with the smallest, every week",
    "S5": "Shorts stocks whose r/wallstreetbets posts spiked 2x, betting retail frenzy fades",
    "B0": "Always holds all 10 stocks in equal amounts, the bar every Reddit strategy must beat",
}
VT_CAVEAT = ("S&P 500 2021-2024, current constituents (survivorship bias), 5 tickers failed to load; "
             "no random-signal or index control was run")


def build(who: str) -> pd.DataFrame:
    log = pd.read_csv(settings.STRATEGY_LOGS / "strategy_log.csv")
    vt = log[log["source"].str.startswith("vibe")].drop_duplicates("strategy_id", keep="last").set_index("strategy_id")
    rid = log.loc[log["source"] == "reddit indicator backtest", "run_id"].iloc[-1]
    r = log[log["run_id"] == rid].set_index("strategy_id")
    b = r.loc["B0"]
    pct = lambda x: f"{x * 100:+.1f}%"
    rows = []
    for sid in ["alpha101_012", "alpha101_002", "alpha101_013", "alpha101_003", "alpha101_006"]:
        x = vt.loc[sid]
        if x["ic_mean"] < 0:
            why = (f"Negative IC ({x['ic_mean']:.4f}, IR {x['ir']:.3f}): points the wrong way, and it was the noisiest "
                   f"(IC std {x['ic_std']:.3f}); raw unranked levels let a few high-volume names dominate. {VT_CAVEAT}")
        else:
            why = (f"IC {x['ic_mean']:.4f} / IR {x['ir']:.3f} is indistinguishable from zero for a daily signal; "
                   f"short-horizon volume-price patterns in liquid large caps are largely arbitraged away. {VT_CAVEAT}")
        rows.append({"Strategy": sid, "IC": round(float(x["ic_mean"]), 4), "Sharpe": "not produced by alpha compare",
                     "Keep or drop": "Drop", "Why you think it did well or badly": why})
    n, period = int(b["eval_weeks"]), f"{b['eval_start_week']} to {b['eval_end_week']}"
    why = {
        "S1": (f"{pct(r.loc['S1','total_return_net'])} net, Sharpe {r.loc['S1','sharpe_net']:.2f} (t {r.loc['S1','t_stat_net']:.2f}) passes our "
               f"pre-set rule, but buy-and-hold made {pct(b['total_return_net'])} at Sharpe {b['sharpe_net']:.2f} with lower volatility. "
               f"The gain is market exposure to mega-caps in a bull run, not spike skill: its market-neutral twin S3 has Sharpe "
               f"{r.loc['S3','sharpe_net']:.2f}"),
        "S2": (f"{pct(r.loc['S2','total_return_net'])}, Sharpe {r.loc['S2','sharpe_net']:.2f}, max drawdown {r.loc['S2','max_drawdown_net']*100:.0f}%. "
               f"Mirror of S1: shorting mega-caps through the 2023-2026 rally; spikes did not mark tops"),
        "S3": (f"{pct(r.loc['S3','total_return_net'])} net, Sharpe {r.loc['S3','sharpe_net']:.2f}, t {r.loc['S3','t_stat_net']:.2f}: "
               f"spiked stocks barely beat their peers (right {r.loc['S3','hit_rate_invested']*100:.0f}% of weeks). Gross Sharpe was "
               f"{r.loc['S3','sharpe_gross']:.2f}; weekly turnover costs ate half of it"),
        "S4": (f"{pct(r.loc['S4','total_return_net'])}, Sharpe {r.loc['S4','sharpe_net']:.2f}: relative attention does not rank next-week "
               f"returns among 10 mega-caps; 3-vs-3 baskets are noisy and turn over every week"),
        "S5": (f"{pct(r.loc['S5','total_return_net'])}, Sharpe {r.loc['S5','sharpe_net']:.2f}: WSB spikes in these names kept rising rather than "
               f"fading; WSB frenzies that reverse are mostly small caps, not the top 10"),
        "B0": f"Rode the mega-cap rally: {pct(b['total_return_net'])} over {n} weeks, max drawdown {b['max_drawdown_net']*100:.0f}%",
    }
    names = {"S1": "Reddit S1 spike_momentum", "S2": "Reddit S2 spike_contrarian", "S3": "Reddit S3 spike_vs_universe",
             "S4": "Reddit S4 attention_rank_ls", "S5": "Reddit S5 wsb_spike_fade", "B0": "Reddit B0 equal_weight_hold (benchmark)"}
    for sid in ["S1", "S2", "S3", "S4", "S5", "B0"]:
        rows.append({"Strategy": names[sid], "IC": "n/a (rule-based, not a ranking factor)" if sid != "B0" else "n/a",
                     "Sharpe": round(float(r.loc[sid, "sharpe_net"]), 2),
                     "Keep or drop": "Benchmark" if sid == "B0" else "Drop",
                     "Why you think it did well or badly": why[sid] + (f". {n} weeks, {period}, net of 10 bps costs" if sid != "B0" else "")})
    df = pd.DataFrame(rows)
    df.insert(0, "Who", who)
    df.insert(2, "What it does (one line)", [WHAT[k.split()[1] if k.startswith("Reddit") else k] for k in df["Strategy"]])
    df.to_csv(settings.STRATEGY_LOGS / "strategy_sheet.csv", index=False)
    df.to_csv(settings.STRATEGY_LOGS / "strategy_sheet.tsv", index=False, sep="\t")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="Joshua")
    print(build(ap.parse_args().who)[["Strategy", "IC", "Sharpe", "Keep or drop"]].to_string(index=False))
