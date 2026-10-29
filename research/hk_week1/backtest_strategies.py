"""Backtest five Hong Kong momentum signals on the week-1 stock sample.

This is a small, reproducible research backtest for the five-stock pipeline
sample. It is not the production HSI universe loader.

Timing convention
-----------------
Signals are calculated at each week's final market close. The portfolio is
rebalanced at the next available close on which every selected stock has
positive volume. The new holdings begin earning returns after that execution
close. This conservative convention prevents a signal from trading at the
same close used to calculate it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
START = pd.Timestamp("2021-01-04")
END = pd.Timestamp("2024-12-31")
STOCKS = ["0700.HK", "0005.HK", "1299.HK", "0941.HK", "0388.HK"]
BENCHMARK = "^HSI"
TOP_N = 2
COST_RATE = 0.001  # 10 bps for each unit of one-way turnover.
TRADING_DAYS = 252


STRATEGY_LABELS = {
    "mom_5d": "5-day momentum",
    "mom_20d": "20-day momentum",
    "mom_60d": "60-day momentum",
    "ma_10_30": "10/30-day moving-average momentum",
    "risk_adj_mom_20d": "20-day risk-adjusted momentum",
}

STRATEGY_DESCRIPTIONS = {
    "mom_5d": "Ranks stocks by their past 5-day return and buys the top two weekly.",
    "mom_20d": "Ranks stocks by their past 20-day return and buys the top two weekly.",
    "mom_60d": "Ranks stocks by their past 60-day return and buys the top two weekly.",
    "ma_10_30": "Ranks stocks by how far their 10-day average is above their 30-day average.",
    "risk_adj_mom_20d": "Ranks 20-day return after dividing it by recent 20-day volatility.",
}

STRATEGY_DECISIONS = {
    "mom_5d": "Drop",
    "mom_20d": "Keep",
    "mom_60d": "Drop",
    "ma_10_30": "Keep",
    "risk_adj_mom_20d": "Drop",
}

STRATEGY_REASONS = {
    "mom_5d": (
        "Negative IC and Sharpe suggest short-term noise and reversal. Frequent "
        "changes also made this the highest-turnover strategy."
    ),
    "mom_20d": (
        "IC and Sharpe were slightly positive. Keep it as a simple baseline, but "
        "the edge is weak and needs a full-universe retest."
    ),
    "mom_60d": (
        "Both IC and Sharpe were negative, so the slower signal did not predict "
        "the next week's relative winners."
    ),
    "ma_10_30": (
        "It had the best Sharpe and was the only strategy with a positive cumulative "
        "return. Its slightly negative IC means it still needs a larger retest."
    ),
    "risk_adj_mom_20d": (
        "Volatility scaling did not improve stock ranking. IC and Sharpe stayed "
        "negative."
    ),
}


@dataclass(frozen=True)
class Rebalance:
    signal_date: pd.Timestamp
    execution_date: pd.Timestamp
    selected: tuple[str, ...]
    target: pd.Series


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load adjusted stock prices, stock volume, and the HSI close."""
    adjusted = {}
    volume = {}

    for symbol in STOCKS:
        path = DATA_DIR / f"{symbol}.csv"
        frame = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        frame = frame.loc[START:END].sort_index()
        adjusted[symbol] = frame["Adj Close"].astype(float)
        volume[symbol] = frame["Volume"].astype(float)

    benchmark_frame = pd.read_csv(
        DATA_DIR / f"{BENCHMARK}.csv", parse_dates=["Date"], index_col="Date"
    ).loc[START:END].sort_index()

    prices = pd.DataFrame(adjusted)
    volumes = pd.DataFrame(volume).reindex(prices.index)
    benchmark_close = benchmark_frame["Close"].astype(float).reindex(prices.index)

    if prices.empty or benchmark_close.isna().any():
        raise ValueError("The requested 2021-2024 price window is incomplete.")
    if prices.isna().any().any() or volumes.isna().any().any():
        raise ValueError("Stock adjusted-price or volume data contain missing values.")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("Stock dates must be sorted and unique.")
    if prices.index.max() > END:
        raise ValueError("The holdout boundary was breached.")

    return prices, volumes, benchmark_close


def calculate_signals(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Calculate the five requested cross-sectional ranking signals."""
    daily_return = prices.pct_change(fill_method=None)
    volatility_20d = daily_return.rolling(20).std()

    return {
        "mom_5d": prices.pct_change(5, fill_method=None),
        "mom_20d": prices.pct_change(20, fill_method=None),
        "mom_60d": prices.pct_change(60, fill_method=None),
        "ma_10_30": (
            prices.rolling(10).mean() / prices.rolling(30).mean() - 1
        ),
        "risk_adj_mom_20d": (
            prices.pct_change(20, fill_method=None) / volatility_20d
        ),
    }


def weekly_signal_dates(index: pd.DatetimeIndex, first_ready: pd.Timestamp) -> list[pd.Timestamp]:
    """Return the last available market date in each Friday-ending week."""
    dates = pd.Series(index=index, data=index)
    final_dates = dates.groupby(index.to_period("W-FRI")).last().tolist()
    return [date for date in final_dates if date >= first_ready and date < index[-1]]


def build_rebalances(
    signal: pd.DataFrame,
    volumes: pd.DataFrame,
    signal_dates: list[pd.Timestamp],
) -> dict[pd.Timestamp, Rebalance]:
    """Map each execution date to its lagged target portfolio."""
    index = signal.index
    events: dict[pd.Timestamp, Rebalance] = {}

    for signal_date in signal_dates:
        row = signal.loc[signal_date].dropna()
        if len(row) < TOP_N:
            continue

        selected = tuple(row.sort_values(ascending=False).index[:TOP_N])
        signal_position = index.get_loc(signal_date)
        execution_position = signal_position + 1

        while execution_position < len(index):
            candidate = index[execution_position]
            if (volumes.loc[candidate, list(selected)] > 0).all():
                break
            execution_position += 1

        if execution_position >= len(index):
            continue

        execution_date = index[execution_position]
        target = pd.Series(0.0, index=STOCKS)
        target.loc[list(selected)] = 1.0 / TOP_N
        events[execution_date] = Rebalance(
            signal_date=signal_date,
            execution_date=execution_date,
            selected=selected,
            target=target,
        )

    return events


def simulate(
    prices: pd.DataFrame,
    events: dict[pd.Timestamp, Rebalance],
    evaluation_start: pd.Timestamp,
) -> tuple[pd.Series, list[dict[str, object]]]:
    """Simulate a drifting-weight portfolio with close-time rebalances."""
    asset_returns = prices.pct_change(fill_method=None)
    weights = pd.Series(0.0, index=STOCKS)
    daily_returns: list[float] = []
    daily_dates: list[pd.Timestamp] = []
    rebalance_log: list[dict[str, object]] = []

    for date in prices.loc[evaluation_start:].index:
        if date == evaluation_start:
            gross_return = 0.0
            drifted = weights.copy()
        else:
            returns_today = asset_returns.loc[date].fillna(0.0)
            gross_return = float((weights * returns_today).sum())
            denominator = 1.0 + gross_return
            if denominator <= 0:
                raise ValueError(f"Portfolio value became non-positive on {date.date()}.")
            drifted = weights * (1.0 + returns_today) / denominator

        cost_fraction = 0.0
        if date in events:
            event = events[date]
            turnover = float((event.target - drifted).abs().sum())
            cost_fraction = COST_RATE * turnover
            weights = event.target.copy()
            rebalance_log.append(
                {
                    "signal_date": event.signal_date,
                    "execution_date": event.execution_date,
                    "selected": ", ".join(event.selected),
                    "one_way_turnover": turnover,
                    "transaction_cost": cost_fraction,
                }
            )
        else:
            weights = drifted

        net_return = (1.0 + gross_return) * (1.0 - cost_fraction) - 1.0
        daily_dates.append(date)
        daily_returns.append(net_return)

        if weights.sum() > 0 and not np.isclose(weights.sum(), 1.0, atol=1e-10):
            raise AssertionError(f"Weights do not sum to one on {date.date()}.")

    return pd.Series(daily_returns, index=daily_dates, name="return"), rebalance_log


def mean_rank_information_coefficient(
    signal: pd.DataFrame,
    prices: pd.DataFrame,
    events: dict[pd.Timestamp, Rebalance],
) -> tuple[float, int]:
    """Average weekly Spearman rank IC over the tradable holding periods."""
    execution_dates = sorted(events)
    weekly_ics: list[float] = []

    for execution_date, next_execution_date in zip(
        execution_dates, execution_dates[1:]
    ):
        event = events[execution_date]
        signal_rank = signal.loc[event.signal_date].rank()
        forward_return_rank = (
            prices.loc[next_execution_date] / prices.loc[execution_date] - 1.0
        ).rank()
        weekly_ics.append(float(signal_rank.corr(forward_return_rank)))

    valid_ics = pd.Series(weekly_ics, dtype=float).dropna()
    if valid_ics.empty:
        raise ValueError("Cannot calculate information coefficient without valid weeks.")
    return float(valid_ics.mean()), int(len(valid_ics))


def metrics(returns: pd.Series) -> dict[str, float | int | str]:
    """Calculate the requested performance statistics."""
    returns = returns.dropna()
    if returns.empty:
        raise ValueError("Cannot calculate metrics from an empty return series.")

    wealth = (1.0 + returns).cumprod()
    cumulative_return = float(wealth.iloc[-1] - 1.0)
    years = len(returns) / TRADING_DAYS
    annualized_return = float(wealth.iloc[-1] ** (1.0 / years) - 1.0)
    annualized_volatility = float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))
    sharpe = (
        float(returns.mean() / returns.std(ddof=1) * np.sqrt(TRADING_DAYS))
        if returns.std(ddof=1) > 0
        else np.nan
    )
    max_drawdown = float((wealth / wealth.cummax() - 1.0).min())

    return {
        "Start date": str(returns.index.min().date()),
        "End date": str(returns.index.max().date()),
        "Observations": int(len(returns)),
        "Cumulative return": cumulative_return,
        "Annualized return": annualized_return,
        "Annualized volatility": annualized_volatility,
        "Sharpe ratio": sharpe,
        "Maximum drawdown": max_drawdown,
    }


def write_strategy_log(
    results: pd.DataFrame,
    evaluation_start: pd.Timestamp,
) -> None:
    """Write the concise meeting-ready strategy decision log."""
    header = (
        "| Strategy and what it does | Mean rank IC | Sharpe | Keep or drop | Why |\n"
        "|---|---:|---:|---|---|\n"
    )
    rows = []
    for _, row in results.iterrows():
        rows.append(
            "| **{strategy}.** {description} | {ic:+.3f} | {sharpe:+.2f} | "
            "**{decision}** | {reason} |".format(
                strategy=row["Strategy"],
                description=row["What it does"],
                ic=row["Mean rank IC"],
                sharpe=row["Sharpe ratio"],
                decision=row["Keep or drop"],
                reason=row["Decision reason"],
            )
        )

    content = f"""# Hong Kong momentum strategy decisions

Evaluation period: {evaluation_start.date()} to {END.date()}.

{header}{chr(10).join(rows)}

## IC definition

Mean weekly Spearman rank correlation between each signal and all five stocks' returns
over the following tradable holding week ({int(results['IC observations'].iloc[0])}
observations per strategy). Positive is better. Values close to zero indicate little
consistent ranking power. The keep decisions are candidates for a full point-in-time
HSI retest, not final proof that the strategies work.
"""
    (ROOT / "strategy_log.md").write_text(content, encoding="utf-8")


def main() -> None:
    prices, volumes, benchmark_close = load_data()
    signals = calculate_signals(prices)

    ready_mask = pd.DataFrame(
        {name: signal.notna().all(axis=1) for name, signal in signals.items()}
    ).all(axis=1)
    if not ready_mask.any():
        raise ValueError("No date has all five signals available.")
    first_ready = ready_mask[ready_mask].index[0]
    signal_dates = weekly_signal_dates(prices.index, first_ready)

    all_events = {
        name: build_rebalances(signal, volumes, signal_dates)
        for name, signal in signals.items()
    }
    if any(not events for events in all_events.values()):
        raise ValueError("At least one strategy produced no rebalance events.")

    first_execution_dates = {min(events) for events in all_events.values()}
    if len(first_execution_dates) != 1:
        raise ValueError(
            "Strategies do not share a common first execution date; "
            "a common-period rule is required."
        )
    evaluation_start = first_execution_dates.pop()

    benchmark_returns = benchmark_close.loc[evaluation_start:].pct_change(fill_method=None)
    benchmark_returns.iloc[0] = 0.0
    benchmark_metrics = metrics(benchmark_returns)

    result_rows = []
    annual_return_rows: dict[str, pd.Series] = {}

    for name, events in all_events.items():
        strategy_returns, rebalance_log = simulate(
            prices, events, evaluation_start=evaluation_start
        )
        strategy_metrics = metrics(strategy_returns)
        total_turnover = float(
            sum(float(row["one_way_turnover"]) for row in rebalance_log)
        )
        mean_ic, ic_observations = mean_rank_information_coefficient(
            signals[name], prices, events
        )

        result_rows.append(
            {
                "Strategy key": name,
                "Strategy": STRATEGY_LABELS[name],
                "What it does": STRATEGY_DESCRIPTIONS[name],
                "Mean rank IC": mean_ic,
                "IC observations": ic_observations,
                "Keep or drop": STRATEGY_DECISIONS[name],
                "Decision reason": STRATEGY_REASONS[name],
                **strategy_metrics,
                "Excess annualized return vs HSI": (
                    strategy_metrics["Annualized return"]
                    - benchmark_metrics["Annualized return"]
                ),
                "Rebalances": len(rebalance_log),
                "Total one-way turnover": total_turnover,
                "Estimated transaction costs": total_turnover * COST_RATE,
            }
        )
        annual_return_rows[STRATEGY_LABELS[name]] = (
            (1.0 + strategy_returns).groupby(strategy_returns.index.year).prod() - 1.0
        )

    annual_return_rows["Hang Seng Index"] = (
        (1.0 + benchmark_returns).groupby(benchmark_returns.index.year).prod() - 1.0
    )
    annual_returns = pd.DataFrame(annual_return_rows).T
    annual_returns.columns = annual_returns.columns.astype(str)

    results = pd.DataFrame(result_rows)
    results.attrs["benchmark_metrics"] = benchmark_metrics
    results.to_csv(ROOT / "strategy_results.csv", index=False)
    report = {
        "evaluation_start": str(evaluation_start.date()),
        "evaluation_end": str(END.date()),
        "benchmark_metrics": benchmark_metrics,
        "results": results.to_dict(orient="records"),
        "annual_returns": {
            strategy: {year: float(value) for year, value in row.items()}
            for strategy, row in annual_returns.iterrows()
        },
        "assumptions": {
            "universe": STOCKS,
            "benchmark": BENCHMARK,
            "top_n": TOP_N,
            "cost_rate": COST_RATE,
            "risk_free_rate": 0.0,
            "rebalance_frequency": "weekly",
            "execution": "next close with positive volume for all selected stocks",
            "board_lot_rounding": False,
        },
    }
    (ROOT / "strategy_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_strategy_log(results, evaluation_start)

    print("\nFIVE-STRATEGY RESULTS")
    display_columns = [
        "Strategy",
        "Mean rank IC",
        "Sharpe ratio",
        "Keep or drop",
    ]
    print(results[display_columns].to_string(index=False))
    print("\nHSI BENCHMARK")
    print(pd.Series(benchmark_metrics).to_string())
    print(f"\nEvaluation starts at the first common execution close: {evaluation_start.date()}")


if __name__ == "__main__":
    main()
