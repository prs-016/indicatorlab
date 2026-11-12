"""Evaluate the hand labels (Week 2, Steps 4 and 5).

  match      matching precision from the hand-checked sample: per ticker (Wilson 95% CI) and overall,
             weighting each ticker by its share of text-matched posts (the sample is 10 per ticker).
             The overall CI is a normal approximation and is too narrow when some tickers score 10/10
             (their variance term is 0); read the per-ticker Wilson intervals alongside it.
  sentiment  Cohen's kappa between the two raters on the overlap posts, then accuracy and macro-F1
             of each scorer against the primary rater's labels, overall and separately for
             reddit_product and reddit_stock, with bootstrap 95% CIs (1,000 resamples)

Choice rule, fixed before any scorer was run on the labels: for each source, the scorer with the
highest macro-F1 wins; ties go to the cheaper scorer (vader, lm, finbert, llm in that order).
Skipped posts and "unsure" match checks are left out and counted.

    python -m src.reddit.label_eval match --rater joshua
    python -m src.reddit.label_eval sentiment --rater joshua --second james
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
)

from src import config
from src.reddit import settings
from src.reddit.label_samples import MATCH_OUT, SENTIMENT_OUT
from src.reddit.label_server import latest_labels
from src.reddit.sentiment_scorers import LABELS, run_scorer
from src.reddit.utils import get_logger

log = get_logger("label_eval", "pipeline.log")

SCORER_ORDER = ["vader", "lm", "finbert", "llm"]   # cheapest first, used to break ties
N_BOOT = 1000
SEED = 42
Z95 = 1.96
SOURCES = ["reddit_product", "reddit_stock"]


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def _labels_frame(task: str, rater: str) -> pd.DataFrame:
    rows = latest_labels(task, rater)
    return pd.DataFrame(rows.values()) if rows else pd.DataFrame(columns=["item_id", "label"])


# ----------------------------------------------------------------------------- Step 4
def match_precision(rater: str) -> pd.DataFrame:
    """Per-ticker and weighted overall precision of the text matcher."""
    items = pd.read_csv(MATCH_OUT, dtype=str)
    lab = items.merge(_labels_frame("match", rater)[["item_id", "label"]], on="item_id", how="left")
    meta = json.loads(MATCH_OUT.with_suffix(".meta.json").read_text())
    pop = {t: n for t, n in meta["strata"]}
    rows = []
    for tk, g in lab.groupby("ticker"):
        k, n = int((g["label"] == "correct").sum()), int(g["label"].isin(["correct", "incorrect"]).sum())
        lo, hi = wilson(k, n)
        rows.append({"ticker": tk, "checked": n, "correct": k, "unsure": int((g["label"] == "unsure").sum()),
                     "unlabelled": int(g["label"].isna().sum()), "precision": k / n if n else math.nan,
                     "ci_low": lo, "ci_high": hi, "population_matches": pop.get(tk, 0)})
    out = pd.DataFrame(rows)
    ok = out["checked"] > 0
    w = out.loc[ok, "population_matches"] / out.loc[ok, "population_matches"].sum()
    p = (w * out.loc[ok, "precision"]).sum()
    se = math.sqrt((w ** 2 * out.loc[ok, "precision"] * (1 - out.loc[ok, "precision"]) / out.loc[ok, "checked"]).sum())
    total = {"ticker": "ALL (weighted)", "checked": int(out["checked"].sum()), "correct": int(out["correct"].sum()),
             "unsure": int(out["unsure"].sum()), "unlabelled": int(out["unlabelled"].sum()), "precision": p,
             "ci_low": p - Z95 * se, "ci_high": p + Z95 * se,
             "population_matches": int(out["population_matches"].sum())}
    out = pd.concat([out, pd.DataFrame([total])], ignore_index=True)
    out.insert(0, "market", settings.MARKET)
    out.to_csv(settings.TABLES / "match_precision.csv", index=False)
    log.info("match precision (weighted) %.3f [%.3f, %.3f] on %d checked posts", p, p - Z95 * se, p + Z95 * se,
             total["checked"])
    return out


# ----------------------------------------------------------------------------- Step 5
def agreement(rater: str, second: str) -> dict:
    """Cohen's kappa on posts both raters labelled (skips by either rater excluded)."""
    a = _labels_frame("sentiment", rater)[["item_id", "label"]]
    b = _labels_frame("sentiment", second)[["item_id", "label"]]
    both = a.merge(b, on="item_id", suffixes=("_a", "_b"))
    both = both[(both["label_a"] != "skip") & (both["label_b"] != "skip")]
    kappa = cohen_kappa_score(both["label_a"], both["label_b"], labels=LABELS) if len(both) else math.nan
    out = {"rater": rater, "second_rater": second, "n_overlap": int(len(both)), "cohen_kappa": kappa,
           "raw_agreement": float((both["label_a"] == both["label_b"]).mean()) if len(both) else math.nan}
    log.info("agreement %s vs %s: kappa=%.3f on %d posts", rater, second, kappa, len(both))
    return out


def _boot_ci(y: np.ndarray, p: np.ndarray, metric, rng: np.random.Generator) -> tuple[float, float]:
    n = len(y)
    vals = [metric(y[idx], p[idx]) for idx in (rng.integers(0, n, n) for _ in range(N_BOOT))]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def _macro_f1(y, p) -> float:
    return f1_score(y, p, labels=LABELS, average="macro", zero_division=0)


def choose_scorers(table: pd.DataFrame) -> dict[str, str]:
    """The fixed choice rule: per source, the highest macro-F1; ties go to the cheaper scorer."""
    choice = {}
    for src in SOURCES:
        t = table[table["source"] == src]
        if len(t):
            best = t["macro_f1"].max()
            choice[src] = next(s for s in SCORER_ORDER if s in set(t.loc[t["macro_f1"] == best, "scorer"]))
    return choice


def compare_scorers(rater: str, scorers: list[str]) -> tuple[pd.DataFrame, dict]:
    """Accuracy and macro-F1 of each scorer vs the rater's labels; returns the table and the choice."""
    items = pd.read_csv(SENTIMENT_OUT, dtype=str, keep_default_na=False)
    gold = items.merge(_labels_frame("sentiment", rater)[["item_id", "label"]], on="item_id")
    n_skip = int((gold["label"] == "skip").sum())
    gold = gold[gold["label"] != "skip"].reset_index(drop=True)
    texts = (gold["title"] + "\n\n" + gold["body"]).str.strip().tolist()
    names = {t: c["name"] for t, c in config.stocks(settings.MARKET).items()}
    companies = gold["ticker"].map(names).tolist()
    rng = np.random.default_rng(SEED)
    rows, preds = [], {}
    for name in scorers:
        try:
            preds[name] = run_scorer(name, texts, companies)["label"].to_numpy()
        except (FileNotFoundError, RuntimeError) as e:
            log.warning("scorer %s skipped: %s", name, e)
            continue
        for src in ["all", *SOURCES]:
            m = np.ones(len(gold), bool) if src == "all" else (gold["source"] == src).to_numpy()
            y, p = gold.loc[m, "label"].to_numpy(), preds[name][m]
            if not len(y):
                continue
            acc_ci, f1_ci = _boot_ci(y, p, accuracy_score, rng), _boot_ci(y, p, _macro_f1, rng)
            rows.append({"scorer": name, "source": src, "n": int(len(y)), "accuracy": accuracy_score(y, p),
                         "accuracy_ci_low": acc_ci[0], "accuracy_ci_high": acc_ci[1], "macro_f1": _macro_f1(y, p),
                         "macro_f1_ci_low": f1_ci[0], "macro_f1_ci_high": f1_ci[1]})
            cm = confusion_matrix(y, p, labels=LABELS)
            pd.DataFrame(cm, index=[f"true_{x}" for x in LABELS], columns=[f"pred_{x}" for x in LABELS]).to_csv(
                settings.TABLES / f"sentiment_confusion_{name}_{src}.csv")
    table = pd.DataFrame(rows)
    table.insert(0, "market", settings.MARKET)
    table.to_csv(settings.TABLES / "sentiment_scorer_comparison.csv", index=False)
    choice = choose_scorers(table)
    pred_out = gold[["item_id", "post_id", "ticker", "source", "label"]].copy()
    for name, p in preds.items():
        pred_out[f"pred_{name}"] = p
    pred_out.to_csv(settings.TABLES / "sentiment_predictions_on_labels.csv", index=False)
    meta = {"rater": rater, "n_labelled": int(len(gold)), "n_skipped": n_skip, "choice": choice,
            "rule": "highest macro-F1 per source; ties to the cheaper scorer (vader < lm < finbert < llm)"}
    (settings.TABLES / "sentiment_choice.json").write_text(json.dumps(meta, indent=2))
    log.info("scorer choice: %s", choice)
    return table, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", choices=["match", "sentiment"])
    ap.add_argument("--rater", default="joshua")
    ap.add_argument("--second", help="second rater for Cohen's kappa")
    ap.add_argument("--scorers", nargs="*", default=SCORER_ORDER, choices=SCORER_ORDER)
    a = ap.parse_args()
    if a.task == "match":
        print(match_precision(a.rater).to_string(index=False))
        return
    if a.second:
        res = agreement(a.rater, a.second)
        (settings.TABLES / "sentiment_kappa.json").write_text(json.dumps(res, indent=2))
        print(res)
    table, meta = compare_scorers(a.rater, a.scorers)
    print(table.to_string(index=False))
    print(meta)


if __name__ == "__main__":
    main()
