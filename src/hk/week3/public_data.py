"""Cached public data acquisition with an enforced pre-holdout research boundary."""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from src import config

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/hk_week3"
CUTOFF = pd.Timestamp("2025-10-01", tz="UTC")
USER_AGENT = "IndicatorLab-HK-research/1.0 (https://github.com/prs-016/indicatorlab)"
_LOCK = threading.Lock()
_NEXT = 0.0


def get_json(url: str, params: dict | None = None) -> dict:
    """Cache immutable request responses; throttle Wikimedia and retry transient errors."""
    global _NEXT
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    path = DATA / "cache" / (key + ".json")
    if path.exists():
        return json.loads(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        if "wikimedia" in url or "wikipedia" in url:
            with _LOCK:
                delay = max(0, _NEXT - time.monotonic())
                _NEXT = max(_NEXT, time.monotonic()) + 0.5
            time.sleep(delay)
        response = requests.get(
            url, params=params, headers={"User-Agent": USER_AGENT}, timeout=40
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            time.sleep(min(30, float(response.headers.get("Retry-After", 2**attempt))))
            continue
        response.raise_for_status()
        result = response.json()
        if result.get("error", {}).get("code") == "maxlag":
            time.sleep(5)
            continue
        if "error" in result:
            raise ValueError(str(result["error"])[:200])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False))
        temporary.replace(path)
        return result
    raise requests.Timeout("Public endpoint exhausted its retries")


def api(lang: str, **params) -> dict:
    """Call MediaWiki with explicit JSON formatting and load-sensitive backoff."""
    return get_json(
        f"https://{lang}.wikipedia.org/w/api.php",
        {"action": "query", "format": "json", "maxlag": 5, **params},
    )


def download_prices(ticker: str, start: str, end: str) -> dict:
    """Store bounded Yahoo split-adjusted OHLCV, adjusted-close and cash actions."""
    if pd.Timestamp(end) >= CUTOFF.tz_localize(None):
        raise ValueError("Research prices cannot include the holdout")
    destination = DATA / "prices" / (ticker.replace("^", "INDEX_") + ".parquet")
    if destination.exists():
        frame = pd.read_parquet(destination)
        if frame.index.max() > pd.Timestamp(end):
            raise ValueError("Existing price snapshot exceeds the declared end")
        return {
            "ticker": ticker,
            "rows": len(frame),
            "first": str(frame.index.min().date()),
            "last": str(frame.index.max().date()),
            "cached": True,
        }
    request_zone = (
        "Asia/Hong_Kong"
        if ticker.endswith(".HK") or ticker == "^HSI"
        else "Europe/London" if ticker.endswith("=X") else "America/New_York"
    )
    exclusive_end = (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize(request_zone)
    params = {
        "period1": int(pd.Timestamp(start, tz="UTC").timestamp()),
        "period2": int(exclusive_end.timestamp()) - 1,
        "interval": "1d",
        "events": "div,splits",
    }
    # Do not cache retrieval-time quote metadata as historical research data.
    response = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/" + quote(ticker),
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=40,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    zone = result["meta"]["exchangeTimezoneName"]
    index = (
        pd.to_datetime(result["timestamp"], unit="s", utc=True)
        .tz_convert(zone)
        .tz_localize(None)
        .normalize()
    )
    frame = pd.DataFrame(result["indicators"]["quote"][0], index=index).sort_index()
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    frame["adj_close"] = adjusted if adjusted is not None else np.nan
    if (frame.index >= CUTOFF.tz_localize(None)).any():
        raise ValueError("Provider returned post-cutoff price bars")
    frame = frame.loc[start:end].copy()
    frame["dividend"] = 0.0
    splits = []
    for event in result.get("events", {}).get("dividends", {}).values():
        date = (
            pd.Timestamp(event["date"], unit="s", tz="UTC")
            .tz_convert(zone)
            .tz_localize(None)
            .normalize()
        )
        if date in frame.index:
            frame.loc[date, "dividend"] += float(event["amount"])
    for event in result.get("events", {}).get("splits", {}).values():
        date = (
            pd.Timestamp(event["date"], unit="s", tz="UTC")
            .tz_convert(zone)
            .tz_localize(None)
            .normalize()
        )
        if pd.Timestamp(start) <= date <= pd.Timestamp(end):
            splits.append(
                {
                    "date": str(date.date()),
                    "numerator": event["numerator"],
                    "denominator": event["denominator"],
                }
            )
    valid = frame.close.notna()
    bad = valid & (
        (frame.close <= 0)
        | (frame.open <= 0)
        | (frame.high < frame.low)
        | (frame.volume < 0)
    )
    if bad.any() or frame.index.has_duplicates or not valid.any():
        raise ValueError(f"Invalid price observations for {ticker}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(destination)
    info = {
        "ticker": ticker,
        "rows": len(frame),
        "first": str(frame.index.min().date()),
        "last": str(frame.index.max().date()),
        "currency": result["meta"].get("currency"),
        "timezone": zone,
        "splits": splits,
        "missing_ohlcv_rows": int(
            frame[["open", "high", "low", "close", "volume"]].isna().any(axis=1).sum()
        ),
        "source": response.url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "price_basis": "Yahoo split-adjusted OHLC; dividends separate; retrieval-vintage adjusted-close retained for diagnostics only",
    }
    destination.with_suffix(".json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def revision_metadata(title: str, lang: str = "en") -> tuple[dict, list[dict]]:
    """Get dated revision identities before cutoff, plus a pre-window anchor."""
    base = {
        "titles": title.replace("_", " "),
        "redirects": 1,
        "prop": "revisions",
        "rvprop": "ids|timestamp|size",
        "rvstart": "2025-09-30T23:59:59Z",
        "rvend": "2015-06-01T00:00:00Z",
        "rvlimit": 500,
    }
    revisions, continuation, identity = [], {}, None
    while True:
        result = api(lang, **base, **continuation)
        page = next(iter(result["query"]["pages"].values()))
        if "missing" in page:
            raise ValueError(f"Missing article {lang}:{title}")
        identity = {"pageid": page["pageid"], "title": page["title"], "lang": lang}
        revisions.extend(page.get("revisions", []))
        continuation = result.get("continue", {})
        if not continuation:
            break
    revisions.sort(key=lambda revision: revision["timestamp"])
    if any(pd.Timestamp(row["timestamp"]) >= CUTOFF for row in revisions):
        raise ValueError("Future revision in historical research")
    return identity, revisions


def revision_contents(revids: list[int], lang: str = "en") -> dict[int, str]:
    """Fetch the immutable contents of selected pre-cutoff revisions, 50 at a time."""
    contents = {}
    cache = DATA / "revision_text" / lang
    cache.mkdir(parents=True, exist_ok=True)
    for revid in revids:
        path = cache / f"{revid}.txt.gz"
        if path.exists():
            contents[revid] = gzip.decompress(path.read_bytes()).decode()
    missing = [revid for revid in revids if revid not in contents]
    for offset in range(0, len(missing), 50):
        result = api(
            lang,
            revids="|".join(map(str, missing[offset : offset + 50])),
            prop="revisions",
            rvprop="ids|timestamp|content",
            rvslots="main",
        )
        for page in result["query"]["pages"].values():
            for row in page.get("revisions", []):
                if pd.Timestamp(row["timestamp"]) >= CUTOFF:
                    raise ValueError("Refusing future text")
                slot = row.get("slots", {}).get("main", {})
                if "*" in slot:
                    contents[row["revid"]] = slot["*"]
                    (cache / f'{row["revid"]}.txt.gz').write_bytes(
                        gzip.compress(slot["*"].encode())
                    )
    return contents


def added_text(before: str, after: str) -> str:
    """Extract net added/changed paragraph lines, strip markup, retain prose."""
    old, new = before.splitlines(), after.splitlines()
    added = []
    for operation, _a, _b, start, end in difflib.SequenceMatcher(
        None, old, new
    ).get_opcodes():
        if operation in {"insert", "replace"}:
            added.extend(
                line
                for line in new[start:end]
                if not line.lstrip().startswith(
                    ("|", "!", "{{", "}}", "[[Category:", "*", "==")
                )
            )
    text = "\n".join(added)
    text = re.sub(
        r"<ref\b[^>]*>.*?</ref>|<ref[^>]*/>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"\{\{.*?\}\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[\[(?:[^]|]*\|)?([^]]+)\]\]", r"\1", text)
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def collect_article(ticker: str, title: str) -> dict:
    """Collect pre-cutoff weekly revision endpoints and net additions for FinBERT."""
    destination = DATA / "wikipedia" / (ticker + ".json")
    if (
        destination.exists()
        and json.loads(destination.read_text()).get("week_definition")
        == "Monday-Sunday UTC"
    ):
        cached = json.loads(destination.read_text())
        return {"ticker": ticker, "weeks": len(cached["weeks"]), "cached": True}
    identity, revisions = revision_metadata(title)
    by_week = {}
    for row in revisions:
        # Shared convention: Monday-labelled weeks ending Sunday 23:59 UTC.
        stamp = pd.Timestamp(row["timestamp"]).tz_localize(None)
        monday = stamp.to_period("W-SUN").start_time.normalize()
        by_week.setdefault(str(monday.date()), []).append(row)
    selected = [rows[-1]["revid"] for _, rows in sorted(by_week.items())]
    if revisions:
        selected.insert(0, revisions[0]["parentid"])
    contents = revision_contents(list(dict.fromkeys(selected)))
    previous = contents.get(revisions[0]["parentid"], "") if revisions else ""
    weeks = []
    for week, rows in sorted(by_week.items()):
        if pd.Timestamp(week) + pd.Timedelta(days=6) >= CUTOFF.tz_localize(None):
            continue  # a partial final week has no completed signal before cutoff
        last = rows[-1]
        content = contents.get(last["revid"])
        text = (
            added_text(previous, content) if content is not None and previous else None
        )
        weeks.append(
            {
                "week": week,
                "edits": len(rows),
                "last_revision": last["revid"],
                "ts_last_revision": last["timestamp"],
                "added_text": text,
            }
        )
        if content is not None:
            previous = content
    result = {
        "ticker": ticker,
        "identity": identity,
        "revisions": revisions,
        "weeks": weeks,
        "week_definition": "Monday-Sunday UTC",
        "text_definition": "Net paragraph additions between successive last-known weekly revisions; not present-day article text",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False))
    return {
        "ticker": ticker,
        "weeks": len(weeks),
        "revisions": len(revisions),
        "text_weeks": sum(bool(row["added_text"]) for row in weeks),
    }


def main() -> None:
    """Acquire prices and English article revisions; no strategy is evaluated."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["prices", "articles", "all"], default="all")
    args = parser.parse_args()
    specification = json.loads((ROOT / "config/hk_week3_research.json").read_text())
    stocks = {
        ticker: value["wikipedia"]["en"]
        for market in ("HK", "US")
        for ticker, value in config.stocks(market).items()
    }
    jobs = []
    if args.kind in {"prices", "all"}:
        tickers = list(stocks) + ["^HSI", "SPY", "HKD=X"]
        jobs.extend(
            (
                "price",
                ticker,
                lambda ticker=ticker: download_prices(
                    ticker, specification["price_start"], specification["end"]
                ),
            )
            for ticker in tickers
        )
    if args.kind in {"articles", "all"}:
        jobs.extend(
            (
                "article",
                ticker,
                lambda ticker=ticker, title=title: collect_article(ticker, title),
            )
            for ticker, title in stocks.items()
        )
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(job): (kind, ticker) for kind, ticker, job in jobs}
        for future in as_completed(futures):
            kind, ticker = futures[future]
            try:
                result = future.result()
                print(json.dumps({"kind": kind, **result}), flush=True)
                results.append({"kind": kind, **result})
            except (
                requests.RequestException,
                ValueError,
                KeyError,
                TypeError,
                OSError,
            ) as exc:
                failure = {
                    "kind": kind,
                    "ticker": ticker,
                    "error": type(exc).__name__,
                    "message": str(exc)[:160],
                }
                results.append(failure)
                print(json.dumps(failure), flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / ("acquisition_" + args.kind + ".json")).write_text(
        json.dumps(results, indent=2)
    )


if __name__ == "__main__":
    main()
