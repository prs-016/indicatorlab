"""Draw the Week 2 hand-labelling samples (research period only, seeded).

  sentiment  (Step 5) about 360 posts: for each of 10 tickers x 2 sources (product, stock) x 3 years
             (2023, 2024, Jan-Sep 2025), PER_CELL_CORE core posts plus PER_CELL_RESERVE reserves.
             The 300 core posts come first in a shuffled order; reserves follow. DOUBLE_N core posts,
             spread over different cells, are marked `double` for the second rater.
  match      (Step 4) MATCH_PER_TICKER text-matched posts per ticker from non-product subreddits,
             uniformly within each ticker, to measure matching precision.

Excluded from both: removed posts, posts from incompletely collected days, and posts that
text-match 5+ stocks (multi_ticker_list). Sentiment posts also need some text
(MIN_TEXT_CHARS of title + body). The page in src/reddit/label_server.py shows these files.

    python -m src.reddit.label_samples sentiment
    python -m src.reddit.label_samples match
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.reddit import settings
from src.reddit.build_posts import attach_text
from src.reddit.match_tickers import clean_text
from src.reddit.reddit_weekly import SOURCE_OF_TYPE
from src.reddit.utils import get_logger, utc_now_iso
from src.reddit.validation_sample import context

log = get_logger("label_samples", "pipeline.log")

SEED = 42
PER_CELL_CORE = 5
PER_CELL_RESERVE = 1
DOUBLE_N = 50
MIN_TEXT_CHARS = 20
BODY_CHARS = 3000          # body text shown on the labelling page
CANDIDATES_PER_CELL = 40   # posts whose text is loaded per cell before the length filter
MATCH_PER_TICKER = 10
YEARS = ["2023", "2024", "2025"]

SENTIMENT_OUT = settings.VALIDATION / "sentiment_sample.csv"
SECOND_RATER_OUT = settings.VALIDATION / "sentiment_second_rater.csv"
MATCH_OUT = settings.VALIDATION / "match_precision_sample.csv"


def _population() -> pd.DataFrame:
    """Research-period matches eligible for labelling."""
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet",
                         filters=[("period", "==", "research")])
    assert (mt["date"] < settings.HOLDOUT_START.isoformat()).all()
    mt = mt[(mt["day_status"] == "complete") & ~mt["removed_flag"] & ~mt["multi_ticker_list"]].copy()
    mt["source"] = mt["subreddit_type"].map(SOURCE_OF_TYPE)
    mt["year"] = mt["date"].str[:4]
    return mt


def _with_text(df: pd.DataFrame) -> pd.DataFrame:
    df = attach_text(df.reset_index(drop=True), ("title", "selftext"))
    df["title"] = df["title"].map(clean_text)
    df["body"] = df["selftext"].map(lambda s: clean_text(s)[:BODY_CHARS])
    df["url"] = "https://www.reddit.com" + df["permalink"].fillna("")
    return df


def draw_sentiment(seed: int = SEED) -> pd.DataFrame:
    """Stratified sentiment sample; writes SENTIMENT_OUT and the blind second-rater file."""
    rng = np.random.default_rng(seed)
    pop = _population()
    picked = []
    want = PER_CELL_CORE + PER_CELL_RESERVE
    for (tk, src, yr), g in pop.groupby(["ticker", "source", "year"], sort=True):
        if yr not in YEARS:
            continue
        cand = _with_text(g.sample(min(len(g), CANDIDATES_PER_CELL), random_state=rng.integers(2**31)))
        cand = cand[(cand["title"].str.len() + cand["body"].str.len()) >= MIN_TEXT_CHARS].head(want)
        cand["core"] = [i < PER_CELL_CORE for i in range(len(cand))]
        cand["cell"] = f"{tk}|{src}|{yr}"
        picked.append(cand)
        if len(cand) < want:
            log.warning("cell %s/%s/%s has only %d usable posts", tk, src, yr, len(cand))
    s = pd.concat(picked, ignore_index=True)
    core = s[s["core"]].sample(frac=1, random_state=seed)
    cells = core["cell"].unique()
    double_cells = set(rng.choice(cells, size=min(DOUBLE_N, len(cells)), replace=False))
    core["double"] = False
    first_in_cell = ~core.duplicated("cell")
    core.loc[first_in_cell & core["cell"].isin(double_cells), "double"] = True
    reserve = s[~s["core"]].sample(frac=1, random_state=seed).assign(double=False)
    out = pd.concat([core, reserve], ignore_index=True)
    out.insert(0, "item_id", [f"s{i + 1:03d}" for i in range(len(out))])
    cols = ["item_id", "post_id", "ticker", "market", "subreddit", "subreddit_type", "source", "year",
            "created_utc_iso", "title", "body", "url", "core", "double", "cell"]
    out = out[cols]
    out.to_csv(SENTIMENT_OUT, index=False)
    out[out["double"]][["item_id", "post_id", "ticker", "subreddit", "title", "body", "url"]].assign(label="").to_csv(
        SECOND_RATER_OUT, index=False)
    _meta(SENTIMENT_OUT, seed, pop, out.groupby(["source", "year"]).size().reset_index().values.tolist())
    log.info("sentiment sample: %d posts (%d core, %d double) -> %s", len(out), int(out["core"].sum()),
             int(out["double"].sum()), SENTIMENT_OUT)
    return out


def draw_match(seed: int = SEED) -> pd.DataFrame:
    """MATCH_PER_TICKER text-matched posts per ticker; population sizes saved for weighting."""
    pop = _population()
    pop = pop[pop["subreddit_type"] != "product"]
    parts = [g.sample(min(len(g), MATCH_PER_TICKER), random_state=seed) for _, g in pop.groupby("ticker", sort=True)]
    s = _with_text(pd.concat(parts))
    s["context"] = s.apply(context, axis=1)
    s.insert(0, "item_id", [f"m{i + 1:03d}" for i in range(len(s))])
    s["core"], s["double"] = True, False
    out = s[["item_id", "post_id", "ticker", "market", "subreddit", "subreddit_type", "source", "created_utc_iso",
             "match_method", "matched_text", "context", "title", "body", "url", "core", "double"]]
    out.to_csv(MATCH_OUT, index=False)
    _meta(MATCH_OUT, seed, pop, pop.groupby("ticker").size().reset_index().values.tolist())
    log.info("match sample: %d posts -> %s", len(out), MATCH_OUT)
    return out


def _meta(path, seed: int, pop: pd.DataFrame, strata: list) -> None:
    path.with_suffix(".meta.json").write_text(json.dumps({
        "seed": seed, "drawn_at_utc": utc_now_iso(), "population_rows": int(len(pop)),
        "population_date_range": [pop["date"].min(), pop["date"].max()], "strata": strata}, indent=2, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", choices=["sentiment", "match"])
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    (draw_sentiment if a.sample == "sentiment" else draw_match)(a.seed)
