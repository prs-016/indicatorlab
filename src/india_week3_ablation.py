"""Explicit drop-one predictive-indicator semantics; baseline kernels unchanged."""

import numpy as np
import pandas as pd

from src.india_week3_strategies import Plan, weekly_plan

COMPONENTS = {
    "AGM_v2": (
        "momentum",
        "sma50",
        "reddit_attention",
        "wikipedia_attention",
        "benchmark_trend",
        "benchmark_volatility",
    ),
    "SCB_v2": (
        "breakout",
        "relative_volume",
        "reddit_attention",
        "wikipedia_attention",
        "sentiment_level",
        "sentiment_change",
        "benchmark_trend",
        "benchmark_volatility",
        "low20_exit",
        "atr_predictive",
    ),
    "AER_v2": (
        "reddit_attention",
        "wikipedia_attention",
        "sentiment_level",
        "sentiment_change",
        "prior_return",
        "sma20",
        "rsi14",
        "price_confirmation",
        "atr_predictive",
        "benchmark_trend",
        "benchmark_volatility",
    ),
}


def drop_one_plan(
    strategy, market, at, frame, benchmark, *, component: str, held=()
) -> Plan:
    """Remove one named indicator from all predictive uses, retaining risk controls.

    Args: baseline snapshot inputs plus a COMPONENTS key. Returns the original
        Plan shape. Removing an additive term omits it; removing a multiplicative
        factor uses its algebraic identity 1. An empty momentum score is constant
        zero with the original ticker tie rule, not a replacement alpha signal.
        Timestamp/provenance validation always reuses the unchanged baseline.
    """
    if component not in COMPONENTS[strategy]:
        raise ValueError("Unknown predictive component")
    weekly_plan(strategy, market, at, frame, benchmark, held=held)
    active = lambda name: component != name
    required = []
    if active("benchmark_trend"):
        required += ["close", "sma200"]
        if strategy == "SCB_v2":
            required += ["sma200_previous20"]
    if active("benchmark_volatility"):
        required += ["rv20"]
    known = all(np.isfinite(benchmark[k]) for k in required)
    regime = None
    if known:
        b = benchmark
        trend = True
        if active("benchmark_trend"):
            trend = b["close"] > b["sma200"]
            if strategy == "SCB_v2":
                trend = trend and b["sma200"] > b["sma200_previous20"]
            if strategy == "AER_v2":
                trend = b["close"] >= 0.9 * b["sma200"]
        limit = {"AGM_v2": 0.35, "SCB_v2": 0.30, "AER_v2": 0.40}[strategy]
        regime = bool(
            trend and (not active("benchmark_volatility") or b["rv20"] <= limit)
        )
    scores = pd.Series(np.nan, index=frame.index)
    eligible = pd.Series(False, index=frame.index)
    attention_ok = True
    multiplier = 1.0
    if strategy == "AGM_v2":
        sources = tuple(
            s
            for s, name in [
                ("reddit", "reddit_attention"),
                ("wiki", "wikipedia_attention"),
            ]
            if active(name)
        )
        # Recompute coverage independently of the benchmark status.
        attention_ok = all(
            np.isfinite(frame[[s + "_ratio", s + "_rz"]]).all(axis=1).sum()
            >= np.ceil(0.8 * len(frame))
            for s in sources
        )
        for s in sources:
            valid = np.isfinite(frame[[s + "_ratio", s + "_rz"]]).all(axis=1)
            if (
                valid.any()
                and (
                    (frame.loc[valid, s + "_ratio"] >= 1.5)
                    & (frame.loc[valid, s + "_rz"] >= 2)
                ).mean()
                >= 0.4
            ):
                multiplier = 0.5
    for t, r in frame.iterrows():
        if not all(np.isfinite(r[k]) and r[k] > 0 for k in ["close", "atr"]):
            continue
        a = r["atr"] / r["close"]
        checks = []
        terms = []
        if strategy == "AGM_v2":
            if active("momentum"):
                checks.append(np.isfinite(r["momentum"]) and r["momentum"] > 0)
                terms.append(r["momentum"])
            if active("sma50"):
                checks.append(np.isfinite(r["sma50"]) and r["close"] > r["sma50"])
            scores[t] = sum(terms)
        elif strategy == "SCB_v2":
            groups = {
                "breakout": (
                    ["hh55"],
                    lambda r=r: r["close"] > r["hh55"],
                    lambda r=r, a=a: (r["close"] / r["hh55"] - 1)
                    / (a if active("atr_predictive") else 1),
                ),
                "relative_volume": (
                    ["vr"],
                    lambda r=r: r["vr"] >= 1.5,
                    lambda r=r: np.log(r["vr"]),
                ),
                "reddit_attention": (
                    ["reddit_ratio", "reddit_rz"],
                    lambda r=r: r["reddit_ratio"] >= 1.5,
                    lambda r=r: np.log(r["reddit_ratio"]),
                ),
                "wikipedia_attention": (
                    ["wiki_ratio", "wiki_rz"],
                    lambda r=r: r["wiki_ratio"] >= 1.5,
                    lambda r=r: np.log(r["wiki_ratio"]),
                ),
                "sentiment_level": (
                    ["sentiment"],
                    lambda r=r: r["sentiment"] >= 0.2,
                    lambda r=r: r["sentiment"],
                ),
                "sentiment_change": (
                    ["sentiment_delta"],
                    lambda r=r: r["sentiment_delta"] >= 0.1,
                    lambda r=r: r["sentiment_delta"],
                ),
            }
            valid = True
            for name, (fields, gate, term) in groups.items():
                if not active(name):
                    continue
                if not all(np.isfinite(r[k]) for k in fields) or any(
                    r[k] <= 0
                    for k in fields
                    if k in ["hh55", "vr", "reddit_ratio", "wiki_ratio"]
                ):
                    valid = False
                    break
                checks.append(gate())
                terms.append(term())
            if not valid:
                continue
            z = [
                r[s + "_rz"]
                for s, name in [
                    ("reddit", "reddit_attention"),
                    ("wiki", "wikipedia_attention"),
                ]
                if active(name)
            ]
            checks.extend([max(z) >= 2, np.isfinite(r["volume"]) and r["volume"] > 0])
            scores[t] = sum(terms)
        else:
            fields = {
                "reddit_attention": [
                    "prior_reddit_ratio",
                    "prior_reddit_rz",
                    "posts",
                    "prior_posts",
                    "reddit_ratio",
                ],
                "wikipedia_attention": ["prior_wiki_ratio", "prior_wiki_rz"],
                "sentiment_level": ["prior_sentiment", "sentiment"],
                "sentiment_change": ["sentiment_delta"],
                "prior_return": ["prior_return5"],
                "sma20": ["prior_close", "prior_sma20", "prior_atr"],
                "rsi14": ["prior_rsi", "rsi"],
                "price_confirmation": ["previous_high"],
            }
            if active("atr_predictive") and (
                not np.isfinite(r["prior_atr_pct"]) or r["prior_atr_pct"] <= 0
            ):
                continue
            if any(
                not np.isfinite(r[k])
                for name, keys in fields.items()
                if active(name)
                and not (name == "sma20" and not active("atr_predictive"))
                for k in keys
            ):
                continue
            gates = {
                "reddit_attention": lambda r=r: r["prior_reddit_ratio"] >= 3
                and r["prior_reddit_rz"] >= 3
                and r["prior_posts"] > 0
                and r["posts"] <= 0.75 * r["prior_posts"]
                and r["reddit_ratio"] >= 1.5,
                "wikipedia_attention": lambda r=r: r["prior_wiki_ratio"] >= 2
                and r["prior_wiki_rz"] >= 2,
                "sentiment_level": lambda r=r: r["prior_sentiment"] <= -0.3
                and r["sentiment"] > -0.1,
                "sentiment_change": lambda r=r: r["sentiment_delta"] >= 0.2,
                "prior_return": lambda r=r: r["prior_return5"] <= -0.08,
                "sma20": lambda r=r: r["prior_close"]
                <= r["prior_sma20"] - 2 * r["prior_atr"],
                "rsi14": lambda r=r: r["prior_rsi"] <= 30 and 30 < r["rsi"] <= 50,
                "price_confirmation": lambda r=r: r["close"] > r["previous_high"],
            }
            checks = [
                gate()
                for name, gate in gates.items()
                if active(name)
                and not (name == "sma20" and not active("atr_predictive"))
            ]
            scores[t] = (
                (r["sentiment_delta"] if active("sentiment_change") else 1)
                * (-r["prior_return5"] if active("prior_return") else 1)
                / (r["prior_atr_pct"] if active("atr_predictive") else 1)
            )
        eligible[t] = all(checks) and max(0.02, 2 * a) <= 0.1 and np.isfinite(scores[t])
    if strategy != "AGM_v2":
        eligible.loc[list(held)] = False
    names = sorted(eligible[eligible].index, key=lambda t: (-scores[t], t))[
        : 2 if strategy == "AGM_v2" else 2 - len(held)
    ]
    ungated = {
        t: min(0.5, 0.01 / max(0.02, 2 * frame.loc[t, "atr"] / frame.loc[t, "close"]))
        for t in names
    }
    targets = (
        {t: w * multiplier for t, w in ungated.items()}
        if regime and attention_ok
        else {}
    )
    return Plan(
        scores,
        eligible,
        ungated,
        targets,
        regime,
        (
            "ready"
            if regime is not None and attention_ok
            else "missing required regime/attention"
        ),
    )
