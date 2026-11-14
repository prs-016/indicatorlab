#!/usr/bin/env python3
"""Backtest five momentum signals and the TGQM worked example on the HSI.

The point-in-time universe starts in late 2014, so the honest training sample is
2015-2019 rather than the generic 2011-2019 template in the assignment.  The
holdout is 2020 through 30-Sep-2025.  Signals are observed after the close,
executed at the next close, and pay 10 bps per unit of one-way turnover.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
MARKET_DIR = ROOT / "data" / "hk_market_history"
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "results" / "hk" / "week2"
TRAIN = (pd.Timestamp("2015-01-01"), pd.Timestamp("2019-12-31"))
TEST = (pd.Timestamp("2020-01-01"), pd.Timestamp("2025-09-30"))
COST = 0.001
TOP_N = 10
RANDOM_RUNS = 200
TRADING_DAYS = 252

LABELS = {
    "mom_5d": "5-day momentum",
    "mom_20d": "20-day momentum",
    "mom_60d": "60-day momentum",
    "ma_10_30": "10/30-day moving-average momentum",
    "risk_adj_mom_20d": "20-day risk-adjusted momentum",
    "tgqm": "TGQM composite",
}


@dataclass
class Market:
    prices: pd.DataFrame
    returns: pd.DataFrame
    volume: pd.DataFrame
    membership: pd.DataFrame
    hsi: pd.Series


def load_market(market_dir: Path, membership_path: Path) -> Market:
    coverage = pd.read_csv(market_dir / "coverage.csv")
    membership_rows = pd.read_csv(membership_path, parse_dates=["member_from", "member_to"])
    benchmark_row = coverage.loc[coverage["ticker"].eq("^HSI") & coverage["status"].eq("downloaded")].iloc[0]
    benchmark = pd.read_csv(market_dir / str(benchmark_row["file"]), parse_dates=["Date"]).set_index("Date").sort_index()
    dates = benchmark.loc["2014-01-01":TEST[1]].index

    prices: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}
    for ticker in sorted(membership_rows["ticker"].unique()):
        row = coverage.loc[coverage["ticker"].eq(ticker) & coverage["status"].eq("downloaded")]
        if row.empty:
            continue
        frame = pd.read_csv(market_dir / str(row.iloc[0]["file"]), parse_dates=["Date"]).set_index("Date").sort_index()
        prices[ticker] = pd.to_numeric(frame["Adj Close"], errors="coerce")
        volumes[ticker] = pd.to_numeric(frame["Volume"], errors="coerce")

    price = pd.DataFrame(prices).reindex(dates).ffill()
    volume = pd.DataFrame(volumes).reindex(dates).fillna(0.0)
    member = pd.DataFrame(False, index=dates, columns=price.columns)
    for row in membership_rows.itertuples(index=False):
        if row.ticker in member.columns:
            member.loc[(dates >= row.member_from) & (dates <= row.member_to), row.ticker] = True
    price = price.where(member)
    returns = price.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0).where(member, 0.0)
    hsi = pd.to_numeric(benchmark["Close"], errors="coerce").reindex(dates).ffill()
    return Market(price, returns, volume, member, hsi)


def signals(market: Market) -> dict[str, pd.DataFrame]:
    prices = market.prices
    daily = prices.pct_change(fill_method=None)
    volatility20 = daily.rolling(20).std()
    raw = {
        "mom_5d": prices.pct_change(5, fill_method=None),
        "mom_20d": prices.pct_change(20, fill_method=None),
        "mom_60d": prices.pct_change(60, fill_method=None),
        "ma_10_30": prices.rolling(10).mean() / prices.rolling(30).mean() - 1.0,
        "risk_adj_mom_20d": prices.pct_change(20, fill_method=None) / volatility20.replace(0, np.nan),
    }
    momentum = prices.shift(21) / prices.shift(252) - 1.0
    low_volatility = -daily.rolling(63).std()
    reversal = -prices.pct_change(5, fill_method=None)

    def zscore(frame: pd.DataFrame) -> pd.DataFrame:
        mean = frame.mean(axis=1)
        std = frame.std(axis=1).replace(0, np.nan)
        return frame.sub(mean, axis=0).div(std, axis=0)

    raw["tgqm"] = 0.5 * zscore(momentum) + 0.3 * zscore(low_volatility) + 0.2 * zscore(reversal)
    return {key: value.where(market.membership) for key, value in raw.items()}


def signal_dates(index: pd.DatetimeIndex, frequency: str) -> list[pd.Timestamp]:
    period = index.to_period("W-FRI" if frequency == "weekly" else "M")
    last = pd.Series(index, index=index).groupby(period).last().tolist()
    return [date for date in last if TRAIN[0] <= date < TEST[1]]


def capped_inverse_vol(vol: pd.Series, cap: float = 0.15) -> pd.Series:
    raw = 1.0 / vol.replace(0, np.nan)
    weights = raw / raw.sum()
    for _ in range(20):
        above = weights > cap
        if not above.any():
            break
        fixed = float(above.sum()) * cap
        rest = weights.loc[~above]
        weights.loc[above] = cap
        if not rest.empty and rest.sum() > 0:
            weights.loc[~above] = rest / rest.sum() * (1.0 - fixed)
    return weights.fillna(0.0)


def build_targets(
    signal: pd.DataFrame,
    market: Market,
    *,
    frequency: str,
    inverse_vol: bool,
    regime_filter: bool,
) -> tuple[dict[int, np.ndarray], list[dict[str, object]]]:
    dates = market.prices.index
    columns = market.prices.columns
    hsi_ma200 = market.hsi.rolling(200).mean()
    vol63 = market.prices.pct_change(fill_method=None).rolling(63).std()
    targets: dict[int, np.ndarray] = {}
    log: list[dict[str, object]] = []
    for date in signal_dates(dates, frequency):
        position = dates.get_loc(date)
        if position + 1 >= len(dates):
            continue
        eligible = signal.loc[date].dropna()
        eligible = eligible.loc[market.volume.loc[date, eligible.index].gt(0)]
        if len(eligible) < 30:
            continue
        selected = eligible.nlargest(TOP_N).index
        if inverse_vol:
            selected_weights = capped_inverse_vol(vol63.loc[date, selected])
        else:
            selected_weights = pd.Series(1.0 / TOP_N, index=selected)
        exposure = 0.5 if regime_filter and market.hsi.loc[date] < hsi_ma200.loc[date] else 1.0
        target = np.zeros(len(columns), dtype=float)
        target[columns.get_indexer(selected)] = selected_weights.to_numpy() * exposure
        targets[position + 1] = target
        log.append({
            "signal_date": date,
            "execution_date": dates[position + 1],
            "selected": ", ".join(selected),
            "eligible_count": len(eligible),
            "gross_exposure": exposure,
        })
    return targets, log


def build_random_targets(
    signal: pd.DataFrame,
    market: Market,
    *,
    frequency: str,
    inverse_vol: bool,
    regime_filter: bool,
    runs: int,
    seed: int,
) -> dict[int, np.ndarray]:
    rng = np.random.default_rng(seed)
    dates = market.prices.index
    columns = market.prices.columns
    hsi_ma200 = market.hsi.rolling(200).mean()
    vol63 = market.prices.pct_change(fill_method=None).rolling(63).std()
    targets: dict[int, np.ndarray] = {}
    for date in signal_dates(dates, frequency):
        position = dates.get_loc(date)
        if position + 1 >= len(dates):
            continue
        eligible = signal.loc[date].dropna().index
        eligible = eligible[market.volume.loc[date, eligible].gt(0)]
        if len(eligible) < 30:
            continue
        exposure = 0.5 if regime_filter and market.hsi.loc[date] < hsi_ma200.loc[date] else 1.0
        event = np.zeros((runs, len(columns)), dtype=float)
        for run in range(runs):
            selected = rng.choice(eligible.to_numpy(), size=TOP_N, replace=False)
            if inverse_vol:
                weights = capped_inverse_vol(vol63.loc[date, selected]).to_numpy()
            else:
                weights = np.full(TOP_N, 1.0 / TOP_N)
            event[run, columns.get_indexer(selected)] = weights * exposure
        targets[position + 1] = event
    return targets


def simulate(market: Market, targets: dict[int, np.ndarray], scenarios: int = 1) -> tuple[pd.DataFrame, pd.DataFrame]:
    asset_returns = market.returns.to_numpy(dtype=float)
    weights = np.zeros((scenarios, asset_returns.shape[1]), dtype=float)
    result = np.zeros((len(market.returns), scenarios), dtype=float)
    turnover_rows = []
    for day, returns_today in enumerate(asset_returns):
        gross = np.sum(weights * returns_today[None, :], axis=1)
        denominator = np.maximum(1.0 + gross, 1e-12)
        drifted = weights * (1.0 + returns_today[None, :]) / denominator[:, None]
        if day in targets:
            target = targets[day]
            if target.ndim == 1:
                target = target[None, :]
            turnover = np.abs(target - drifted).sum(axis=1)
            result[day] = (1.0 + gross) * (1.0 - COST * turnover) - 1.0
            weights = target.copy()
            turnover_rows.append({"date": market.returns.index[day], "mean_turnover": float(turnover.mean())})
        else:
            result[day] = gross
            weights = drifted
    return pd.DataFrame(result, index=market.returns.index), pd.DataFrame(turnover_rows)


def performance(returns: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    series = returns.loc[start:end].dropna()
    wealth = (1.0 + series).cumprod()
    years = len(series) / TRADING_DAYS
    std = series.std(ddof=1)
    return {
        "cagr": float(wealth.iloc[-1] ** (1.0 / years) - 1.0),
        "sharpe": float(series.mean() / std * np.sqrt(TRADING_DAYS)) if std > 0 else np.nan,
        "max_drawdown": float((wealth / wealth.cummax() - 1.0).min()),
        "cumulative_return": float(wealth.iloc[-1] - 1.0),
    }


def mean_ic(signal: pd.DataFrame, prices: pd.DataFrame, dates: list[pd.Timestamp], horizon: int, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float, int]:
    values = []
    for date in dates:
        if not start <= date <= end:
            continue
        position = prices.index.get_loc(date)
        if position + horizon >= len(prices):
            continue
        x = signal.loc[date]
        y = prices.iloc[position + horizon] / prices.iloc[position] - 1.0
        valid = x.notna() & y.notna()
        if valid.sum() >= 10:
            values.append(x.loc[valid].corr(y.loc[valid], method="spearman"))
    series = pd.Series(values, dtype=float).dropna()
    return (float(series.mean()) if not series.empty else np.nan, int(len(series)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-dir", type=Path, default=MARKET_DIR)
    parser.add_argument("--membership", type=Path, default=MARKET_DIR.parents[1] / "config" / "hsi_membership_intervals.csv")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--random-runs", type=int, default=RANDOM_RUNS)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    market = load_market(args.market_dir, args.membership)
    factor_signals = signals(market)
    hsi_returns = market.hsi.pct_change(fill_method=None).fillna(0.0)

    # A monthly-rebalanced point-in-time equal-weight benchmark.
    ew_signal = market.prices.notna().astype(float).where(market.membership)
    ew_targets: dict[int, np.ndarray] = {}
    for date in signal_dates(market.prices.index, "monthly"):
        pos = market.prices.index.get_loc(date)
        eligible = ew_signal.loc[date].dropna().index
        if pos + 1 < len(market.prices.index) and len(eligible):
            target = np.zeros(len(market.prices.columns))
            target[market.prices.columns.get_indexer(eligible)] = 1.0 / len(eligible)
            ew_targets[pos + 1] = target
    ew_returns, _ = simulate(market, ew_targets)

    results = []
    random_rows = []
    daily = {"hsi_price_index": hsi_returns, "hsi_equal_weight": ew_returns.iloc[:, 0]}
    rebalance_rows = []
    for number, (strategy, signal) in enumerate(factor_signals.items(), start=1):
        tgqm = strategy == "tgqm"
        frequency = "monthly" if tgqm else "weekly"
        targets, event_log = build_targets(signal, market, frequency=frequency, inverse_vol=tgqm, regime_filter=tgqm)
        returns, turnover = simulate(market, targets)
        strategy_returns = returns.iloc[:, 0]
        daily[strategy] = strategy_returns
        for item in event_log:
            rebalance_rows.append({"strategy": strategy, **item})

        random_targets = build_random_targets(
            signal, market, frequency=frequency, inverse_vol=tgqm, regime_filter=tgqm,
            runs=args.random_runs, seed=20261104 + number,
        )
        random_returns, _ = simulate(market, random_targets, scenarios=args.random_runs)
        factor_dates = signal_dates(market.prices.index, frequency)
        horizon = 21 if tgqm else 5
        period_stats = {}
        for period, (start, end) in {"train": TRAIN, "test": TEST}.items():
            stats = performance(strategy_returns, start, end)
            index_stats = performance(hsi_returns, start, end)
            ew_stats = performance(ew_returns.iloc[:, 0], start, end)
            ic, ic_count = mean_ic(signal, market.prices, factor_dates, horizon, start, end)
            random_sharpes = []
            for run in range(args.random_runs):
                random_stat = performance(random_returns.iloc[:, run], start, end)
                random_sharpes.append(random_stat["sharpe"])
                random_rows.append({"strategy": strategy, "random_run": run + 1, "period": period, **random_stat})
            percentile = float(np.mean(stats["sharpe"] > np.asarray(random_sharpes)) * 100.0)
            avg_turnover = float(turnover.loc[turnover["date"].between(start, end), "mean_turnover"].mean())
            period_stats[period] = {**stats, "ic": ic, "ic_observations": ic_count, "average_one_way_turnover": avg_turnover, "random_sharpe_percentile": percentile, "index_sharpe": index_stats["sharpe"], "equal_weight_sharpe": ew_stats["sharpe"]}

        train_pass = period_stats["train"]["random_sharpe_percentile"] >= 90.0
        test_pass = period_stats["test"]["random_sharpe_percentile"] >= 90.0
        beats_index = period_stats["test"]["sharpe"] > period_stats["test"]["index_sharpe"]
        if train_pass and test_pass and beats_index:
            decision = "Keep"
            reason = "Beat at least 90% of random portfolios in both periods and exceeded the HSI test Sharpe."
        elif train_pass or test_pass:
            decision = "Watch"
            reason = "The edge cleared the random-baseline hurdle in only one period, so it is not stable enough to keep."
        else:
            decision = "Drop"
            reason = "Failed the 90th-percentile random-baseline hurdle in both train and test."
        for period, stats in period_stats.items():
            results.append({"strategy": strategy, "strategy_name": LABELS[strategy], "description": {
                "mom_5d": "Ranks HSI members by 5-day adjusted-price return; buys the top 10 weekly.",
                "mom_20d": "Ranks HSI members by 20-day adjusted-price return; buys the top 10 weekly.",
                "mom_60d": "Ranks HSI members by 60-day adjusted-price return; buys the top 10 weekly.",
                "ma_10_30": "Ranks HSI members by the 10-day average divided by the 30-day average; buys the top 10 weekly.",
                "risk_adj_mom_20d": "Ranks 20-day momentum divided by 20-day volatility; buys the top 10 weekly.",
                "tgqm": "Monthly 50% 12-to-1 momentum, 30% low volatility and 20% reversal; top 10 inverse-vol weighted, 15% cap, 50% exposure below HSI 200DMA.",
            }[strategy], "period": period, **stats, "decision": decision, "reason": reason})

    results_frame = pd.DataFrame(results)
    results_frame.to_csv(args.output_dir / "strategy_results.csv", index=False)
    pd.DataFrame(random_rows).to_csv(args.output_dir / "random_baseline_results.csv", index=False)
    pd.DataFrame(daily).loc[TRAIN[0]:TEST[1]].to_csv(args.output_dir / "strategy_daily_returns.csv", index_label="date")
    pd.DataFrame(rebalance_rows).to_csv(args.output_dir / "strategy_rebalances.csv", index=False)

    test_rows = results_frame.loc[results_frame["period"].eq("test")]
    lines = ["# Hong Kong Strategy Log", "", "Signals use point-in-time HSI membership, next-close execution and 10 bps one-way turnover costs.", "", "| Strategy | What it does | Test IC | Test Sharpe | Decision | Why |", "|---|---|---:|---:|---|---|"]
    for row in test_rows.itertuples(index=False):
        lines.append(f"| {row.strategy_name} | {row.description} | {row.ic:.3f} | {row.sharpe:.3f} | {row.decision} | {row.reason} |")
    lines.extend(["", "## Honest limitations", "", "- Historical point-in-time membership begins in late 2014, so train is 2015-2019, not 2011-2019.", "- Constituent returns use Yahoo adjusted prices (include distributions), while ^HSI is a price index; the equal-weight comparison is therefore more like-for-like.", "- The free historical reconstruction is checked against official review counts but is not a licensed HSI constituent-history product.", ""])
    (args.output_dir / "strategy_log.md").write_text("\n".join(lines))
    summary = {"strategies_tested": len(factor_signals), "random_runs_per_strategy": args.random_runs, "train": [str(TRAIN[0].date()), str(TRAIN[1].date())], "test": [str(TEST[0].date()), str(TEST[1].date())], "decisions": test_rows.set_index("strategy")["decision"].to_dict()}
    (args.output_dir / "strategy_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
