"""Wikipedia edit history: revisions, weekly edit activity, reverts and keyword tags of edit summaries.

Revisions come from the MediaWiki API (prop=revisions), following `rvcontinue` until done.
The revert pattern and the tag keywords live in config.yaml (`wikipedia.revert_pattern`, `edit_tags`).
"""
import re
from pathlib import Path

import pandas as pd

from src import config
from src.wiki_attention import (
    ACTION_API_URL,
    REQUEST_TIMEOUT_S,
    SESSION,
    user_agent,
    week_start,
)

REV_PROPS = "ids|timestamp|comment|size|user"
REV_COLS = ["revid", "timestamp", "user", "size", "comment"]


def _rev_query(title: str, lang: str, **extra) -> dict:
    params = {"action": "query", "prop": "revisions", "titles": title, "rvprop": REV_PROPS,
              "format": "json", "formatversion": 2, **extra}
    r = SESSION.get(ACTION_API_URL.format(lang=lang), params=params, headers=user_agent(),
                     timeout=REQUEST_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def _rows(data: dict) -> list[dict]:
    page = data["query"]["pages"][0]
    if page.get("missing"):
        raise ValueError(f"no Wikipedia page {page['title']!r}")
    return [{c: rev.get(c) for c in REV_COLS} for rev in page.get("revisions", [])]


def revisions(title: str, start: pd.Timestamp, end: pd.Timestamp, lang: str = "en") -> pd.DataFrame:
    """Every revision of a page with start <= timestamp <= end (UTC), oldest first.

    Also returns the last revision before `start` (flagged `before_start`), so the size change of
    the first revision in the window is known. Hidden users or summaries come back empty.
    """
    rows = _rows(_rev_query(title, lang, rvlimit=1, rvdir="older", rvstart=f"{start:%Y-%m-%dT00:00:00Z}"))
    for row in rows:
        row["before_start"] = True
    params = {"rvlimit": "max", "rvdir": "newer", "rvstart": f"{start:%Y-%m-%dT00:00:00Z}",
              "rvend": f"{end:%Y-%m-%dT23:59:59Z}"}
    while True:
        data = _rev_query(title, lang, **params)
        rows += _rows(data)
        if "continue" not in data:
            break
        params["rvcontinue"] = data["continue"]["rvcontinue"]
    df = pd.DataFrame(rows, columns=[*REV_COLS, "before_start"])
    df["before_start"] = df["before_start"].fillna(False).astype(bool)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df["comment"] = df["comment"].fillna("")
    df["user"] = df["user"].fillna("")
    return df.drop_duplicates("revid").sort_values("timestamp").reset_index(drop=True)


def load_revisions(ticker: str, title: str, start: pd.Timestamp, end: pd.Timestamp, cache_dir: Path,
                   lang: str = "en") -> pd.DataFrame:
    """Revisions for one stock's article, read from `cache_dir/<ticker>.csv` or pulled and cached there.

    Use one cache directory per period (research, recent): a cached file is reused as is.
    """
    f = Path(cache_dir) / f"{ticker}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["timestamp"], keep_default_na=False,
                           dtype={"comment": str, "user": str})
    df = revisions(title, start, end, lang)
    f.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False)
    return df


def _word_regex(alternatives: list[str] | str) -> re.Pattern:
    alts = alternatives if isinstance(alternatives, str) else "|".join(alternatives)
    return re.compile(rf"\b(?:{alts})\b", re.IGNORECASE)


def tag_summaries(comments: pd.Series) -> pd.DataFrame:
    """Boolean columns: `revert` plus one `tag_<name>` per keyword group in config.yaml."""
    cfg = config.load()["wikipedia"]
    out = {"revert": comments.str.contains(_word_regex(cfg["revert_pattern"]))}
    for name, words in cfg["edit_tags"].items():
        out[f"tag_{name}"] = comments.str.contains(_word_regex(words))
    return pd.DataFrame(out, index=comments.index)


def edit_table(revs: pd.DataFrame) -> pd.DataFrame:
    """One row per revision inside the window, with size change, revert flag and tags."""
    df = revs.sort_values("timestamp").copy()
    df["delta"] = df["size"].diff()
    df = df[~df["before_start"]]
    return pd.concat([df, tag_summaries(df["comment"])], axis=1)


def weekly_edits(edits: pd.DataFrame, weeks: pd.DatetimeIndex) -> pd.DataFrame:
    """Per Monday-labelled week: edits, distinct editors, bytes added and removed, reverts, tag counts.

    Weeks with no edits are 0. `weeks` is the full grid of week labels to report.
    """
    e = edits.assign(week=week_start(edits["timestamp"]))
    tag_cols = [c for c in e.columns if c.startswith("tag_")]
    g = e.groupby("week")
    out = pd.DataFrame({
        "edits": g.size(),
        "editors": g["user"].nunique(),
        "bytes_added": g["delta"].apply(lambda d: d.clip(lower=0).sum()),
        "bytes_removed": g["delta"].apply(lambda d: (-d).clip(lower=0).sum()),
        "reverts": g["revert"].sum(),
        **{c: g[c].sum() for c in tag_cols},
    })
    out = out.reindex(weeks, fill_value=0)
    out.index.name = "week"
    return out


def daily_edits(edits: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    """Number of edits per calendar day (UTC) on the `days` grid."""
    return edits.groupby(edits["timestamp"].dt.normalize()).size().reindex(days, fill_value=0)
