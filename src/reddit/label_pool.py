"""Pre-2023 posts for the sentiment-label sample, kept apart from the research corpus.

The guide wants sentiment labels spread over 2016-2025-09, but the collected corpus starts in 2023.
A full 2016-2022 backfill is about a day of API calls, so this pulls a seeded random handful of days
per (subreddit, year) instead (config.yaml `reddit.label_pool`) and runs them through the same
collection, post-building and ticker-matching code as the corpus. Nothing here is written under
raw/arctic_shift/ or processed/posts/, so weekly tables and backtests never see these partial years.

    python -m src.reddit.label_pool collect     # download the sampled days (resumes; ~30-60 min)
    python -m src.reddit.label_pool build       # posts + ticker matches -> processed/label_pool/
"""
from __future__ import annotations

import argparse
from datetime import date

import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient
from src.reddit.build_posts import _finish, _read_day
from src.reddit.collect_reddit import collect_day, sample_days
from src.reddit.match_tickers import match_subreddit
from src.reddit.utils import daterange, get_logger, read_json_gz, write_json_gz

log = get_logger("label_pool", "pipeline.log")

CFG = config.load()["reddit"]["label_pool"]
RAW_POOL = settings.RAW / "label_pool"
POOL = settings.PROCESSED / "label_pool"
POOL_POSTS = POOL / "posts.parquet"
POOL_MATCHES = POOL / "matches.parquet"
TEXT_COLS = ["title", "selftext", "permalink"]


def pool_days(start: date, end: date, per_year: int, seed: int) -> list[date]:
    """Seeded random days from each calendar year between start and end (inclusive)."""
    return sample_days(list(daterange(start, end)), per_year, seed)


def raw_file(subreddit: str, d: date):
    """data/reddit/raw/label_pool/<sub>/<date>.json.gz"""
    return RAW_POOL / subreddit / f"{d:%Y-%m-%d}.json.gz"


def collect(client: ArcticShiftClient | None = None) -> pd.DataFrame:
    """Download every sampled (subreddit, day) not yet saved as complete; returns one status row per pair."""
    client = client or ArcticShiftClient()
    days = pool_days(CFG["start"], CFG["end"], CFG["days_per_year"], CFG["seed"])
    subs = [v["subreddit"] for v in config.subreddit_map(settings.MARKET).values()]
    rows = []
    for i, sub in enumerate(subs, 1):
        for d in days:
            f = raw_file(sub, d)
            if f.exists():
                raw = read_json_gz(f)
                if raw["status"] != "failed":
                    rows.append({"subreddit": sub, "date": d.isoformat(), "status": raw["status"]})
                    continue
            raw = collect_day(client, sub, d, max_pages=CFG["max_pages"])
            write_json_gz(f, raw)
            rows.append({"subreddit": sub, "date": d.isoformat(), "status": raw["status"]})
        log.info("label pool r/%s done (%d/%d subreddits, %d requests so far)", sub, i, len(subs), client.n_requests)
    return pd.DataFrame(rows)


def build() -> pd.DataFrame:
    """Posts and ticker matches of the pool, with text, in processed/label_pool/."""
    sub_map = config.subreddit_map(settings.MARKET)
    posts, matches = [], []
    for sub_dir in sorted(p for p in RAW_POOL.iterdir() if p.is_dir()):
        files = sorted(sub_dir.glob("*.json.gz"))
        raws = [read_json_gz(f) for f in files]
        records = [r for f in files for r in _read_day(str(f))]
        if not records:
            continue
        status = pd.DataFrame({"subreddit": sub_dir.name.lower(), "date": [r["date"] for r in raws],
                               "day_status": [r["status"] for r in raws]})
        p = _finish(pd.DataFrame(records), status, sub_map)
        posts.append(p)
        m = match_subreddit(p)
        matches.append(m.merge(p[["id", *TEXT_COLS]].rename(columns={"id": "post_id"}), on="post_id", how="left"))
    POOL.mkdir(parents=True, exist_ok=True)
    allp = pd.concat(posts, ignore_index=True)
    allm = pd.concat(matches, ignore_index=True)
    assert (allm["date"] < settings.HOLDOUT_START.isoformat()).all()
    allp.to_parquet(POOL_POSTS, index=False)
    allm.to_parquet(POOL_MATCHES, index=False)
    log.info("label pool: %d posts, %d (post, ticker) matches, %s", len(allp), len(allm),
             allm.groupby(allm["date"].str[:4]).size().to_dict())
    return allm


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["collect", "build"])
    a = ap.parse_args()
    out = collect() if a.step == "collect" else build()
    if a.step == "collect":
        log.info("label pool collect: %s", out["status"].value_counts().to_dict())
