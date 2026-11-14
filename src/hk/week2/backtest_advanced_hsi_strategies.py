#!/usr/bin/env python3
"""Backtest five institutional-style, price/volume HSI strategies.

Every candidate satisfies the assignment's eight design requirements: at least
two signals, explicit entry and exit rules, risk-based sizing, an index regime
filter, turnover costs, delayed execution, and a real point-in-time universe.
The models are deliberately limited to daily adjusted prices and volume because
those are the fields available consistently in the local archive.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .backtest_hsi_strategies import (
    COST,
    MARKET_DIR,
    OUTPUT_DIR,
    TEST,
    TRAIN,
    capped_inverse_vol,
    load_market,
    mean_ic,
    performance,
    signal_dates,
    simulate,
)


TOP_N = 10
RANDOM_RUNS = 200
MIN_ELIGIBLE = 30


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    signals_used: str
    regime_rule: str
    exposure: Callable[[pd.Timestamp, pd.Series, pd.DataFrame], float]


def cross_sectional_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Winsorized cross-sectional z-score for each date."""
    low = frame.quantile(0.025, axis=1)
    high = frame.quantile(0.975, axis=1)
    clipped = frame.clip(lower=low, upper=high, axis=0)
    mean = clipped.mean(axis=1)
    std = clipped.std(axis=1).replace(0.0, np.nan)
    return clipped.sub(mean, axis=0).div(std, axis=0)


def product_return(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    log_return = np.log1p(frame.clip(lower=-0.999999))
    return np.expm1(log_return.rolling(window, min_periods=window).sum())


def make_signals(market) -> tuple[dict[str, pd.DataFrame], dict[str, StrategySpec]]:
    prices = market.prices
    daily = prices.pct_change(fill_method=None)
    hsi_return = market.hsi.pct_change(fill_method=None)

    # Rolling market model.  Beta is estimated only with observations available
    # at that close; residual signals are then traded at the following close.
    beta126 = daily.rolling(126).cov(hsi_return).div(hsi_return.rolling(126).var(), axis=0)
    residual = daily.sub(beta126.mul(hsi_return, axis=0))
    residual_momentum = product_return(residual.shift(5), 126)
    idiosyncratic_volatility = residual.rolling(63).std()

    momentum21 = prices.pct_change(21, fill_method=None)
    momentum63 = prices.pct_change(63, fill_method=None)
    momentum12_1 = prices.shift(21) / prices.shift(252) - 1.0
    trend200 = prices / prices.rolling(200).mean() - 1.0

    prior_high63 = prices.shift(1).rolling(63).max()
    breakout63 = prices / prior_high63 - 1.0
    volume_median63 = market.volume.shift(1).rolling(63).median().replace(0.0, np.nan)
    volume_confirmation = np.log1p(market.volume).sub(np.log1p(volume_median63))

    reversal5 = -prices.pct_change(5, fill_method=None)
    reversal20 = -prices.pct_change(20, fill_method=None)
    downside = daily.clip(upper=0.0).pow(2).rolling(63).mean().pow(0.5)
    beta63 = daily.rolling(63).cov(hsi_return).div(hsi_return.rolling(63).var(), axis=0)
    volatility63 = daily.rolling(63).std()
    volume_persistence = market.volume.rolling(20).mean() / market.volume.rolling(126).mean() - 1.0

    hsi_ma50 = market.hsi.rolling(50).mean()
    hsi_ma200 = market.hsi.rolling(200).mean()
    hsi_drawdown63 = market.hsi / market.hsi.rolling(63).max() - 1.0
    hsi_vol20 = hsi_return.rolling(20).std()
    hsi_vol_threshold = hsi_vol20.rolling(252).quantile(0.75)
    context = pd.DataFrame({
        "ma50": hsi_ma50,
        "ma200": hsi_ma200,
        "drawdown63": hsi_drawdown63,
        "vol20": hsi_vol20,
        "vol75": hsi_vol_threshold,
    })

    def residual_exposure(date: pd.Timestamp, hsi: pd.Series, ctx: pd.DataFrame) -> float:
        return 1.0 if hsi.loc[date] >= ctx.loc[date, "ma200"] else 0.5

    def trend_exposure(date: pd.Timestamp, hsi: pd.Series, ctx: pd.DataFrame) -> float:
        above50 = hsi.loc[date] >= ctx.loc[date, "ma50"]
        above200 = hsi.loc[date] >= ctx.loc[date, "ma200"]
        return 1.0 if above50 and above200 else (0.6 if above50 or above200 else 0.25)

    def breakout_exposure(date: pd.Timestamp, hsi: pd.Series, ctx: pd.DataFrame) -> float:
        trend_ok = hsi.loc[date] >= ctx.loc[date, "ma200"]
        volatility_ok = ctx.loc[date, "vol20"] <= ctx.loc[date, "vol75"]
        return 1.0 if trend_ok and volatility_ok else 0.35

    def reversal_exposure(date: pd.Timestamp, hsi: pd.Series, ctx: pd.DataFrame) -> float:
        distress = ctx.loc[date, "drawdown63"] <= -0.05 or hsi.loc[date] < ctx.loc[date, "ma200"]
        return 1.0 if distress else 0.5

    def adaptive_exposure(date: pd.Timestamp, hsi: pd.Series, ctx: pd.DataFrame) -> float:
        return 1.0 if hsi.loc[date] >= ctx.loc[date, "ma200"] else 0.6

    bull_score = (
        0.50 * cross_sectional_zscore(momentum12_1)
        + 0.30 * cross_sectional_zscore(trend200)
        + 0.20 * cross_sectional_zscore(volume_persistence)
    )
    bear_score = (
        0.45 * cross_sectional_zscore(reversal20)
        + 0.35 * cross_sectional_zscore(-beta63)
        + 0.20 * cross_sectional_zscore(-volatility63)
    )
    bull_regime = market.hsi.ge(hsi_ma200)
    adaptive = bull_score.where(bull_regime, bear_score, axis=0)

    factor_signals = {
        "residual_momentum_low_risk": (
            0.65 * cross_sectional_zscore(residual_momentum)
            + 0.35 * cross_sectional_zscore(-idiosyncratic_volatility)
        ),
        "multi_horizon_trend": (
            0.25 * cross_sectional_zscore(momentum21)
            + 0.35 * cross_sectional_zscore(momentum63)
            + 0.40 * cross_sectional_zscore(momentum12_1)
        ),
        "breakout_volume_confirmation": (
            0.45 * cross_sectional_zscore(breakout63)
            + 0.35 * cross_sectional_zscore(momentum63)
            + 0.20 * cross_sectional_zscore(volume_confirmation)
        ),
        "crash_aware_defensive_reversal": (
            0.45 * cross_sectional_zscore(reversal5)
            + 0.30 * cross_sectional_zscore(-downside)
            + 0.25 * cross_sectional_zscore(-beta63)
        ),
        "regime_adaptive_ensemble": adaptive,
    }
    factor_signals = {key: value.where(market.membership) for key, value in factor_signals.items()}

    specs = {
        "residual_momentum_low_risk": StrategySpec(
            "Residual Momentum + Low Risk",
            "Ranks market-model residual momentum and low idiosyncratic volatility, reducing exposure below the HSI 200-day average.",
            "126-day residual momentum excluding the latest 5 days; 63-day idiosyncratic volatility",
            "100% exposure above HSI 200DMA; 50% below",
            residual_exposure,
        ),
        "multi_horizon_trend": StrategySpec(
            "Multi-Horizon Trend Consensus",
            "Combines 1-, 3- and 12-to-1-month momentum so a stock must trend across several horizons.",
            "21-day momentum; 63-day momentum; 12-to-1-month momentum",
            "100% above HSI 50DMA and 200DMA; 60% above either; 25% below both",
            trend_exposure,
        ),
        "breakout_volume_confirmation": StrategySpec(
            "Breakout + Volume Confirmation",
            "Looks for 63-day price breakouts supported by medium-term momentum and unusual volume.",
            "63-day breakout; 63-day momentum; volume surprise versus 63-day median",
            "100% only when HSI is above 200DMA and volatility is below its rolling 75th percentile; otherwise 35%",
            breakout_exposure,
        ),
        "crash_aware_defensive_reversal": StrategySpec(
            "Crash-Aware Defensive Reversal",
            "Buys short-term losers with low downside risk and low market beta, emphasizing market-stress periods.",
            "5-day reversal; 63-day downside deviation; 63-day market beta",
            "100% after a 5% 63-day HSI drawdown or below 200DMA; 50% otherwise",
            reversal_exposure,
        ),
        "regime_adaptive_ensemble": StrategySpec(
            "Regime-Adaptive Factor Ensemble",
            "Uses momentum, trend and volume in bull regimes, then switches to reversal, low beta and low volatility below the HSI 200DMA.",
            "Bull: 12-to-1 momentum, 200-day trend, volume persistence; Bear: 20-day reversal, low beta, low volatility",
            "Bull factor mix and 100% exposure above 200DMA; defensive mix and 60% below",
            adaptive_exposure,
        ),
    }
    return factor_signals, specs, context


def build_targets(
    signal: pd.DataFrame,
    market,
    context: pd.DataFrame,
    spec: StrategySpec,
) -> tuple[dict[int, np.ndarray], list[dict[str, object]]]:
    dates = market.prices.index
    columns = market.prices.columns
    vol63 = market.prices.pct_change(fill_method=None).rolling(63).std()
    targets: dict[int, np.ndarray] = {}
    event_log: list[dict[str, object]] = []
    for signal_date in signal_dates(dates, "monthly"):
        position = dates.get_loc(signal_date)
        if position + 1 >= len(dates):
            continue
        eligible = signal.loc[signal_date].dropna()
        eligible = eligible.loc[market.volume.loc[signal_date, eligible.index].gt(0.0)]
        eligible = eligible.loc[vol63.loc[signal_date, eligible.index].gt(0.0)]
        if len(eligible) < MIN_ELIGIBLE:
            continue
        selected = eligible.nlargest(TOP_N).index
        selected_weights = capped_inverse_vol(vol63.loc[signal_date, selected])
        exposure = spec.exposure(signal_date, market.hsi, context)
        target = np.zeros(len(columns), dtype=float)
        target[columns.get_indexer(selected)] = selected_weights.to_numpy() * exposure
        targets[position + 1] = target
        event_log.append({
            "signal_date": signal_date,
            "execution_date": dates[position + 1],
            "selected": ", ".join(selected),
            "eligible_count": len(eligible),
            "gross_exposure": exposure,
        })
    return targets, event_log


def build_random_targets(
    signal: pd.DataFrame,
    market,
    context: pd.DataFrame,
    spec: StrategySpec,
    runs: int,
    seed: int,
) -> dict[int, np.ndarray]:
    rng = np.random.default_rng(seed)
    dates = market.prices.index
    columns = market.prices.columns
    vol63 = market.prices.pct_change(fill_method=None).rolling(63).std()
    targets: dict[int, np.ndarray] = {}
    for signal_date in signal_dates(dates, "monthly"):
        position = dates.get_loc(signal_date)
        if position + 1 >= len(dates):
            continue
        eligible = signal.loc[signal_date].dropna().index
        eligible = eligible[market.volume.loc[signal_date, eligible].gt(0.0)]
        eligible = eligible[vol63.loc[signal_date, eligible].gt(0.0)]
        if len(eligible) < MIN_ELIGIBLE:
            continue
        exposure = spec.exposure(signal_date, market.hsi, context)
        event = np.zeros((runs, len(columns)), dtype=float)
        for run in range(runs):
            selected = rng.choice(eligible.to_numpy(), size=TOP_N, replace=False)
            weights = capped_inverse_vol(vol63.loc[signal_date, selected]).to_numpy()
            event[run, columns.get_indexer(selected)] = weights * exposure
        targets[position + 1] = event
    return targets


def decision_and_reason(test: dict[str, float], train: dict[str, float]) -> tuple[str, str]:
    keep = (
        test["ic"] > 0.0
        and test["sharpe"] > test["index_sharpe"]
        and test["random_sharpe_percentile"] >= 90.0
        and train["sharpe"] > 0.0
    )
    if keep:
        return (
            "Keep",
            f"Positive holdout IC ({test['ic']:.3f}), Sharpe ({test['sharpe']:.3f}) beat the HSI "
            f"({test['index_sharpe']:.3f}), and it beat {test['random_sharpe_percentile']:.1f}% of matched random portfolios.",
        )
    failures = []
    if test["ic"] <= 0.0:
        failures.append(f"holdout IC was non-positive ({test['ic']:.3f})")
    if test["sharpe"] <= test["index_sharpe"]:
        failures.append(f"Sharpe ({test['sharpe']:.3f}) did not beat the HSI ({test['index_sharpe']:.3f})")
    if test["random_sharpe_percentile"] < 90.0:
        failures.append(f"it beat only {test['random_sharpe_percentile']:.1f}% of matched random portfolios")
    if train["sharpe"] <= 0.0:
        failures.append(f"training Sharpe was non-positive ({train['sharpe']:.3f})")
    sentence = "; ".join(failures)
    return "Drop", sentence[:1].upper() + sentence[1:] + "."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-dir", type=Path, default=MARKET_DIR)
    parser.add_argument("--membership", type=Path, default=MARKET_DIR.parents[1] / "config" / "hsi_membership_intervals.csv")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--random-runs", type=int, default=RANDOM_RUNS)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    market = load_market(args.market_dir, args.membership)
    factor_signals, specs, context = make_signals(market)
    hsi_returns = market.hsi.pct_change(fill_method=None).fillna(0.0)
    monthly_dates = signal_dates(market.prices.index, "monthly")

    result_rows: list[dict[str, object]] = []
    random_rows: list[dict[str, object]] = []
    rebalance_rows: list[dict[str, object]] = []
    daily_returns = {"hsi_price_index": hsi_returns}

    for number, (key, signal) in enumerate(factor_signals.items(), start=1):
        spec = specs[key]
        targets, event_log = build_targets(signal, market, context, spec)
        returns, turnover = simulate(market, targets)
        strategy_returns = returns.iloc[:, 0]
        daily_returns[key] = strategy_returns
        for item in event_log:
            rebalance_rows.append({"strategy": key, **item})

        random_targets = build_random_targets(
            signal, market, context, spec, args.random_runs, seed=20261140 + number
        )
        random_returns, _ = simulate(market, random_targets, scenarios=args.random_runs)
        period_stats: dict[str, dict[str, float]] = {}
        for period, (start, end) in {"train": TRAIN, "test": TEST}.items():
            stats = performance(strategy_returns, start, end)
            index_stats = performance(hsi_returns, start, end)
            ic, observations = mean_ic(signal, market.prices, monthly_dates, 21, start, end)
            random_sharpes = []
            for run in range(args.random_runs):
                random_stats = performance(random_returns.iloc[:, run], start, end)
                random_sharpes.append(random_stats["sharpe"])
                random_rows.append({"strategy": key, "period": period, "random_run": run + 1, **random_stats})
            random_percentile = float(np.mean(stats["sharpe"] > np.asarray(random_sharpes)) * 100.0)
            period_turnover = turnover.loc[turnover["date"].between(start, end), "mean_turnover"]
            period_stats[period] = {
                **stats,
                "ic": ic,
                "ic_observations": observations,
                "average_one_way_turnover": float(period_turnover.mean()),
                "random_sharpe_percentile": random_percentile,
                "index_sharpe": index_stats["sharpe"],
            }

        decision, reason = decision_and_reason(period_stats["test"], period_stats["train"])
        for period, stats in period_stats.items():
            result_rows.append({
                "strategy": key,
                "strategy_name": spec.name,
                "description": spec.description,
                "signals_used": spec.signals_used,
                "regime_rule": spec.regime_rule,
                "period": period,
                **stats,
                "decision": decision,
                "reason": reason,
            })

    results = pd.DataFrame(result_rows)
    results.to_csv(args.output_dir / "advanced_strategy_results.csv", index=False)
    pd.DataFrame(random_rows).to_csv(args.output_dir / "advanced_strategy_random_baselines.csv", index=False)
    pd.DataFrame(daily_returns).loc[TRAIN[0]:TEST[1]].to_csv(
        args.output_dir / "advanced_strategy_daily_returns.csv", index_label="date"
    )
    pd.DataFrame(rebalance_rows).to_csv(args.output_dir / "advanced_strategy_rebalances.csv", index=False)

    requirements = []
    for key, spec in specs.items():
        requirements.append({
            "strategy": key,
            "strategy_name": spec.name,
            "1_multiple_signals": spec.signals_used,
            "2_entry_rule": "At month-end, rank eligible point-in-time HSI members and buy the top 10 at the next close.",
            "3_exit_rule": "At the next monthly rebalance, exit names outside the top 10; securities outside the effective HSI membership interval are ineligible for the new portfolio.",
            "4_position_sizing": "63-day inverse-volatility weights, normalized with a 15% single-name cap.",
            "5_regime_filter": spec.regime_rule,
            "6_cost_model": f"{COST * 10_000:.0f} bps per unit of one-way turnover.",
            "7_timing": "Signals use closing data and execute at the following trading day's close.",
            "8_real_universe": "Effective-dated HSI constituents; at least 30 eligible names and positive volume required.",
        })
    pd.DataFrame(requirements).to_csv(args.output_dir / "advanced_strategy_requirements.csv", index=False)

    test_rows = results.loc[results["period"].eq("test")]
    lines = [
        "# Advanced Hong Kong Strategy Log",
        "",
        "All candidates use point-in-time HSI membership, monthly ranking, next-close execution, capped inverse-volatility sizing and 10 bps one-way turnover costs.",
        "",
        "| Strategy | What it does | Test IC | Test Sharpe | Keep/Drop | Why |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in test_rows.itertuples(index=False):
        lines.append(
            f"| {row.strategy_name} | {row.description} | {row.ic:.3f} | {row.sharpe:.3f} | {row.decision} | {row.reason} |"
        )
    lines.extend([
        "",
        "## Interpretation limits",
        "",
        "- These are institutional-style research ideas, not proprietary models from a specific quant firm.",
        "- Only adjusted daily price and volume are consistently available, so there are no fundamentals, order-book features, borrow costs or short positions.",
        "- The holdout ends on 30 September 2025 because that is the last fully reconstructed point-in-time membership date.",
        "- Five candidates create multiple-testing risk; only the stated untouched holdout and random baselines are used for the decision.",
        "",
    ])
    (args.output_dir / "advanced_strategy_log.md").write_text("\n".join(lines))

    summary = {
        "strategies_tested": len(specs),
        "random_runs_per_strategy": args.random_runs,
        "train": [str(TRAIN[0].date()), str(TRAIN[1].date())],
        "test": [str(TEST[0].date()), str(TEST[1].date())],
        "top_n": TOP_N,
        "decisions": test_rows.set_index("strategy")["decision"].to_dict(),
    }
    (args.output_dir / "advanced_strategy_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
