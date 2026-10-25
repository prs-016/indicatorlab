"""Collect historical Reddit submissions from Arctic Shift, one UTC day per subreddit.

Subcommands
-----------
collect   Download every (subreddit, day) in a date range with pagination,
          checkpointing and resume. Only days recorded as `complete` are skipped.
coverage  Find the earliest available post per subreddit (limit=1&sort=asc) and
          verify it with an independent second request.
verify    Spot-check archived days: an independent sort=desc request for the day
          must return only post IDs that already exist in the archive.
status    Summarise the manifest (complete / partial / failed / missing days).

Raw responses are stored per (subreddit, day) at
data/reddit/raw/arctic_shift/<subreddit>/<YYYY>/<YYYY-MM-DD>.json.gz together with the
request URL, parameters, UTC retrieval time, HTTP status, attempts and record count
of every page.
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timezone
from pathlib import Path

from src import config
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient, ArcticShiftError
from src.reddit.utils import (
    daterange,
    day_bounds_epoch,
    epoch_to_iso,
    get_logger,
    read_json_gz,
    utc_now_iso,
    write_json_gz,
)

log = get_logger("collect_reddit", "collect_reddit.log")

COLLECTOR_VERSION = "1.0"
MAX_PAGES = 300
MANIFEST_FIELDS = ["subreddit", "date", "status", "n_posts", "n_pages", "n_http_attempts",
                   "first_retrieved_utc", "last_retrieved_utc", "file", "note"]


# ----------------------------------------------------------------------------- manifest
def raw_path(subreddit: str, d: date) -> Path:
    return settings.RAW_ARCTIC / subreddit / f"{d:%Y}" / f"{d:%Y-%m-%d}.json.gz"


def append_manifest(row: dict) -> None:
    new = not settings.MANIFEST.exists()
    settings.MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.MANIFEST, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


def load_manifest_latest() -> dict[tuple[str, str], dict]:
    """Latest manifest row per (subreddit, date) — the manifest is append-only."""
    latest: dict[tuple[str, str], dict] = {}
    if settings.MANIFEST.exists():
        with open(settings.MANIFEST, newline="") as f:
            for row in csv.DictReader(f):
                latest[(row["subreddit"], row["date"])] = row
    return latest


# ----------------------------------------------------------------------------- collection
def collect_day(client: ArcticShiftClient, subreddit: str, d: date, max_pages: int = MAX_PAGES,
                min_page_size: int = 100) -> dict:
    """Download all submissions of one subreddit for one UTC day.

    Pagination: sort=asc with an exclusive `after`. Each next page starts at
    `after = last_created_utc - 1` so that posts sharing the final second of a page
    are not skipped; overlap is removed by de-duplicating on post id. Paging stops
    when a page holds fewer than `min_page_size` records (the window is exhausted) or
    contributes no new ids. If a page with no new ids is full (>= the API's minimum
    page size of 100 observed for limit=auto), more posts may share that one second
    than fit in a page, so the day is marked `partial` rather than complete.

    The short-page stop was checked on the 12,059 Week 1 pages (Oct 2026): a page with
    fewer than 100 records was never followed by a page adding new ids.
    """
    start, end = day_bounds_epoch(d)
    after = start
    pages, errors = [], []
    seen: set[str] = set()
    status, note = "complete", ""
    out_of_window = 0
    for page_no in range(1, max_pages + 1):
        params = {"subreddit": subreddit, "after": after, "before": end, "limit": "auto", "sort": "asc"}
        try:
            res = client.get("posts/search", params)
        except ArcticShiftError as e:
            status, note = "failed", str(e)
            errors.append({"page": page_no, "error": str(e), "attempts": e.attempts})
            break
        data = res.body["data"]
        new_ids = [p["id"] for p in data if p["id"] not in seen]
        seen.update(new_ids)
        out_of_window += sum(1 for p in data if not (start <= int(p["created_utc"]) < end))
        pages.append({
            "page": page_no, "url": res.url, "params": res.params, "retrieved_at_utc": res.retrieved_at_utc,
            "http_status": res.http_status, "attempts": res.attempts, "n_records": len(data),
            "n_new": len(new_ids), "response": res.body,
        })
        if not new_ids:
            if len(data) >= min_page_size:
                status, note = "partial", f"possible tie overflow: full page with no new ids after={after}"
            break
        if len(data) < min_page_size:
            break   # short page: nothing left in the window
        next_after = max(int(p["created_utc"]) for p in data) - 1
        if next_after <= after:
            # >1 page of posts inside one second: cannot page further with second resolution.
            status, note = "partial", f"tie overflow at {after + 1}"
            break
        after = next_after
    else:
        status, note = "partial", f"hit max_pages={max_pages}"

    if out_of_window:
        note = (note + "; " if note else "") + f"{out_of_window} records outside day window"
    return {
        "collector_version": COLLECTOR_VERSION,
        "source": "arctic_shift",
        "endpoint": f"{client.base_url}/posts/search",
        "subreddit": subreddit,
        "date": d.isoformat(),
        "window_utc": {"after": start, "before": end, "after_iso": epoch_to_iso(start), "before_iso": epoch_to_iso(end)},
        "status": status,
        "note": note,
        "n_posts_unique": len(seen),
        "n_pages": len(pages),
        "pages": pages,
        "errors": errors,
    }


def run_collect(args) -> None:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else settings.default_end_date()
    today = datetime.now(timezone.utc).date()
    if end >= today and not args.allow_partial_today:
        log.warning("end %s is not a completed UTC day; clamping to %s", end, settings.default_end_date())
        end = settings.default_end_date()
    subs = args.subreddits or config.subreddits(args.market)
    client = ArcticShiftClient(min_interval=args.interval)
    latest = load_manifest_latest()
    todo = [(d, s) for d in daterange(start, end) for s in subs
            if args.force or latest.get((s, d.isoformat()), {}).get("status") != "complete"
            or not raw_path(s, d).exists()]
    log.info("collect %s..%s subs=%s: %d (day,sub) pairs to fetch", start, end, subs, len(todo))
    done = 0
    for d, s in todo:
        result = collect_day(client, s, d, max_pages=args.max_pages)
        path = raw_path(s, d)
        write_json_gz(path, result)
        retrieved = [p["retrieved_at_utc"] for p in result["pages"]]
        append_manifest({
            "subreddit": s, "date": d.isoformat(), "status": result["status"],
            "n_posts": result["n_posts_unique"] if result["status"] != "failed" else "",
            "n_pages": result["n_pages"],
            "n_http_attempts": sum(len(p["attempts"]) for p in result["pages"]) + sum(len(e["attempts"]) for e in result["errors"]),
            "first_retrieved_utc": retrieved[0] if retrieved else "", "last_retrieved_utc": retrieved[-1] if retrieved else utc_now_iso(),
            "file": str(path.relative_to(settings.ROOT)), "note": result["note"],
        })
        done += 1
        lvl = log.info if result["status"] == "complete" else log.error
        lvl("[%d/%d] r/%s %s: %s, %d posts, %d pages %s", done, len(todo), s, d, result["status"],
            result["n_posts_unique"], result["n_pages"], result["note"])
    log.info("finished; total HTTP requests this run: %d", client.n_requests)


# ----------------------------------------------------------------------------- coverage
def run_coverage(args) -> None:
    client = ArcticShiftClient(min_interval=args.interval)
    rows = []
    for s in args.subreddits or config.subreddits(args.market):
        params = {"subreddit": s, "limit": 1, "sort": "asc"}
        row = {"subreddit": s, "retrieval_utc": utc_now_iso(), "request_url": "", "earliest_post_utc": "",
               "earliest_created_utc_epoch": "", "earliest_post_id": "", "earliest_post_title": "",
               "verified": False, "verification_url": "", "note": ""}
        try:
            res = client.get("posts/search", params)
            row["request_url"] = res.url
            write_json_gz(settings.RAW_COVERAGE / f"earliest_{s}.json.gz",
                          {"url": res.url, "retrieved_at_utc": res.retrieved_at_utc, "response": res.body})
            if not res.body["data"]:
                row["note"] = "no data returned"
            else:
                p = res.body["data"][0]
                ts = int(p["created_utc"])
                row.update(earliest_post_utc=epoch_to_iso(ts), earliest_created_utc_epoch=ts,
                           earliest_post_id=p["id"], earliest_post_title=p.get("title", "")[:120])
                # Independent check: everything strictly before (earliest + 1 day), ascending.
                vparams = {"subreddit": s, "before": ts + 86400, "limit": 5, "sort": "asc"}
                v = client.get("posts/search", vparams)
                row["verification_url"] = v.url
                vids = [q["id"] for q in v.body["data"]]
                vmin = min((int(q["created_utc"]) for q in v.body["data"]), default=None)
                row["verified"] = bool(vids) and vids[0] == p["id"] and vmin == ts
                row["note"] = f"verification returned {len(vids)} posts; first={vids[0] if vids else None}"
        except ArcticShiftError as e:
            row["note"] = f"failed: {e}"
        log.info("coverage r/%s: %s (%s) verified=%s", s, row["earliest_post_utc"], row["earliest_post_id"], row["verified"])
        rows.append(row)
    out = settings.TABLES / "subreddit_coverage.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %s", out)


# ----------------------------------------------------------------------------- verify
def run_verify(args) -> None:
    """Independent spot-check of archived days with a sort=desc request."""
    rng = random.Random(args.seed)
    latest = load_manifest_latest()
    complete = [(s, d) for (s, d), r in latest.items() if r["status"] == "complete"]
    by_sub: dict[str, list] = {}
    for s, d in sorted(complete):
        by_sub.setdefault(s, []).append(d)
    client = ArcticShiftClient(min_interval=args.interval)
    rows = []
    for s, days in by_sub.items():
        for d in rng.sample(days, min(args.n_per_sub, len(days))):
            day = date.fromisoformat(d)
            archive = read_json_gz(raw_path(s, day))
            archived_ids = {p["id"] for pg in archive["pages"] for p in pg["response"]["data"]}
            start, end = day_bounds_epoch(day)
            params = {"subreddit": s, "after": start, "before": end, "limit": "auto", "sort": "desc"}
            try:
                res = client.get("posts/search", params)
            except ArcticShiftError as e:
                rows.append({"subreddit": s, "date": d, "archived_posts": len(archived_ids), "check_returned": "",
                             "missing_from_archive": "", "passed": "", "note": f"check failed: {e}"})
                continue
            ids = [p["id"] for p in res.body["data"]]
            missing = [i for i in ids if i not in archived_ids]
            rows.append({"subreddit": s, "date": d, "archived_posts": len(archived_ids), "check_returned": len(ids),
                         "missing_from_archive": len(missing), "passed": not missing,
                         "note": ("missing ids: " + ",".join(missing[:10])) if missing else "",
                         "check_url": res.url, "checked_at_utc": res.retrieved_at_utc})
            log.info("verify r/%s %s: archive=%d check=%d missing=%d", s, d, len(archived_ids), len(ids), len(missing))
    out = settings.VALIDATION / "collection_spotcheck.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["subreddit", "date", "archived_posts", "check_returned", "missing_from_archive", "passed",
              "note", "check_url", "checked_at_utc"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %s (%d checks, %d passed)", out, len(rows), sum(r["passed"] is True for r in rows))


# ----------------------------------------------------------------------------- status
def run_status(args) -> None:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else settings.default_end_date()
    latest = load_manifest_latest()
    sub_map = config.subreddit_map(args.market)
    rows = []
    for s in args.subreddits or config.subreddits(args.market):
        days = [d.isoformat() for d in daterange(start, end)]
        raw_dir = settings.RAW_ARCTIC / s
        size_mb = sum(f.stat().st_size for f in raw_dir.rglob("*.json.gz")) / 2**20 if raw_dir.exists() else 0.0
        info = sub_map.get(s.lower(), {})
        st = [latest.get((s, d), {}).get("status", "missing") for d in days]
        n_posts = sum(int(latest[(s, d)]["n_posts"]) for d in days
                      if latest.get((s, d), {}).get("status") == "complete")
        bad = [d for d, x in zip(days, st) if x in ("failed", "partial")]
        rows.append({"market": args.market, "subreddit": s, "type": info.get("type"), "ticker": info.get("ticker"),
                     "start": start.isoformat(), "end": end.isoformat(), "days_expected": len(days),
                     "complete": st.count("complete"), "partial": st.count("partial"), "failed": st.count("failed"),
                     "missing": st.count("missing"), "posts_in_complete_days": n_posts,
                     "raw_storage_mb": round(size_mb, 1), "failed_or_partial_dates": ";".join(bad)})
        print(f"r/{s}: {rows[-1]['complete']}/{len(days)} complete, partial={rows[-1]['partial']}, "
              f"failed={rows[-1]['failed']}, missing={rows[-1]['missing']}, posts={n_posts:,}")
    out = settings.TABLES / "collection_summary.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap.add_argument("--market", default=settings.MARKET, choices=config.markets(),
                    help="subreddits default to every subreddit of this market in config.yaml")
    c = sub.add_parser("collect")
    c.add_argument("--start", default=settings.START_DATE.isoformat())
    c.add_argument("--end", default=None, help="inclusive; default = last complete UTC day")
    c.add_argument("--subreddits", nargs="*")
    c.add_argument("--interval", type=float, default=settings.ARCTIC_MIN_INTERVAL_S)
    c.add_argument("--max-pages", type=int, default=MAX_PAGES)
    c.add_argument("--force", action="store_true", help="re-download even complete days")
    c.add_argument("--allow-partial-today", action="store_true")
    c.set_defaults(func=run_collect)
    v = sub.add_parser("coverage")
    v.add_argument("--subreddits", nargs="*")
    v.add_argument("--interval", type=float, default=1.5)
    v.set_defaults(func=run_coverage)
    k = sub.add_parser("verify")
    k.add_argument("--n-per-sub", type=int, default=10)
    k.add_argument("--seed", type=int, default=42)
    k.add_argument("--interval", type=float, default=settings.ARCTIC_MIN_INTERVAL_S)
    k.set_defaults(func=run_verify)
    t = sub.add_parser("status")
    t.add_argument("--start", default=settings.START_DATE.isoformat())
    t.add_argument("--end", default=None)
    t.add_argument("--subreddits", nargs="*")
    t.set_defaults(func=run_status)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
