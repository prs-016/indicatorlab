"""Draw a reproducible, stratified sample of 50 matched posts for manual validation.

Design (seed=42):
  * 4 rows per ticker (40): one cashtag, one ticker-symbol and two company-name
    matches where available, rotating subreddits.
  * 6 extra capitalised "Meta" company-name matches (the main ambiguity risk).
  * 4 extra ambiguous company-name matches for Apple / Amazon / Alphabet.
Each (post_id, ticker) appears at most once.

Output: data/reddit/validation/ticker_validation_50.csv with empty `agent_label`/`human_label`
columns. Agent labels are filled in a separate, explicit review step
(data/reddit/validation/agent_labels_50.csv) and merged by `--merge-labels`.
"""
from __future__ import annotations

import argparse
import json
import random
import re

import pandas as pd

from src.reddit import settings
from src.reddit.build_posts import attach_text
from src.reddit.match_tickers import clean_text
from src.reddit.utils import get_logger, utc_now_iso

log = get_logger("validation_sample", "pipeline.log")
SEED = 42
OUT = settings.VALIDATION / "ticker_validation_50.csv"
LABELS = settings.VALIDATION / "agent_labels_50.csv"


def context(row, width=150) -> str:
    for field in ("title", "selftext"):
        txt = clean_text(row[field])
        i = txt.find(row["matched_text"])
        if i < 0:
            m = re.search(re.escape(row["matched_text"]), txt, re.I)
            i = m.start() if m else -1
        if i >= 0:
            s, e = max(0, i - width), min(len(txt), i + len(row["matched_text"]) + width)
            snippet = txt[s:e].replace("\n", " ")
            return f"[{field}] " + ("…" if s else "") + snippet + ("…" if e < len(txt) else "")
    return ""


def draw(mt: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    rng = random.Random(seed)
    mt = mt.sort_values(["post_id", "ticker"]).reset_index(drop=True)
    chosen: list[int] = []
    taken: set[tuple[str, str]] = set()

    def pick(cands: pd.DataFrame, prefer_sub: str | None = None) -> bool:
        mask = pd.Series([(p, t) not in taken for p, t in zip(cands["post_id"], cands["ticker"])],
                         index=cands.index, dtype=bool)
        cands = cands[mask]
        if prefer_sub is not None and (cands["subreddit"] == prefer_sub).any():
            cands = cands[cands["subreddit"] == prefer_sub]
        if cands.empty:
            return False
        i = rng.choice(list(cands.index))
        chosen.append(i)
        taken.add((mt.at[i, "post_id"], mt.at[i, "ticker"]))
        return True

    subs = settings.SUBREDDITS
    for k, t in enumerate(settings.TICKERS):
        tk = mt[mt["ticker"] == t]
        for j, method in enumerate(["cashtag", "ticker", "company_name", "company_name"]):
            sub = subs[(k + j) % len(subs)]
            if not pick(tk[tk["match_method"] == method], sub):
                pick(tk, sub)   # fall back to any method for this ticker
    meta_amb = mt[(mt["ticker"] == "META") & (mt["match_method"] == "company_name") & mt["ambiguous_term"]]
    for j in range(6):
        pick(meta_amb, subs[j % 3])
    other_amb = mt[mt["ticker"].isin(["AAPL", "AMZN", "GOOGL"]) & mt["ambiguous_term"]]
    for j in range(4):
        pick(other_amb, subs[j % 3])
    while len(chosen) < 50:   # top up if any stratum was empty
        if not pick(mt):
            break
    s = mt.loc[chosen].copy()
    s.insert(0, "sample_no", range(1, len(s) + 1))
    return s


def build(seed: int = SEED) -> pd.DataFrame:
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet")
    mt = mt[(mt["day_status"] == "complete") & mt["subreddit"].isin(settings.SUBREDDITS)]   # Week 1 subreddits
    s = attach_text(draw(mt, seed), ("title", "selftext"))
    s["relevant_context"] = s.apply(context, axis=1)
    s["body_excerpt"] = s["selftext"].map(lambda x: clean_text(x)[:500].replace("\n", " "))
    s["url"] = "https://www.reddit.com" + s["permalink"].fillna("")
    out = s[["sample_no", "post_id", "subreddit", "created_utc_iso", "ticker", "matched_text", "match_method",
             "all_methods", "found_in", "ambiguous_term", "relevant_context", "title", "body_excerpt", "url"]].copy()
    for c in ["agent_label", "agent_reason", "human_label", "human_notes"]:
        out[c] = ""
    out["review_status"] = "unreviewed"
    out.to_csv(OUT, index=False)
    (settings.VALIDATION / "ticker_validation_50.meta.json").write_text(json.dumps({
        "seed": seed, "drawn_at_utc": utc_now_iso(), "population_rows": int(len(mt)),
        "population_date_range": [mt["date"].min(), mt["date"].max()],
        "strata": out.groupby(["ticker", "match_method"]).size().reset_index().values.tolist(),
    }, indent=2, default=str))
    log.info("wrote %s (%d rows)\n%s\n%s", OUT, len(out), out["ticker"].value_counts().to_dict(),
             out["match_method"].value_counts().to_dict())
    return out


def merge_labels() -> pd.DataFrame:
    """Merge the agent's explicit per-post review into the validation file and compute FPR."""
    v = pd.read_csv(OUT, dtype=str, keep_default_na=False)
    lab = pd.read_csv(LABELS, dtype=str, keep_default_na=False)
    assert set(lab["agent_label"]) <= {"correct", "incorrect", "uncertain"}
    v = v.drop(columns=["agent_label", "agent_reason"]).merge(
        lab[["sample_no", "post_id", "ticker", "agent_label", "agent_reason"]], on=["sample_no", "post_id", "ticker"],
        how="left", validate="one_to_one")
    assert v["agent_label"].notna().all() and len(v) == 50, "every sampled post needs an agent label"
    v["review_status"] = v["human_label"].map(lambda h: "agent+human reviewed" if h else "agent reviewed (human pending)")
    cols = [c for c in v.columns if c not in ("agent_label", "agent_reason", "human_label", "human_notes", "review_status")]
    v = v[cols + ["agent_label", "agent_reason", "human_label", "human_notes", "review_status"]]
    v.to_csv(OUT, index=False)
    n = len(v)
    inc, unc = (v["agent_label"] == "incorrect").sum(), (v["agent_label"] == "uncertain").sum()
    summary = {
        "reviewer": "Claude (AI agent) — not yet human-verified",
        "n": int(n), "correct": int((v["agent_label"] == "correct").sum()), "incorrect": int(inc), "uncertain": int(unc),
        "false_positive_rate": inc / n,
        "false_positive_rate_if_uncertain_counted_incorrect": (inc + unc) / n,
        "by_method": v.groupby("match_method")["agent_label"].value_counts().unstack(fill_value=0).to_dict("index"),
        "by_ticker_incorrect": v[v["agent_label"] == "incorrect"]["ticker"].value_counts().to_dict(),
    }
    (settings.TABLES / "ticker_validation_summary.json").write_text(json.dumps(summary, indent=2, default=int))
    log.info("validation: %s", summary)
    return v


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-labels", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    merge_labels() if a.merge_labels else build(a.seed)
