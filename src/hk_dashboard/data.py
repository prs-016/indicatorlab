"""HK dashboard projections of actual display caches and frozen saved outputs.

There is no strategy execution, data repair, inferred Reddit corpus or newly
scored sentiment here. Wikipedia counts remain Wikipedia, and missing is null.
"""

from __future__ import annotations

import json
import math
import threading
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.hk_dashboard.live import LiveSource
from src.hk_dashboard.paths import ROOT, canonical, display_root, names, source_root
from src.reddit.spike_rule import flag_spikes

SOURCES = {
    "views": {"label": "Wikipedia views", "unit": "views"},
    "edits": {"label": "Wikipedia edits", "unit": "edits"},
}


def scalar(value):
    """Convert saved numeric values to finite JSON numbers without inventing zeros."""
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def json_file(path: Path, limit=12_000_000):
    """Read bounded local metadata and recorded views, never arbitrary browser paths."""
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("HK source exceeds its size bound")
    return json.loads(raw)


def mtime(path: Path):
    return path.stat().st_mtime_ns if path.is_file() else 0


class HKData:
    """Read-only market adapter with separate quote, historical and display provenance.

    Args:
        root: Existing HK source checkout or mounted data root.
        display: Separately refreshed display cache.
        live: Quote reader, injectable in offline tests.
    """

    def __init__(self, *, root=None, display=None, live=None):
        self.root = Path(root) if root else source_root()
        self.display = Path(display) if display else display_root()
        self.live = live or LiveSource()
        self.roster = names()
        self._attention_cache = None
        self._prices = {}
        self.lock = threading.RLock()

    def stock_code(self, raw) -> str:
        """Resolve only configured HSI codes; cross-market names never fall back to US."""
        code = canonical(raw)
        if code not in self.roster:
            raise KeyError("Unknown HK stock in this roster")
        return code

    def _raw_attention(self, code):
        path = self.display / "wikipedia" / f"{code}.json"
        if path.is_file():
            document = json_file(path)
            if any(
                row.get("views") is not None or row.get("edits") is not None
                for row in document.get("weeks", [])
            ):
                return document
        older = self.root / "data/hk_week4/attention" / f"{code}.parquet"
        if older.is_file():
            frame = pd.read_parquet(older)
            rows = [
                {
                    "week": str(pd.Timestamp(day).date()),
                    "views": scalar(row["views"]),
                    "edits": scalar(row["edits"]),
                    "days_covered": 7,
                    "partial": False,
                }
                for day, row in frame.iterrows()
            ]
            identity = self.roster[code]
            return {
                "symbol": code,
                "weeks": rows,
                "revisions": [],
                "title": identity.get("wiki_en") or identity.get("wiki_zh"),
                "lang": "en" if identity.get("wiki_en") else "zh",
                "as_of": datetime.fromtimestamp(older.stat().st_mtime, UTC).isoformat(),
                "source_kind": "saved_research_counts",
                "display_only": True,
                "errors": {"refresh": "No current display cache"},
            }
        return {
            "symbol": code,
            "weeks": [],
            "revisions": [],
            "errors": {"attention": "Not collected"},
        }

    def attention(self) -> tuple[dict, dict]:
        """Reuse the shared past-only rule, retaining weekly gaps and partial-week dates."""
        token = tuple(
            (
                mtime(self.display / "wikipedia" / f"{code}.json"),
                mtime(self.root / "data/hk_week4/attention" / f"{code}.parquet"),
            )
            for code in self.roster
        )
        with self.lock:
            if self._attention_cache and self._attention_cache[0] == token:
                return self._attention_cache[1:]
            all_frames = {}
            documents = {}
            for code in self.roster:
                try:
                    document = self._raw_attention(code)
                except (OSError, ValueError, KeyError, TypeError):
                    document = {
                        "symbol": code,
                        "weeks": [],
                        "errors": {"attention": "Unreadable source"},
                    }
                documents[code] = document
                if not document.get("weeks"):
                    continue
                frame = pd.DataFrame(document["weeks"])
                frame.index = pd.to_datetime(frame.pop("week"))
                if frame.index.has_duplicates:
                    continue
                frame = frame.sort_index().reindex(
                    pd.date_range(frame.index.min(), frame.index.max(), freq="W-MON")
                )
                frame.index.name = "week"
                for source in SOURCES:
                    raw = pd.to_numeric(
                        frame.get(source, pd.Series(index=frame.index, dtype=float)),
                        errors="coerce",
                    )
                    days = pd.to_numeric(
                        frame.get("days_covered", pd.Series(7, index=frame.index)),
                        errors="coerce",
                    )
                    comparison = raw.copy()
                    partial = days.lt(7)
                    comparison.loc[partial] = np.nan
                    # Only the current partial week uses daily-rate projection;
                    # older incomplete weeks never masquerade as full baselines.
                    last = frame.index[-1]
                    current = pd.Timestamp(datetime.now(UTC).date())
                    current = current - pd.Timedelta(days=current.weekday())
                    if last == current and 0 < days.loc[last] < 7:
                        comparison.loc[last] = raw.loc[last] * 7 / days.loc[last]
                    flags = flag_spikes(comparison, config.spike_rule())
                    for column in ["baseline", "ratio", "rz", "spike"]:
                        frame[f"{source}_{column}"] = flags[column]
                    frame[source] = raw
                all_frames[code] = frame
            self._attention_cache = (token, all_frames, documents)
            return all_frames, documents

    def _metric(self, frame, week, source):
        if frame is None or week not in frame.index:
            return {
                "available": False,
                "count": None,
                "baseline": None,
                "ratio": None,
                "spike": False,
                "tone": None,
            }
        row = frame.loc[week]
        count = scalar(row.get(source))
        return {
            "available": count is not None,
            "count": count,
            "baseline": scalar(row.get(source + "_baseline")),
            "ratio": scalar(row.get(source + "_ratio")),
            "rz": scalar(row.get(source + "_rz")),
            "spike": bool(row.get(source + "_spike", False))
            if count is not None
            else False,
            "days_covered": scalar(row.get("days_covered")),
            "partial": bool(row.get("partial", False)),
            "tone": None,
        }

    def latest_weeks(self, frames):
        """Choose the latest week observed for at least half the covered stocks.

        Maximizing coverage alone can pin a page to a months-old week because
        one recently created article has a gap. A majority keeps the display
        current without letting one early-published daily observation set it.
        """
        result = {}
        for source in SOURCES:
            coverage = {}
            for frame in frames.values():
                for week in frame.index[frame[source].notna()]:
                    coverage[week] = coverage.get(week, 0) + 1
            if coverage:
                minimum = max(1, (len(frames) + 1) // 2)
                choices = [week for week, count in coverage.items() if count >= minimum]
                if choices:
                    result[source] = max(choices)
        return result

    def now(self):
        """Return all 95 names, actual attention coverage and independently live prices."""
        frames, documents = self.attention()
        latest = self.latest_weeks(frames)
        live = self.live.snapshot()
        quotes = {row["symbol"]: row for row in live["quotes"]}
        rows = []
        for code, metadata in self.roster.items():
            row = {
                "ticker": code,
                "name": metadata["short_name"],
                "name_zh": metadata["name_zh"],
                "quote": quotes.get(code),
                "metrics": {},
                "spark": {},
                "wiki_language": documents.get(code, {}).get("lang"),
            }
            frame = frames.get(code)
            for source in SOURCES:
                week = latest.get(source)
                row["metrics"][source] = self._metric(frame, week, source)
                row["metrics"][source]["week"] = (
                    str(week.date()) if week is not None else None
                )
                row["spark"][source] = (
                    [
                        scalar(value)
                        for value in frame.loc[:week, source + "_ratio"].tail(12)
                    ]
                    if frame is not None and week is not None
                    else []
                )
            rows.append(row)
        return {
            "market": "hk",
            "names": {code: value["short_name"] for code, value in self.roster.items()},
            "rows": rows,
            "latest_weeks": {key: str(value.date()) for key, value in latest.items()},
            "sources": SOURCES,
            "rule": config.spike_rule(),
            "live": live,
            "roster_as_of": "2026-11-04",
            "attention_stocks": len(frames),
            "reddit_available": False,
            "display_only": True,
        }

    def price_weeks(self, code):
        """Read one consistent price vintage; never splice adjusted vintages together."""
        newer = self.display / "prices" / f"{code}.parquet"
        path = None
        if newer.is_file():
            path = newer
        else:
            matches = sorted(
                (self.root / "research/hk_market_history/prices").glob(
                    f"{code}__daily__*.csv"
                )
            )
            if matches:
                path = matches[-1]
        if path is None:
            return pd.DataFrame(), None
        key = (str(path), mtime(path))
        with self.lock:
            if key in self._prices:
                return self._prices[key]
        if path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path, index_col="Date", parse_dates=True)
        frame.index = pd.DatetimeIndex(frame.index)
        if frame.index.tz is not None:
            frame.index = frame.index.tz_localize(None)
        frame = frame.sort_index()
        if frame.index.has_duplicates:
            raise ValueError("Duplicate historical price dates")
        adjusted = "Adj Close" if "Adj Close" in frame else None
        if adjusted is None:
            raise ValueError("Historical adjusted-price basis is unavailable")
        weekly = (
            pd.DataFrame(
                {
                    "close": pd.to_numeric(frame[adjusted], errors="coerce"),
                    "nominal_close": pd.to_numeric(frame["Close"], errors="coerce"),
                }
            )
            .resample("W-SUN")
            .last()
        )
        weekly.index = weekly.index - pd.Timedelta(days=6)
        weekly["ret"] = weekly["close"].pct_change(fill_method=None)
        meta = {
            "price_basis": "vendor split/dividend-adjusted weekly close",
            "currency": "HKD",
            "last_date": str(frame.index.max().date()),
            "first_date": str(frame.index.min().date()),
            "source": "Yahoo Finance",
            "vintage": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        }
        result = weekly, meta
        with self.lock:
            if len(self._prices) >= 128:
                self._prices.clear()
            self._prices[key] = result
        return result

    def _sentiment(self, code, document):
        path = self.root / "data/hk_week4/wiki_sentiment.parquet"
        if not path.is_file():
            return {}
        old = self.root / "data/hk_week4/wikipedia" / f"{code}.json"
        if not old.is_file():
            return {}
        identity = json_file(old).get("identity", {})
        if identity.get("lang") != document.get("lang") or identity.get(
            "title", ""
        ).replace(" ", "_") != str(document.get("title", "")).replace(" ", "_"):
            return {}
        values = pd.read_parquet(path)
        values = values[values["ticker"] == code]
        available = {row["week"]: row for row in values.to_dict("records")}
        if document.get("source_kind") == "saved_research_counts":
            return available
        revision_weeks = {}
        for revision in document.get("revisions", []):
            day = (
                pd.Timestamp(revision["timestamp"])
                .tz_convert("UTC")
                .tz_localize(None)
                .normalize()
            )
            week = day - pd.Timedelta(days=day.weekday())
            old_row = revision_weeks.get(str(week.date()))
            if old_row is None or revision["timestamp"] > old_row["timestamp"]:
                revision_weeks[str(week.date())] = revision
        return {
            week: row
            for week, row in available.items()
            if revision_weeks.get(str(week), {}).get("revid") == row["last_revision"]
        }

    def stock(self, raw):
        """Price, sourced attention, saved FinBERT and linked revision evidence."""
        code = self.stock_code(raw)
        meta = self.roster[code]
        frames, documents = self.attention()
        frame = frames.get(code)
        document = documents[code]
        prices, price_meta = self.price_weeks(code)
        weeks = prices.index
        if frame is not None:
            weeks = weeks.union(frame.index)
        scores = self._sentiment(code, document)
        rows = []
        for week in weeks.sort_values():
            row = {
                "week": str(week.date()),
                "close": scalar(prices.loc[week, "close"])
                if week in prices.index
                else None,
                "ret": scalar(prices.loc[week, "ret"])
                if week in prices.index
                else None,
                "research_grade": (week + pd.Timedelta(days=7)).date()
                <= config.holdout_start(),
                "metrics": {
                    source: self._metric(frame, week, source) for source in SOURCES
                },
            }
            score = scores.get(str(week.date()))
            row["tone"] = scalar(score["sentiment"]) if score is not None else None
            row["tone_source"] = (
                "Saved FinBERT on Wikipedia additions" if score is not None else None
            )
            rows.append(row)
        revisions = []
        for row in document.get("revisions", []):
            item = {
                key: row.get(key) for key in ["revid", "timestamp", "size", "comment"]
            }
            item["url"] = (
                f"https://{document.get('lang', 'en')}.wikipedia.org/w/index.php?oldid={int(row['revid'])}"
            )
            day = (
                pd.Timestamp(row["timestamp"])
                .tz_convert("UTC")
                .tz_localize(None)
                .normalize()
            )
            item["week"] = str((day - pd.Timedelta(days=day.weekday())).date())
            revisions.append(item)
        live = self.live.snapshot()
        quote = next((row for row in live["quotes"] if row["symbol"] == code), None)
        return {
            "market": "hk",
            "ticker": code,
            "name": meta["name"],
            "name_zh": meta["name_zh"],
            "aliases": meta["aliases"],
            "weeks": rows,
            "price_metadata": price_meta,
            "quote": quote,
            "live": {key: value for key, value in live.items() if key != "quotes"},
            "wiki": {
                key: document.get(key)
                for key in [
                    "title",
                    "lang",
                    "as_of",
                    "start",
                    "end",
                    "source_note",
                    "article_url",
                    "errors",
                ]
            },
            "revisions": revisions,
            "reddit_available": False,
            "sentiment_weeks": len(scores),
            "rule": config.spike_rule(),
            "sources": SOURCES,
        }

    def spikes(self):
        """Actual historical Wiki spike flags, not price moves relabelled as chatter."""
        frames, documents = self.attention()
        rows = []
        for code, frame in frames.items():
            for source in SOURCES:
                for week in frame.index[frame[source + "_spike"].fillna(False)]:
                    metric = self._metric(frame, week, source)
                    if metric["available"]:
                        rows.append(
                            {
                                "ticker": code,
                                "name": self.roster[code]["short_name"],
                                "week": str(week.date()),
                                "source": source,
                                "source_label": SOURCES[source]["label"],
                                "language": documents[code].get("lang"),
                                **metric,
                            }
                        )
        rows.sort(key=lambda row: (row["week"], row["ratio"] or 0), reverse=True)
        return {
            "market": "hk",
            "rows": rows,
            "names": {code: row["short_name"] for code, row in self.roster.items()},
            "rule": config.spike_rule(),
            "sources": SOURCES,
            "display_only": True,
        }

    def strategies(self):
        """Expose frozen HK results and saved net-return curves without running them."""
        bundled = ROOT / "results/hk_dashboard/saved_research.json"
        if bundled.is_file():
            return json_file(bundled)
        path = self.root / "results/hk/week4/three_strategy_results.csv"
        rows = []
        series = {}
        if path.is_file():
            frame = pd.read_csv(path)
            frame = frame[frame["market"] == "HK"]
            rows = json.loads(frame.to_json(orient="records"))
            run = self.root / "data/hk_week4/runs/three_v2_paths_20261115"
            returns_path = run / "HK_test_evaluations.npz"
            dates_path = run / "HK.npz"
            request_path = run / "HK_test_evaluations.request.json"
            if (
                returns_path.is_file()
                and dates_path.is_file()
                and request_path.is_file()
            ):
                request = json_file(request_path)
                with (
                    np.load(returns_path, allow_pickle=False) as saved,
                    np.load(dates_path, allow_pickle=False) as inputs,
                ):
                    tasks = {task["id"]: task for task in request["tasks"]}
                    for row in rows:
                        key = f"HK.{row['strategy']}.test.base"
                        if key not in saved or key not in tasks:
                            continue
                        task = tasks[key]
                        dates = pd.to_datetime(
                            inputs["dates"][int(task["start"]) : int(task["end"]) + 1]
                        )
                        values = np.asarray(saved[key], dtype=float)
                        if len(values) != len(dates) or not np.isfinite(values).all():
                            continue
                        series[row["strategy"]] = {
                            "dates": [str(day.date()) for day in dates],
                            "growth": np.cumprod(1 + values).tolist(),
                            "currency": "HKD",
                            "basis": "saved net daily returns",
                        }
        return {
            "market": "hk",
            "rows": rows,
            "series": series,
            "saved_only": True,
            "cohort_stocks": 5,
            "train": ["2016-06-01", "2021-12-31"],
            "test": ["2022-01-01", "2026-10-31"],
            "native_confirmation": "Numerical differences documented; nominee ineligible",
            "note": "Archived five-stock research, not a new 95-stock test. All three cases are DROP.",
        }

    def status(self):
        """Report input coverage rather than treating missing datasets as zero activity."""
        frames, documents = self.attention()
        price_count = sum(
            bool(
                list(
                    (self.root / "research/hk_market_history/prices").glob(
                        f"{code}__daily__*.csv"
                    )
                )
            )
            or (self.display / "prices" / f"{code}.parquet").is_file()
            for code in self.roster
        )
        refreshed = sum(
            document.get("source_kind") != "saved_research_counts"
            and bool(document.get("weeks"))
            for document in documents.values()
        )
        return {
            "market": "hk",
            "roster_as_of": "2026-11-04",
            "roster_count": len(self.roster),
            "live": self.live.snapshot(),
            "historical_price_stocks": price_count,
            "attention_stocks": len(frames),
            "refreshed_attention_stocks": refreshed,
            "wiki_english": sum(
                document.get("lang") == "en" for document in documents.values()
            ),
            "wiki_chinese": sum(
                document.get("lang") == "zh" for document in documents.values()
            ),
            "reddit_available": False,
            "saved_finbert_cohort_stocks": 5,
            "research_cutoff": str(config.holdout_start()),
            "source_notes": [
                "Wikipedia pageviews and edits are separate from Reddit mentions.",
                "Fresh counts use current article titles; shared articles and language differences are disclosed.",
                "Missing sentiment remains unavailable. Display refreshes do not expand the frozen research cohort.",
            ],
            "attention_errors": {
                code: document["errors"]
                for code, document in documents.items()
                if document.get("errors")
            },
        }
