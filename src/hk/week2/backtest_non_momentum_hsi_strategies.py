#!/usr/bin/env python3
"""Backtest five non-momentum strategies on point-in-time HSI members.

The candidates deliberately avoid positive trend and breakout ranking.  They
test defensive risk, contrarian mean reversion, liquidity quality, shareholder
yield, and volatility compression using the local daily OHLCV/dividend archive.
Signals are observed at month-end and traded at the next close with 10 bps per
unit of one-way turnover.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest_advanced_hsi_strategies import (
    MIN_ELIGIBLE,
    RANDOM_RUNS,
    TOP_N,
    StrategySpec,
    build_random_targets,
    build_targets,
    cross_sectional_zscore,
    decision_and_reason,
)
from .backtest_hsi_strategies import (
    COST,
    MARKET_DIR,
    OUTPUT_DIR,
    TEST,
    TRAIN,
    load_market,
    mean_ic,
    performance,
    signal_dates,
    simulate,
)


@dataclass
class AuxiliaryMarket:
    adjusted_open: pd.DataFrame
    adjusted_high: pd.DataFrame
    adjusted_low: pd.DataFrame
    raw_close: pd.DataFrame
    dividends: pd.DataFrame


def load_auxiliary_market(market, market_dir: Path) -> AuxiliaryMarket:
    """Load adjusted intraday ranges and dividends for the base market panel."""
    coverage = pd.read_csv(market_dir / "coverage.csv")
    dates = market.prices.index
    columns = market.prices.columns
    opens: dict[str, pd.Series] = {}
    highs: dict[str, pd.Series] = {}
    lows: dict[str, pd.Series] = {}
    raw_closes: dict[str, pd.Series] = {}
    dividends: dict[str, pd.Series] = {}

    for ticker in columns:
        row = coverage.loc[
            coverage["ticker"].eq(ticker) & coverage["status"].eq("downloaded")
        ]
        if row.empty:
            continue
        frame = (
            pd.read_csv(market_dir / str(row.iloc[0]["file"]), parse_dates=["Date"])
            .drop_duplicates("Date")
            .set_index("Date")
            .sort_index()
        )
        raw_close = pd.to_numeric(frame["Close"], errors="coerce")
        adjusted_close = pd.to_numeric(frame["Adj Close"], errors="coerce")
        adjustment = adjusted_close.div(raw_close.replace(0.0, np.nan))
        opens[ticker] = pd.to_numeric(frame["Open"], errors="coerce").mul(adjustment)
        highs[ticker] = pd.to_numeric(frame["High"], errors="coerce").mul(adjustment)
        lows[ticker] = pd.to_numeric(frame["Low"], errors="coerce").mul(adjustment)
        raw_closes[ticker] = raw_close
        dividends[ticker] = pd.to_numeric(frame["Dividends"], errors="coerce").fillna(0.0)

    def aligned(values: dict[str, pd.Series], *, fill_zero: bool = False) -> pd.DataFrame:
        result = pd.DataFrame(values).reindex(index=dates, columns=columns)
        if fill_zero:
            result = result.fillna(0.0).where(market.membership, 0.0)
        else:
            result = result.ffill().where(market.membership)
        return result

    return AuxiliaryMarket(
        adjusted_open=aligned(opens),
        adjusted_high=aligned(highs),
        adjusted_low=aligned(lows),
        raw_close=aligned(raw_closes),
        dividends=aligned(dividends, fill_zero=True),
    )


def make_non_momentum_signals(market, auxiliary: AuxiliaryMarket):
    prices = market.prices
    daily = prices.pct_change(fill_method=None)
    hsi_return = market.hsi.pct_change(fill_method=None)

    beta126 = daily.rolling(126).cov(hsi_return).div(
        hsi_return.rolling(126).var(), axis=0
    )
    beta63 = daily.rolling(63).cov(hsi_return).div(
        hsi_return.rolling(63).var(), axis=0
    )
    residual = daily.sub(beta126.mul(hsi_return, axis=0))
    idiosyncratic_volatility = residual.rolling(63).std()
    downside_deviation = daily.clip(upper=0.0).pow(2).rolling(63).mean().pow(0.5)

    # Contrarian rather than trend-following: rank recent losers and oversold
    # names more highly.  All inputs are known by the signal close.
    reversal5 = -prices.pct_change(5, fill_method=None)
    deviation20 = -(prices / prices.rolling(20).mean() - 1.0)
    change = prices.diff()
    average_gain = change.clip(lower=0.0).rolling(14).mean()
    average_loss = -change.clip(upper=0.0).rolling(14).mean()
    rsi14 = 100.0 - 100.0 / (1.0 + average_gain / average_loss.replace(0.0, np.nan))
    oversold_rsi = -rsi14

    dollar_volume = auxiliary.raw_close.mul(market.volume).replace(0.0, np.nan)
    median_dollar_volume = dollar_volume.rolling(63).median()
    amihud = daily.abs().div(dollar_volume).rolling(63).mean()
    liquidity_efficiency = -np.log(amihud.clip(lower=1e-18))
    volume_stability = -market.volume.rolling(63).std().div(
        market.volume.rolling(63).mean().replace(0.0, np.nan)
    )

    trailing_dividends = auxiliary.dividends.rolling(252).sum()
    dividend_yield = trailing_dividends.div(auxiliary.raw_close.replace(0.0, np.nan))
    dividend_frequency = auxiliary.dividends.gt(0.0).rolling(504).sum()

    high_low_log = np.log(
        auxiliary.adjusted_high.div(auxiliary.adjusted_low.replace(0.0, np.nan))
    )
    parkinson_volatility = (
        high_low_log.pow(2).rolling(63).mean().div(4.0 * np.log(2.0)).pow(0.5)
    )
    close_volatility20 = daily.rolling(20).std()
    volatility_of_volatility = close_volatility20.rolling(63).std()
    overnight_gap = auxiliary.adjusted_open.div(prices.shift(1)) - 1.0
    gap_risk = overnight_gap.rolling(63).std()

    hsi_ma200 = market.hsi.rolling(200).mean()
    hsi_vol20 = hsi_return.rolling(20).std()
    hsi_vol50 = hsi_vol20.rolling(252).median()
    hsi_vol75 = hsi_vol20.rolling(252).quantile(0.75)
    hsi_drawdown20 = market.hsi / market.hsi.rolling(20).max() - 1.0
    context = pd.DataFrame(
        {
            "ma200": hsi_ma200,
            "vol20": hsi_vol20,
            "vol50": hsi_vol50,
            "vol75": hsi_vol75,
            "drawdown20": hsi_drawdown20,
        }
    )

    def low_risk_exposure(date, hsi, ctx) -> float:
        defensive_regime = (
            hsi.loc[date] < ctx.loc[date, "ma200"]
            or ctx.loc[date, "vol20"] > ctx.loc[date, "vol75"]
        )
        return 1.0 if defensive_regime else 0.75

    def mean_reversion_exposure(date, hsi, ctx) -> float:
        if ctx.loc[date, "vol20"] > ctx.loc[date, "vol75"]:
            return 0.25
        return 1.0 if ctx.loc[date, "drawdown20"] <= -0.02 else 0.5

    def liquidity_exposure(date, hsi, ctx) -> float:
        return 1.0 if ctx.loc[date, "vol20"] <= ctx.loc[date, "vol75"] else 0.5

    def dividend_exposure(date, hsi, ctx) -> float:
        return 1.0 if hsi.loc[date] < ctx.loc[date, "ma200"] else 0.75

    def compression_exposure(date, hsi, ctx) -> float:
        return 1.0 if ctx.loc[date, "vol20"] > ctx.loc[date, "vol50"] else 0.75

    factor_signals = {
        "defensive_low_risk": (
            0.35 * cross_sectional_zscore(-beta126)
            + 0.35 * cross_sectional_zscore(-downside_deviation)
            + 0.30 * cross_sectional_zscore(-idiosyncratic_volatility)
        ),
        "oversold_mean_reversion": (
            0.40 * cross_sectional_zscore(reversal5)
            + 0.35 * cross_sectional_zscore(deviation20)
            + 0.25 * cross_sectional_zscore(oversold_rsi)
        ),
        "liquidity_quality": (
            0.40 * cross_sectional_zscore(np.log(median_dollar_volume))
            + 0.35 * cross_sectional_zscore(liquidity_efficiency)
            + 0.25 * cross_sectional_zscore(volume_stability)
        ),
        "shareholder_yield_quality": (
            0.50 * cross_sectional_zscore(dividend_yield)
            + 0.20 * cross_sectional_zscore(dividend_frequency)
            + 0.30 * cross_sectional_zscore(-downside_deviation)
        ),
        "volatility_compression": (
            0.40 * cross_sectional_zscore(-parkinson_volatility)
            + 0.30 * cross_sectional_zscore(-volatility_of_volatility)
            + 0.30 * cross_sectional_zscore(-gap_risk)
        ),
    }
    factor_signals = {
        key: value.where(market.membership) for key, value in factor_signals.items()
    }

    specs = {
        "defensive_low_risk": StrategySpec(
            "Defensive Low Risk",
            "Selects stocks with low market beta, low downside deviation and low idiosyncratic volatility.",
            "126-day market beta; 63-day downside deviation; 63-day idiosyncratic volatility",
            "100% exposure below the HSI 200DMA or in the top volatility quartile; 75% otherwise",
            low_risk_exposure,
        ),
        "oversold_mean_reversion": StrategySpec(
            "Oversold Mean Reversion",
            "Buys recent losers that are far below their 20-day average and have a low 14-day RSI.",
            "5-day reversal; distance below 20-day average; 14-day RSI",
            "100% after a 2% 20-day HSI drawdown, 50% normally and 25% in extreme volatility",
            mean_reversion_exposure,
        ),
        "liquidity_quality": StrategySpec(
            "Liquidity Quality",
            "Favors high and stable traded value with low Amihud price impact.",
            "63-day median dollar volume; 63-day Amihud illiquidity; 63-day volume stability",
            "100% below the rolling 75th-percentile HSI volatility threshold; 50% above",
            liquidity_exposure,
        ),
        "shareholder_yield_quality": StrategySpec(
            "Shareholder Yield Quality",
            "Combines trailing dividend yield, payment frequency and low downside risk.",
            "252-day dividend yield; 504-day dividend-payment frequency; 63-day downside deviation",
            "100% exposure below the HSI 200DMA; 75% above",
            dividend_exposure,
        ),
        "volatility_compression": StrategySpec(
            "Volatility Compression",
            "Selects narrow high-low ranges, stable realized volatility and small overnight gaps.",
            "63-day Parkinson range volatility; volatility-of-volatility; 63-day overnight-gap risk",
            "100% when HSI volatility is above its rolling median; 75% otherwise",
            compression_exposure,
        ),
    }
    return factor_signals, specs, context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-dir", type=Path, default=MARKET_DIR)
    parser.add_argument(
        "--membership",
        type=Path,
        default=MARKET_DIR.parents[1] / "config" / "hsi_membership_intervals.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--random-runs", type=int, default=RANDOM_RUNS)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    market = load_market(args.market_dir, args.membership)
    auxiliary = load_auxiliary_market(market, args.market_dir)
    factor_signals, specs, context = make_non_momentum_signals(market, auxiliary)
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
            signal,
            market,
            context,
            spec,
            args.random_runs,
            seed=20261111 + number,
        )
        random_returns, _ = simulate(
            market, random_targets, scenarios=args.random_runs
        )
        period_stats: dict[str, dict[str, float]] = {}
        for period, (start, end) in {"train": TRAIN, "test": TEST}.items():
            stats = performance(strategy_returns, start, end)
            index_stats = performance(hsi_returns, start, end)
            ic, observations = mean_ic(
                signal, market.prices, monthly_dates, 21, start, end
            )
            random_sharpes = []
            for run in range(args.random_runs):
                random_stats = performance(random_returns.iloc[:, run], start, end)
                random_sharpes.append(random_stats["sharpe"])
                random_rows.append(
                    {
                        "strategy": key,
                        "period": period,
                        "random_run": run + 1,
                        **random_stats,
                    }
                )
            random_percentile = float(
                np.mean(stats["sharpe"] > np.asarray(random_sharpes)) * 100.0
            )
            period_turnover = turnover.loc[
                turnover["date"].between(start, end), "mean_turnover"
            ]
            period_stats[period] = {
                **stats,
                "ic": ic,
                "ic_observations": observations,
                "average_one_way_turnover": float(period_turnover.mean()),
                "random_sharpe_percentile": random_percentile,
                "index_sharpe": index_stats["sharpe"],
            }

        decision, reason = decision_and_reason(
            period_stats["test"], period_stats["train"]
        )
        for period, stats in period_stats.items():
            result_rows.append(
                {
                    "strategy": key,
                    "strategy_name": spec.name,
                    "description": spec.description,
                    "signals_used": spec.signals_used,
                    "regime_rule": spec.regime_rule,
                    "period": period,
                    **stats,
                    "decision": decision,
                    "reason": reason,
                }
            )

    results = pd.DataFrame(result_rows)
    results.to_csv(args.output_dir / "non_momentum_strategy_results.csv", index=False)
    pd.DataFrame(random_rows).to_csv(
        args.output_dir / "non_momentum_strategy_random_baselines.csv", index=False
    )
    pd.DataFrame(daily_returns).loc[TRAIN[0] : TEST[1]].to_csv(
        args.output_dir / "non_momentum_strategy_daily_returns.csv",
        index_label="date",
    )
    pd.DataFrame(rebalance_rows).to_csv(
        args.output_dir / "non_momentum_strategy_rebalances.csv", index=False
    )

    requirements = []
    for key, spec in specs.items():
        requirements.append(
            {
                "strategy": key,
                "strategy_name": spec.name,
                "1_multiple_signals": spec.signals_used,
                "2_entry_rule": "At month-end, rank eligible point-in-time HSI members and buy the top 10 at the next close.",
                "3_exit_rule": "At the next monthly rebalance, exit names outside the top 10; securities outside the effective HSI membership interval are ineligible.",
                "4_position_sizing": "63-day inverse-volatility weights, normalized with a 15% single-name cap.",
                "5_regime_filter": spec.regime_rule,
                "6_cost_model": f"{COST * 10_000:.0f} bps per unit of one-way turnover.",
                "7_timing": "Signals use closing data and execute at the following trading day's close.",
                "8_real_universe": f"Effective-dated HSI constituents; at least {MIN_ELIGIBLE} eligible names and positive volume required.",
            }
        )
    pd.DataFrame(requirements).to_csv(
        args.output_dir / "non_momentum_strategy_requirements.csv", index=False
    )

    test_rows = results.loc[results["period"].eq("test")]
    lines = [
        "# Non-Momentum Hong Kong Strategy Log",
        "",
        "The five candidates avoid positive trend and breakout ranking. All use point-in-time HSI membership, monthly ranking, next-close execution, capped inverse-volatility sizing and 10 bps one-way turnover costs.",
        "",
        "| Strategy | What it does | Test IC | Test Sharpe | Keep/Drop | Why |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in test_rows.itertuples(index=False):
        lines.append(
            f"| {row.strategy_name} | {row.description} | {row.ic:.3f} | "
            f"{row.sharpe:.3f} | {row.decision} | {row.reason} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- The inputs are daily OHLCV and dividends. There are no accounting fundamentals, order-book features, borrow costs or short positions.",
            "- Oversold Mean Reversion uses recent returns contrarily; it is not a positive momentum or trend strategy.",
            "- Dividend data is sourced from the same free Yahoo archive and is not independently audited against company filings.",
            "- The holdout ends on 30 September 2025 because that is the last fully reconstructed point-in-time membership date.",
            "- Keep means retain for further research, not approve for live trading.",
            "",
        ]
    )
    (args.output_dir / "non_momentum_strategy_log.md").write_text(
        "\n".join(lines)
    )

    summary = {
        "strategies_tested": len(specs),
        "random_runs_per_strategy": args.random_runs,
        "train": [str(TRAIN[0].date()), str(TRAIN[1].date())],
        "test": [str(TEST[0].date()), str(TEST[1].date())],
        "top_n": TOP_N,
        "decisions": test_rows.set_index("strategy")["decision"].to_dict(),
    }
    (args.output_dir / "non_momentum_strategy_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
