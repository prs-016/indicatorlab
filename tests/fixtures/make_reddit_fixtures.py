"""Write the tiny parquet files the /reddit/* route tests read (no AWS, no real data).

Two tickers (AAPL, TSLA) over four weeks; the last week (2025-09-29) runs into the holdout and must
never be served, so it is included on purpose.

    python tests/fixtures/make_reddit_fixtures.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
WEEKS = [date(2025, 9, 8), date(2025, 9, 15), date(2025, 9, 22), date(2025, 9, 29)]


def weekly() -> pd.DataFrame:
    """reddit_weekly: one row per ticker x week."""
    rows = []
    for tk, base in (("AAPL", 100.0), ("TSLA", 40.0)):
        for i, w in enumerate(WEEKS):
            value = base * (3 if i == 1 else 1) + i
            rows.append({"ticker": tk, "market": "us", "source": "reddit", "week": w, "value": value,
                         "baseline": base, "ratio": (value + 1) / (base + 1), "spike": i == 1,
                         "sentiment_pos": 0.5, "sentiment_neg": 0.2, "sentiment_neu": 0.3, "n_scored": int(value)})
    return pd.DataFrame(rows)


def by_type() -> pd.DataFrame:
    """reddit_weekly_by_type: the same split into investor and product subreddits."""
    parts = []
    for kind, share, pos in (("investor", 0.3, 0.4), ("product", 0.7, 0.6)):
        d = weekly().assign(subreddit_type=kind, sentiment_pos=pos, sentiment_neg=1 - pos - 0.3)
        d["value"] = (d["value"] * share).round()
        parts.append(d)
    out = pd.concat(parts, ignore_index=True)
    out.loc[(out["ticker"] == "TSLA") & (out["week"] == WEEKS[0]), ["sentiment_pos", "sentiment_neg",
                                                                     "sentiment_neu"]] = float("nan")
    return out


def top_posts() -> pd.DataFrame:
    """reddit_top_posts: three posts per ticker-week, ranked by score."""
    rows = []
    for tk in ("AAPL", "TSLA"):
        for w in WEEKS:
            for rank, score in enumerate((900, 400, 50), 1):
                rows.append({"ticker": tk, "market": "us", "week": w, "rank": rank,
                             "post_id": f"{tk.lower()}{w:%m%d}{rank}", "subreddit": "stocks" if rank == 2 else "apple",
                             "subreddit_type": "investor" if rank == 2 else "product",
                             "title": f"{tk} post {rank}", "url": f"https://www.reddit.com/r/x/{rank}",
                             "score": score, "num_comments": 10 * rank, "sentiment_label": "positive",
                             "sentiment_pos": 0.8, "sentiment_neg": 0.1, "sentiment_neu": 0.1})
    return pd.DataFrame(rows)


def write(folder: Path = HERE) -> None:
    """Write the three fixture files into `folder`."""
    weekly().to_parquet(folder / "reddit_weekly.parquet", index=False)
    by_type().to_parquet(folder / "reddit_weekly_by_type.parquet", index=False)
    top_posts().to_parquet(folder / "reddit_top_posts.parquet", index=False)


if __name__ == "__main__":
    write()
    print(f"wrote fixtures to {HERE}")
