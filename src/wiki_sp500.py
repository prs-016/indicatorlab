"""Wikipedia views and edits for every S&P 500 constituent over the last 5 years (config `wikipedia.sp500`).

    python -m src.wiki_sp500 titles      # constituent -> article map: config/us_sp500_wiki_titles.csv
    python -m src.wiki_sp500             # titles (if missing), then pull and build the weekly table

The window runs `years` years up to `end`. Weeks before `holdout_start` go to the research table;
later weeks go to a separate recent table, which is for the dashboard and spike checks, never for
strategy tests. Constituents come from Wikipedia's "List of S&P 500 companies" as it stood the day
before `holdout_start`, so nothing published after it picks the stocks. They are that day's members, so
stocks that left the index earlier in the window are missing (survivorship bias); `date_added` shows
which ones joined during it. Each stock's article is the page its table row links to, after redirects.

Views are summed over the article's redirects and edits come from its revision history, both from the
first full week the page was an article. Raw pulls are cached per stock under `data/raw/wikipedia/sp500/`
and reused, so an interrupted run resumes. Share classes on one article (GOOGL and GOOG) are pulled once,
under the first ticker listed.
"""
import argparse
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from src import config
from src.wiki_attention import ACTION_API_URL, article_views, weekly
from src.wiki_edits import edit_table, load_revisions, weekly_edits
from src.wiki_pipeline import PROCESSED, RAW, article_start
from src.wiki_titles import _get, page_info

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
TITLES_CSV = ROOT / "config" / "us_sp500_wiki_titles.csv"
RAW_SP500 = RAW / "sp500"
OUT_WEEKLY = {p: PROCESSED / f"sp500_weekly_{p}.csv" for p in ("research", "recent")}
OUT_COVERAGE = ROOT / "results" / "wikipedia" / "sp500_coverage.csv"
MARKET = "US"
TITLE_COLS = ["ticker", "yahoo", "name", "title", "sector", "sub_industry", "date_added", "cik",
              "duplicate_of", "list_revid", "status"]

# One constituent row of the list's wikitext table:  |{{NyseSymbol|MMM}}\n|[[3M]]|| Industrials || ...
# The symbol line may carry an editor comment (BRK.B) and the name cell text after the link
# ("[[Alphabet Inc.]] (Class A)", "[[Vistra Corp]].").
ROW_RE = re.compile(r"^\|\{\{\s*\w*Symbol\s*\|\s*([^}|]+?)\s*\}\}[^\n]*\n"
                    r"\|\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\][^|\n]*\|\|(.*)$", re.MULTILINE)


def params() -> dict:
    """The `wikipedia.sp500` block of config.yaml."""
    return config.load()["wikipedia"]["sp500"]


def window() -> tuple[pd.Timestamp, pd.Timestamp]:
    """Pull window, inclusive: `years` years up to `end`."""
    end = pd.Timestamp(params()["end"])
    return end + pd.Timedelta(days=1) - pd.DateOffset(years=params()["years"]), end


def split_holdout(weekly_rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Research rows (weeks that end before `holdout_start`) and recent rows (every later week)."""
    holdout = pd.Timestamp(config.holdout_start())
    research = pd.to_datetime(weekly_rows["week"]) + pd.Timedelta(days=6) < holdout
    return {"research": weekly_rows[research], "recent": weekly_rows[~research]}


def list_revision(as_of: pd.Timestamp, page: str | None = None) -> int:
    """Revision id of the list page as it stood at the end of day `as_of` (UTC)."""
    q = _get(ACTION_API_URL.format(lang="en"), {
        "action": "query", "prop": "revisions", "titles": page or params()["list_page"], "rvlimit": 1,
        "rvdir": "older", "rvstart": f"{as_of:%Y-%m-%d}T23:59:59Z", "rvprop": "ids", "formatversion": 2})
    return q["query"]["pages"][0]["revisions"][0]["revid"]


def parse_constituents(wikitext: str) -> pd.DataFrame:
    """Constituent rows of the list's first table: ticker, linked article title, sector, date added, CIK.

    `yahoo` is the ticker Yahoo uses (BRK.B -> BRK-B). Later tables (index changes) are ignored.
    """
    start = wikitext.find('id="constituents"')
    table = wikitext[start:wikitext.find("\n|}", start)]
    rows = []
    for symbol, title, rest in ROW_RE.findall(table):
        cells = [c.strip() for c in rest.split("||")]
        rows.append({"ticker": symbol.strip(), "yahoo": symbol.strip().replace(".", "-"),
                     "name": re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", title).strip(),
                     "title": title.strip().replace(" ", "_"), "sector": cells[0], "sub_industry": cells[1],
                     "date_added": cells[3] if len(cells) > 3 else "", "cik": cells[4] if len(cells) > 4 else ""})
    return pd.DataFrame(rows)


def resolve_titles(df: pd.DataFrame) -> pd.DataFrame:
    """Follow redirects to each article's current title and mark missing, disambiguation or shared articles."""
    shown = df["title"].str.replace("_", " ")
    info = page_info(shown.drop_duplicates().tolist(), "en")
    rows = [info[t] for t in shown]                     # one lookup per row; share classes repeat a title
    out = df.copy()
    out["title"] = [(i["redirect_to"] or t).replace(" ", "_") for t, i in zip(shown, rows)]
    out["status"] = ["missing" if not i["exists"] else "disambiguation" if i["disambiguation"] else "ok"
                     for i in rows]
    first = out.drop_duplicates("title").set_index("title")["ticker"]
    out["duplicate_of"] = [first[t] if first[t] != tk else "" for tk, t in zip(out["ticker"], out["title"])]
    return out


def build_titles(path: Path = TITLES_CSV) -> pd.DataFrame:
    """Write the constituent -> article map for the list as it stood the day before the holdout."""
    as_of = pd.Timestamp(config.holdout_start()) - pd.Timedelta(days=1)
    revid = list_revision(as_of)
    wikitext = _get(ACTION_API_URL.format(lang="en"),
                    {"action": "parse", "oldid": revid, "prop": "wikitext", "formatversion": 2})["parse"]["wikitext"]
    df = resolve_titles(parse_constituents(wikitext)).assign(list_revid=revid)[TITLE_COLS]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("%d constituents (%d articles) from revision %d", len(df), df["title"].nunique(), revid)
    return df


def stock_weekly(ticker: str, title: str, start: pd.Timestamp, end: pd.Timestamp,
                 raw: Path = RAW_SP500) -> pd.DataFrame:
    """Weekly views and edit counts of one article over full Monday weeks in `start`..`end`.

    Weeks before the page was an article (see `article_start`) are dropped. Views and revisions are
    cached in `raw/views/<ticker>.csv` and `raw/revisions/<ticker>.csv`.
    """
    revs = load_revisions(ticker, title, start, end, raw / "revisions")
    first_week = max(article_start(revs), start)
    vf = raw / "views" / f"{ticker}.csv"
    if vf.exists():
        views = pd.read_csv(vf, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        views = article_views(title, start, end).rename(ticker)
        vf.parent.mkdir(parents=True, exist_ok=True)
        views.rename_axis("date").to_csv(vf)
    wk_views = weekly(views)
    wk_views = wk_views[wk_views.index >= first_week]
    edits = weekly_edits(edit_table(revs), wk_views.index)
    return edits.assign(views=wk_views).reset_index().assign(ticker=ticker, market=MARKET, source="wikipedia")


def build(titles: pd.DataFrame | None = None, raw: Path = RAW_SP500) -> pd.DataFrame:
    """Pull every article (in parallel, resumable); write the research and recent weekly tables and coverage."""
    if titles is None:
        titles = pd.read_csv(TITLES_CSV, dtype=str, keep_default_na=False) if TITLES_CSV.exists() else build_titles()
    todo = titles[(titles["status"] == "ok") & (titles["duplicate_of"] == "")]
    start, end = window()
    frames, coverage = [], []
    with ThreadPoolExecutor(max_workers=params()["workers"]) as pool:
        jobs = {pool.submit(stock_weekly, r.ticker, r.title, start, end, raw): r for r in todo.itertuples()}
        for i, job in enumerate(as_completed(jobs), 1):
            r = jobs[job]
            try:
                wk = job.result()
                frames.append(wk)
                coverage.append({"ticker": r.ticker, "title": r.title, "weeks": len(wk), "first_week": wk["week"].min(),
                                 "views": wk["views"].sum(), "edits": wk["edits"].sum(), "error": ""})
            except (requests.RequestException, ValueError) as e:
                coverage.append({"ticker": r.ticker, "title": r.title, "error": f"{type(e).__name__}: {e}"})
            if i % 25 == 0 or i == len(jobs):
                log.info("%d/%d stocks", i, len(jobs))
    skipped = titles[titles["status"] != "ok"]
    coverage += [{"ticker": r.ticker, "title": r.title, "error": r.status} for r in skipped.itertuples()]
    out = pd.concat(frames, ignore_index=True).sort_values(["ticker", "week"])
    cols = ["week", "ticker", "market", "source", "views", "edits"]
    out = out[cols + [c for c in out.columns if c not in cols]]
    for period, rows in split_holdout(out).items():
        OUT_WEEKLY[period].parent.mkdir(parents=True, exist_ok=True)
        rows.to_csv(OUT_WEEKLY[period], index=False)
    OUT_COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(coverage).sort_values("ticker").to_csv(OUT_COVERAGE, index=False)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", choices=["titles", "build"], default="build")
    if ap.parse_args().step == "titles":
        build_titles()
    else:
        build()
