"""Refresh dated HKEX board lots and inspect public HK attention coverage.

Reference downloads are operational data, separate from pre-2025-10 research.
Wikipedia valid_from means first observed here, never an inferred move date.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.hk.live import read_symbols, symbol, write_json

ROOT = Path(__file__).resolve().parents[2]
LOTS_URL = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
WIKI_URL = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
WIKI_API = "https://en.wikipedia.org/w/api.php"
ARCTIC = "https://arctic-shift.photon-reddit.com/api/posts/search/aggregate"
# Supplement the older Wikipedia roster with article candidates for newer members.
# Each candidate is resolved by the API, with missing pages recorded explicitly.
TITLE_CANDIDATES = {
    "0728.HK": "China_Telecom",
    "1347.HK": "Hua_Hong_Semiconductor",
    "1519.HK": "J%26T_Express",
    "1801.HK": "Innovent_Biologics",
    "1876.HK": "Budweiser_APAC",
    "2338.HK": "Weichai_Power",
    "2600.HK": "Aluminum_Corporation_of_China_Limited",
    "3750.HK": "CATL",
    "3993.HK": "CMOC_Group",
    "6160.HK": "BeOne_Medicines",
    "6181.HK": "Laopu_Gold",
    "9901.HK": "New_Oriental",
}
# Verified article URLs when English interwiki links are absent. The CHALCO
# article also covers its parent; that shared scope is disclosed below.
CHINESE_TITLES = {"1876.HK": "百威亞太", "2600.HK": "中國鋁業", "6181.HK": "老鋪黃金"}


def board_lots(content: bytes, pulled_at: str) -> pd.DataFrame:
    """Parse HKD equity lots from the official securities workbook, without filling."""
    frame = pd.read_excel(io.BytesIO(content), header=2, dtype=str)
    frame = frame[
        frame["Category"].isin(["Equity", "Real Estate Investment Trusts"])
        & (frame["Trading Currency"] == "HKD")
    ].copy()
    frame["symbol"] = frame["Stock Code"].map(
        lambda value: symbol(value) if int(value) < 10000 else None
    )
    frame["board_lot"] = pd.to_numeric(
        frame["Board Lot"].str.replace(",", "", regex=False), errors="raise"
    )
    frame = frame.dropna(subset=["symbol"])
    frame["pulled_at"] = pulled_at
    frame["source"] = LOTS_URL
    frame["source_sha256"] = hashlib.sha256(content).hexdigest()
    frame["stamp_duty_subject"] = frame["Subject to Stamp Duty"]
    if (
        frame.symbol.duplicated().any()
        or (frame.board_lot <= 0).any()
        or frame.board_lot.isna().any()
        or (frame.board_lot % 1).ne(0).any()
    ):
        raise ValueError("Invalid official board-lot reference")
    return frame[
        [
            "symbol",
            "board_lot",
            "stamp_duty_subject",
            "pulled_at",
            "source",
            "source_sha256",
        ]
    ]


def wiki_seeds(html: str) -> dict[str, str]:
    """Read company article links from Wikipedia's current constituents table."""
    seeds = {}
    for table in BeautifulSoup(html, "html.parser").select("table"):
        if "Sub-index" not in table.get_text():
            continue
        for row in table.select("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            code = re.search(r"\d+", cells[0].get_text())
            links = cells[1].select("a[href]")
            if code and links:
                seeds[symbol(code.group())] = unquote(
                    links[0]["href"].split("/wiki/")[-1]
                ).replace("_", " ")
    return seeds


def wiki_titles(
    session: requests.Session, roster: list[str], html: str, observed: str
) -> tuple[pd.DataFrame, dict]:
    """Resolve English/Chinese titles and redirect aliases with provenance gaps."""
    seeds = wiki_seeds(html) | {
        code: unquote(title).replace("_", " ")
        for code, title in TITLE_CANDIDATES.items()
    }
    rows, gaps = [], []
    for offset in range(0, len(roster), 25):
        codes = roster[offset : offset + 25]
        requested = {code: seeds[code] for code in codes if code in seeds}
        response = session.get(
            WIKI_API,
            params={
                "action": "query",
                "format": "json",
                "redirects": 1,
                "titles": "|".join(requested.values()),
                "prop": "langlinks|redirects",
                "lllang": "zh",
                "lllimit": "max",
                "rdnamespace": 0,
                "rdlimit": "max",
            },
            timeout=30,
        )
        response.raise_for_status()
        query = response.json()["query"]
        aliases = {
            item["from"]: item["to"]
            for key in ("normalized", "redirects")
            for item in query.get(key, [])
        }
        pages = {page["title"]: page for page in query["pages"].values()}
        for code in codes:
            title = requested.get(code)
            seen = set()
            while title in aliases and title not in seen:
                seen.add(title)
                title = aliases[title]
            page = pages.get(title, {})
            if "missing" in page or not page:
                gaps.append(
                    {
                        "symbol": code,
                        "reason": "missing_english_article",
                        "candidate": title,
                    }
                )
                continue
            for item in [title] + [
                alias["title"] for alias in page.get("redirects", [])
            ]:
                rows.append(
                    {
                        "symbol": code,
                        "title": item.replace(" ", "_"),
                        "lang": "en",
                        "valid_from": observed,
                    }
                )
            chinese = next(
                (
                    item["*"]
                    for item in page.get("langlinks", [])
                    if item["lang"] == "zh"
                ),
                None,
            )
            if chinese:
                rows.append(
                    {
                        "symbol": code,
                        "title": chinese.replace(" ", "_"),
                        "lang": "zh",
                        "valid_from": observed,
                    }
                )
            else:
                gaps.append(
                    {
                        "symbol": code,
                        "reason": "missing_chinese_article",
                        "candidate": title,
                    }
                )
        time.sleep(1)
    for code, title in CHINESE_TITLES.items():
        if code in roster and not any(
            row["symbol"] == code and row["lang"] == "zh" for row in rows
        ):
            rows.append(
                {"symbol": code, "title": title, "lang": "zh", "valid_from": observed}
            )
            gaps = [
                gap
                for gap in gaps
                if not (
                    gap["symbol"] == code and gap["reason"] == "missing_chinese_article"
                )
            ]
    return pd.DataFrame(rows).drop_duplicates(), {
        "gaps": gaps,
        "valid_from_semantics": "first observed on retrieval date; historical move dates unverified",
        "redirects_are_not_proven_historical_titles": True,
        "historical_mapping_ready": False,
        "manual_article_sources": {
            code: "https://zh.wikipedia.org/wiki/" + title
            for code, title in CHINESE_TITLES.items()
        },
        "shared_article_scope": {
            "2600.HK": "Chinese article covers parent and listed subsidiary; isolate scope before research."
        },
        "source": WIKI_URL,
    }


def survey(session: requests.Session) -> pd.DataFrame:
    """Count archived 2024 posts; failed requests remain unavailable, never zero."""
    rows = []
    for name in [
        "HongKongStocks",
        "HKStocks",
        "InvestingHK",
        "ChinaStocks",
        "China_Stocks",
        "AlibabaStock",
        "BABAStock",
        "Tencent",
        "HongKong",
        "Xiaomi",
    ]:
        row = {
            "subreddit": name,
            "year": 2024,
            "posts": None,
            "posts_per_week": None,
            "meets_20_per_week": False,
            "market_specific": name not in {"HongKong", "Xiaomi"},
        }
        try:
            response = session.get(
                ARCTIC,
                params={
                    "aggregate": "created_utc",
                    "frequency": "year",
                    "subreddit": name,
                    "after": "2024-01-01",
                    "before": "2025-01-01",
                },
                timeout=40,
            )
            response.raise_for_status()
            data = response.json()["data"]
            total = sum(int(item["count"]) for item in data)
            weekly = total / (366 / 7)
            row.update(
                {
                    "posts": total,
                    "posts_per_week": weekly,
                    "meets_20_per_week": weekly >= 20,
                    "status": "observed",
                    "url": response.url,
                }
            )
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            row.update({"status": "unavailable", "error": type(exc).__name__})
        rows.append(row)
        time.sleep(1)
    return pd.DataFrame(rows)


def main() -> None:
    """Download a new ignored reference snapshot without replacing frozen inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached-sources", type=Path)
    parser.add_argument("--skip-survey", action="store_true")
    args = parser.parse_args()
    now = datetime.now(UTC)
    observed = now.date().isoformat()
    output = ROOT / "data/hk_reference_refresh" / now.strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    roster = read_symbols(ROOT / "config/hsi_constituents_2026-11-04.csv")
    session = requests.Session()
    session.headers["User-Agent"] = "IndicatorLab-HK-research/1.0"
    if args.cached_sources:
        content = (args.cached_sources / "lots.xlsx").read_bytes()
        html = (args.cached_sources / "wiki.txt").read_text()
    else:
        response = session.get(LOTS_URL, timeout=40)
        response.raise_for_status()
        content = response.content
        response = session.get(WIKI_URL, timeout=30)
        response.raise_for_status()
        html = response.text
    lots = board_lots(content, now.isoformat())
    lots.to_csv(
        output / f"hk_board_lots_{observed}.csv", index=False, lineterminator="\n"
    )
    titles, metadata = wiki_titles(session, roster, html, observed)
    titles.to_csv(
        output / "wiki_aliases_observed.csv", index=False, lineterminator="\n"
    )
    metadata.update(
        {
            "pulled_at": now.isoformat(),
            "roster_symbols": len(roster),
            "mapped_symbols": int(titles.symbol.nunique()),
            "lot_missing": sorted(set(roster) - set(lots.symbol)),
            "snapshot_directory": str(output),
            "canonical_inputs_unchanged": True,
        }
    )
    write_json(output / "reference_manifest.json", metadata)
    counts = survey(session) if not args.skip_survey else None
    if counts is not None:
        counts.to_csv(
            output / "reddit_survey_2024.csv", index=False, lineterminator="\n"
        )
    print(json.dumps(metadata, indent=2))
    if counts is not None:
        print(counts.to_string(index=False))


if __name__ == "__main__":
    main()
