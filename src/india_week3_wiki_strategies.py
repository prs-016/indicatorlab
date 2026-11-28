"""Frozen WATM/WVB/WCR signals and orders on caller-supplied verified inputs.

No downloads, implicit registration, data approval or accounting implementation.
The existing PortfolioBook, replay, evaluation, IC and India fee bindings are reused.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from math import ceil, floor
from pathlib import Path

import numpy as np
import pandas as pd

from src.india_week3_evaluation import fill_cost
from src.india_week3_portfolio import PortfolioBook, account_orders, validate_panel
from src.india_week3_runner import ORDER_COLUMNS, TrialLedger, evaluate_recorded_run
from src.india_week3_strategies import UNIVERSES, _time, price_features

VERSIONS = ("WATM_v1_2", "WVB_v1_2", "WCR_v1_2")
COMPONENTS = {
    VERSIONS[0]: ("benchmark_trend", "momentum", "sma50", "wiki_attention"),
    VERSIONS[1]: (
        "benchmark_trend",
        "breakout",
        "relative_volume",
        "wiki_attention",
        "atr_predictive",
        "low10_exit",
    ),
    VERSIONS[2]: (
        "benchmark_trend",
        "sma20",
        "rsi14",
        "price_confirmation",
        "wiki_ratio",
        "wiki_z",
        "atr_predictive",
    ),
}
HOLDING_LIMITS = {VERSIONS[0]: None, VERSIONS[1]: 20, VERSIONS[2]: 10}
FREEZE = (
    Path(__file__).resolve().parents[1]
    / "india_research/reports/week3_wiki_frozen_20261117_v1_2"
)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _finite(row, names):
    return all(np.isfinite(float(row.get(k, np.nan))) for k in names)


def wiki_price_features(bars):
    """Extend existing causal indicators with prior-window breakout/volume means.

    Args: verified actual-close-indexed OHLCV frame. Returns a fresh frame;
    original values, NaNs, Wilder RSI and ATR semantics remain unchanged.
    """
    frame = price_features(bars)
    frame["hh20"] = frame.high.shift(1).rolling(20).max()
    frame["ll10"] = frame.low.shift(1).rolling(10).min()
    denom = frame.volume.shift(1).rolling(20).mean()
    frame["volume_mean_ratio"] = frame.volume / denom.where(denom > 0)
    frame["return1"] = frame.close.pct_change(fill_method=None)
    return frame


def prepare_wiki_snapshots(market, bars, benchmark_bars, wiki):
    """Join existing price kernels to weekly Wikipedia features without imputation.

    Args: exact basket of verified UTC-close OHLCV bars with published_at, same
    benchmark clock, and existing company-week feature table with decision_at,
    ticker, wiki_ratio/wiki_rz, eligible_at_snapshot, wiki_published_at_guide.
    Returns snapshots and full daily features; no prices or attention are fetched.
    Guide-lag timestamps remain labelled assumptions, not historical receipts.
    """
    if market not in UNIVERSES or set(bars) != set(UNIVERSES[market]):
        raise ValueError("Exact frozen market basket required")
    for frame in [*bars.values(), benchmark_bars]:
        if "published_at" not in frame:
            raise ValueError("Verified price publication evidence required")
        for at, release in zip(frame.index, frame.published_at, strict=True):
            if _time(release) < _time(at):
                raise ValueError("Price publication precedes close")
        if not frame.index.equals(benchmark_bars.index):
            raise ValueError("Stock/benchmark session clocks disagree")
    daily = {t: wiki_price_features(b) for t, b in bars.items()}
    benchmark = wiki_price_features(benchmark_bars)
    w = wiki[wiki.ticker.isin(UNIVERSES[market])].copy()
    if w.duplicated(["ticker", "decision_at"]).any():
        raise ValueError("Duplicate company-week")
    w["decision_at"] = [_time(t) for t in w.decision_at]
    snapshots = {}
    for at, group in w.groupby("decision_at", sort=True):
        if at.weekday() != 1 or at != at.normalize():
            raise ValueError("Tuesday 00:00 UTC snapshots required")
        rows = []
        for ticker in UNIVERSES[market]:
            prior = daily[ticker].loc[daily[ticker].index < at]
            if prior.empty:
                raise ValueError("No prior price history")
            latest = prior.index[-1]
            release = max(_time(t) for t in bars[ticker].loc[:latest, "published_at"])
            if release > at:
                raise ValueError("Price unavailable at decision")
            attention = group[group.ticker.eq(ticker)]
            row = prior.iloc[-1].to_dict()
            row.update(close_at=latest, published_at=release, wiki_valid=False)
            row.update(wiki_ratio=np.nan, wiki_rz=np.nan)
            if not attention.empty:
                a = attention.iloc[0]
                if _time(a.attention_week) != at - pd.Timedelta(days=8):
                    raise ValueError("Wikipedia week does not precede decision")
                if pd.notna(a.wiki_published_at_guide):
                    pub = _time(a.wiki_published_at_guide)
                    if pub > at or pub < at - pd.Timedelta(days=1):
                        raise ValueError(
                            "Wikipedia unavailable at decision or guide lag violated"
                        )
                    row.update(
                        wiki_ratio=a.wiki_ratio,
                        wiki_rz=a.wiki_rz,
                        wiki_valid=isinstance(a.eligible_at_snapshot, (bool, np.bool_))
                        and bool(a.eligible_at_snapshot),
                        wiki_published_at_guide=pub,
                        published_at=max(release, pub),
                    )
            rows.append(row)
        frame = pd.DataFrame(rows, index=UNIVERSES[market])
        previous = snapshots.get(at - pd.Timedelta(days=7))
        for key in ["wiki_ratio", "wiki_rz", "wiki_valid"]:
            frame["prior_" + key] = (
                previous[0][key]
                if previous is not None
                else (False if key == "wiki_valid" else np.nan)
            )
        prior_b = benchmark.loc[benchmark.index < at]
        if prior_b.empty:
            raise ValueError("No prior benchmark history")
        b = prior_b.iloc[-1].to_dict()
        b.update(
            close_at=prior_b.index[-1],
            published_at=max(
                _time(t)
                for t in benchmark_bars.loc[: prior_b.index[-1], "published_at"]
            ),
        )
        if b["published_at"] > at:
            raise ValueError("Benchmark unavailable at decision")
        snapshots[at] = (frame, b)
    return snapshots, daily


@dataclass
class WikiPlan:
    """Immutable-input plan values consumed by the existing evaluation interface."""

    scores: pd.Series
    eligible: pd.Series
    regime: bool
    multiplier: float
    status: str


def wiki_plan(strategy, market, at, frame, benchmark, *, disabled=None):
    """Return fixed entry/ranking/regime decisions, including frozen deletions.

    Args: version, exact basket and causal prepared snapshot; disabled removes
    one named predictive component only. Returns WikiPlan; ATR sizing/stops,
    execution, costs and position limits remain fixed in every ablation.
    """
    if strategy not in VERSIONS or market not in UNIVERSES:
        raise ValueError("Unknown frozen strategy/market")
    if disabled is not None and disabled not in COMPONENTS[strategy]:
        raise ValueError("Unknown drop-one indicator")
    at = _time(at)
    if set(frame.index) != set(UNIVERSES[market]):
        raise ValueError("Exact snapshot basket required")
    for r in [*frame.to_dict("index").values(), benchmark]:
        if _time(r["close_at"]) >= at or _time(r["published_at"]) > at:
            raise ValueError("Noncausal snapshot")
    regime_known = _finite(benchmark, ["close", "sma200"])
    if not regime_known and disabled != "benchmark_trend":
        raise ValueError("Missing benchmark regime indicator")
    regime = disabled == "benchmark_trend" or (
        regime_known and benchmark["close"] > benchmark["sma200"]
    )
    scores = pd.Series(np.nan, index=frame.index, dtype=float)
    eligible = pd.Series(False, index=frame.index)
    valid_wiki = frame.apply(
        lambda r: bool(r.get("wiki_valid", False))
        and _finite(r, ["wiki_ratio", "wiki_rz"]),
        axis=1,
    )
    multiplier, status = 1.0, "ready"
    if strategy == VERSIONS[0] and disabled != "wiki_attention":
        if int(valid_wiki.sum()) < ceil(0.8 * len(frame)):
            multiplier, status = 0.0, "attention_unavailable"
        elif frame.loc[valid_wiki, "wiki_rz"].median() >= 2:
            multiplier = 0.5
    risk_allowed = pd.Series(False, index=frame.index)
    for ticker, r in frame.iterrows():
        if not _finite(r, ["close", "atr"]) or r.atr <= 0 or r.close <= 0:
            continue
        risk_allowed[ticker] = max(0.02, 2 * r.atr / r.close) <= 0.10
        if strategy == VERSIONS[0]:
            if disabled != "momentum" and not _finite(r, ["momentum"]):
                continue
            if disabled != "sma50" and not _finite(r, ["sma50"]):
                continue
            scores[ticker] = 0.0 if disabled == "momentum" else r.momentum
            eligible[ticker] = (disabled == "momentum" or r.momentum > 0) and (
                disabled == "sma50" or r.close > r.sma50
            )
        elif strategy == VERSIONS[1]:
            if disabled != "breakout" and not _finite(r, ["hh20"]):
                continue
            if disabled != "relative_volume" and not _finite(r, ["volume_mean_ratio"]):
                continue
            if disabled != "wiki_attention" and not valid_wiki[ticker]:
                continue
            excess = 0.0 if disabled == "breakout" else r.close - r.hh20
            scores[ticker] = excess if disabled == "atr_predictive" else excess / r.atr
            eligible[ticker] = (
                (disabled == "breakout" or excess > 0)
                and (disabled == "relative_volume" or r.volume_mean_ratio >= 1.2)
                and (disabled == "wiki_attention" or r.wiki_ratio >= 1.2)
            )
        else:
            fields = []
            if disabled != "sma20":
                fields.append("sma20")
            if disabled != "rsi14":
                fields.append("rsi")
            if disabled != "price_confirmation":
                fields.append("return1")
            if not _finite(r, fields):
                continue
            if not valid_wiki[ticker] or not bool(r.get("prior_wiki_valid", False)):
                continue
            if not _finite(r, ["prior_wiki_ratio", "prior_wiki_rz"]):
                continue
            confirmation = 0.0 if disabled == "price_confirmation" else r.return1
            scores[ticker] = (
                confirmation
                if disabled == "atr_predictive"
                else confirmation / (r.atr / r.close)
            )
            eligible[ticker] = (
                (
                    disabled == "wiki_ratio"
                    or (
                        r.prior_wiki_ratio >= 1.5
                        and 1 <= r.wiki_ratio < r.prior_wiki_ratio
                    )
                )
                and (disabled == "wiki_z" or r.prior_wiki_rz >= 2)
                and (disabled == "sma20" or r.close < r.sma20)
                and (disabled == "rsi14" or 30 <= r.rsi <= 45)
                and (disabled == "price_confirmation" or r.return1 > 0)
            )
    return WikiPlan(scores, eligible & risk_allowed, bool(regime), multiplier, status)


def build_wiki_orders(
    strategy,
    market,
    split,
    close,
    volume,
    snapshots,
    daily_features,
    *,
    policy,
    trial_id,
    ledger: TrialLedger,
    provenance,
    india_engine=None,
    disabled=None,
):
    """Build persistent causal targets using the existing cash/position ledger.

    Args: already verified split panels, fixed snapshots/features, explicit
    AccountingPolicy and original India engine; no initial-capital assumption.
    Returns the existing run/result format. Every attempted run is trial-audited;
    partial accounting, terminal positions and missing held prices fail closed.
    """
    validate_panel(close, volume, split)
    if set(close) != set(UNIVERSES[market]):
        raise ValueError("Exact execution basket required")
    if strategy not in VERSIONS or (
        disabled is not None and disabled not in COMPONENTS[strategy]
    ):
        raise ValueError("Unknown strategy or deletion")
    if market == "IN" and (india_engine is None or policy.quantity_mode != "whole"):
        raise ValueError("India needs original engine and whole shares")
    freeze = json.loads((FREEZE / "checksums.json").read_text())
    for name, expected in freeze["rules_files"].items():
        if _hash((FREEZE / name).read_bytes()) != expected:
            raise ValueError("Frozen specification changed")
    if strategy not in json.loads((FREEZE / "rules.json").read_text())["versions"]:
        raise ValueError("Strategy absent from frozen rule set")
    settings = {
        "strategy": strategy,
        "market": market,
        "split": split,
        "policy": asdict(policy),
        "variant": "baseline" if disabled is None else "drop:" + disabled,
        "engine": getattr(india_engine, "provenance", None),
        "provenance": provenance,
        "specification_sha256": _hash((FREEZE / "rules.json").read_bytes()),
        "implementation_sha256": _hash(Path(__file__).read_bytes()),
        "data_sha256": {
            k: _hash(v.to_csv().encode())
            for k, v in {"close": close, "volume": volume}.items()
        },
    }
    settings["data_sha256"]["daily_features"] = {
        t: _hash(f.to_csv().encode()) for t, f in daily_features.items()
    }
    settings["data_sha256"]["snapshots"] = {
        str(at): _hash(
            (f.to_csv() + json.dumps(b, sort_keys=True, default=str)).encode()
        )
        for at, (f, b) in snapshots.items()
    }
    try:
        return _build(
            strategy,
            market,
            split,
            close,
            volume,
            snapshots,
            daily_features,
            policy,
            trial_id,
            ledger,
            settings,
            india_engine,
            disabled,
        )
    except Exception as exc:
        ledger.record(
            trial_id,
            kind="strategy" if disabled is None else "ablation",
            settings=settings,
            status="failed",
            error=type(exc).__name__,
        )
        raise


def _build(
    strategy,
    market,
    split,
    close,
    volume,
    snapshots,
    daily_features,
    policy,
    trial_id,
    ledger,
    settings,
    engine,
    disabled,
):
    dates = close.index
    for frame in daily_features.values():
        for at in frame.index:
            _time(at)
    decisions = {
        at: v
        for at, v in snapshots.items()
        if dates[0].normalize() <= _time(at) <= dates[-1]
    }
    if set(decisions) & set(dates):
        raise ValueError("Decision must differ from execution close")
    book = PortfolioBook(policy, market, engine)
    pending, risks, last_exit = {}, {}, {}
    orders, plans, events = [], {}, []
    for at in sorted(set(dates) | set(decisions)):
        if at in decisions:
            frame, benchmark = decisions[at]
            for t in list(pending):
                if pending[t]["target_weight"] > 0:
                    del pending[t]
            plan = wiki_plan(strategy, market, at, frame, benchmark, disabled=disabled)
            plans[at] = plan
            names = sorted(
                plan.eligible[plan.eligible].index, key=lambda t: (-plan.scores[t], t)
            )
            if strategy == VERSIONS[0]:
                selected = (
                    set(names[:2]) if plan.regime and plan.multiplier > 0 else set()
                )
                for ticker in book.held:
                    if ticker not in selected:
                        pending.setdefault(
                            ticker,
                            {
                                "decision_at": at,
                                "target_weight": 0.0,
                                "reason": "weekly_exit",
                            },
                        )
                targets = [t for t in names[:2] if t in selected]
            else:
                if not plan.regime:
                    # Regime only gates entries for WVB/WCR; their explicit exits persist.
                    targets = []
                else:
                    names = [t for t in names if t not in book.held]
                    if strategy == VERSIONS[2]:
                        names = [
                            t
                            for t in names
                            if t not in last_exit
                            or sum(last_exit[t] < s < at for s in decisions) >= 4
                        ]
                    targets = names[: max(0, 2 - len(book.held))]
            for ticker in targets:
                if ticker in pending and pending[ticker]["target_weight"] == 0:
                    continue
                row = frame.loc[ticker]
                distance = max(0.02, 2 * row.atr / row.close)
                pending[ticker] = {
                    "decision_at": at,
                    "target_weight": min(0.5, 0.01 / distance) * plan.multiplier,
                    "reason": "weekly_target",
                    "atr": row.atr,
                    "distance": distance,
                    "attempts": 0,
                }
            continue
        i = dates.get_loc(at)
        for ticker, risk in risks.items():
            limit = HOLDING_LIMITS[strategy]
            if i == len(dates) - 1 or (
                limit is not None and i - risk["entry_i"] + 1 >= limit
            ):
                pending[ticker] = {
                    "decision_at": risk["entry_at"],
                    "target_weight": 0.0,
                    "reason": "terminal" if i == len(dates) - 1 else "time",
                }
        if i == len(dates) - 1:
            pending = {t: p for t, p in pending.items() if p["target_weight"] == 0}
        active, meta = [], {}
        exiting = {
            t
            for t, p in pending.items()
            if p["target_weight"] == 0
            and p["decision_at"] < at
            and np.isfinite(volume.at[at, t])
            and volume.at[at, t] > 0
        }
        slots = 2 - len(set(book.held) - exiting)
        for ticker, p in sorted(
            pending.items(), key=lambda x: (x[1]["target_weight"] > 0, x[0])
        ):
            if p["decision_at"] >= at:
                continue
            entry = p["target_weight"] > 0
            if entry:
                p["attempts"] += 1
                if ticker not in book.held and (
                    p["attempts"] > 2 or len(dates) - i < 5
                ):
                    events.append(
                        {"at": at, "ticker": ticker, "event": "entry_expired"}
                    )
                    del pending[ticker]
                    continue
                if ticker not in book.held and slots <= 0:
                    continue
            if (
                not np.isfinite(volume.at[at, ticker])
                or volume.at[at, ticker] <= 0
                or not np.isfinite(close.at[at, ticker])
            ):
                continue
            # Whole-share resize rounding follows the existing ledger, not an alpha threshold.
            if entry and ticker in book.held and policy.quantity_mode == "whole":
                nav = book.cash + sum(q * close.at[at, t] for t, q in book.held.items())
                delta = (
                    p["target_weight"] * nav - book.held[ticker] * close.at[at, ticker]
                )
                one_share = close.at[at, ticker]
                if delta > 0:
                    quote = fill_cost(
                        market,
                        quantity=1,
                        close=one_share,
                        buy=True,
                        india_engine=engine,
                    )
                    one_share = quote["price"] + quote["commission"]
                if abs(delta) < one_share and abs(delta) > 1e-9:
                    del pending[ticker]
                    events.append(
                        {"at": at, "ticker": ticker, "event": "resize_below_one_share"}
                    )
                    continue
            active.append(
                dict(
                    execution_at=at,
                    ticker=ticker,
                    **{k: p[k] for k in ["decision_at", "target_weight", "reason"]},
                )
            )
            meta[ticker] = dict(p)
            if entry and ticker not in book.held:
                slots -= 1
        active = _fund_targets(book, active, close.loc[at], events, at, engine)
        before = set(book.held)
        book.step(
            at,
            close.loc[at],
            volume.loc[at],
            pd.DataFrame(active, columns=ORDER_COLUMNS),
            i=i,
            remaining=len(dates) - i,
        )
        orders.extend(active)
        after = set(book.held)
        for ticker in before - after:
            del risks[ticker]
            last_exit[ticker] = at
        for ticker in meta:
            pending.pop(ticker, None)
        for ticker in after - before:
            p = meta[ticker]
            fill = next(
                f
                for f in reversed(book.fills)
                if f["ticker"] == ticker and f["execution_at"] == at
            )
            risks[ticker] = {
                "entry_i": i,
                "entry_at": at,
                "atr": p["atr"],
                "stop": fill["price"] * (1 - p["distance"]),
                "highest": close.at[at, ticker],
            }
        for ticker in after:
            risk = risks[ticker]
            c = close.at[at, ticker]
            row = daily_features[ticker].loc[at]
            required = []
            if (
                ticker in before
                and strategy == VERSIONS[1]
                and disabled != "low10_exit"
            ):
                required.append("ll10")
            if ticker in before and strategy == VERSIONS[2]:
                required.extend(
                    k
                    for k, component in [("sma20", "sma20"), ("rsi", "rsi14")]
                    if disabled != component
                )
            if not _finite(row, required):
                raise ValueError("Missing required held-position exit indicator")
            reason = "stop" if c <= risk["stop"] else None
            if (
                ticker in before
                and strategy == VERSIONS[1]
                and disabled != "low10_exit"
                and np.isfinite(row.get("ll10", np.nan))
                and c < row.ll10
            ):
                reason = reason or "low10"
            if ticker in before and strategy == VERSIONS[2]:
                if (
                    disabled != "sma20"
                    and np.isfinite(row.get("sma20", np.nan))
                    and c >= row.sma20
                ):
                    reason = reason or "mean_reversion"
                if (
                    disabled != "rsi14"
                    and np.isfinite(row.get("rsi", np.nan))
                    and row.rsi >= 60
                ):
                    reason = reason or "rsi60"
            risk["highest"] = max(risk["highest"], c)
            risk["stop"] = max(risk["stop"], risk["highest"] - 2 * risk["atr"])
            if reason and ticker not in pending:
                pending[ticker] = {
                    "decision_at": at,
                    "target_weight": 0.0,
                    "reason": reason,
                }
    if book.held:
        raise ValueError("Unfilled terminal liquidation")
    order_frame = pd.DataFrame(orders, columns=ORDER_COLUMNS)
    result = account_orders(
        close,
        volume,
        order_frame,
        market=market,
        split=split,
        policy=policy,
        india_engine=engine,
    )
    pd.testing.assert_frame_equal(result.daily, pd.DataFrame(book.daily, index=dates))
    ledger.record(
        trial_id,
        kind="strategy" if disabled is None else "ablation",
        settings=settings,
        status="complete",
        metrics=result.metrics,
    )
    return {
        "trial_id": trial_id,
        "settings": settings,
        "orders": order_frame,
        "result": result,
        "plans": plans,
        "events": events,
    }


def run_wiki_ablations(*, strategy, arguments, trial_prefix):
    """Run every frozen predictive deletion through the same persistent builder.

    Args: baseline builder arguments excluding strategy/trial_id/disabled; ledger
    captures failures too. Returns per-variant runs; failed variants remain None.
    """
    outputs = {}
    for component in [None, *COMPONENTS[strategy]]:
        key = "baseline" if component is None else "drop:" + component
        try:
            outputs[key] = build_wiki_orders(
                strategy=strategy,
                trial_id=trial_prefix + ":" + key,
                disabled=component,
                **arguments,
            )
        except (ValueError, RuntimeError):
            outputs[key] = None
    return outputs


def evaluate_wiki_run(run, **kwargs):
    """Delegate IC, 200 timing nulls, benchmark metrics and DSR without duplication.

    Args/return follow evaluate_recorded_run. Missing trial evidence remains N/A;
    evaluation permission and verified input checks belong to the real-run gate.
    """
    return evaluate_recorded_run(run, **kwargs)


def wiki_random_candidates(run, close, volume):
    """Return return-independent weekly/regime/coverage timing-null candidates.

    Args: completed baseline run and same split panels. Returns trade_id ->
    entry-session indices; original ticker, weights, resize path and durations
    are retained by the existing 200-run evaluator. No future profits select dates.
    Feasibility uses calendar duration and complete execution observations only.
    """
    trades = run["result"].trades
    if trades.empty:
        raise ValueError("No completed trades for timing comparison")
    answer = {}
    for trade in trades.itertuples():
        choices = []
        for at, plan in run["plans"].items():
            if (
                not plan.regime
                or plan.status != "ready"
                or not np.isfinite(plan.scores[trade.ticker])
            ):
                continue
            candidates = close.index[close.index > at][:2]
            for entry in candidates:
                i = close.index.get_loc(entry)
                if (
                    np.isfinite(volume.at[entry, trade.ticker])
                    and volume.at[entry, trade.ticker] > 0
                    and np.isfinite(close.at[entry, trade.ticker])
                ):
                    if len(close) - i >= 5 and i + trade.duration <= len(close):
                        end = int(i + trade.duration)
                        # Reject impossible scheduled fills; do not shorten a trade.
                        if (
                            volume[trade.ticker].iloc[end - 1] > 0
                            and close[trade.ticker].iloc[i:end].notna().all()
                        ):
                            choices.append(int(i))
                    break
        answer[trade.trade_id] = sorted(set(choices))
    return answer


def _fund_targets(book, active, prices, events, at, engine):
    """Reserve actual sale fees before funding same-close requested buy budgets.

    This does no accounting: all actual fills/cash charges still go through the
    original PortfolioBook and replay. Target requests are caps subject to cash;
    executable funded weights and any rounding no-op are explicitly recorded.
    """
    nav = book.cash + sum(q * prices[t] for t, q in book.held.items())
    available = book.cash
    buys = []
    for row in active:
        t = row["ticker"]
        mark = book.held.get(t, 0.0) * prices[t]
        delta = row["target_weight"] * nav - mark
        if delta < -1e-9:
            old = book.held[t]
            qty = old if row["target_weight"] == 0 else min(old, -delta / prices[t])
            if book.policy.quantity_mode == "whole" and row["target_weight"] != 0:
                qty = floor(qty + 1e-10)
            if qty > 0:
                quote = fill_cost(
                    book.market,
                    quantity=qty,
                    close=prices[t],
                    buy=False,
                    india_engine=engine,
                )
                available += qty * quote["price"] - quote["commission"]
        elif delta > 1e-9:
            buys.append((row, mark, delta))
    requested = sum(delta for _, _, delta in buys)
    factor = min(1.0, max(0.0, available) / requested) if requested else 1.0
    omitted = set()
    if factor < 1.0:
        for row, mark, delta in buys:
            funded = delta * factor
            desired = row["target_weight"]
            row["target_weight"] = (mark + funded) / nav
            events.append(
                {
                    "at": at,
                    "ticker": row["ticker"],
                    "event": "fee_inclusive_cash_funding",
                    "requested_target": desired,
                    "funded_target": row["target_weight"],
                }
            )
            if mark and book.policy.quantity_mode == "whole":
                quote = fill_cost(
                    book.market,
                    quantity=1,
                    close=prices[row["ticker"]],
                    buy=True,
                    india_engine=engine,
                )
                if funded < quote["price"] + quote["commission"]:
                    omitted.add(row["ticker"])
                    events.append(
                        {
                            "at": at,
                            "ticker": row["ticker"],
                            "event": "funded_resize_below_one_share",
                        }
                    )
    return [row for row in active if row["ticker"] not in omitted]
