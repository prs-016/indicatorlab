"""Flatten raw Arctic Shift day files into one de-duplicated post-level table.

Output: data/reddit/processed/posts/<subreddit>.parquet (one row per Reddit post id) and
data/reddit/processed/day_status.csv (latest collection status per subreddit-day).
Posts from non-complete days are kept but carry `day_status` so downstream code
can exclude them; failed days are never turned into zero-activity days.

Columns include the Week 2 spec set (id, subreddit, created_utc, title, selftext, score,
num_comments, author, removed_flag) plus `market`, `subreddit_type` and `owner_ticker`
from config.yaml, and `period`: "research" before the holdout date, "recent" from it on.
Research code must use only `period == "research"` rows (see `load_posts`).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.collect_reddit import load_manifest_latest
from src.reddit.utils import REMOVED_TEXT, get_logger, read_json_gz

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


def _finish(df: pd.DataFrame, status: pd.DataFrame, sub_map: dict) -> pd.DataFrame:
    """Deduplicate one subreddit's records and add the derived columns."""
    n_raw = len(df)
    df = df.sort_values("page_retrieved_at_utc").drop_duplicates("id", keep="last")
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
    df["removed_flag"] = df["removed_by_category"].notna() | df["selftext"].str.strip().str.lower().isin(REMOVED_TEXT)

    unknown = sorted(set(df["subreddit"]) - set(sub_map))
    if unknown:
        raise ValueError(f"subreddits missing from config.yaml: {unknown}")
    df["market"] = settings.MARKET
    df["subreddit_type"] = df["subreddit"].map(lambda s: sub_map[s]["type"])
    df["owner_ticker"] = df["subreddit"].map(lambda s: sub_map[s]["ticker"])
    df["period"] = np.where(df["date"] < settings.HOLDOUT_START.isoformat(), "research", "recent")
    df = df.merge(status[["subreddit", "date", "day_status"]], on=["subreddit", "date"], how="left")
    log.info("r/%s: records=%d unique posts=%d", df["subreddit"].iloc[0] if len(df) else "?", n_raw, len(df))
    return df.sort_values(["created_utc", "id"]).reset_index(drop=True)


def build(workers: int = 4, force: bool = False) -> pd.DataFrame:
    """Write one parquet file of posts per subreddit (posts/<subreddit>.parquet) and day_status.csv.

    One subreddit at a time keeps memory low. A subreddit whose file is newer than its latest
    manifest row is skipped unless `force`. Returns the day-status table.
    """
    latest = load_manifest_latest()
    sub_map = config.subreddit_map(settings.MARKET)
    status = pd.DataFrame([{"subreddit": s.lower(), "date": d, "day_status": v["status"],
                            "n_posts_manifest": v["n_posts"]} for (s, d), v in latest.items()])
    settings.POSTS.mkdir(parents=True, exist_ok=True)
    by_sub: dict[str, list[dict]] = {}
    for (sub, _), v in sorted(latest.items()):
        by_sub.setdefault(sub, []).append(v)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for sub, rows_meta in by_sub.items():
            out = settings.POSTS / f"{sub.lower()}.parquet"
            last = max(pd.Timestamp(v["last_retrieved_utc"]) for v in rows_meta if v["last_retrieved_utc"])
            if not force and out.exists() and pd.Timestamp(out.stat().st_mtime, unit="s", tz="UTC") > last:
                continue
            files = [str(settings.ROOT / v["file"]) for v in rows_meta
                     if v["status"] in ("complete", "partial") and (settings.ROOT / v["file"]).exists()]
            rows: list[dict] = []
            for chunk in ex.map(_read_day, files, chunksize=8):
                rows.extend(chunk)
            df = pd.DataFrame(rows, columns=KEEP + ["page_retrieved_at_utc", "raw_file_date"])
            _finish(df, status, sub_map).to_parquet(out, index=False)
    status.sort_values(["subreddit", "date"]).to_csv(settings.PROCESSED / "day_status.csv", index=False)
    log.info("posts in %s, day_status.csv (%d subreddit-days)", settings.POSTS, len(status))
    return status


def load_posts(period: str = "research", columns: list[str] | None = None,
               subreddits: list[str] | None = None) -> pd.DataFrame:
    """Posts of one period ("research" = before the holdout date, "recent" = from it on).

    Research code calls this with the default so holdout posts can never leak in. `subreddits`
    limits which per-subreddit files are read.
    """
    cols = sorted(set(columns) | {"period", "date"}) if columns else None
    files = sorted(settings.POSTS.glob("*.parquet"))
    if subreddits is not None:
        wanted = {s.lower() for s in subreddits}
        files = [f for f in files if f.stem in wanted]
    parts = [pd.read_parquet(f, columns=cols, filters=[("period", "==", period)]) for f in files]
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols or [])
    if period == "research":
        assert (df["date"] < settings.HOLDOUT_START.isoformat()).all(), "holdout posts in research data"
    return df


def attach_text(df: pd.DataFrame, cols: tuple[str, ...] = ("title", "selftext", "permalink")) -> pd.DataFrame:
    """Add post text columns to rows keyed by `post_id` (the matches table carries no text)."""
    out = []
    for sub, g in df.groupby("subreddit"):
        f = settings.POSTS / f"{sub.lower()}.parquet"
        txt = pd.read_parquet(f, columns=["id", *cols], filters=[("id", "in", list(g["post_id"].unique()))])
        out.append(g.merge(txt.rename(columns={"id": "post_id"}), on="post_id", how="left"))
    return pd.concat(out).loc[df.index] if out else df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="rebuild every subreddit file")
    a = ap.parse_args()
    build(a.workers, a.force)
