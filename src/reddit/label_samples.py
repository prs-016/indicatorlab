"""Draw the Week 2 hand-labelling samples (research period only, seeded).

  sentiment  (Week 3) about 400 posts: for each of 10 tickers x 2 sources (product, stock) x 5 two-year
             buckets (2016-17 ... 2024-Sep 2025), PER_CELL_CORE core posts plus PER_CELL_RESERVE
             reserves. The 300 core posts come first in a shuffled order; reserves follow. DOUBLE_N
             core posts, spread over different cells, are marked `double` for the second rater.
             2023 onward comes from the research corpus; 2016-06 to 2022 from the label pool
             (src/reddit/label_pool.py: seeded random days per subreddit and year). Week 2's
             2023-2025-only draw had no labels yet, so redrawing it broke nothing.
  match      (Step 4) MATCH_PER_TICKER text-matched posts per ticker from non-product subreddits,
             uniformly within each ticker, to measure matching precision.

A sample that already has labels is never redrawn unless --force is given. Drawing from the
priority-pass days (see collect_reddit --sample-days-per-year) is still a random sample: the days
are seeded random draws and the posts are drawn at random within them.

Excluded from both: removed posts, posts from incompletely collected days, and posts that
text-match 5+ stocks (multi_ticker_list). Sentiment posts also need some text
(MIN_TEXT_CHARS of title + body). The page in src/reddit/label_server.py shows these files.

  human120   (Week 4) the human label check: 120 (post, ticker) items stratified by year (2016 .. the
             last research year) and investor vs product subreddits. Items come from the sentiment
             sample first; a cell it cannot fill (2022, and every month from 2025-10 to the cutoff) is
             topped up from the corpus and the label pool with the same exclusions. Half the items
             belong to joshua and half to james; HUMAN_OVERLAP_N of them (half from each side) are
             labelled by both, blind, for Cohen's kappa. James gets a blind CSV without owners,
             overlap flags or any model output.

    python -m src.reddit.label_samples sentiment
    python -m src.reddit.label_samples match
    python -m src.reddit.label_samples human120
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta

import numpy as np
import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.build_posts import attach_text
from src.reddit.label_pool import POOL_MATCHES
from src.reddit.match_tickers import clean_text
from src.reddit.reddit_weekly import SOURCE_OF_TYPE
from src.reddit.utils import get_logger, utc_now_iso
from src.reddit.validation_sample import context

log = get_logger("label_samples", "pipeline.log")

SEED = 42
PER_CELL_CORE = 3
PER_CELL_RESERVE = 1
DOUBLE_N = 50
MIN_TEXT_CHARS = 20
BODY_CHARS = 3000          # body text shown on the labelling page
CANDIDATES_PER_CELL = 40   # posts whose text is loaded per cell before the length filter
MATCH_PER_TICKER = 10


def year_buckets(first_year: int, last_year: int) -> dict[str, str]:
    """Year -> two-year bucket label, e.g. {"2016": "2016-17", "2017": "2016-17", ..., "2026": "2026"}."""
    out = {}
    for start in range(first_year, last_year + 1, 2):
        end = min(start + 1, last_year)
        label = f"{start}-{end % 100:02d}" if end > start else str(start)
        out.update({str(y): label for y in range(start, end + 1)})
    return out


# Two-year buckets over the team period: from the label pool's first year (config.yaml
# `reddit.label_pool.start`) to the last research year (the day before `holdout_start`).
YEAR_BUCKETS = year_buckets(config.load()["reddit"]["label_pool"]["start"].year,
                            (settings.HOLDOUT_START - timedelta(days=1)).year)
TEXT_COLS = ("title", "selftext", "permalink")

SENTIMENT_OUT = settings.VALIDATION / "sentiment_sample.csv"
SECOND_RATER_OUT = settings.VALIDATION / "sentiment_second_rater.csv"
MATCH_OUT = settings.VALIDATION / "match_precision_sample.csv"
HUMAN120_OUT = settings.VALIDATION / "human120_sample.csv"
JAMES_BLIND_OUT = settings.VALIDATION / "human120_james_blind.csv"
HUMAN_N = 120
HUMAN_OVERLAP_N = 30
HUMAN_RATERS = ("joshua", "james")
INVESTOR_TYPES = ("general", "sector", "stock")   # everything else (product) is the company/product group


def _guard(path, task: str, force: bool) -> None:
    """Refuse to redraw a sample that already has labels (item ids would no longer match them)."""
    labelled = sorted((settings.VALIDATION / "labels").glob(f"{task}_*.csv"))
    if path.exists() and labelled and not force:
        raise SystemExit(f"{path.name} already has labels ({', '.join(f.name for f in labelled)}); "
                         "pass --force only if you mean to start the labelling over")


def _population(include_pool: bool = False, include_recent: bool = False) -> pd.DataFrame:
    """Research-period matches eligible for labelling (plus the 2016-2022 label pool if asked).

    Corpus rows need a completely collected day; pool rows may come from a day cut at
    `label_pool.max_pages` pages, which still gives a random set of that day's posts.
    """
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet",
                         filters=None if include_recent else [("period", "==", "research")])
    mt = mt[mt["date"] < settings.HOLDOUT_START.isoformat()]   # `period` was set with an older cutoff
    mt = mt[mt["day_status"] == "complete"]
    if include_pool and POOL_MATCHES.exists():
        pool = pd.read_parquet(POOL_MATCHES)
        mt = pd.concat([mt, pool[pool["day_status"].isin(["complete", "partial"])]], ignore_index=True)
    assert (mt["date"] < settings.HOLDOUT_START.isoformat()).all()
    mt = mt[~mt["removed_flag"].astype(bool) & ~mt["multi_ticker_list"].astype(bool)].copy()
    mt["source"] = mt["subreddit_type"].map(SOURCE_OF_TYPE)
    mt["year"] = mt["date"].str[:4]
    return mt


def _with_text(df: pd.DataFrame) -> pd.DataFrame:
    """Add display text; pool rows already carry it, corpus rows read it from processed/posts/."""
    df = df.reset_index(drop=True)
    has = df["title"].notna() if "title" in df else pd.Series(False, index=df.index)
    parts = [df[has]] if has.any() else []
    if (~has).any():
        parts.append(attach_text(df[~has], TEXT_COLS))
    df = pd.concat(parts).loc[df.index]
    df["title"] = df["title"].map(clean_text)
    df["body"] = df["selftext"].map(lambda s: clean_text(s)[:BODY_CHARS])
    df["url"] = "https://www.reddit.com" + df["permalink"].fillna("")
    return df


def draw_sentiment(seed: int = SEED, force: bool = False) -> pd.DataFrame:
    """Stratified sentiment sample; writes SENTIMENT_OUT and the blind second-rater file."""
    _guard(SENTIMENT_OUT, "sentiment", force)
    rng = np.random.default_rng(seed)
    pop = _population(include_pool=True)
    pop["years"] = pop["year"].map(YEAR_BUCKETS)
    pop = pop[pop["years"].notna()]
    picked = []
    want = PER_CELL_CORE + PER_CELL_RESERVE
    for (tk, src, yrs), g in pop.groupby(["ticker", "source", "years"], sort=True):
        cand = _with_text(g.sample(min(len(g), CANDIDATES_PER_CELL), random_state=rng.integers(2**31)))
        cand = cand[(cand["title"].str.len() + cand["body"].str.len()) >= MIN_TEXT_CHARS].head(want)
        cand["core"] = np.arange(len(cand)) < PER_CELL_CORE      # a bool column even for an empty cell
        cand["cell"] = f"{tk}|{src}|{yrs}"
        picked.append(cand)
        if len(cand) < want:
            log.warning("cell %s/%s/%s has only %d usable posts", tk, src, yrs, len(cand))
    s = pd.concat(picked, ignore_index=True)
    s["core"] = s["core"].astype(bool)
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
    _meta(SENTIMENT_OUT, seed, pop, out.groupby(["source", "year"]).size().reset_index().values.tolist(),
          note="Week 3 redraw over 2016-06..2025-09 (no labels existed for the Week 2 draw); 2016-2022 posts "
               "come from the label pool of seeded random days, see src/reddit/label_pool.py")
    log.info("sentiment sample: %d posts (%d core, %d double) -> %s", len(out), int(out["core"].sum()),
             int(out["double"].sum()), SENTIMENT_OUT)
    return out


def _allocate(cells: list[str], n: int, rng: np.random.Generator) -> dict[str, int]:
    """Equal items per cell; the remainder goes to randomly chosen cells (seeded)."""
    base, extra = divmod(n, len(cells))
    lucky = set(rng.choice(cells, size=extra, replace=False)) if extra else set()
    return {c: base + (c in lucky) for c in cells}


def draw_human120(seed: int = SEED, force: bool = False) -> pd.DataFrame:
    """The Week 4 human label set; writes HUMAN120_OUT and James's blind file."""
    _guard(HUMAN120_OUT, "human120", force)
    rng = np.random.default_rng(seed)
    first = config.load()["reddit"]["label_pool"]["start"].year
    last = (settings.HOLDOUT_START - timedelta(days=1)).year
    cells = [f"{y}|{g}" for y in range(first, last + 1) for g in ("investor", "product")]
    quota = _allocate(cells, HUMAN_N, rng)

    def group(types: pd.Series) -> pd.Series:
        return np.where(types.isin(INVESTOR_TYPES), "investor", "product")

    old = pd.read_csv(SENTIMENT_OUT, dtype=str, keep_default_na=False)
    old["cell"] = old["year"] + "|" + group(old["subreddit_type"])
    old["from_item"] = old["item_id"]
    pop = _population(include_pool=True, include_recent=True)
    pop["cell"] = pop["year"] + "|" + group(pop["subreddit_type"])
    picked = []
    for cell in cells:
        want = quota[cell]
        have = old[old["cell"] == cell]
        take = have.sample(min(len(have), want), random_state=rng.integers(2**31))
        if len(take) < want:
            cand = pop[(pop["cell"] == cell) & ~pop.set_index(["post_id", "ticker"]).index.isin(
                list(zip(old["post_id"], old["ticker"])))]
            cand = _with_text(cand.sample(min(len(cand), CANDIDATES_PER_CELL), random_state=rng.integers(2**31)))
            cand = cand[(cand["title"].str.len() + cand["body"].str.len()) >= MIN_TEXT_CHARS]
            cand = cand.drop_duplicates(["post_id", "ticker"]).head(want - len(take)).assign(from_item="")
            take = pd.concat([take, cand], ignore_index=True)
        if len(take) < want:
            log.warning("human120 cell %s has only %d of %d items", cell, len(take), want)
        picked.append(take.assign(cell=cell))
    s = pd.concat(picked, ignore_index=True).sample(frac=1, random_state=seed).reset_index(drop=True)
    s["group"] = s["cell"].str.split("|").str[1]
    s["year"] = s["cell"].str.split("|").str[0]
    half = len(s) // 2
    s["owner"] = [HUMAN_RATERS[0]] * half + [HUMAN_RATERS[1]] * (len(s) - half)
    s["overlap"] = False
    for r in HUMAN_RATERS:      # half of the overlap from each rater's own items
        idx = s.index[s["owner"] == r][: HUMAN_OVERLAP_N // 2]
        s.loc[idx, "overlap"] = True
    s = s.sample(frac=1, random_state=seed + 1).reset_index(drop=True)   # owners and overlap are not in id order
    s = s.drop(columns=["item_id"], errors="ignore")   # reused rows carry their old s### id in from_item
    s.insert(0, "item_id", [f"h{i + 1:03d}" for i in range(len(s))])
    s["core"], s["double"] = True, s["overlap"]
    cols = ["item_id", "post_id", "ticker", "market", "subreddit", "subreddit_type", "group", "year",
            "created_utc_iso", "title", "body", "url", "owner", "overlap", "core", "double", "from_item", "cell"]
    out = s[cols]
    out.to_csv(HUMAN120_OUT, index=False)
    blind = out[(out["owner"] == "james") | out["overlap"]]
    blind[["item_id", "post_id", "ticker", "subreddit", "title", "body", "url"]].assign(label="").to_csv(
        JAMES_BLIND_OUT, index=False)
    _meta(HUMAN120_OUT, seed, pop, out.groupby("cell").size().reset_index().values.tolist(),
          note=f"Week 4 human label check: {HUMAN_N} items, {HUMAN_OVERLAP_N} labelled by both raters; "
               f"{int((out['from_item'] != '').sum())} reused from sentiment_sample.csv, the rest topped up")
    log.info("human120: %d items (%d overlap, %d reused) -> %s; James's blind file has %d", len(out),
             int(out["overlap"].sum()), int((out["from_item"] != "").sum()), HUMAN120_OUT, len(blind))
    return out


def draw_match(seed: int = SEED, force: bool = False) -> pd.DataFrame:
    """MATCH_PER_TICKER text-matched posts per ticker; population sizes saved for weighting."""
    _guard(MATCH_OUT, "match", force)
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


def _meta(path, seed: int, pop: pd.DataFrame, strata: list, note: str = "") -> None:
    """Write <sample>.meta.json: seed, draw time, population size and date range, strata counts."""
    path.with_suffix(".meta.json").write_text(json.dumps({
        "seed": seed, "drawn_at_utc": utc_now_iso(), "population_rows": len(pop),
        "population_date_range": [pop["date"].min(), pop["date"].max()], "strata": strata, "note": note},
        indent=2, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sample", choices=["sentiment", "match", "human120"])
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--force", action="store_true", help="redraw even if labels exist (they will no longer match)")
    a = ap.parse_args()
    {"sentiment": draw_sentiment, "match": draw_match, "human120": draw_human120}[a.sample](a.seed, a.force)
