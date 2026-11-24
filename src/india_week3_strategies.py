"""Offline v2 strategy kernels; no acquisition, registration or historical runner.

Prepared snapshots use UTC publication times and completed local-session bars.
These decisions do not imply approved data, PM registration or portfolio results.
"""

from dataclasses import dataclass
from math import ceil

import numpy as np
import pandas as pd

from src.reddit.spike_rule import flag_spikes

STRATEGIES = {"AGM_v2": 63, "SCB_v2": 42, "AER_v2": 20}
UNIVERSES = {
    "IN": (
        "RELIANCE.NS",
        "TCS.NS",
        "INFY.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
    ),
    "US": (
        "AAPL",
        "MSFT",
        "NVDA",
        "TSLA",
        "AMZN",
        "META",
        "GOOGL",
        "AMD",
        "NFLX",
        "JPM",
    ),
}
CUTOFF = pd.Timestamp("2025-10-01", tz="UTC")


def _time(value) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if result.tzinfo is None or pd.isna(result):
        raise ValueError("Explicit timezone required")
    result = result.tz_convert("UTC")
    if result >= CUTOFF:
        raise ValueError("Holdout timestamp rejected")
    return result


def _finite(row, *names) -> bool:
    return all(np.isfinite(float(row[name])) for name in names)


def price_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Calculate v2 trailing indicators for one aligned local-session OHLCV series.

    Args:
        bars: Sorted unique UTC close index and high/low/close/volume columns.
            Must already include missing exchange sessions as missing rows.
    Returns:
        Causal indicators, retaining missing/warm-up values. No calendar or price
        repairs occur; callers must verify adjustment/volume bases separately.
    """
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("Sorted unique session closes required")
    for timestamp in bars.index:
        _time(timestamp)
    frame = bars[["high", "low", "close", "volume"]].astype(float).copy()
    if np.isinf(frame.to_numpy()).any():
        raise ValueError("Infinite OHLCV")
    c, h, low, v = (frame[k] for k in ["close", "high", "low", "volume"])
    if ((c <= 0) | (h < c) | (low > c) | (low <= 0) | (v < 0)).any():
        raise ValueError("Invalid OHLCV; no silent repair")
    tr = pd.concat(
        [h - low, (h - c.shift()).abs(), (low - c.shift()).abs()], axis=1
    ).max(axis=1, skipna=False)
    frame["atr"] = tr.rolling(20).mean()
    for n in [20, 50, 200]:
        frame[f"sma{n}"] = c.rolling(n).mean()
    frame["sma200_previous20"] = frame["sma200"].shift(20)
    frame["rv20"] = c.pct_change(fill_method=None).rolling(20).std(ddof=1) * np.sqrt(
        252
    )
    frame["momentum"] = c.shift(21) / c.shift(126) - 1
    frame["return5"] = c / c.shift(5) - 1
    frame["hh55"] = h.shift().rolling(55).max()
    frame["ll20"] = low.shift().rolling(20).min()
    frame["previous_high"] = h.shift()
    frame["vr"] = v / v.shift().rolling(20).median().where(lambda x: x > 0)
    # Wilder seed from 14 complete changes; a gap resets warm-up, never fills it.
    delta = c.diff()
    rsi = np.full(len(c), np.nan)
    history = []
    gain = loss = None
    for i, change in enumerate(delta):
        if not np.isfinite(change):
            history, gain, loss = [], None, None
            continue
        if gain is None:
            history.append(change)
            if len(history) < 14:
                continue
            gain = np.mean(np.maximum(history, 0))
            loss = np.mean(np.maximum(-np.asarray(history), 0))
        else:
            gain = (13 * gain + max(change, 0)) / 14
            loss = (13 * loss + max(-change, 0)) / 14
        rsi[i] = (
            50
            if gain == loss == 0
            else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
        )
    frame["rsi"] = rsi
    return frame


def attention_features(counts: pd.Series) -> pd.DataFrame:
    """Reuse the shared past-only eight-week spike rule for complete Monday weeks.

    Args:
        counts: Continuous Monday-UTC weekly grid, missing coverage represented
            by NaN, with no post-cutoff observation weeks.
    Returns:
        Original spike columns; ratio/rz remain NaN when unavailable.
    """
    expected = pd.date_range(counts.index.min(), counts.index.max(), freq="7D")
    if not counts.index.equals(expected) or any(t.weekday() != 0 for t in counts.index):
        raise ValueError("Continuous Monday weekly grid required")
    for t in counts.index:
        _time(t + pd.Timedelta(days=7) - pd.Timedelta(nanoseconds=1))
    if ((counts < 0) | np.isinf(counts)).any():
        raise ValueError("Invalid attention counts")
    return flag_spikes(
        counts,
        {
            "baseline_weeks": 8,
            "offset": 1,
            "rz_min_history": 26,
            "mad_scale": 1.4826,
            "ratio": 1.5,
            "rz_threshold": 2,
        },
    )


def sentiment_net(posts: pd.DataFrame, *, complete: bool) -> float:
    """Aggregate shared FinBERT probabilities, without loading a model or labels.

    Args:
        posts: Unique post_id/ticker rows for one English company-week, with the
            shared sentiment_pos/neg/neu probability columns. Upstream must verify
            text versions, company matching, publication and model provenance.
        complete: Verified complete collection; false returns unavailable.
    Returns:
        Mean positive minus negative probability, or NaN below 20 scored posts.
        Invalid probabilities/duplicate identities fail rather than bias counts.
    """
    if posts.duplicated(["post_id", "ticker"]).any() or posts["ticker"].nunique() > 1:
        raise ValueError("One deduplicated company-week required")
    probabilities = posts[["sentiment_pos", "sentiment_neg", "sentiment_neu"]].astype(
        float
    )
    if ((probabilities < 0) | (probabilities > 1)).any().any() or np.isinf(
        probabilities.to_numpy()
    ).any():
        raise ValueError("Invalid probabilities")
    scored = probabilities.dropna()
    if not np.allclose(scored.sum(axis=1), 1, atol=1e-6):
        raise ValueError("Probabilities must sum to one")
    if not complete or len(scored) < 20:
        return float("nan")
    return float((scored["sentiment_pos"] - scored["sentiment_neg"]).mean())


@dataclass(frozen=True)
class Plan:
    """Weekly raw scores, gate eligibility, ungated/gated entry weights and status."""

    scores: pd.Series
    eligible: pd.Series
    ungated: dict[str, float]
    targets: dict[str, float]
    regime: bool | None
    status: str


def weekly_plan(
    strategy: str,
    market: str,
    snapshot,
    features: pd.DataFrame,
    benchmark: dict,
    *,
    held: tuple[str, ...] = (),
    attention_sources: tuple[str, ...] = ("reddit", "wiki"),
) -> Plan:
    """Execute fixed v2 entry/ranking/sizing rules on an auditable weekly snapshot.

    Args:
        strategy: Exact v2 ID; market: US or IN; snapshot: Tuesday 00:00 UTC.
        features: Full fixed-basket rows indexed by ticker; price close_at and
            combined published_at, attention_week plus indicated numeric fields.
            AER prior_* features must carry prior_snapshot and prior_published_at.
        benchmark: Completed close_at, published_at, close/sma200/rv20 and SCB
            sma200_previous20. Features must be consistent adjusted price units.
        held: Existing names; SCB/AER fill only vacant slots, never pyramid.
        attention_sources: AGM-only declared no-attention/source-only ablations;
            the unchanged baseline uses both sources.
    Returns:
        Plan retaining ungated scores and unknown-input status. No trades, costs
        or returns are inferred. Exit/cooldown checks must precede actual entries.
    """
    STRATEGIES[strategy]
    if len(set(attention_sources)) != len(attention_sources) or not set(
        attention_sources
    ) <= {"reddit", "wiki"}:
        raise ValueError("Unknown attention ablation source")
    if strategy != "AGM_v2" and attention_sources != ("reddit", "wiki"):
        raise ValueError("Only AGM attention-source ablations are defined")
    universe = UNIVERSES[market]
    now = _time(snapshot)
    if now.weekday() != 1 or now != now.normalize():
        raise ValueError("Tuesday 00:00 UTC snapshot required")
    if set(features.index) != set(universe) or not features.index.is_unique:
        raise ValueError("Exact fixed universe required")
    if len(held) > 2 or len(set(held)) != len(held) or not set(held) <= set(universe):
        raise ValueError("Invalid existing holdings")
    f = features.reindex(universe)
    for _, row in f.iterrows():
        if _time(row["close_at"]) >= now or _time(row["published_at"]) > now:
            raise ValueError("Future/unpublished signal input")
        if _time(row["attention_week"]) != now - pd.Timedelta(days=8):
            raise ValueError("Wrong attention week")
        if strategy == "AER_v2":
            prior = now - pd.Timedelta(days=7)
            if (
                _time(row["prior_snapshot"]) != prior
                or _time(row["prior_published_at"]) > prior
            ):
                raise ValueError("Prior shock must be available at its prior snapshot")
    if _time(benchmark["close_at"]) >= now or _time(benchmark["published_at"]) > now:
        raise ValueError("Future benchmark")
    known = _finite(benchmark, "close", "sma200", "rv20")
    if strategy == "SCB_v2":
        known = known and _finite(benchmark, "sma200_previous20")
    regime = None
    if known:
        b = benchmark
        regime = bool(b["close"] > b["sma200"] and b["rv20"] <= 0.35)
        if strategy == "SCB_v2":
            regime = bool(
                b["close"] > b["sma200"] > b["sma200_previous20"] and b["rv20"] <= 0.30
            )
        if strategy == "AER_v2":
            regime = bool(b["close"] >= 0.9 * b["sma200"] and b["rv20"] <= 0.40)
    scores = pd.Series(np.nan, index=f.index, dtype=float)
    eligible = pd.Series(False, index=f.index)
    multiplier, attention_ok = 1.0, True
    if strategy == "AGM_v2":
        for source in attention_sources:
            valid = np.isfinite(f[[source + "_ratio", source + "_rz"]]).all(axis=1)
            if valid.sum() < ceil(0.8 * len(universe)):
                attention_ok = False
            elif (
                (f.loc[valid, source + "_ratio"] >= 1.5)
                & (f.loc[valid, source + "_rz"] >= 2)
            ).mean() >= 0.40:
                multiplier = 0.5
    for ticker, r in f.iterrows():
        if not _finite(r, "close", "atr") or r["close"] <= 0 or r["atr"] <= 0:
            continue
        a = r["atr"] / r["close"]
        d = max(0.02, 2 * a)
        if strategy == "AGM_v2" and _finite(r, "momentum", "sma50"):
            scores[ticker] = r["momentum"]
            eligible[ticker] = r["momentum"] > 0 and r["close"] > r["sma50"]
        elif strategy == "SCB_v2" and _finite(
            r,
            "hh55",
            "volume",
            "vr",
            "reddit_ratio",
            "wiki_ratio",
            "reddit_rz",
            "wiki_rz",
            "sentiment",
            "sentiment_delta",
        ):
            if (
                min(r["hh55"], r["vr"], r["reddit_ratio"], r["wiki_ratio"]) > 0
                and r["volume"] > 0
            ):
                scores[ticker] = (
                    (r["close"] / r["hh55"] - 1) / a
                    + np.log(r["vr"])
                    + np.log(r["reddit_ratio"])
                    + np.log(r["wiki_ratio"])
                    + r["sentiment"]
                    + r["sentiment_delta"]
                )
                eligible[ticker] = (
                    r["close"] > r["hh55"]
                    and r["vr"] >= 1.5
                    and min(r["reddit_ratio"], r["wiki_ratio"]) >= 1.5
                    and max(r["reddit_rz"], r["wiki_rz"]) >= 2
                    and r["sentiment"] >= 0.20
                    and r["sentiment_delta"] >= 0.10
                )
        elif (
            strategy == "AER_v2"
            and _finite(r, "prior_return5", "prior_atr_pct", "sentiment_delta")
            and r["prior_atr_pct"] > 0
        ):
            scores[ticker] = (
                r["sentiment_delta"] * -r["prior_return5"] / r["prior_atr_pct"]
            )
            names = [
                "prior_reddit_ratio",
                "prior_reddit_rz",
                "prior_wiki_ratio",
                "prior_wiki_rz",
                "prior_sentiment",
                "prior_close",
                "prior_sma20",
                "prior_atr",
                "prior_rsi",
                "prior_posts",
                "posts",
                "reddit_ratio",
                "sentiment",
                "rsi",
                "previous_high",
            ]
            if _finite(r, *names) and r["prior_posts"] > 0:
                eligible[ticker] = (
                    r["prior_reddit_ratio"] >= 3
                    and r["prior_reddit_rz"] >= 3
                    and r["prior_wiki_ratio"] >= 2
                    and r["prior_wiki_rz"] >= 2
                    and r["prior_sentiment"] <= -0.30
                    and r["prior_return5"] <= -0.08
                    and r["prior_close"] <= r["prior_sma20"] - 2 * r["prior_atr"]
                    and r["prior_rsi"] <= 30
                    and r["posts"] <= 0.75 * r["prior_posts"]
                    and r["reddit_ratio"] >= 1.5
                    and r["sentiment_delta"] >= 0.20
                    and r["sentiment"] > -0.10
                    and 30 < r["rsi"] <= 50
                    and r["close"] > r["previous_high"]
                )
        eligible[ticker] = bool(eligible[ticker] and d <= 0.10)
    if strategy != "AGM_v2":
        eligible.loc[list(held)] = False
    candidates = sorted(eligible[eligible].index, key=lambda t: (-scores[t], t))
    selected = candidates[: 2 if strategy == "AGM_v2" else 2 - len(held)]
    ungated = {
        t: min(0.5, 0.01 / max(0.02, 2 * f.loc[t, "atr"] / f.loc[t, "close"]))
        for t in selected
    }
    targets = (
        {t: w * multiplier for t, w in ungated.items()}
        if regime and attention_ok
        else {}
    )
    status = (
        "ready"
        if regime is not None and attention_ok
        else "missing required regime/attention"
    )
    return Plan(scores, eligible, ungated, targets, regime, status)


@dataclass(frozen=True)
class Holding:
    """Entry price/ATR/distance, completed held-session count and ratcheted stop."""

    strategy: str
    entry_price: float
    entry_atr: float
    distance: float
    held_sessions: int
    highest_close: float
    stop: float


def open_holding(strategy: str, price: float, atr: float, distance: float) -> Holding:
    """Create filled-entry risk state; caller supplies validated price/ATR/distance.

    Returns a Holding counting the entry close as session 1. This does not debit
    cash or certify quantity/fee rules; it is the execution-independent risk state.
    """
    STRATEGIES[strategy]
    if (
        not all(np.isfinite([price, atr, distance]))
        or price <= 0
        or atr <= 0
        or not 0.02 <= distance <= 0.10
    ):
        raise ValueError("Invalid entry risk state")
    return Holding(strategy, price, atr, distance, 1, price, price * (1 - distance))


def daily_risk(
    holding: Holding, close: float, *, sma: float = np.nan, low20: float = np.nan
) -> tuple[Holding, str | None]:
    """Advance a completed close and report next-close price exit or scheduled expiry.

    Args:
        holding: Risk state before this close; close: valid held close.
        sma: SMA50 for AGM, SMA20 for AER; low20: prior low for SCB.
    Returns:
        Updated holding and reason. Check the prior stop before ratcheting.
        'time' is a predeclared same-close expiry, unlike price-triggered exits.
    """
    if not np.isfinite(close) or close <= 0:
        raise ValueError("Missing held close blocks evaluation")
    reason = "stop" if close <= holding.stop else None
    if holding.strategy == "AGM_v2" and np.isfinite(sma) and close < sma:
        reason = reason or "sma50"
    if holding.strategy == "SCB_v2" and np.isfinite(low20) and close < low20:
        reason = reason or "prior_low20"
    if holding.strategy == "AER_v2" and np.isfinite(sma) and close >= sma:
        reason = reason or "sma20_target"
    n = holding.held_sessions + 1
    if n >= STRATEGIES[holding.strategy]:
        reason = "time"
    highest = max(holding.highest_close, close)
    new = Holding(
        holding.strategy,
        holding.entry_price,
        holding.entry_atr,
        holding.distance,
        n,
        highest,
        max(holding.stop, highest - 2 * holding.entry_atr),
    )
    return new, reason


def weekly_exit(
    strategy: str,
    *,
    regime: bool | None,
    selected: bool = True,
    momentum: float = np.nan,
    sentiment: float = np.nan,
) -> str | None:
    """Return the explicit weekly next-close exit reason; missing values do not exit.

    Parameters correspond to fixed strategy weekly gates. Returns None for no
    known exit. Missing entries remain blocked by weekly_plan independently.
    """
    STRATEGIES[strategy]
    if regime is False:
        return "regime"
    if strategy == "AGM_v2" and (
        not selected or (np.isfinite(momentum) and momentum <= 0)
    ):
        return "selection_or_momentum"
    if strategy == "SCB_v2" and np.isfinite(sentiment) and sentiment < 0:
        return "sentiment"
    if strategy == "AER_v2" and np.isfinite(sentiment) and sentiment >= 0.20:
        return "sentiment"
    return None


def entry_close(
    signal_at,
    session_closes: pd.DatetimeIndex,
    volumes: pd.Series,
    *,
    split_end,
    remaining_sessions: int,
) -> pd.Timestamp | None:
    """Return first positive-volume close in the next two sessions, or no entry.

    Args:
        signal_at: Weekly decision timestamp; session_closes: verified future local
            close schedule; volumes: actual observations keyed by those closes.
        split_end: Last permitted execution close; remaining_sessions: known local
            sessions after decision (including the candidate entry close).
    Returns:
        Strictly subsequent close, never signal-close execution. Fewer than five
        remaining sessions, zero volume or missing data cannot invent a fill.
    """
    signal, end = _time(signal_at), _time(split_end)
    if not session_closes.is_unique or not session_closes.is_monotonic_increasing:
        raise ValueError("Sorted unique execution calendar required")
    for t in session_closes:
        _time(t)
    if remaining_sessions < 5:
        return None
    for t in session_closes[(session_closes > signal) & (session_closes <= end)][:2]:
        value = volumes.get(t, np.nan)
        if np.isfinite(value) and value > 0:
            return t
    return None


def aer_event_eligible(
    event_id: str, consumed: set[str], *, sessions_since_exit: int | None
) -> bool:
    """Check AER one-entry-per-shock and ten-session cooldown before selection.

    Args: event_id identifies the prior snapshot; consumed records filled shocks;
        sessions_since_exit is None before the first entry, else a calendar count.
    Returns: Whether the event can create a new entry; never mutates the ledger.
    """
    return event_id not in consumed and (
        sessions_since_exit is None or sessions_since_exit >= 10
    )


def exit_close(
    trigger_at, session_closes: pd.DatetimeIndex, volumes: pd.Series, *, split_end
) -> pd.Timestamp | None:
    """Schedule a price/weekly exit after its trigger, without entry-order expiry.

    Args:
        trigger_at: Time the completed-price/weekly exit became known.
        session_closes: Verified sorted local close calendar; volumes: observations.
        split_end: Last permitted close in this split.
    Returns:
        First subsequent positive-volume close, or None if unresolved. Never
        fabricates a fill at the trigger or after the split/holdout boundary.
        Predeclared time/terminal exits have separately known same-close schedules.
    """
    trigger, end = _time(trigger_at), _time(split_end)
    if not session_closes.is_unique or not session_closes.is_monotonic_increasing:
        raise ValueError("Sorted unique execution calendar required")
    for timestamp in session_closes:
        _time(timestamp)
        value = volumes.get(timestamp, np.nan)
        if trigger < timestamp <= end and np.isfinite(value) and value > 0:
            return timestamp
    return None
