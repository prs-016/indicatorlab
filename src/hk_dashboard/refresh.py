"""Refresh display-only HK Wikipedia counts, without running any research job.

Official protocols: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
and https://www.mediawiki.org/wiki/API:Revisions . Source failures remain explicit;
no missing article, failed day or unfinished pagination is imputed as zero.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from src.hk_dashboard.paths import display_root, names

USER_AGENT = "IndicatorLab-HK-Display/1.0 (+https://github.com/prs-016/indicatorlab)"


def save(path: Path, value) -> None:
    """Atomically publish a complete display view after a successful fetch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    pending.replace(path)


class Wikimedia:
    """Serial identifiable API client with bounded requests and conservative pacing."""

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.last = 0.0

    def get(self, url, params=None):
        """Make at most two attempts, respecting Retry-After and Wikimedia maxlag."""
        for attempt in range(2):
            time.sleep(max(0, 1 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            response = self.session.get(
                url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15
            )
            if response.status_code in {429, 503} and attempt == 0:
                wait = response.headers.get("Retry-After", "2")
                time.sleep(min(30, float(wait) if wait.isdigit() else 2))
                continue
            response.raise_for_status()
            if len(response.content) > 8_000_000:
                raise ValueError("Source response exceeds size bound")
            payload = response.json()
            if "error" in payload:
                raise ValueError("Wikimedia returned an API error")
            return payload
        raise RuntimeError("Wikimedia request did not complete")

    def views(self, lang, title, start, end):
        """Read daily article views in bounded annual chunks, retaining source gaps."""
        days = {}
        urls = []
        cursor = start
        while cursor <= end:
            last = min(end, cursor + timedelta(days=365))
            url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/{quote(title.replace(' ', '_'), safe='')}/daily/{cursor:%Y%m%d}00/{last:%Y%m%d}00"
            data = self.get(url)
            urls.append(url)
            for item in data["items"]:
                stamp = datetime.strptime(str(item["timestamp"])[:8], "%Y%m%d").date()
                value = item["views"]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError("Invalid pageview count")
                if cursor <= stamp <= last:
                    days[stamp.isoformat()] = value
            cursor = last + timedelta(days=1)
        return days, urls

    def revisions(self, lang, title, start, end):
        """Read one page's complete revision metadata with continuation and identity."""
        url = f"https://{lang}.wikipedia.org/w/api.php"
        creation = self.get(
            url,
            {
                "action": "query",
                "format": "json",
                "formatversion": 2,
                "redirects": 1,
                "prop": "revisions",
                "titles": title,
                "rvprop": "timestamp",
                "rvlimit": 1,
                "rvdir": "newer",
                "maxlag": 5,
            },
        )
        first = creation["query"]["pages"]
        if len(first) != 1 or "missing" in first[0] or not first[0].get("revisions"):
            raise ValueError("No evidenced article creation time")
        created_at = first[0]["revisions"][0]["timestamp"]
        params = {
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
            "prop": "revisions",
            "titles": title,
            "rvprop": "ids|timestamp|size|comment",
            "rvlimit": 500,
            "rvdir": "older",
            "rvstart": f"{end}T23:59:59Z",
            "rvend": f"{start}T00:00:00Z",
            "maxlag": 5,
        }
        found = {}
        effective = first[0]["pageid"]
        requests_used = []
        for _ in range(30):
            data = self.get(url, params)
            requests_used.append(dict(params))
            pages = data["query"]["pages"]
            if len(pages) != 1 or "missing" in pages[0]:
                raise ValueError("Wikipedia article is unavailable")
            page = pages[0]
            if effective is not None and effective != page["pageid"]:
                raise ValueError("Wikipedia page identity changed during pagination")
            effective = page["pageid"]
            for row in page.get("revisions", []):
                stamp = datetime.fromisoformat(row["timestamp"])
                if start <= stamp.date() <= end:
                    found[row["revid"]] = {
                        key: row.get(key)
                        for key in ["revid", "parentid", "timestamp", "size", "comment"]
                    }
            more = data.get("continue")
            if not more:
                return list(found.values()), {
                    "url": url,
                    "pageid": effective,
                    "title": page["title"],
                    "created_at": created_at,
                    "requests": requests_used,
                    "complete": True,
                }
            params.update(more)
        raise ValueError("Revision pagination did not complete within its bound")


def weekly(
    days: dict,
    revisions: list,
    start: date,
    end: date,
    *,
    views_ok: bool,
    edits_ok: bool,
    created: date | None = None,
) -> list:
    """Aggregate only observed days; distinguish full, partial and missing weeks."""
    edits = {}
    for revision in revisions:
        stamp = date.fromisoformat(revision["timestamp"][:10])
        monday = stamp - timedelta(days=stamp.weekday())
        edits[monday] = edits.get(monday, 0) + 1
    result = []
    for monday in pd.date_range(
        start - timedelta(days=start.weekday()), end, freq="W-MON"
    ):
        monday = monday.date()
        expected = [
            monday + timedelta(days=i)
            for i in range(7)
            if start <= monday + timedelta(days=i) <= end
            and (created is None or monday + timedelta(days=i) >= created)
        ]
        present = [days[str(day)] for day in expected if str(day) in days]
        complete_views = views_ok and bool(expected) and len(present) == len(expected)
        result.append(
            {
                "week": str(monday),
                "views": sum(present) if complete_views else None,
                "edits": edits.get(monday, 0)
                if edits_ok and expected and created is not None
                else None,
                "days_covered": len(expected),
                "view_days_observed": len(present),
                "partial": len(expected) < 7,
            }
        )
    return result


def run(output: Path, symbols=None, *, history_weeks=104) -> dict:
    """Fetch a new display cache; do not mutate price corpora, models or results."""
    now = datetime.now(UTC)
    end = now.date() - timedelta(days=1)
    start = now.date() - timedelta(days=now.weekday()) - timedelta(weeks=history_weeks)
    all_names = names()
    chosen = symbols or list(all_names)
    client = Wikimedia()
    page_cache = {}
    report = {
        "as_of": now.isoformat(),
        "start": str(start),
        "end": str(end),
        "display_only": True,
        "stocks": {},
    }
    for index, symbol in enumerate(chosen, 1):
        meta = all_names[symbol]
        lang = "en" if meta.get("wiki_en") else "zh"
        title = meta.get("wiki_en") or meta.get("wiki_zh")
        destination = output / "wikipedia" / f"{symbol}.json"
        if destination.exists():
            previous = json.loads(destination.read_text())
            if (
                previous.get("start") == str(start)
                and previous.get("end") == str(end)
                and not previous.get("errors")
                and previous.get("title", "").replace("_", " ")
                == previous.get("revisions_source", {})
                .get("title", "")
                .replace("_", " ")
            ):
                report["stocks"][symbol] = {
                    "errors": {},
                    "view_days": sum(
                        row["view_days_observed"] for row in previous["weeks"]
                    ),
                    "revisions": len(previous["revisions"]),
                    "language": lang,
                    "reused": True,
                }
                save(output / "refresh_status.json", report)
                print(
                    json.dumps(
                        {
                            "done": index,
                            "total": len(chosen),
                            "symbol": symbol,
                            **report["stocks"][symbol],
                        }
                    ),
                    flush=True,
                )
                continue
        errors = {}
        views = {}
        edits = []
        view_urls = []
        edit_source = {}
        if not title:
            errors["identity"] = "No sourced Wikipedia title"
        elif (lang, title) in page_cache:
            views, view_urls, edits, edit_source, errors = page_cache[(lang, title)]
        else:
            try:
                edits, edit_source = client.revisions(lang, title, start, end)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                errors["edits"] = type(exc).__name__
            try:
                # A whole annual chunk before article creation returns 404;
                # request only the article's evidenced lifetime, retaining null
                # weeks before that date instead of abandoning later views.
                views_start = (
                    max(start, date.fromisoformat(edit_source["created_at"][:10]))
                    if edit_source.get("created_at")
                    else start
                )
                if views_start <= end:
                    views, view_urls = client.views(
                        lang, edit_source.get("title", title), views_start, end
                    )
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                errors["views"] = type(exc).__name__
            page_cache[(lang, title)] = (views, view_urls, edits, edit_source, errors)
        created = (
            date.fromisoformat(edit_source["created_at"][:10])
            if edit_source.get("created_at")
            else None
        )
        rows = weekly(
            views,
            edits,
            start,
            end,
            views_ok="views" not in errors and bool(title),
            edits_ok="edits" not in errors and bool(title),
            created=created,
        )
        record = {
            "symbol": symbol,
            "lang": lang,
            "title": edit_source.get("title", title),
            "mapped_title": title,
            "as_of": datetime.now(UTC).isoformat(),
            "start": str(start),
            "end": str(end),
            "display_only": True,
            "errors": errors,
            "weeks": rows,
            "revisions": edits,
            "views_sources": view_urls,
            "revisions_source": edit_source,
            "article_url": f"https://{lang}.wikipedia.org/wiki/{quote(edit_source.get('title', title) or '', safe='')}",
            "source_note": meta.get("wiki_note"),
        }
        # A refresh failure stays visible in the status report. Retain a previous
        # usable display cache rather than replacing it with an empty success.
        if not errors or not destination.exists():
            save(destination, record)
        report["stocks"][symbol] = {
            "errors": errors,
            "view_days": len(views),
            "revisions": len(edits),
            "language": lang,
        }
        save(output / "refresh_status.json", report)
        print(
            json.dumps(
                {
                    "done": index,
                    "total": len(chosen),
                    "symbol": symbol,
                    **report["stocks"][symbol],
                }
            ),
            flush=True,
        )
    return report


def main() -> None:
    """Refresh the standalone display cache using public Wikimedia APIs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=display_root())
    parser.add_argument("--symbols", nargs="*")
    parser.add_argument("--history-weeks", type=int, default=104)
    args = parser.parse_args()
    if not 1 <= args.history_weeks <= 104:
        parser.error("history-weeks must be between 1 and 104")
    run(args.output, args.symbols, history_weeks=args.history_weeks)


if __name__ == "__main__":
    main()
