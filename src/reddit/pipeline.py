"""The Reddit pipeline on AWS: one container image, three modes.

  hourly  (container Lambda, EventBridge Scheduler every hour; feeds "Hot right now")
          Pull posts newer than each subreddit's high-water mark (raw/reddit/_state.json) from Arctic
          Shift, match tickers, score with FinBERT (shared cache), write raw/reddit/date=YYYY-MM-DD/HHMM.parquet
          and processed/reddit_hourly/date=YYYY-MM-DD/HHMM.parquet, then rebuild
          processed/reddit_current.parquet: the in-progress week plus trailing-7-day attention against
          the 8-week baseline, in attention-record columns (+ value_trailing_7d, as_of).
  weekly  (Fargate task, Mondays; feeds the research tables)
          Mirror the corpus state from S3, collect last week's complete days, then run the same steps
          as the local pipeline (build_posts, match_tickers, score_posts --scorer finbert, reddit_weekly),
          push back what changed and publish processed/reddit_weekly*.parquet and reddit_top_posts*.parquet.
  seed    (once, from a laptop) upload the local corpus state so the first weekly run has history.

The root is INDICATORLAB_ROOT_URI (default s3://$INDICATORLAB_BUCKET); a local folder works the same
way for testing. Each run prints a CloudWatch embedded-metric line (namespace IndicatorLab/Reddit) that
the alarms in infra/reddit/template.yaml watch.

    python -m src.reddit.pipeline --mode hourly
    python -m src.reddit.pipeline --mode weekly
    python -m src.reddit.pipeline --mode seed
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from src import config, storage
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient, ArcticShiftError
from src.reddit.build_posts import KEEP, _finish
from src.reddit.match_tickers import match_subreddit
from src.reddit.reddit_weekly import ATTENTION_COLS, ATTENTION_OUT, PROB_COLS
from src.reddit.score_posts import _score_finbert, rows_to_score
from src.reddit.spike_rule import add_spikes
from src.reddit.utils import epoch_to_iso, get_logger

log = get_logger("pipeline", "pipeline.log")

ROOT_ENV, BUCKET_ENV = "INDICATORLAB_ROOT_URI", "INDICATORLAB_BUCKET"
METRIC_NAMESPACE = "IndicatorLab/Reddit"
FIRST_LOOKBACK_S = 7 * 24 * 3600   # first run (no state yet) fills the trailing week; the page cap spreads it out
OVERLAP_S = 3 * 3600              # re-ask for this much before the high-water mark: Arctic Shift can ingest late
HOURLY_MAX_PAGES = 5              # per subreddit per run (100 posts a page): keeps a Lambda run well under 15 min
TRAILING_DAYS = 7
KEEP_HOURLY_DAYS = TRAILING_DAYS + 1
RAW_COLS = ["id", "subreddit", "subreddit_type", "created_utc", "title", "selftext", "score", "num_comments",
            "permalink", "removed_flag"]
HOURLY_COLS = ["post_id", "ticker", "market", "subreddit", "subreddit_type", "created_utc", "score",
               "sentiment_label", *PROB_COLS]
CURRENT_COLS = [*ATTENTION_COLS, "value_trailing_7d", "as_of"]
STATE_FILES = ["post_ticker_matches.parquet", "day_status.csv", "post_sentiment.parquet"]
STATE_DIRS = ["posts", "post_sentiment", "sentiment_cache"]


def root_uri() -> str:
    """Where the pipeline reads and writes: INDICATORLAB_ROOT_URI, else s3://$INDICATORLAB_BUCKET."""
    root = os.environ.get(ROOT_ENV) or f"s3://{os.environ[BUCKET_ENV]}"
    return root.rstrip("/")


def emit_metric(name: str, value: float, mode: str) -> None:
    """One CloudWatch Embedded Metric Format line on stdout (Lambda/ECS logs turn it into a metric)."""
    print(json.dumps({"_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [
        {"Namespace": METRIC_NAMESPACE, "Dimensions": [["Mode"]], "Metrics": [{"Name": name, "Unit": "Count"}]}]},
        "Mode": mode, name: value}))


# ----------------------------------------------------------------------------- hourly
def fetch_new(client: ArcticShiftClient, subreddit: str, after: int, before: int,
              max_pages: int = HOURLY_MAX_PAGES) -> list[dict]:
    """Posts of one subreddit created in (after, before), oldest first, paging like collect_day."""
    out: dict[str, dict] = {}
    for _ in range(max_pages):
        data = client.get("posts/search", {"subreddit": subreddit, "after": after, "before": before,
                                           "limit": "auto", "sort": "asc"}).body["data"]
        new = [p for p in data if p["id"] not in out]
        out.update({p["id"]: p for p in new})
        if not new or len(data) < 100:
            break
        after = max(int(p["created_utc"]) for p in data) - 1
    return list(out.values())


def _posts_frame(records: list[dict], now_iso: str) -> pd.DataFrame:
    """Arctic Shift records -> the corpus post table (same columns and flags as build_posts)."""
    df = pd.DataFrame([{**{k: r.get(k) for k in KEEP}, "page_retrieved_at_utc": now_iso,
                        "raw_file_date": epoch_to_iso(int(r["created_utc"]))[:10]} for r in records])
    status = pd.DataFrame({"subreddit": df["subreddit"].str.lower(), "date": df["raw_file_date"],
                           "day_status": "partial"}).drop_duplicates()
    return _finish(df, status, config.subreddit_map(settings.MARKET))


def _recent_partitions(root: str, prefix: str, now: datetime, columns: list[str]) -> pd.DataFrame:
    """Rows of the last KEEP_HOURLY_DAYS date partitions under `prefix` (raw/reddit or processed/reddit_hourly)."""
    parts = []
    for i in range(KEEP_HOURLY_DAYS + 1):
        t = storage.read_parquet_dir(f"{root}/{prefix}/date={(now - timedelta(days=i)).date()}", columns=columns)
        if t is not None:
            parts.append(t)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)


def _score_hourly(posts: pd.DataFrame, mt: pd.DataFrame, root: str) -> pd.DataFrame:
    """FinBERT label and probabilities for each matched (post, ticker) of this run (NaN where there is no text)."""
    to_score = rows_to_score(posts[["id", "title", "selftext", "removed_flag"]], mt)
    rows = mt.assign(market=mt["market"].astype(str).str.lower())
    if len(to_score):
        scored = _score_finbert(to_score, cache_uri=f"{root}/processed/sentiment_cache")
        rows = rows.merge(scored[["post_id", "ticker", "sentiment_label", *PROB_COLS]], on=["post_id", "ticker"],
                          how="left")
    for c in ["sentiment_label", *PROB_COLS]:
        if c not in rows:
            rows[c] = np.nan
    return rows[HOURLY_COLS]


def build_current(rows: pd.DataFrame, weekly_recent: pd.DataFrame | None, now: datetime,
                  market: str = settings.MARKET) -> pd.DataFrame:
    """Attention records for the in-progress week, with ratio/spike from the trailing 7 days vs the baseline.

    `value` counts posts since Monday; `value_trailing_7d` counts the last 7 days, and that number goes
    through the shared spike rule as if it were the next week after the last full week in `weekly_recent`.
    """
    week = (now - timedelta(days=now.weekday())).date()
    rows = rows.drop_duplicates(["post_id", "ticker"])
    created = pd.to_datetime(rows["created_utc"], unit="s", utc=True)
    in_week = rows[created >= pd.Timestamp(week, tz="UTC")]
    trailing = rows[created >= pd.Timestamp(now) - pd.Timedelta(days=TRAILING_DAYS)]
    out = pd.DataFrame({"ticker": config.tickers(market)})
    out["value"] = out["ticker"].map(in_week.groupby("ticker")["post_id"].nunique()).fillna(0)
    out["value_trailing_7d"] = out["ticker"].map(trailing.groupby("ticker")["post_id"].nunique()).fillna(0)
    sent = trailing.groupby("ticker")[PROB_COLS].mean()
    for c in PROB_COLS:
        out[c] = out["ticker"].map(sent[c])
    out["n_scored"] = out["ticker"].map(trailing.groupby("ticker")["sentiment_pos"].count()).fillna(0).astype(int)
    hist = (weekly_recent[["ticker", "week", "value"]].copy() if weekly_recent is not None and len(weekly_recent)
            else pd.DataFrame(columns=["ticker", "week", "value"]))
    hist["week"] = pd.to_datetime(hist["week"])
    hist = hist[hist["week"] < pd.Timestamp(week)]
    now_row = out[["ticker"]].assign(week=pd.Timestamp(week), value=out["value_trailing_7d"])
    flagged = add_spikes(pd.concat([hist, now_row], ignore_index=True), ["ticker"], "value")
    flagged = flagged[flagged["week"] == pd.Timestamp(week)].set_index("ticker")
    for c in ("baseline", "ratio", "spike"):
        out[c] = out["ticker"].map(flagged[c]) if c in flagged else np.nan
    out["spike"] = out["spike"].fillna(False).astype(bool)
    out["market"], out["source"], out["week"] = market.lower(), "reddit", week
    out["as_of"] = now.isoformat(timespec="seconds")
    return out[CURRENT_COLS]


def hourly(root: str | None = None, now: datetime | None = None, client: ArcticShiftClient | None = None) -> dict:
    """One hourly run; returns a small summary (also logged)."""
    root = root or root_uri()
    now = now or datetime.now(UTC)
    client = client or ArcticShiftClient()
    state_uri = f"{root}/raw/reddit/_state.json"
    state = storage.read_json(state_uri, default={"hwm": {}})
    seen = _recent_partitions(root, "processed/reddit_hourly", now, HOURLY_COLS)
    seen_ids = set(_recent_partitions(root, "raw/reddit", now, ["id"])["id"])
    before = int(now.timestamp())
    records, failed = [], []
    for v in config.subreddit_map(settings.MARKET).values():
        sub = v["subreddit"].lower()
        after = int(state["hwm"].get(sub, before - FIRST_LOOKBACK_S)) - OVERLAP_S
        try:
            got = fetch_new(client, v["subreddit"], after, before)
        except ArcticShiftError as e:
            log.error("hourly r/%s failed: %s", sub, e)
            failed.append(sub)
            continue
        records += got
        if got:
            state["hwm"][sub] = max(int(state["hwm"].get(sub, 0)), *(int(p["created_utc"]) for p in got))
    records = list({r["id"]: r for r in records if r["id"] not in seen_ids}.values())
    stamp, day = f"{now:%H%M}", now.date()
    if records:
        posts = _posts_frame(records, now.isoformat(timespec="seconds"))
        mt = pd.concat([match_subreddit(g) for _, g in posts.groupby("subreddit")], ignore_index=True)
        mt = mt[~mt["removed_flag"].astype(bool)]
        if len(mt):
            rows = _score_hourly(posts, mt, root)
            storage.write_parquet(rows, f"{root}/processed/reddit_hourly/date={day}/{stamp}.parquet")
            seen = pd.concat([seen, rows], ignore_index=True)
        # Raw last: the next run skips ids found here, so they must already be scored and stored above.
        storage.write_parquet(posts[RAW_COLS], f"{root}/raw/reddit/date={day}/{stamp}.parquet")
    weekly_recent_uri = f"{root}/processed/{ATTENTION_OUT['combined']}_recent.parquet"
    weekly_recent = storage.read_parquet(weekly_recent_uri) if storage.exists(weekly_recent_uri) else None
    current = build_current(seen, weekly_recent, now)
    storage.write_parquet(current, f"{root}/processed/reddit_current.parquet")
    storage.write_json(state, state_uri)
    emit_metric("PostsFetched", len(records), "hourly")
    summary = {"mode": "hourly", "new_posts": len(records), "failed_subreddits": failed,
               "hot": int((current["ratio"] > 1).sum())}
    log.info("hourly: %s", summary)
    return summary


# ----------------------------------------------------------------------------- weekly
def last_full_week(today: date) -> tuple[date, date]:
    """Monday and Sunday of the last complete week before `today`'s week."""
    monday = today - timedelta(days=today.weekday() + 7)
    return monday, monday + timedelta(days=6)


def _sync_state(root: str, down: bool, newer_than: float | None = None) -> int:
    """Copy the corpus state (raw archive, manifest, processed tables) between `root` and the local data dir."""
    pairs = [(f"{root}/raw/reddit/arctic_shift", settings.RAW_ARCTIC)]
    pairs += [(f"{root}/processed/reddit_state/{d}", settings.PROCESSED / d) for d in STATE_DIRS]
    n = 0
    for remote, local in pairs:
        n += storage.copy_tree(remote, local) if down else storage.copy_tree(local, remote, newer_than)
    files = [(f"{root}/raw/reddit/manifest.csv", settings.MANIFEST)]
    files += [(f"{root}/processed/reddit_state/{f}", settings.PROCESSED / f) for f in STATE_FILES]
    for remote, local in files:
        if down:
            n += storage.copy_file(remote, local)
        elif newer_than is None or (local.exists() and local.stat().st_mtime > newer_than):
            n += storage.copy_file(local, remote)
    return n


def publish(root: str) -> list[str]:
    """Copy the research and *_recent attention tables to processed/ at the root."""
    out = []
    for stem in ATTENTION_OUT.values():
        for name in (f"{stem}.parquet", f"{stem}_recent.parquet"):
            if storage.copy_file(settings.PROCESSED / name, f"{root}/processed/{name}"):
                out.append(name)
    return out


def weekly(root: str | None = None, today: date | None = None) -> dict:
    """Collect last week, rebuild every weekly table with the local pipeline code, push and publish."""
    from src.reddit import build_posts, collect_reddit, match_tickers, reddit_weekly, score_posts
    root = root or root_uri()
    log.info("weekly: pulled %d state files from %s", _sync_state(root, down=True), root)
    started = time.time()       # after the download, so only files this run writes are pushed back
    monday, sunday = last_full_week(today or datetime.now(UTC).date())
    collect_reddit.run_collect(argparse.Namespace(
        start=monday.isoformat(), end=sunday.isoformat(), allow_partial_today=False, subreddits=None,
        market=settings.MARKET, interval=settings.ARCTIC_MIN_INTERVAL_S, sample_days_per_year=0, seed=0,
        force=False, max_pages=collect_reddit.MAX_PAGES))
    build_posts.build()
    match_tickers.run()
    score_posts.run("finbert", confirm_llm_cost=False, rescore=True)   # cache: only new posts reach the model
    reddit_weekly.run()
    pushed = _sync_state(root, down=False, newer_than=started)
    published = publish(root)
    emit_metric("WeeklyRunSucceeded", 1, "weekly")
    summary = {"mode": "weekly", "week": f"{monday}..{sunday}", "state_files_pushed": pushed, "published": published}
    log.info("weekly: %s", summary)
    return summary


def seed(root: str | None = None) -> dict:
    """One-time upload of the local corpus state and published tables, so the first weekly run has history."""
    root = root or root_uri()
    summary = {"mode": "seed", "state_files": _sync_state(root, down=False), "published": publish(root)}
    log.info("seed: %s", summary)
    return summary


MODES = {"hourly": hourly, "weekly": weekly, "seed": seed}


def lambda_handler(event, context):
    """AWS Lambda entry point: {"mode": "hourly"} (default from PIPELINE_MODE)."""
    mode = (event or {}).get("mode") or os.environ.get("PIPELINE_MODE", "hourly")
    return MODES[mode]()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=list(MODES), default=os.environ.get("PIPELINE_MODE", "hourly"))
    a = ap.parse_args()
    MODES[a.mode]()
