"""Fill a gap in the hourly job's files from Arctic Shift's plain listing (no keyword search).

The hourly job's first run was on 2026-11-13 at 04:24 UTC. Posts created from ``holdout_start``
(2026-11-01) until then are in neither the saved corpus (it stops on Oct 31) nor the hourly files,
so on-demand counts for those weeks are too low (``coverage.missing_days``). This lists every post
of the saved subreddits in a window and writes them in the hourly files' format, one
``backfill.parquet`` per day::

    raw/reddit/date=YYYY-MM-DD/backfill.parquet               (pipeline.RAW_COLS)
    processed/reddit_hourly/date=YYYY-MM-DD/backfill.parquet  (pipeline.HOURLY_COLS, sentiment empty)

Each subreddit's listing is saved on the laptop first (``data/reddit/backfill/<window>/<sub>.parquet``),
so a rerun skips the subreddits already done. Only ``--upload`` writes the day files to the root
(default ``s3://indicatorlab-data``). Readers de-duplicate by Reddit id, so overlapping the hourly
files is harmless. Sentiment is left empty because only the trailing 7 days of hourly rows are scored
("Hot right now"); on-demand counts only need post ids, tickers and times.

    python -m src.reddit.backfill_hourly --start 2026-11-01 --end 2026-11-13T05:00            # fetch only
    python -m src.reddit.backfill_hourly --start 2026-11-01 --end 2026-11-13T05:00 --upload   # then write
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config, storage
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient, ArcticShiftError
from src.reddit.build_posts import KEEP
from src.reddit.match_tickers import match_subreddit
from src.reddit.on_demand import data_root
from src.reddit.pipeline import HOURLY_COLS, RAW_COLS, _posts_frame, fetch_new
from src.reddit.reddit_weekly import PROB_COLS
from src.reddit.utils import get_logger

log = get_logger("backfill_hourly", "backfill_hourly.log")

CHECKPOINTS = settings.DATA / "backfill"
MAX_PAGES = 10_000            # the whole window of one subreddit
BACKFILL_ATTEMPTS = 8         # patient: the client waits for each rate-limit reset
FILE_NAME = "backfill.parquet"


def _utc(s: str) -> datetime:
    t = datetime.fromisoformat(s)
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def fetch_subreddits(start: datetime, end: datetime, subs: list[str], folder: Path, client) -> list[str]:
    """List every post of each subreddit created in [start, end) into folder/<sub>.parquet.

    Subreddits that already have a file are skipped. Returns the subreddits that failed.
    """
    folder.mkdir(parents=True, exist_ok=True)
    failed = []
    for sub in subs:
        path = folder / f"{sub.lower()}.parquet"
        if path.exists():
            continue
        t0 = time.monotonic()
        try:
            recs = fetch_new(client, sub, int(start.timestamp()) - 1, int(end.timestamp()), max_pages=MAX_PAGES)
        except ArcticShiftError as e:
            log.error("r/%s failed: %s", sub, e)
            failed.append(sub)
            continue
        df = pd.DataFrame([{k: r.get(k) for k in KEEP} for r in recs], columns=KEEP)
        df.to_parquet(path, index=False)
        log.info("r/%s: %d posts in %.0fs", sub, len(df), time.monotonic() - t0)
    return failed


def build_day_files(records: list[dict], now: datetime) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """(raw rows, processed rows) per UTC date, in the hourly job's columns."""
    if not records:
        return {}, {}
    posts = _posts_frame(records, now.isoformat(timespec="seconds"))
    raw = {d: g[RAW_COLS].reset_index(drop=True) for d, g in posts.groupby("date")}
    mt = pd.concat([match_subreddit(g) for _, g in posts.groupby("subreddit")], ignore_index=True)
    mt = mt[~mt["removed_flag"].astype(bool)].copy()
    mt["market"] = mt["market"].astype(str).str.lower()
    mt["sentiment_label"] = pd.array([pd.NA] * len(mt), dtype="string")   # string type, like scored files
    for c in PROB_COLS:
        mt[c] = np.nan
    processed = {d: g[HOURLY_COLS].reset_index(drop=True) for d, g in mt.groupby("date")}
    return raw, processed


def write_day_files(root: str, raw: dict[str, pd.DataFrame], processed: dict[str, pd.DataFrame]) -> list[str]:
    """Write one backfill.parquet per day under raw/reddit and processed/reddit_hourly; returns the paths."""
    out = []
    for prefix, days in (("raw/reddit", raw), ("processed/reddit_hourly", processed)):
        for d, df in sorted(days.items()):
            uri = f"{root.rstrip('/')}/{prefix}/date={d}/{FILE_NAME}"
            storage.write_parquet(df, uri)
            out.append(uri)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", required=True, help="UTC, e.g. 2026-11-01")
    ap.add_argument("--end", required=True, help="UTC, exclusive, e.g. 2026-11-13T05:00")
    ap.add_argument("--upload", action="store_true", help="write the day files to --root (default: fetch only)")
    ap.add_argument("--root", default=None, help="default INDICATORLAB_ROOT_URI or s3://indicatorlab-data")
    a = ap.parse_args(argv)
    start, end = _utc(a.start), _utc(a.end)
    folder = CHECKPOINTS / f"{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}"
    subs = [v["subreddit"] for v in config.subreddit_map(settings.MARKET).values()]
    failed = fetch_subreddits(start, end, subs, folder, ArcticShiftClient(max_attempts=BACKFILL_ATTEMPTS))
    if failed:
        print(f"{len(failed)} subreddits failed ({failed}); run again to retry them. Nothing written.")
        return 1
    records = pd.concat([pd.read_parquet(p) for p in sorted(folder.glob("*.parquet"))],
                        ignore_index=True).to_dict("records")
    raw, processed = build_day_files(records, datetime.now(UTC))
    for d in sorted(raw):
        print(f"{d}: {len(raw[d])} posts, {len(processed.get(d, ()))} ticker matches")
    if not a.upload:
        print(f"Fetched {len(records)} posts into {folder}. Nothing written to the root (no --upload).")
        return 0
    paths = write_day_files(a.root or data_root(), raw, processed)
    print(f"Wrote {len(paths)} files, e.g. {paths[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
