"""The daily Wikipedia job for AWS (Week 4 guide, "Wikipedia pipeline on AWS").

Each run pulls daily views and the day's revisions for every stock in the US config and the India/HK
title maps, then rewrites "Hot right now". It needs no local cache, so it runs as a Lambda.

    python -m src.wiki_daily                    # yesterday (UTC), under INDICATORLAB_DATA (data/ when unset)
    python -m src.wiki_daily --day 2026-11-18

On AWS it is the Lambda `indicatorlab-wikipedia-daily` (`lambda_handler`), started at 06:00 UTC by
EventBridge Scheduler, after Wikimedia has published the previous day. It writes:

  raw/wikipedia/date=YYYY-MM-DD/views.parquet      the day's views per article (ticker, market, lang, title;
                                                   `complete` is False if Wikimedia had not finished the day)
  raw/wikipedia/date=YYYY-MM-DD/revisions.parquet  the day's revisions: time, size, summary (no usernames)
  processed/wiki_current.parquet                   trailing 7 days vs the 8-week baseline, every market

processed/wiki_weekly.parquet only holds research weeks (before `holdout_start`), which no longer
change, so it is written once by `python -m src.wiki_export` and uploaded, not rewritten here.
A run that writes no rows raises, so the Lambda's error alarm fires; on S3 it also publishes the
CloudWatch metric IndicatorLab/WikiRowsWritten for the zero-rows alarm.
"""
import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pandas as pd
import requests

from src import config, storage
from src.wiki_attention import pageviews
from src.wiki_edits import revisions
from src.wiki_export import MARKET_NAMES, current_record
from src.wiki_pipeline import ROOT, article_titles, universe

METRIC_NAMESPACE = "IndicatorLab"
METRIC_NAME = "WikiRowsWritten"
SPARE_WEEKS = 2   # the history starts mid-week and the newest days are a partial week
# Wikimedia fills a day in over several hours, so a day whose views across every stock are under half
# their median over the week before is taken as not fully published yet. Real traffic never halves overnight
# across 100+ stocks; at 03:40 UTC on Nov 20, 2026 only 66 of 146 stocks had any Nov 19 views.
PUBLISHED_MIN_SHARE = 0.5

log = logging.getLogger("wiki_daily")


def history_days() -> int:
    """Days of views each run pulls: enough full weeks for the spike rule's baseline and its rz history."""
    rule = config.spike_rule()
    return (rule["baseline_weeks"] + rule["rz_min_history"] + SPARE_WEEKS) * 7


def map_titles(market: str) -> dict[str, list[tuple[str, str]]]:
    """Ticker -> [(language, title)] of one market's articles under their current names.

    US comes from config.yaml (tracked stocks plus the strategy universe). India and HK come from the
    CSV title maps in config `wikipedia.title_maps` (symbol, title, lang, valid_from; one row for each
    title an article has had), keeping each article's newest title. A market whose map is not in the
    repo yet is empty.
    """
    if market == "US":
        return {t: article_titles(titles) for t, titles in universe("US").items()}
    path = config.load()["wikipedia"]["title_maps"].get(market)
    if not path or not (ROOT / path).exists():
        return {}
    m = pd.read_csv(ROOT / path).sort_values("valid_from").groupby(["symbol", "lang"]).last().reset_index()
    return {s: list(zip(g["lang"], g["title"])) for s, g in m.groupby("symbol")}


def pull_stock(ticker: str, market: str, articles: list[tuple[str, str]], day: pd.Timestamp
               ) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """One stock's daily total views, the day's views per article, and the day's revisions.

    Views are the article title's own, without its redirects: big articles have 100+ redirects
    (Apple_Inc. 103), so adding them takes thousands of requests a run. "Hot right now" compares a stock
    with its own recent weeks pulled the same way, so the ratio stays consistent; only an article
    renamed inside the window would look low before the rename.
    """
    start = day - pd.Timedelta(days=history_days() - 1)
    views, day_rows, revs = [], [], []
    for lang, title in articles:
        v = pageviews(title, start, day, lang)
        views.append(v)
        day_rows.append({"lang": lang, "title": title, "views": int(v.get(day, 0))})
        r = revisions(title, day, day, lang)
        revs.append(r[~r["before_start"]].drop(columns=["user", "before_start"]).assign(lang=lang, title=title))
    tag = {"ticker": ticker, "market": MARKET_NAMES[market], "date": day}
    return (sum(views), pd.DataFrame(day_rows).assign(**tag),
            pd.concat(revs, ignore_index=True).assign(**tag))


def published_end(totals: dict[str, pd.Series]) -> pd.Timestamp:
    """Last fully published day: the newest day whose views across all stocks are at least
    PUBLISHED_MIN_SHARE of their median over the 7 days before it (unpublished days come back as zeros)."""
    by_day = pd.concat(totals.values(), axis=1).sum(axis=1).sort_index()
    end = len(by_day) - 1
    while end > 7 and by_day.iloc[end] < PUBLISHED_MIN_SHARE * by_day.iloc[end - 7:end].median():
        end -= 1
    return by_day.index[end]


def run(day: pd.Timestamp, root: str) -> dict:
    """Pull every market's stocks for `day`, write the raw and processed tables under `root`."""
    jobs = [(t, m, a) for m in config.markets() for t, a in map_titles(m).items()]
    workers = config.load()["wikipedia"]["sp500"]["workers"]

    def pull(job):
        try:
            return job, pull_stock(*job, day)
        except (requests.RequestException, ValueError, KeyError) as e:
            # a wrong or missing title, or a network failure: logged and listed, the run goes on
            log.warning("%s (%s): %s", job[0], job[1], e)
            return job, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        done = [(job, out) for job, out in pool.map(pull, jobs) if out is not None]
    if not done:
        raise RuntimeError(f"no stock could be pulled for {day.date()}")
    end = published_end({job[0]: out[0] for job, out in done})
    current = pd.DataFrame([current_record(out[0].loc[:end], t, m) for (t, m, _), out in done])
    current = current.sort_values("ratio", ascending=False).reset_index(drop=True)
    raw = f"{root}/raw/wikipedia/date={day:%Y-%m-%d}"
    views = pd.concat([out[1] for _, out in done], ignore_index=True).assign(complete=day <= end)
    storage.write_parquet(views, f"{raw}/views.parquet")
    storage.write_parquet(pd.concat([out[2] for _, out in done], ignore_index=True), f"{raw}/revisions.parquet")
    storage.write_parquet(current, f"{root}/processed/wiki_current.parquet")
    summary = {"day": f"{day:%Y-%m-%d}", "published_to": f"{end:%Y-%m-%d}", "rows": len(current),
               "failed": [job[0] for job in jobs if job[0] not in set(current["ticker"])]}
    log.info("wrote %s", summary)
    return summary


def publish_metric(rows: int) -> None:
    """Send the row count to CloudWatch, for the alarm on a run that wrote nothing."""
    import boto3
    boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION")).put_metric_data(
        Namespace=METRIC_NAMESPACE, MetricData=[{"MetricName": METRIC_NAME, "Value": rows, "Unit": "Count"}])


def yesterday() -> pd.Timestamp:
    """The last full UTC day."""
    return pd.Timestamp(datetime.now(UTC).date()) - pd.Timedelta(days=1)


def data_root() -> str:
    """Where to write: INDICATORLAB_DATA (e.g. s3://indicatorlab-data), else the repo's data/ folder."""
    return (os.getenv("INDICATORLAB_DATA") or str(ROOT / "data")).rstrip("/")


def lambda_handler(event: dict | None, context: object) -> dict:
    """Lambda entry point; `event` may name a {"day": "YYYY-MM-DD"} to rerun."""
    logging.getLogger().setLevel(logging.INFO)
    day = pd.Timestamp((event or {}).get("day") or yesterday())
    root = data_root()
    summary = run(day, root)
    if root.startswith("s3://"):
        publish_metric(summary["rows"])
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--day", help="UTC day to pull (default: yesterday)")
    a = p.parse_args()
    print(run(pd.Timestamp(a.day) if a.day else yesterday(), data_root()))
