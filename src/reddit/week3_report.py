"""Assemble docs/reddit/week3_report.md (committed) from the git-ignored Week 3 result files.

One section per Week 3 deliverable of Joshua's. A section whose inputs do not exist yet says
"pending" and what produces them, so the report can be regenerated after each step.

    python -m src.reddit.week3_report
"""
from __future__ import annotations

import json

import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.auto_label import RATER
from src.reddit.label_samples import SENTIMENT_OUT
from src.reddit.label_server import label_path
from src.reddit.reddit_weekly import ATTENTION_OUT, SENTIMENT_PATH
from src.reddit.utils import utc_now_iso
from src.reddit.week2_report import _md, _pending

OUT = settings.ROOT / "docs" / "reddit" / "week3_report.md"
T = settings.TABLES
COMPARISON_COLS = ["scorer", "source", "n", "accuracy", "accuracy_wilson_low", "accuracy_wilson_high", "macro_f1",
                   "macro_f1_ci_low", "macro_f1_ci_high"]
RECALL_COLS = ["scorer", "source", *[f"recall_{lab}{s}" for lab in ("positive", "negative", "neutral")
                                     for s in ("", "_ci_low", "_ci_high")]]
SOURCE_NAMES = {"all": "all", "reddit_product": "company/product subs", "reddit_stock": "investor subs"}


def section_sample() -> str:
    """Label sample: strata by source and year, and how pre-2023 posts were drawn."""
    if not SENTIMENT_OUT.exists():
        return _pending("`python -m src.reddit.label_pool collect && ... build`, then `label_samples sentiment`")
    s = pd.read_csv(SENTIMENT_OUT, dtype=str, keep_default_na=False)
    tab = pd.crosstab(s["year"], s["source"].map(SOURCE_NAMES)).reset_index()
    meta_p = SENTIMENT_OUT.with_suffix(".meta.json")
    note = json.loads(meta_p.read_text()).get("note", "") if meta_p.exists() else ""
    return (f"{len(s)} (post, ticker) items: {int((s['core'] == 'True').sum())} core, "
            f"{int((s['double'] == 'True').sum())} marked for the second rater; years "
            f"{s['year'].min()}-{s['year'].max()}.\n\n{_md(tab)}\n\n{note}")


def section_answer_key() -> str:
    """The Claude answer key: label counts, skips, fallbacks and agreement with the human check."""
    p = label_path("sentiment", RATER)
    if not p.exists():
        return _pending("Anthropic credentials in `.env`, then `python -m src.reddit.auto_label --confirm-cost`")
    lab = pd.read_csv(p, dtype=str, keep_default_na=False).drop_duplicates("item_id", keep="last")
    model = config.load()["sentiment"]["labeler_model"]
    counts = lab["label"].value_counts().rename_axis("label").reset_index(name="items")
    fallback = int(lab["note"].str.startswith("[").sum())
    out = [(f"No hand labels this week (Joshua's decision). `{model}` labelled every sampled item with the rubric in "
           "`src/reddit/prompts/label_v1.txt`; the scorers below are graded against that key."), "", _md(counts), "",
           f"Answers served by a fallback model after a policy decline: {fallback}.", "",
           ("**Caveats.** The key is model-made, not human. The Haiku LLM scorer is from the same model family as "
           "the labeller, which may flatter it. FinBERT and VADER are independent of it.")]
    k = T / "sentiment_kappa.json"
    if k.exists():
        r = json.loads(k.read_text())
        out.append(f"\n**Human check:** {r['second_rater']} vs {r['rater']} on {r['n_overlap']} posts: Cohen's kappa "
                   f"{r['cohen_kappa']:.2f} (95% CI {r['kappa_ci_low']:.2f}-{r['kappa_ci_high']:.2f}), raw agreement "
                   f"{r['raw_agreement']:.0%}.")
    else:
        out.append("\n**Human check:** pending (James blind-labels the 50 `double` posts; "
                   "`label_eval sentiment --second james`). Until then the key is unchecked.")
    return "\n".join(out)


def section_scorers() -> str:
    """FinBERT vs VADER vs LLM on the answer key, overall and by subreddit type."""
    p = T / "sentiment_scorer_comparison.csv"
    if not p.exists():
        return _pending("the answer key, then `python -m src.reddit.label_eval sentiment --scorers vader finbert llm`")
    d = pd.read_csv(p).assign(source=lambda x: x["source"].map(SOURCE_NAMES))
    out = ["Accuracy with Wilson 95% CI, macro-F1 with bootstrap 95% CI (1,000 resamples):", "",
           _md(d[[c for c in COMPARISON_COLS if c in d]])]
    if all(c in d for c in RECALL_COLS):
        out += ["", "Per-class recall (bootstrap 95% CI):", "", _md(d[RECALL_COLS])]
    c = T / "sentiment_choice.json"
    if c.exists():
        meta = json.loads(c.read_text())
        out.append(f"\n**Winner per source (macro-F1):** {meta['choice']}.")
        if set(meta["choice"].values()) != {"finbert"}:
            out.append("**FinBERT did not win everywhere: tell Prakhar before switching anything.**")
    return "\n".join(out)


def section_production() -> str:
    """The full-corpus rescore with the production scorer."""
    if not SENTIMENT_PATH.exists():
        return _pending("`python -m src.reddit.score_posts --scorer finbert` (about 6-7 h on Apple MPS)")
    s = pd.read_parquet(SENTIMENT_PATH, columns=["scorer", "model_version", "sentiment_label"])
    by = s.groupby(["scorer", "model_version"], dropna=False).size().rename("rows").reset_index()
    labels = s["sentiment_label"].value_counts(normalize=True).rename_axis("label").reset_index(name="share")
    return (f"{len(s):,} (post, ticker) rows scored. Every score is cached by (post_id, ticker, model_version) "
            "in `processed/sentiment_cache/`, so reruns never rescore.\n\n" + _md(by) + "\n\n" + _md(labels))


def section_weekly() -> str:
    """The attention-record parquet files the API and dashboard read."""
    rows = []
    for stem in ATTENTION_OUT.values():
        for suffix in ("", "_recent"):
            p = settings.PROCESSED / f"{stem}{suffix}.parquet"
            if p.exists():
                d = pd.read_parquet(p)
                rows.append({"file": p.name, "rows": len(d), "first_week": str(d["week"].min()),
                             "last_week": str(d["week"].max()),
                             "spikes": int(d["spike"].sum()) if "spike" in d else ""})
    if not rows:
        return _pending("`python -m src.reddit.reddit_weekly` after the rescore")
    return ("Columns follow the shared attention record (`ticker, market, source, week, value, baseline, ratio, "
            "spike, sentiment_pos, sentiment_neg, sentiment_neu, n_scored`); research files stop before "
            f"{settings.HOLDOUT_START}.\n\n" + _md(pd.DataFrame(rows)))


AWS_NOTE = _pending("shared AWS resources, the hourly/weekly Reddit runs and the `/reddit/*` router; "
                    "see `infra/README.md` once deployed")
UPSTREAM_NOTE = _pending("design issue A and the FinBERT scorer PR on HKUDS/Vibe-Trading (drafts in `docs/upstream/`)")
STRATEGY_NOTE = "On hold this week (Joshua's call); not started."

SECTIONS = [
    ("1. Label sample (2016 to Sep 2025)", section_sample),
    ("2. Answer key and agreement", section_answer_key),
    ("3. Scorer comparison: FinBERT vs VADER vs LLM", section_scorers),
    ("4. FinBERT as the production scorer", section_production),
    ("5. Weekly attention tables", section_weekly),
    ("6. AWS pipeline and Reddit API", lambda: AWS_NOTE),
    ("7. Open source A", lambda: UPSTREAM_NOTE),
    ("8. Strategies", lambda: STRATEGY_NOTE),
]


def build() -> str:
    """The whole report as markdown."""
    head = ["# Week 3 Reddit results (Joshua)", "",
            (f"Generated {utc_now_iso()[:16]} UTC by `python -m src.reddit.week3_report`. Research numbers use data "
            f"before {settings.HOLDOUT_START} only."), ""]
    body = [f"## {title}\n\n{fn()}\n" for title, fn in SECTIONS]
    return "\n".join(head + body)


if __name__ == "__main__":
    OUT.write_text(build())
    print(f"wrote {OUT}")
