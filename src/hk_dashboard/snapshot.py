"""Build the existing HK pages from shared local/S3 tables, never a Mac service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src import storage
from src.hk_dashboard.data import SOURCES, HKData, scalar
from src.hk_dashboard.paths import canonical, names


class SnapshotData:
    """Read-only build-time adapter for James's shared attention record schema.

    A required current table prevents publishing a silently empty HK site.
    Optional history, prices and quotes remain explicitly unavailable until
    their publishers populate the shared bucket. No model or network collector
    runs here. The browser only reads generated JSON files.
    """

    def __init__(self, root_uri: str, *, reader=None, json_reader=None):
        self.root = root_uri.rstrip("/")
        self.read = reader or storage.read_parquet
        self.read_json = json_reader or storage.read_json
        self.default_reader = reader is None
        self.default_json_reader = json_reader is None
        self.roster = names()
        self.built_at = datetime.now(UTC).isoformat()
        self.errors = {}
        self.current = self._table("wiki_current.parquet", required=True)
        if self.current.empty:
            raise ValueError("The shared wiki_current table has no HK observations")
        self.weekly = self._table("wiki_weekly.parquet")
        self.prices = self._table("prices_weekly.parquet")
        self.edits = self._table("wiki_edit_summaries.parquet")
        self.live = self._quotes()

    def _table(self, name, required=False):
        uri = f"{self.root}/processed/{name}"
        if not required and self.default_reader and not storage.exists(uri):
            self.errors[name] = "not_available"
            return pd.DataFrame()
        try:
            frame = self.read(uri).copy()
        except FileNotFoundError as exc:
            if required:
                raise RuntimeError(
                    f"Required shared HK table unavailable: {name}"
                ) from exc
            self.errors[name] = "not_available"
            return pd.DataFrame()
        if not {"market", "ticker"}.issubset(frame):
            raise ValueError(f"Shared {name} requires market and ticker columns")
        frame = frame[
            frame["market"].astype(str).str.lower().isin(["hk", "hong_kong"])
        ].copy()
        if frame.empty:
            self.errors[name] = "no_hk_rows"
            return frame
        frame["ticker"] = frame["ticker"].map(canonical)
        frame = frame[frame["ticker"].isin(self.roster)]
        if name.startswith("wiki_") and name != "wiki_edit_summaries.parquet":
            if not {"week", "value"}.issubset(frame):
                raise ValueError(f"Shared {name} requires week and value columns")
            if "source" in frame:
                frame = frame[frame["source"].astype(str).str.lower() == "wikipedia"]
        if "week" in frame:
            frame["week"] = pd.to_datetime(frame["week"], utc=True).dt.tz_localize(None)
        unique = ["ticker"] if name == "wiki_current.parquet" else ["ticker", "week"]
        if (
            name != "wiki_edit_summaries.parquet"
            and set(unique).issubset(frame)
            and frame.duplicated(unique).any()
        ):
            raise ValueError(f"Duplicate HK rows in {name}")
        return frame

    def _quotes(self):
        uri = f"{self.root}/raw/live/hk/current/latest.json"
        try:
            if self.default_json_reader and not storage.exists(uri):
                raise FileNotFoundError(uri)
            rows = self.read_json(uri)
        except FileNotFoundError:
            rows = []
            self.errors["hk_quotes"] = "not_published"
        if not isinstance(rows, list):
            raise TypeError("HK latest quote snapshot must contain a list")
        from src.hk_dashboard.live import valid_quote

        now = datetime.now(UTC)
        latest = {}
        for row in rows:
            try:
                quote = valid_quote(row, now, set(self.roster))
            except (KeyError, ValueError, TypeError):
                continue
            quote.update(
                name=self.roster[quote["symbol"]]["short_name"],
                currency="HKD",
                label="snapshot",
            )
            previous = latest.get(quote["symbol"])
            if not previous or quote["ts_exchange"] > previous["ts_exchange"]:
                latest[quote["symbol"]] = quote
        quotes = list(latest.values())
        return {
            "market": "hk",
            "quotes": quotes,
            "requested_count": len(self.roster),
            "received_count": len(quotes),
            "as_of": max((q["ts_received"] for q in quotes), default=None),
            "market_state": "snapshot",
            "market_open": False,
            "is_stale": True,
            "snapshot": True,
            "built_at": self.built_at,
        }

    @staticmethod
    def metric(row, source):
        column = "value" if source == "views" else "edits"
        prefix = "" if source == "views" else "edits_"
        value = scalar(row.get(column))
        flag = row.get(prefix + "spike")
        return {
            "available": value is not None,
            "count": value,
            "baseline": scalar(row.get(prefix + "baseline")),
            "ratio": scalar(row.get(prefix + "ratio")),
            "spike": bool(flag) if pd.notna(flag) and value is not None else False,
            "partial": False,
            "days_covered": 7,
            "tone": None,
        }

    def now(self):
        current = {row["ticker"]: row for row in self.current.to_dict("records")}
        quotes = {row["symbol"]: row for row in self.live["quotes"]}
        rows = []
        for code, meta in self.roster.items():
            record = current.get(code, {})
            rows.append(
                {
                    "ticker": code,
                    "name": meta["short_name"],
                    "name_zh": meta["name_zh"],
                    "quote": quotes.get(code),
                    "metrics": {
                        source: self.metric(record, source) for source in SOURCES
                    },
                    "spark": {},
                    "wiki_language": None,
                }
            )
        as_of = max(
            (str(v)[:10] for v in self.current.get("as_of", []) if pd.notna(v)),
            default=None,
        )
        return {
            "market": "hk",
            "snapshot": True,
            "built_at": self.built_at,
            "rows": rows,
            "names": {code: meta["short_name"] for code, meta in self.roster.items()},
            "live": self.live,
            "attention_stocks": len(current),
            "sources": SOURCES,
            "latest_weeks": {},
            "attention_window": f"Trailing seven published days through {as_of or 'the source as-of date'}. Values and baselines come from the shared S3 export; edits are unavailable where not published.",
            "reddit_available": False,
            "display_only": True,
        }

    def stock(self, code):
        code = canonical(code)
        meta = self.roster[code]
        history = (
            self.weekly[self.weekly["ticker"] == code]
            if not self.weekly.empty
            else pd.DataFrame()
        )
        prices = (
            self.prices[self.prices["ticker"] == code]
            if not self.prices.empty
            else pd.DataFrame()
        )
        h = {row["week"]: row for row in history.to_dict("records")}
        p = {row["week"]: row for row in prices.to_dict("records")}
        weeks = []
        for week in sorted(set(h) | set(p)):
            row = h.get(week, {})
            count = scalar(row.get("n_scored"))
            pos, neg = (
                scalar(row.get("sentiment_pos")),
                scalar(row.get("sentiment_neg")),
            )
            tone = (
                pos - neg
                if count and count > 0 and pos is not None and neg is not None
                else None
            )
            weeks.append(
                {
                    "week": str(week.date()),
                    "close": scalar(p.get(week, {}).get("close")),
                    "ret": scalar(p.get(week, {}).get("ret")),
                    "metrics": {s: self.metric(row, s) for s in SOURCES},
                    "tone": tone,
                    "tone_source": "Published Wikipedia edit sentiment"
                    if tone is not None
                    else None,
                }
            )
        last = str(prices["week"].max().date()) if not prices.empty else None
        quote = next((q for q in self.live["quotes"] if q["symbol"] == code), None)
        current = self.current[self.current["ticker"] == code]
        current_row = current.iloc[0].to_dict() if not current.empty else {}
        current_attention = {
            "as_of": str(current_row.get("as_of", ""))[:10],
            "metrics": {source: self.metric(current_row, source) for source in SOURCES},
        }
        revisions = []
        evidence = (
            self.edits[self.edits["ticker"] == code]
            if not self.edits.empty
            else pd.DataFrame()
        )
        if not evidence.empty and "timestamp" in evidence:
            for item in (
                evidence.sort_values("timestamp", ascending=False)
                .head(100)
                .to_dict("records")
            ):
                stamp = pd.Timestamp(item["timestamp"])
                week = pd.Timestamp(item.get("week", stamp))
                revisions.append(
                    {
                        "timestamp": stamp.isoformat(),
                        "week": str(week.date()),
                        "revid": None,
                        "url": None,
                        "comment": item.get("comment") or "No summary",
                    }
                )
        return {
            "market": "hk",
            "snapshot": True,
            "ticker": code,
            "name": meta["name"],
            "name_zh": meta["name_zh"],
            "current_attention": current_attention,
            "weeks": weeks,
            "quote": quote,
            "live": self.live,
            "revisions": revisions,
            "price_label": "Weekly price · HKD",
            "price_metadata": {
                "last_date": last,
                "source": "Shared processed/prices_weekly.parquet",
                "price_basis": "Shared weekly close; adjustment basis must be checked with its publisher",
            },
            "wiki": {
                "title": meta.get("wiki_en") or meta.get("wiki_zh"),
                "lang": None,
                "end": None,
            },
            "sentiment_weeks": sum(row["tone"] is not None for row in weeks),
            "sentiment_note": "Sentiment is shown only where the shared table publishes scored Wikipedia observations. Missing scores remain unavailable.",
            "sources": SOURCES,
            "reddit_available": False,
        }

    def spikes(self):
        rows = []
        source_table = self.weekly if not self.weekly.empty else self.current
        current_only = self.weekly.empty
        for row in source_table.to_dict("records"):
            for source in SOURCES:
                metric = self.metric(row, source)
                if metric["spike"]:
                    rows.append(
                        {
                            "ticker": row["ticker"],
                            "name": self.roster[row["ticker"]]["short_name"],
                            "week": str(row["week"].date()),
                            "period_label": f"7 days through {str(row.get('as_of', ''))[:10]}"
                            if current_only
                            else str(row["week"].date()),
                            "source": source,
                            "source_label": SOURCES[source]["label"]
                            + (" · trailing 7 days" if current_only else ""),
                            "language": None,
                            **metric,
                        }
                    )
        rows.sort(key=lambda row: row["week"], reverse=True)
        from src import config

        return {
            "market": "hk",
            "snapshot": True,
            "rows": rows,
            "current_only": current_only,
            "rule": config.spike_rule(),
            "sources": SOURCES,
        }

    def status(self):
        from src import config

        return {
            "market": "hk",
            "snapshot": True,
            "built_at": self.built_at,
            "roster_count": len(self.roster),
            "roster_as_of": "2026-11-04",
            "live": self.live,
            "attention_stocks": self.current["ticker"].nunique(),
            "historical_price_stocks": int(self.prices["ticker"].nunique())
            if not self.prices.empty
            else 0,
            "refreshed_attention_stocks": int(self.current["ticker"].nunique()),
            "wiki_english": None,
            "wiki_chinese": None,
            "wiki_languages_label": "Language breakdown not published in the shared table",
            "reddit_available": False,
            "saved_finbert_cohort_stocks": int(
                self.weekly[self.weekly["n_scored"].fillna(0) > 0]["ticker"].nunique()
            )
            if not self.weekly.empty and "n_scored" in self.weekly
            else 0,
            "research_cutoff": str(config.holdout_start()),
            "source_notes": [
                "Hosted snapshot generated from shared S3/local tables at build time; no localhost or personal checkout is used.",
                "Browser reloads cannot collect new quotes. Rebuild and publish the site to refresh this snapshot.",
                "Optional missing quote/history tables remain unavailable. Wikipedia current values are trailing-seven-day windows, not full calendar weeks.",
            ],
            "attention_errors": {
                name: {"source": value} for name, value in self.errors.items()
            },
        }

    def write(self, out: Path):
        """Write the finite read-only endpoint set consumed by the HK browser module."""
        base = out / "api/hk"
        payloads = {
            "now": self.now(),
            "live": self.live,
            "status": self.status(),
            "spike_weeks": self.spikes(),
            "strategy_log": HKData(root=out, display=out, live=object()).strategies(),
        }
        payloads.update({f"stock/{code}": self.stock(code) for code in self.roster})
        for name, value in payloads.items():
            path = base / f"{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, allow_nan=False, default=str) + "\n")
        return {
            "built_at": self.built_at,
            "stocks": len(self.roster),
            "attention_stocks": int(self.current["ticker"].nunique()),
            "missing_sources": self.errors,
        }
