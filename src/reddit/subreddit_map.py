"""Week 2, Step 2: survey candidate subreddits for each stock and build the subreddit map.

For every candidate in ``subreddit_candidates.yaml`` this records, from Arctic Shift:

  subscribers          ``subreddits/search`` (count in Arctic Shift's latest snapshot of the subreddit)
  first_post_utc       ``posts/search?limit=1&sort=asc`` (earliest archived post)
  posts_2024           ``posts/search/aggregate?aggregate=created_utc&frequency=month`` summed over 2024
  posts_per_week_2024  posts_2024 / (366 / 7), or from 14 sampled days when the aggregate times out
  volume_method        aggregate_year / aggregate_month / sampled_<n>_days
  type                 product / stock / sector, from the candidates file

A subreddit is kept when it averaged at least ``reddit.min_posts_per_week`` posts a week in 2024.
Writes ``results/reddit/tables/subreddit_map.csv`` and keeps every raw response under
``data/reddit/raw/subreddit_map/``. It never edits config.yaml; ``--print-config`` prints the kept
lists so they can be pasted into the stock entries.

    python -m src.reddit.subreddit_map --market US --print-config
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timezone

import pandas as pd
import yaml

from src import config
from src.reddit import settings
from src.reddit.arctic_client import ArcticShiftClient, ArcticShiftError
from src.reddit.collect_reddit import collect_day
from src.reddit.utils import (
    daterange,
    epoch_to_iso,
    get_logger,
    read_json_gz,
    utc_now_iso,
    write_json_gz,
)

log = get_logger("subreddit_map", "collect_reddit.log")

CANDIDATES = settings.ROOT / "src" / "reddit" / "subreddit_candidates.yaml"
RAW_DIR = settings.RAW / "subreddit_map"
OUT = settings.TABLES / "subreddit_map.csv"
SURVEY_YEAR = 2024
SAMPLE_DAYS = 14        # fallback when the aggregate endpoint keeps timing out
MIN_SAMPLED_DAYS = 10   # sampled days that must download for the estimate to count
SAMPLE_SEED = 42


def load_candidates(market: str) -> list[dict]:
    """Flatten the candidates file into one row per (ticker or sector, subreddit)."""
    with open(CANDIDATES, encoding="utf-8") as f:
        cand = yaml.safe_load(f)[market]
    rows = [{"market": market, "ticker": None, "subreddit": s, "type": "sector"} for s in cand.get("sector", [])]
    for ticker, kinds in cand["stocks"].items():
        for kind, subs in kinds.items():
            rows += [{"market": market, "ticker": ticker, "subreddit": s, "type": kind} for s in subs]
    return rows


def _cached_get(client: ArcticShiftClient, path: str, params: dict, cache_name: str) -> dict:
    """Response body of a survey request, reusing the saved raw response from an earlier run."""
    f = RAW_DIR / cache_name
    if f.exists():
        return read_json_gz(f)["response"]
    res = client.get(path, params)
    write_json_gz(f, {"url": res.url, "retrieved_at_utc": res.retrieved_at_utc, "response": res.body})
    return res.body


def subreddit_info(client: ArcticShiftClient, name: str) -> dict | None:
    """Arctic Shift's subreddit record for `name` (exact, case-insensitive), or None if it has none."""
    body = _cached_get(client, "subreddits/search", {"subreddit": name, "limit": 1}, f"{name.lower()}_info.json.gz")
    hits = [d for d in body["data"] if str(d.get("display_name", "")).lower() == name.lower()]
    return hits[0] if hits else None


def first_post(client: ArcticShiftClient, name: str) -> tuple[int | None, str | None]:
    """Epoch and id of the earliest archived post (limit=1&sort=asc)."""
    params = {"subreddit": name, "limit": 1, "sort": "asc", "fields": "id,created_utc"}
    body = _cached_get(client, "posts/search", params, f"{name.lower()}_first_post.json.gz")
    data = body["data"]
    return (int(data[0]["created_utc"]), data[0]["id"]) if data else (None, None)


def _aggregate_count(client: ArcticShiftClient, name: str, after: str, before: str) -> int:
    """Posts created in [after, before) from Arctic Shift's monthly aggregate counts."""
    params = {"aggregate": "created_utc", "frequency": "month", "subreddit": name, "after": after, "before": before}
    body = _cached_get(client, "posts/search/aggregate", params, f"{name.lower()}_posts_{after}_{before}.json.gz")
    return sum(int(b["count"]) for b in body["data"])


def posts_per_week(client: ArcticShiftClient, name: str, year: int) -> tuple[float, int | None, str]:
    """Average posts per week in `year`, the exact yearly count if known, and how it was measured.

    A single yearly aggregate times out on every large subreddit (checked Oct 25, 2026), so this
    sums twelve monthly aggregates and, if those fail too, averages SAMPLE_DAYS seeded random
    days counted with the same paginated day download the collector uses.
    """
    weeks = (date(year + 1, 1, 1) - date(year, 1, 1)).days / 7
    try:
        bounds = [date(year, m, 1) for m in range(1, 13)] + [date(year + 1, 1, 1)]
        n = sum(_aggregate_count(client, name, a.isoformat(), b.isoformat()) for a, b in zip(bounds, bounds[1:]))
        return n / weeks, n, "aggregate_month"
    except ArcticShiftError as e:
        log.warning("r/%s monthly aggregate failed (%s); sampling days", name, e)
    days = list(daterange(date(year, 1, 1), date(year, 12, 31)))
    counts = []
    for d in random.Random(SAMPLE_SEED).sample(days, SAMPLE_DAYS):
        r = collect_day(client, name, d)
        if r["status"] == "complete":
            counts.append(r["n_posts_unique"])
    if len(counts) < MIN_SAMPLED_DAYS:
        raise ArcticShiftError(f"only {len(counts)} of {SAMPLE_DAYS} sampled days downloaded for r/{name}", [])
    return 7 * sum(counts) / len(counts), None, f"sampled_{len(counts)}_days"


def survey(market: str, client: ArcticShiftClient) -> pd.DataFrame:
    """One row per candidate with subscribers, first post, 2024 volume and the keep decision."""
    min_ppw = config.load()["reddit"]["min_posts_per_week"]
    rows = []
    for c in load_candidates(market):
        name = c["subreddit"]
        row = {**c, "subscribers": None, "first_post_utc": None, "first_post_id": None,
               f"posts_{SURVEY_YEAR}": None, f"posts_per_week_{SURVEY_YEAR}": None, "volume_method": None,
               "kept": False,
               "reason": "", "retrieved_utc": utc_now_iso()}
        try:
            info = subreddit_info(client, name)
            if info is None:
                row["reason"] = "not in Arctic Shift"
                rows.append(row)
                continue
            row["subscribers"] = info.get("subscribers")
            ts, pid = first_post(client, name)
            row.update(first_post_utc=epoch_to_iso(ts) if ts else None, first_post_id=pid)
            ppw, n, method = posts_per_week(client, name, SURVEY_YEAR)
            row.update({f"posts_{SURVEY_YEAR}": n, f"posts_per_week_{SURVEY_YEAR}": round(ppw, 1),
                        "volume_method": method, "kept": ppw >= min_ppw,
                        "reason": "" if ppw >= min_ppw else f"< {min_ppw} posts/week in {SURVEY_YEAR}"})
        except ArcticShiftError as e:
            row["reason"] = f"request failed: {e}"
        log.info("r/%s (%s %s): subs=%s first=%s ppw=%s kept=%s %s", name, c["type"], c["ticker"],
                 row["subscribers"], row["first_post_utc"], row[f"posts_per_week_{SURVEY_YEAR}"], row["kept"],
                 row["reason"])
        rows.append(row)
    return pd.DataFrame(rows)


def kept_config(df: pd.DataFrame) -> str:
    """YAML snippet of the kept subreddits per ticker, to paste into config.yaml."""
    kept = df[df["kept"]]
    out = {"sector": kept.loc[kept["type"] == "sector", "subreddit"].tolist(), "stocks": {}}
    for ticker, g in kept[kept["ticker"].notna()].groupby("ticker", sort=False):
        out["stocks"][ticker] = {k: g.loc[g["type"] == k, "subreddit"].tolist() for k in config.STOCK_SUBREDDIT_TYPES}
    return yaml.safe_dump(out, sort_keys=False, default_flow_style=None)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market", default=settings.MARKET, choices=config.markets())
    ap.add_argument("--interval", type=float, default=settings.ARCTIC_MIN_INTERVAL_S)
    ap.add_argument("--print-config", action="store_true")
    a = ap.parse_args()
    df = survey(a.market, ArcticShiftClient(min_interval=a.interval))
    df.insert(len(df.columns), "surveyed_on", datetime.now(timezone.utc).date().isoformat())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    log.info("wrote %s: %d candidates, %d kept", OUT, len(df), int(df["kept"].sum()))
    if a.print_config:
        print(kept_config(df))


if __name__ == "__main__":
    main()
