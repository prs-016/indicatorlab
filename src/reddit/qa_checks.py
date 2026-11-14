"""End-to-end quality checks. Writes results/reddit/tables/qa_report.md; exits 1 if any check FAILs."""
from __future__ import annotations

import random
import subprocess
import sys
from datetime import date

import numpy as np
import pandas as pd

from src.reddit import settings
from src.reddit.collect_reddit import load_manifest_latest
from src.reddit.utils import daterange, day_bounds_epoch

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool | None, detail: str = "") -> None:
    status = "PASS" if ok else ("WARN" if ok is None else "FAIL")
    results.append((status, name, detail))
    print(f"[{status}] {name}: {detail}")


def main(end: date | None = None) -> int:
    end = end or settings.default_end_date()
    days = [d.isoformat() for d in daterange(settings.START_DATE, end)]
    latest = load_manifest_latest()

    # 1. coverage
    for s in settings.SUBREDDITS:
        st = [latest.get((s, d), {}).get("status", "missing") for d in days]
        bad = {k: st.count(k) for k in ("partial", "failed", "missing") if st.count(k)}
        check(f"coverage r/{s} {days[0]}..{days[-1]}", st.count("complete") == len(days),
              f"{st.count('complete')}/{len(days)} complete" + (f"; {bad}" if bad else ""))

    # 2. raw files exist, were retrieved after the day ended, and hold only that day's posts
    rows = [(k, v) for k, v in latest.items() if v["status"] == "complete"]
    missing_files = [v["file"] for _, v in rows if not (settings.ROOT / v["file"]).exists()]
    check("raw file exists for every complete day", not missing_files, f"{len(missing_files)} missing")
    early = [f"{s} {d}" for (s, d), v in rows
             if pd.Timestamp(v["first_retrieved_utc"]) < pd.Timestamp(day_bounds_epoch(date.fromisoformat(d))[1], unit="s", tz="UTC")]
    check("every day retrieved after it ended (UTC)", not early, f"{len(early)} retrieved early {early[:5]}")

    posts = pd.read_parquet(settings.POSTS, columns=["id", "date", "raw_file_date", "day_status", "score",
                                                     "num_comments", "created_utc"])
    check("post ids unique", posts["id"].is_unique, f"{len(posts):,} posts")
    mism = (posts["date"] != posts["raw_file_date"]).sum()
    check("post UTC date == raw file date", mism == 0, f"{mism} mismatches")
    man_total = sum(int(v["n_posts"]) for _, v in rows)
    got = posts[posts["day_status"] == "complete"].shape[0]
    check("posts table matches manifest counts", man_total == got, f"manifest={man_total:,} table={got:,}")
    for c in ["score", "num_comments", "created_utc"]:
        n = posts[c].isna().sum()
        check(f"no missing/non-numeric {c}", n == 0, f"{n} missing")

    # 3. matching
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet")
    check("no duplicate post/ticker rows", not mt.duplicated(["post_id", "ticker"]).any(), f"{len(mt):,} rows")
    fi = mt["found_in"].value_counts().to_dict()
    check("matching uses title and body", fi.get("body", 0) > 0 and fi.get("title", 0) > 0, str(fi))
    check("all 10 tickers matched", set(mt["ticker"]) == set(settings.TICKERS), str(sorted(set(mt["ticker"]))))

    # 4. weekly
    w = pd.read_csv(settings.PROCESSED / "reddit_weekly.csv", parse_dates=["week_start"])
    ws = pd.read_csv(settings.PROCESSED / "reddit_weekly_by_subreddit.csv", parse_dates=["week_start"])
    check("all week_start are Mondays", (w["week_start"].dt.day_of_week == 0).all() and (ws["week_start"].dt.day_of_week == 0).all())
    check("10 rows per week in reddit_weekly.csv", w.groupby("week_start").size().eq(10).all())
    inc = w.loc[~w["coverage_complete"], "week_start"].dt.strftime("%Y-%m-%d").unique().tolist()
    check("incomplete weeks have NaN (not 0) metrics", w.loc[~w["coverage_complete"], "posts"].isna().all(),
          f"{len(inc)} incomplete weeks: {inc[:6]}{'…' if len(inc) > 6 else ''}")
    comp = w[w["coverage_complete"]].set_index(["week_start", "ticker"])["posts"]
    summed = ws.groupby(["week_start", "ticker"])["posts"].sum(min_count=3).reindex(comp.index)
    check("combined posts == sum of subreddit posts", np.allclose(comp, summed))
    # independent brute-force recomputation of the 4-week median / ratio (no look-ahead)
    rng = random.Random(0)
    idx = rng.sample(list(w.index), min(400, len(w)))
    errs = 0
    for i in idx:
        r = w.loc[i]
        prev = w[(w["ticker"] == r["ticker"]) & (w["week_start"] < r["week_start"]) &
                 (w["week_start"] >= r["week_start"] - pd.Timedelta(weeks=4))]["posts"]
        exp = prev.median() if len(prev) == 4 and prev.notna().all() else np.nan
        ratio = r["posts"] / exp if exp and exp > 0 else np.nan
        if not (np.isclose(exp, r["posts_median_4w"], equal_nan=True) and
                np.isclose(ratio, r["posts_spike_ratio"], equal_nan=True)):
            errs += 1
    check("brute-force 4-week median & ratio match (prior weeks only)", errs == 0, f"{errs}/{len(idx)} mismatches")
    flag_ok = (w["posts_spike_flag"] == (w["posts_spike_ratio"] >= 2)).all()
    check("spike flag == ratio >= 2", flag_ok)

    # 5. returns
    pr = pd.read_csv(settings.RAW_PRICES / "AAPL_daily_yfinance.csv", parse_dates=["date"])
    ev = pd.read_csv(settings.TABLES / "apple_event_study.csv")
    errs = []
    for r in ev.itertuples():
        ws_ = pd.Timestamp(r.event_week_start)
        cur = pr[(pr["date"] >= ws_) & (pr["date"] < ws_ + pd.Timedelta(days=7))]["Close"].iloc[-1]
        prv = pr[(pr["date"] >= ws_ - pd.Timedelta(days=7)) & (pr["date"] < ws_)]["Close"].iloc[-1]
        nxt = pr[(pr["date"] >= ws_ + pd.Timedelta(days=7)) & (pr["date"] < ws_ + pd.Timedelta(days=14))]["Close"].iloc[-1]
        if not (np.isclose(cur / prv - 1, r.event_week_return) and np.isclose(nxt / cur - 1, r.next_week_return)):
            errs.append(r.year)
    check("event-week and next-week returns recomputed from raw prices", not errs, f"mismatch years: {errs}")
    check("event weeks have complete Reddit coverage", ev["reddit_coverage_complete"].all(),
          str(dict(zip(ev["year"], ev["reddit_coverage_complete"]))))

    # 6. unit tests
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", str(settings.ROOT / "tests" / "reddit")],
                       capture_output=True, text=True, cwd=settings.ROOT)
    check("pytest", p.returncode == 0, p.stdout.strip().splitlines()[-1] if p.stdout else p.stderr[-200:])

    n_fail = sum(s == "FAIL" for s, _, _ in results)
    lines = ["# QA report\n", f"Range checked: {days[0]} .. {days[-1]} (UTC)\n",
             f"**{len(results) - n_fail} passed / {n_fail} failed**\n", "| status | check | detail |", "|---|---|---|"]
    lines += [f"| {s} | {n} | {d.replace('|', '/')} |" for s, n, d in results]
    (settings.TABLES / "qa_report.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(results) - n_fail} passed / {n_fail} failed -> results/reddit/tables/qa_report.md")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
