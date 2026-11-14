"""Reconstruct article-title intervals from creation revisions and move logs."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd
import requests

from src.hk.week3.public_data import DATA, ROOT, api


def page_details(title: str, lang: str) -> dict:
    """Resolve identity, first revision date and all currently observed redirects."""
    query = api(
        lang,
        titles=title.replace("_", " "),
        redirects=1,
        prop="revisions|redirects",
        rvprop="timestamp",
        rvdir="newer",
        rvlimit=1,
        rdnamespace=0,
        rdlimit=500,
    )
    page = next(iter(query["query"]["pages"].values()))
    if "missing" in page or not page.get("revisions"):
        raise ValueError(f"No creation revision: {lang}:{title}")
    aliases = {title.replace("_", " "), page["title"]}
    aliases.update(row["title"] for row in page.get("redirects", []))
    continuation = query.get("continue", {})
    while continuation:
        query = api(
            lang,
            titles=page["title"],
            prop="redirects",
            rdnamespace=0,
            rdlimit=500,
            **continuation,
        )
        extra = next(iter(query["query"]["pages"].values()))
        aliases.update(row["title"] for row in extra.get("redirects", []))
        continuation = query.get("continue", {})
    return {
        "pageid": page["pageid"],
        "title": page["title"],
        "created": page["revisions"][0]["timestamp"],
        "aliases": sorted(aliases),
        "lang": lang,
    }


def move_logs(title: str, lang: str) -> list[dict]:
    """Read all public source-title move events, retaining stable logpage identity."""
    records, continuation = [], {}
    while True:
        result = api(
            lang,
            list="logevents",
            letitle=title,
            letype="move",
            leprop="ids|title|timestamp|details",
            lelimit=500,
            **continuation,
        )
        records.extend(result["query"]["logevents"])
        continuation = result.get("continue", {})
        if not continuation:
            return records


def reconstruct(page: dict, logs: list[dict]) -> tuple[list[dict], list[str]]:
    """Build exact timestamp intervals; flag discontinuities instead of hiding them."""
    if page.get("symbol") == "0006.HK" and page["lang"] == "zh":
        # A 2011 history merge changed page identity. The actual entity move is
        # independently recorded as log 1986552; do not treat its temporary
        # maintenance title as the company's canonical article for 2011 onward.
        evidence = "entity_move_log:1986552; original_logpage:1523392; history_merge_changed_identity"
        return [
            {
                "title": "香港電燈",
                "lang": "zh",
                "valid_from": None,
                "valid_to": "2011-02-16T10:56:17Z",
                "pageid": 1523392,
                "evidence": evidence + "; earliest_title_date_unknown",
            },
            {
                "title": "電能實業",
                "lang": "zh",
                "valid_from": "2011-02-16T10:56:17Z",
                "valid_to": None,
                "pageid": page["pageid"],
                "evidence": evidence,
            },
        ], []
    events = sorted(
        {
            row["logid"]: row
            for row in logs
            if row.get("logpage") == page["pageid"]
            and row.get("params", {}).get("target_ns") == 0
        }.values(),
        key=lambda row: row["timestamp"],
    )
    current = events[0]["title"] if events else page["title"]
    since, intervals, gaps = page["created"], [], []
    for event in events:
        if event["timestamp"] < since:
            continue
        normalize = lambda value: (
            value.replace("_", " ").translate(
                str.maketrans("团网点评电灯实业", "團網點評電燈實業")
            )
            if page["lang"] == "zh"
            else value.replace("_", " ")
        )
        if normalize(current) != normalize(event["title"]):
            gaps.append(f"Unlinked title transition before log {event['logid']}")
        intervals.append(
            {
                "title": current.replace(" ", "_"),
                "lang": page["lang"],
                "valid_from": since,
                "valid_to": event["timestamp"],
                "pageid": page["pageid"],
                "evidence": f"move_log:{event['logid']}",
            }
        )
        current, since = event["params"]["target_title"], event["timestamp"]
    intervals.append(
        {
            "title": current.replace(" ", "_"),
            "lang": page["lang"],
            "valid_from": since,
            "valid_to": None,
            "pageid": page["pageid"],
            "evidence": "creation_revision_and_observed_move_chain",
        }
    )
    if current.replace("_", " ") != page["title"].replace("_", " "):
        gaps.append("Latest reconstructed title differs from resolved current title")
    return intervals, gaps


def main() -> None:
    """Resolve HK and US reference maps; acquisition does not evaluate a strategy."""
    original = ROOT / "config/hk_wiki_aliases_observed_2026-11-12.csv"
    source = ROOT / "config/hk_wiki_titles.csv"
    if not original.exists():
        original.write_bytes(source.read_bytes())
    aliases = pd.read_csv(original)
    seeds = aliases.groupby(["symbol", "lang"], sort=False).first().reset_index()
    from src import config

    us = pd.DataFrame(
        [
            {"symbol": ticker, "lang": "en", "title": stock["wikipedia"]["en"]}
            for ticker, stock in config.stocks("US").items()
        ]
    )
    seeds = pd.concat([seeds, us], ignore_index=True)
    pages, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {
            pool.submit(page_details, row.title, row.lang): row
            for row in seeds.itertuples(index=False)
        }
        for future in as_completed(pending):
            row = pending[future]
            try:
                page = future.result() | {"symbol": row.symbol}
                page["aliases"] = sorted(
                    set(page["aliases"])
                    | set(
                        aliases.loc[
                            (aliases.symbol == row.symbol) & (aliases.lang == row.lang),
                            "title",
                        ].str.replace("_", " ")
                    )
                )
                pages.append(page)
            except (
                requests.RequestException,
                ValueError,
                KeyError,
                TypeError,
                OSError,
            ) as exc:
                errors.append(
                    {"symbol": row.symbol, "lang": row.lang, "error": str(exc)[:150]}
                )
            if len(pages) % 20 == 0:
                print(f"resolved_pages={len(pages)} failures={len(errors)}", flush=True)
    jobs = {(page["lang"], title) for page in pages for title in page["aliases"]}
    logs, completed = {}, 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {
            pool.submit(move_logs, title, lang): (lang, title)
            for lang, title in sorted(jobs)
        }
        for future in as_completed(pending):
            key = pending[future]
            try:
                logs[key] = future.result()
            except (
                requests.RequestException,
                ValueError,
                KeyError,
                TypeError,
                OSError,
            ) as exc:
                errors.append(
                    {"lang": key[0], "title": key[1], "error": str(exc)[:150]}
                )
            completed += 1
            if completed % 50 == 0:
                print(
                    f"move_queries={completed}/{len(jobs)} failures={len(errors)}",
                    flush=True,
                )
    # Reverse moves often suppress a redirect, so the temporary target is no
    # longer in today's redirect table. Follow those logged targets explicitly.
    identities = {page["pageid"] for page in pages}
    for _round in range(5):
        extra = {
            (lang, row["params"]["target_title"])
            for (lang, _title), rows in logs.items()
            for row in rows
            if row.get("logpage") in identities
            and row.get("params", {}).get("target_ns") == 0
            and (lang, row["params"]["target_title"]) not in logs
        }
        if not extra:
            break
        for lang, title in sorted(extra):
            logs[(lang, title)] = move_logs(title, lang)
        print(f"followed_temporary_targets={len(extra)} round={_round+1}", flush=True)
    intervals, gaps = [], []
    for page in pages:
        records = [
            record
            for (lang, _title), rows in logs.items()
            if lang == page["lang"]
            for record in rows
            if record.get("logpage") == page["pageid"]
        ]
        items, issues = reconstruct(page, records)
        intervals.extend(item | {"symbol": page["symbol"]} for item in items)
        gaps.extend(
            {"symbol": page["symbol"], "lang": page["lang"], "issue": issue}
            for issue in issues
        )
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "wiki_history_evidence.json").write_text(
        json.dumps({"pages": pages, "errors": errors, "gaps": gaps}, ensure_ascii=False)
    )
    frame = pd.DataFrame(intervals)
    hk = frame[frame.symbol.str.endswith(".HK")]
    for market, selected in [
        ("hk", hk),
        ("us", frame[~frame.symbol.str.endswith(".HK")]),
    ]:
        selected.to_csv(ROOT / f"config/{market}_wiki_title_intervals.csv", index=False)
    hk[["symbol", "title", "lang", "valid_from"]].to_csv(source, index=False)
    summary = {
        "retrieved_at": datetime.now(UTC).isoformat(),
        "article_identities": len(pages),
        "title_intervals": len(frame),
        "hk_symbols": int(hk.symbol.nunique()),
        "errors": errors,
        "discontinuities": gaps,
        "method": "Creation revision + currently observed redirects' move events filtered by stable logpage; suppressed/deleted aliases may be unavailable",
        "missing_english_article": ["6181.HK"],
        "shared_article_scope": {
            "2600.HK": "Chinese article includes parent and listed subsidiary; not separable company attention"
        },
        "unknown_earliest_title_dates": [
            {
                "symbol": "0006.HK",
                "lang": "zh",
                "title": "香港電燈",
                "reason": "2011 history merge; earliest date unavailable, left blank rather than invented",
            }
        ],
    }
    output = ROOT / "results/hk/week3/wiki_history_summary.json"
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
