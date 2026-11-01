"""Configurable India portfolios: original Vibe factors plus Jack-style accounting.

Developer-approved provisional baseline; no PM approval of these portfolio
parameters is implied. Nothing runs on import and this module writes no files.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from src.india_data import (
    BACKTEST_END, NSE_STOCKS, IndiaPanel, _validate_dates, validate_close,
)
from src.india_vibe_bridge import compute_rank_ic, evaluate_strev


MOVE_FLAG_THRESHOLD = 0.20  # Original India data-quality assignment.
TRADE_WEIGHT_TOLERANCE = 1e-12  # Numerical noise, not an economic trade filter.


@dataclass(frozen=True)
class PortfolioConfig:
    """Portfolio settings; dates bound evaluation, not input warm-up.

    top_n controls long-only equal target weights; cost_bps applies per unit
    absolute traded NAV. rebalance_frequency uses a pandas weekly period rule.
    annualization and annual_risk_free specify Sharpe only (cash earns zero).
    min_signal_names is the minimum finite scores required to create a target.
    """

    start: str = "2021-01-04"
    end: str = "2024-12-31"
    top_n: int = 2
    rebalance_frequency: str = "W-FRI"
    cost_bps: float = 10.0
    annualization: int = 252
    annual_risk_free: float = 0.0
    min_signal_names: int = 8

    def __post_init__(self) -> None:
        dates = [pd.Timestamp(self.start), pd.Timestamp(self.end)]
        for date in dates:
            _validate_dates(pd.DatetimeIndex([date]))
        if dates[0] > dates[1] or dates[-1] > BACKTEST_END:
            raise ValueError("Evaluation must end by December 31, 2024")
        if (not isinstance(self.top_n, int) or not isinstance(self.min_signal_names, int)
                or not 1 <= self.top_n <= self.min_signal_names <= len(NSE_STOCKS)):
            raise ValueError("Require 1 <= top_n <= min_signal_names <= 8")
        if self.rebalance_frequency not in {
            "W-MON", "W-TUE", "W-WED", "W-THU", "W-FRI", "W-SAT", "W-SUN",
        }:
            raise ValueError("Use a weekly period frequency such as W-FRI")
        if (not np.isfinite(self.cost_bps) or not 0 <= self.cost_bps < 5000
                or not isinstance(self.annualization, int) or self.annualization < 2
                or not np.isfinite(self.annual_risk_free) or self.annual_risk_free <= -1):
            raise ValueError("Invalid cost or Sharpe configuration")


@dataclass(frozen=True)
class ResearchView:
    """Independent panel copy, auditable verified exclusions, unresolved flags.

    ledger lists evidence-backed operations, not inferred price corrections.
    flags is long-form observed quality evidence, with no automatic exclusions.
    """

    panel: IndiaPanel
    ledger: list[dict]
    flags: pd.DataFrame


def prepare_research_view(panel: IndiaPanel) -> ResearchView:
    """Return a copy applying only independently verified validity exclusions.

    Parameters: panel is an adapted snapshot. Returns a ResearchView excluding
    July 28, 2005 (NSE closure), and masking TCS before its August 25, 2004
    listing. Raw snapshots are untouched. No weekday filter, automatic repair,
    full-window mask, or unexplained-spike exclusion is applied.
    """
    validate_close(panel.close)
    close, volume = panel.close.copy(), panel.volume.copy()
    benchmark = panel.benchmark.copy()
    ledger = []
    holiday = pd.Timestamp("2005-07-28")
    if holiday in close.index:
        close = close.drop(index=holiday)
        volume = volume.drop(index=holiday)
        benchmark = benchmark.drop(index=holiday)
        ledger.append({
            "operation": "exclude_non_session", "symbol": "ALL",
            "date": str(holiday.date()), "rows_per_series": 1,
            "evidence": "https://nsearchives.nseindia.com/content/press/27072005.pdf",
            "reason": "NSE explicitly closed on this date",
        })
    prelisting = close.index < pd.Timestamp("2004-08-25")
    if prelisting.any():
        old = close.loc[prelisting, "TCS.NS"]
        ledger.append({
            "operation": "mask_prelisting", "symbol": "TCS.NS",
            "start": str(old.index.min().date()), "end": str(old.index.max().date()),
            "rows": int(prelisting.sum()), "nonmissing_closes": int(old.notna().sum()),
            "evidence": "https://www.nseindia.com/static/ipo-past-issues/prior-to-2016",
            "reason": "TCS first listed August 25, 2004",
        })
        close.loc[prelisting, "TCS.NS"] = np.nan
        volume.loc[prelisting, "TCS.NS"] = np.nan
    flags = []
    for symbol in NSE_STOCKS:
        prices = close[symbol]
        checks = {
            "missing_close": prices.isna(),
            "zero_volume": volume[symbol].eq(0),
            "missing_volume": volume[symbol].isna(),
            "repeated_close": prices.eq(prices.shift()),
            "move_over_20pct": (
                prices.pct_change(fill_method=None).abs() > MOVE_FLAG_THRESHOLD
            ),
        }
        for kind, mask in checks.items():
            flags.extend({"date": date, "symbol": symbol, "flag": kind}
                         for date in close.index[mask])
    return ResearchView(
        IndiaPanel(close, volume, benchmark, panel.close_basis), ledger,
        pd.DataFrame(flags, columns=["date", "symbol", "flag"]),
    )


@dataclass(frozen=True)
class PortfolioResult:
    """Accounting and labelled IC inputs, without a final strategy designation.

    weights are end-of-close holdings; costs are fractions of pretrade NAV.
    ic_scores/ic_returns align each completed execution interval to its signal.
    No final interval is invented after the last execution or historical cutoff.
    """

    net_returns: pd.Series
    gross_returns: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    executions: pd.DataFrame
    order_log: list[dict]
    ic_scores: pd.DataFrame
    ic_returns: pd.DataFrame
    sharpe: float
    configuration: dict
    benchmark_returns: pd.Series


def annualized_sharpe(
    net_returns: pd.Series, *, annualization: int = 252,
    annual_risk_free: float = 0.0,
) -> float:
    """Return annualized daily excess-return Sharpe, or NaN if undefined.

    Parameters: net_returns contains finite cost-adjusted daily returns;
    annualization is sessions/year and annual_risk_free is an effective annual
    rate. Missing/nonfinite values fail rather than being dropped. No IC input
    or IC information ratio enters this calculation.
    """
    if (not isinstance(annualization, int) or annualization < 2
            or not np.isfinite(annual_risk_free)
            or annual_risk_free <= -1):
        raise ValueError("Invalid Sharpe convention")
    values = net_returns.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Cannot calculate Sharpe with missing/nonfinite returns")
    if len(values) < 2:
        return float("nan")
    excess = values - ((1 + annual_risk_free) ** (1 / annualization) - 1)
    if np.ptp(excess) == 0:
        return float("nan")
    std = excess.std(ddof=1)
    return float(excess.mean() / std * np.sqrt(annualization)) if std > 0 else float("nan")


def simulate_portfolio(
    panel: IndiaPanel, scores: pd.DataFrame, *,
    config: PortfolioConfig = PortfolioConfig(),
) -> PortfolioResult:
    """Simulate sequential, lagged close execution on an explicitly supplied calendar.

    Parameters: panel includes all intended sessions (including valid special
    sessions) and separate volume; scores must have exactly matching axes and
    be computed using available information. config sets the portfolio rules.
    Returns PortfolioResult; missing held prices raise ValueError with no partial
    Sharpe. Unheld gaps remain allowed. The input calendar is not certified here.
    This pure accounting function does not call factors, network, or write files.
    """
    validate_close(panel.close)
    if (not scores.index.equals(panel.close.index)
            or not scores.columns.equals(panel.close.columns)
            or not panel.volume.index.equals(panel.close.index)
            or not panel.volume.columns.equals(panel.close.columns)):
        raise ValueError("Scores, prices, and volumes must align exactly")
    if panel.close_basis != "adjusted":
        raise ValueError("The baseline requires explicitly adjusted closes")
    if np.isinf(scores.to_numpy(dtype=float)).any():
        raise ValueError("Scores cannot contain infinity")
    volumes = panel.volume.to_numpy(dtype=float)
    if np.isinf(volumes).any() or (volumes < 0).any():
        raise ValueError("Observed volumes must be finite and nonnegative")
    dates = panel.close.loc[config.start:config.end].index
    if dates.empty:
        raise ValueError("No sessions in the requested evaluation period")
    if not panel.benchmark.index.equals(panel.close.index):
        raise ValueError("Benchmark must align exactly with the stock calendar")
    benchmark = panel.benchmark.loc[dates]
    if (not np.isfinite(benchmark.to_numpy(dtype=float)).all()
            or benchmark.le(0).any()):
        raise ValueError("Missing or invalid benchmark close in evaluation period")
    benchmark_returns = benchmark.pct_change(fill_method=None)
    benchmark_returns.iloc[0] = 0.0
    periods = dates.to_period(config.rebalance_frequency)
    # The supplied session calendar determines week ends; prices never select
    # signal dates. Saturday special sessions belong to the next W-FRI period.
    signal_dates = set(pd.Series(dates, index=dates).groupby(periods).last())
    weights = pd.Series(0.0, index=NSE_STOCKS)
    pending = None
    executions, logs, rows = [], [], []
    previous = None
    for date in dates:
        gross = 0.0
        active = weights > 0
        if active.any():
            current = panel.close.loc[date, active]
            prior = panel.close.loc[previous, active]
            if current.isna().any() or prior.isna().any():
                bad = current.index[current.isna() | prior.isna()].tolist()
                raise ValueError(f"Missing held price on {date.date()}: {bad}")
            returns = current / prior - 1
            gross = float((weights[active] * returns).sum())
            if not np.isfinite(gross) or gross <= -1:
                raise ValueError("Portfolio NAV became invalid")
            weights.loc[active] = weights[active] * (1 + returns) / (1 + gross)
        turnover = cost = 0.0
        if pending is not None:
            target = pending["target"]
            changes = (target - weights).abs()
            traded = changes > TRADE_WEIGHT_TOLERANCE
            eligible = (
                panel.close.loc[date, traded].notna().all()
                and panel.volume.loc[date, traded].gt(0).all()
            )
            if eligible:
                turnover = float(changes.sum())
                cost = turnover * config.cost_bps / 10000
                if cost >= 1:
                    raise ValueError("Trading costs consume NAV")
                weights = target.copy()
                executions.append({
                    "signal_date": pending["signal_date"], "execution_date": date,
                    "selected": pending["selected"], "turnover": turnover,
                    "cost_fraction": cost,
                })
                pending = None
            else:
                logs.append({"date": date, "status": "deferred",
                             "signal_date": pending["signal_date"]})
        # Only after valuation and prior-order execution do today's closing
        # scores become available. A new target cannot earn today's return.
        if date in signal_dates:
            if pending is not None:
                status = ("expired_at_cutoff" if date == dates[-1]
                          else "cancelled_replaced")
                logs.append({"date": date, "status": status,
                             "signal_date": pending["signal_date"]})
                pending = None
            row = scores.loc[date].dropna()
            if len(row) >= config.min_signal_names and date != dates[-1]:
                selected = tuple(sorted(row.index, key=lambda s: (-row[s], s))[:config.top_n])
                target = pd.Series(0.0, index=NSE_STOCKS)
                target.loc[list(selected)] = 1 / config.top_n
                pending = {"signal_date": date, "selected": selected, "target": target}
            else:
                logs.append({"date": date, "status": "signal_skipped",
                             "reason": "insufficient_scores_or_no_later_session"})
        net = (1 + gross) * (1 - cost) - 1
        rows.append((gross, net, turnover, cost, weights.copy()))
        previous = date
    if pending is not None:
        logs.append({"date": dates[-1], "status": "expired_at_cutoff",
                     "signal_date": pending["signal_date"]})
    ic_dates, signal_rows, return_rows = [], [], []
    for first, second in zip(executions, executions[1:]):
        signal = first["signal_date"]
        ic_dates.append(signal)
        signal_rows.append(scores.loc[signal])
        return_rows.append(panel.close.loc[second["execution_date"]]
                           / panel.close.loc[first["execution_date"]] - 1)
    ix = pd.DatetimeIndex(ic_dates)
    net_returns = pd.Series([r[1] for r in rows], index=dates, name="net_return")
    return PortfolioResult(
        net_returns,
        pd.Series([r[0] for r in rows], index=dates, name="gross_return"),
        pd.DataFrame([r[4] for r in rows], index=dates),
        pd.Series([r[2] for r in rows], index=dates, name="turnover"),
        pd.Series([r[3] for r in rows], index=dates, name="cost_fraction"),
        pd.DataFrame(executions, columns=["signal_date", "execution_date", "selected",
                                          "turnover", "cost_fraction"]),
        logs, pd.DataFrame(signal_rows, index=ix, columns=NSE_STOCKS),
        pd.DataFrame(return_rows, index=ix, columns=NSE_STOCKS),
        annualized_sharpe(net_returns, annualization=config.annualization,
                          annual_risk_free=config.annual_risk_free), asdict(config),
        benchmark_returns.rename("benchmark_return"),
    )


@dataclass(frozen=True)
class StrevPortfolioRun:
    """Provisional portfolio result plus actual Vibe IC and quality provenance."""

    portfolio: PortfolioResult
    execution_ic: pd.Series
    research_view: ResearchView
    factor_source_sha256: dict[str, str]


def backtest_strev(
    panel: IndiaPanel, *, vibe_root: str | Path,
    config: PortfolioConfig = PortfolioConfig(),
    python_executable: str | Path = sys.executable,
) -> StrevPortfolioRun:
    """Compose verified exclusions, original Vibe STREV, accounting, and Vibe IC.

    Parameters: panel supplies the reviewed input calendar and warm-up prices;
    vibe_root/python_executable select the isolated factor worker; config sets
    the portfolio. Returns a provisional StrevPortfolioRun without publishing or
    a Keep/Drop decision. Flags are returned, not silently repaired/excluded.
    Final evaluations still require calendar/anomaly review and user approval.
    """
    view = prepare_research_view(panel)
    factor = evaluate_strev(view.panel, vibe_root=vibe_root,
                            python_executable=python_executable)
    portfolio = simulate_portfolio(view.panel, factor.scores, config=config)
    ic = compute_rank_ic(portfolio.ic_scores, portfolio.ic_returns,
                         vibe_root=vibe_root, python_executable=python_executable)
    return StrevPortfolioRun(portfolio, ic, view, factor.source_sha256)
