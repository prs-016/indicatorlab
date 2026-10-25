"""Flatten raw Arctic Shift day files into one de-duplicated post-level table.

Output: data/reddit/processed/posts.parquet (one row per Reddit post id) and
data/reddit/processed/day_status.csv (latest collection status per subreddit-day).
Posts from non-complete days are kept but carry `day_status` so downstream code
can exclude them; failed days are never turned into zero-activity days.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from src.reddit import settings
from src.reddit.collect_reddit import load_manifest_latest
from src.reddit.utils import get_logger, read_json_gz

log = get_logger("build_posts", "pipeline.log")

KEEP = ["id", "subreddit", "created_utc", "title", "selftext", "score", "num_comments", "author",
        "permalink", "upvote_ratio", "link_flair_text", "removed_by_category", "stickied", "over_18",
        "retrieved_on"]


def _read_day(path: str) -> list[dict]:
    raw = read_json_gz(Path(path))
    rows = []
    for pg in raw["pages"]:
        for p in pg["response"]["data"]:
            r = {k: p.get(k) for k in KEEP}
            r["page_retrieved_at_utc"] = pg["retrieved_at_utc"]
            r["raw_file_date"] = raw["date"]
            rows.append(r)
    return rows


def build(workers: int = 6) -> pd.DataFrame:
    latest = load_manifest_latest()
    files = [(k, v) for k, v in sorted(latest.items()) if v["status"] in ("complete", "partial")
             and (settings.ROOT / v["file"]).exists()]
    log.info("reading %d raw day files", len(files))
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for chunk in ex.map(_read_day, [str(settings.ROOT / v["file"]) for _, v in files], chunksize=8):
            rows.extend(chunk)
    df = pd.DataFrame(rows, columns=KEEP + ["page_retrieved_at_utc", "raw_file_date"])
    n_raw = len(df)
    df = df.sort_values("page_retrieved_at_utc").drop_duplicates("id", keep="last")
    log.info("records=%d unique post ids=%d (dropped %d page-overlap duplicates)", n_raw, len(df), n_raw - len(df))

    df["subreddit"] = df["subreddit"].str.lower()
    df["created_utc"] = pd.to_numeric(df["created_utc"], errors="raise").astype("int64")
    df["created_dt"] = pd.to_datetime(df["created_utc"], unit="s", utc=True)
    df["date"] = df["created_dt"].dt.strftime("%Y-%m-%d")
    bad_day = (df["date"] != df["raw_file_date"]).sum()
    if bad_day:
        log.warning("%d posts whose UTC date differs from their raw file date", bad_day)
    for c in ["score", "num_comments"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        n_na = df[c].isna().sum()
        if n_na:
            log.warning("%d posts with non-numeric %s", n_na, c)
    df["title"] = df["title"].fillna("")
    df["selftext"] = df["selftext"].fillna("")

    status = pd.DataFrame([{"subreddit": s, "date": d, "day_status": v["status"], "n_posts_manifest": v["n_posts"]}
                           for (s, d), v in latest.items()])
    df = df.merge(status[["subreddit", "date", "day_status"]], on=["subreddit", "date"], how="left")
    df = df.sort_values(["created_utc", "id"]).reset_index(drop=True)

    settings.PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(settings.PROCESSED / "posts.parquet", index=False)
    status.sort_values(["subreddit", "date"]).to_csv(settings.PROCESSED / "day_status.csv", index=False)
    log.info("wrote posts.parquet (%d posts) and day_status.csv (%d subreddit-days)", len(df), len(status))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    build(ap.parse_args().workers)
