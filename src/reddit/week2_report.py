"""Assemble docs/reddit/week2_report.md (committed) from the git-ignored result tables.

One section per item the PDF asks Joshua to bring to the meeting. Sections whose inputs do not
exist yet say "pending" and what produces them, so the report can be regenerated after each step.

    python -m src.reddit.week2_report
"""
from __future__ import annotations

import json

import pandas as pd

from src.reddit import settings
from src.reddit.utils import utc_now_iso

OUT = settings.ROOT / "docs" / "reddit" / "week2_report.md"
T = settings.TABLES


def _md(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    """A pandas table as a GitHub markdown table (no extra dependency)."""
    def fmt(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else floatfmt.format(v)
        return str(v)
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(v).replace("|", "/") for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def _pending(what: str) -> str:
    return f"_Pending: {what}._"


def section_subreddits() -> str:
    p = T / "subreddit_map.csv"
    if not p.exists():
        return _pending("`python -m src.reddit.subreddit_map`")
    d = pd.read_csv(p)
    d = d[["ticker", "subreddit", "type", "subscribers", "first_post_utc", "posts_per_week_2024", "volume_method",
           "kept", "reason"]].fillna({"ticker": "(sector)"})
    d["first_post_utc"] = d["first_post_utc"].str[:10]
    return _md(d, "{:,.1f}")


def section_collection() -> str:
    p = T / "collection_summary.csv"
    if not p.exists():
        return _pending("`python -m src.reddit.collect_reddit status --end 2025-09-30`")
    d = pd.read_csv(p)
    cols = ["subreddit", "type", "ticker", "start", "end", "days_expected", "complete", "failed", "partial", "missing",
            "posts_in_complete_days", "raw_storage_mb"]
    d = d[[c for c in cols if c in d.columns]]
    total = f"**Total:** {int(d['posts_in_complete_days'].sum()):,} posts, {int(d['failed'].sum())} failed days, " \
            f"{d['raw_storage_mb'].sum():,.0f} MB of raw JSON (gzip)." if "raw_storage_mb" in d else ""
    fails = pd.read_csv(p, dtype={"failed_or_partial_dates": str}, keep_default_na=False)
    bad = fails[fails["failed_or_partial_dates"] != ""][["subreddit", "failed_or_partial_dates"]]
    out = _md(d, "{:,.1f}") + "\n\n" + total
    if len(bad):
        out += "\n\nFailed or partial days:\n\n" + _md(bad)
    return out


def section_labels() -> str:
    parts = []
    k = T / "sentiment_kappa.json"
    parts.append(_md(pd.DataFrame([json.loads(k.read_text())])) if k.exists() else
                 _pending("second rater's 50 labels, then `label_eval sentiment --second <name>`"))
    c = T / "sentiment_choice.json"
    if c.exists():
        meta = json.loads(c.read_text())
        parts.append(f"Labelled by {meta['rater']}: {meta['n_labelled']} posts used, {meta['n_skipped']} skipped.")
    m = T / "match_precision.csv"
    parts.append("**Match precision (hand-checked):**\n\n" + (_md(pd.read_csv(m)) if m.exists() else
                                                             _pending("100 match checks, then `label_eval match`")))
    return "\n\n".join(parts)


def section_scorers() -> str:
    p = T / "sentiment_scorer_comparison.csv"
    if not p.exists():
        return _pending("300+ sentiment labels, then `label_eval sentiment`")
    d = pd.read_csv(p)
    out = _md(d[["scorer", "source", "n", "accuracy", "accuracy_ci_low", "accuracy_ci_high", "macro_f1",
                 "macro_f1_ci_low", "macro_f1_ci_high"]])
    c = T / "sentiment_choice.json"
    if c.exists():
        meta = json.loads(c.read_text())
        out += f"\n\n**Chosen:** {meta['choice']} ({meta['rule']})."
    return out


def section_cause() -> str:
    p, q = T / "cause_vs_reaction.csv", T / "cause_vs_reaction_direction.csv"
    if not p.exists():
        return _pending("full collection and scoring, then `python -m src.reddit.cause_reaction`")
    d = pd.read_csv(p)
    pooled = d[d["scope"] == "pooled"][["direction", "x", "y", "lag", "n", "pearson", "spearman", "ci_low", "ci_high",
                                        "block_ci_low", "block_ci_high"]]
    out = "**Pooled correlations (z-scored within stock, 95% bootstrap CIs over weeks):**\n\n" + _md(pooled)
    if q.exists():
        out += ("\n\n**Which direction is stronger** (|forward r| - |reverse r|; CI above 0 = product leads):\n\n"
                + _md(pd.read_csv(q)))
    return out


def section_spike_check() -> str:
    p = T / "last3weeks_spikes.csv"
    if not p.exists():
        return _pending("collection run B, then `python -m src.reddit.spike_check_recent`")
    d = pd.read_csv(p)
    cols = ["ticker", "week", "product_spike", "stock_spike", "wiki_views_spike", "wiki_edits_spike", "product_ratio",
            "stock_ratio", "ret_week", "ret_next_week", "first_spike_day_product", "first_spike_day_stock"]
    notes = settings.ROOT / "docs" / "reddit" / "last3weeks_notes.md"
    out = _md(d[[c for c in cols if c in d.columns]])
    out += "\n\n" + (notes.read_text() if notes.exists() else _pending("notes per spiking stock (read the posts)"))
    return out


def section_strategy() -> str:
    p = settings.STRATEGY_LOGS / "strategy_log_week2.csv"
    if not p.exists():
        return _pending("`python -m src.reddit.strategy_product_buzz`")
    d = pd.read_csv(p)
    last = d[d["run_id"] == d["run_id"].iloc[-1]]
    cols = ["strategy", "train_sharpe", "test_sharpe", "index_sharpe_test", "ew_sharpe_test", "pct_random_beaten_train",
            "pct_random_beaten_test", "test_max_drawdown", "test_turnover", "n_trades_train", "n_trades_test",
            "decision", "why", "notes"]
    return f"Run `{last['run_id'].iloc[0]}` (every run is kept in the append-only log):\n\n" + _md(last[cols])


API_NOTE = ("`GET /sentiment` and `GET /spikes` in `src/api/reddit.py`, tested in `tests/test_api_reddit.py`. "
            "Run `.venv/bin/uvicorn src.api.main:app` and open `/docs`.")

SECTIONS = [
    ("1. Subreddit map", section_subreddits),
    ("2. Posts pulled and failed days (research window)", section_collection),
    ("3. Hand labels and agreement", section_labels),
    ("4. Sentiment scorer comparison", section_scorers),
    ("5. Cause vs reaction", section_cause),
    ("6. Last-3-weeks spike check", section_spike_check),
    ("7. API endpoints", lambda: API_NOTE),
    ("8. Strategy results", section_strategy),
]


def build() -> str:
    """The whole report as markdown."""
    head = ["# Week 2 Reddit results (Joshua)", "",
            f"Generated {utc_now_iso()[:16]} UTC by `python -m src.reddit.week2_report`. Research numbers use data "
            "before 2025-10-01 only; the spike check (section 6) looks at the holdout weeks without testing.", ""]
    body = [f"## {title}\n\n{fn()}\n" for title, fn in SECTIONS]
    return "\n".join(head + body)


if __name__ == "__main__":
    OUT.write_text(build())
    print(f"wrote {OUT}")
