"""Offline CSV adapter for James's ticker -> language -> current title interface.

Historical rows remain explicit records. This module performs no downloads,
config writes, redirect aggregation or point-in-time coverage certification.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "config/india_wiki_titles.csv"
DEFAULT_LEDGER = ROOT / "config/india_wiki_mapping_ledger.json"
FIELDS = ["symbol", "title", "lang", "valid_from"]
KINDS = {"current", "historical_move_observed"}


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Title boundaries must be explicit UTC timestamps")
    return parsed


@dataclass(frozen=True)
class TitleRecord:
    """One evidenced title; unknown UTC boundaries remain None.

    Attributes:
        symbol: Bare NSE symbol.
        title: Original canonical or historical title, with no translation.
        lang: Wikipedia language code (en or hi).
        kind: Current title or observed historical move.
        valid_from: Evidenced start event, or None when unknown.
        valid_to: Known end event from the ledger, or None.
    """

    symbol: str
    title: str
    lang: str
    kind: str
    valid_from: datetime | None
    valid_to: datetime | None


@dataclass(frozen=True)
class IndiaTitleMapping:
    """Validated title records for export; does not infer historical eligibility.

    Attributes:
        records: Immutable current and historical title records from the CSV.
    """

    records: tuple[TitleRecord, ...]

    def current_titles(self) -> dict[str, dict[str, str]]:
        """Return ticker -> language -> current title, matching universe() output.

        Takes no arguments. Returns a fresh dictionary using .NS tickers. This
        export is current identity only, not a date-qualified historical universe.
        Unmapped companies are omitted; historical rows never overwrite current.
        """
        out: dict[str, dict[str, str]] = {}
        for row in self.records:
            if row.kind == "current":
                out.setdefault(row.symbol + ".NS", {})[row.lang] = row.title
        return out

    def title_history(self) -> dict[str, dict[str, tuple[TitleRecord, ...]]]:
        """Return all titles grouped by ticker/language, retaining known boundaries.

        Takes no arguments. Returns current and former records without summing,
        filling dates or treating unknown boundaries as an unbounded interval.
        """
        grouped: dict[str, dict[str, tuple[TitleRecord, ...]]] = {}
        for row in self.records:
            langs = grouped.setdefault(row.symbol + ".NS", {})
            langs[row.lang] = (*langs.get(row.lang, ()), row)
        return grouped


def load_india_titles(
    csv_path: Path = DEFAULT_CSV, ledger_path: Path = DEFAULT_LEDGER
) -> IndiaTitleMapping:
    """Read the required CSV with its evidence ledger, failing on ambiguity.

    Args:
        csv_path: UTF-8 four-column mapping CSV.
        ledger_path: JSON ledger identifying current/former titles and end events.
            Required because the CSV alone cannot identify the current title.

    Returns:
        Validated records with unknown dates preserved as None. Raises ValueError
        for duplicate/conflicting keys, unmatched evidence or invalid boundaries.
        Filesystem/JSON errors propagate. No network or configuration changes occur.
    """
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    evidence = {}
    for item in ledger:
        key = (item["symbol"], item["lang"], item["title"])
        if key in evidence:
            raise ValueError(f"Duplicate ledger key: {key}")
        evidence[key] = item
    records = []
    seen = set()
    current = set()
    with Path(csv_path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("Expected symbol,title,lang,valid_from schema")
        for row in reader:
            if None in row or any(row[field] is None for field in FIELDS):
                raise ValueError("Malformed mapping row")
            symbol, title, lang = (row[field] for field in FIELDS[:3])
            if (
                not symbol
                or not title
                or symbol != symbol.strip()
                or title != title.strip()
                or symbol.endswith(".NS")
                or lang not in {"en", "hi"}
            ):
                raise ValueError("Invalid symbol, title or language")
            key = (symbol, lang, title)
            if key in seen:
                raise ValueError(f"Duplicate mapping key: {key}")
            seen.add(key)
            item = evidence.get(key)
            if item is None or row["valid_from"] != item.get("valid_from"):
                raise ValueError(f"Mapping has no matching date/title evidence: {key}")
            kind = item.get("row_kind")
            if kind not in KINDS:
                raise ValueError(f"Unknown title kind: {key}")
            start = _timestamp(row["valid_from"])
            end = _timestamp(item.get("valid_to"))
            if start and not item.get("start_logid"):
                raise ValueError(f"Title start lacks event evidence: {key}")
            if end and not item.get("end_logid"):
                raise ValueError(f"Title end lacks event evidence: {key}")
            if start and end and start >= end:
                raise ValueError(f"Invalid title interval: {key}")
            pair = (symbol, lang)
            if kind == "current":
                if pair in current or end is not None:
                    raise ValueError(f"Conflicting current title: {pair}")
                current.add(pair)
            records.append(TitleRecord(symbol, title, lang, kind, start, end))
    for row in records:
        if row.kind != "current" and (row.symbol, row.lang) not in current:
            raise ValueError(
                "Historical title lacks a current company/language mapping"
            )
    return IndiaTitleMapping(tuple(records))
