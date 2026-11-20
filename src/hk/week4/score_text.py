"""Score bounded Wikipedia additions with the team's unchanged shared FinBERT core."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.hk.week4.public_data import CUTOFF, DATA, ROOT
from src.sentiment.finbert_scorer import FinbertScorer, prepare_text


def score_additions(model_dir: Path | None = None) -> dict:
    """Keep missing additions missing; shared preprocessing, batches and probabilities."""
    rows = []
    for path in sorted((DATA / "wikipedia").glob("*.json")):
        article = json.loads(path.read_text())
        if article.get("research_cutoff") != str(CUTOFF.date()):
            raise ValueError("Article cache belongs to another research boundary")
        for row in article["weeks"]:
            if pd.Timestamp(row["week"], tz="UTC") + pd.Timedelta(days=7) > CUTOFF:
                raise ValueError("Partial or future attention week")
            text = prepare_text(None, row.get("added_text"))
            if len(text) >= 20:
                rows.append(
                    {
                        "ticker": article["ticker"],
                        "week": row["week"],
                        "text": text,
                        "last_revision": row["last_revision"],
                        "available_at": (
                            pd.Timestamp(row["week"], tz="UTC") + pd.Timedelta(days=7)
                        ).isoformat(),
                        "ts_last_revision": row["ts_last_revision"],
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
    if not rows:
        raise ValueError("No dated additions available")
    frame = pd.DataFrame(rows)
    p = config.load()["sentiment"]
    scorer = FinbertScorer(
        str(model_dir) if model_dir else p["model"],
        str(p["revision"]),
        int(p["batch_size"]),
        int(p["max_tokens"]),
    )
    # Only a Week4 cache produced by this shared core is eligible for reuse.
    dest = DATA / "wiki_sentiment.parquet"
    marker = DATA / "wiki_sentiment_method.json"
    method = {
        "shared_scorer_commit": "ca3d391cd596a08af6d7ea290563c2fb1712fda9",
        "shared_scorer_sha256": hashlib.sha256(
            (ROOT / "src/sentiment/finbert_scorer.py").read_bytes()
        ).hexdigest(),
        "model": p["model"],
        "revision": str(p["revision"]),
        "max_tokens": int(p["max_tokens"]),
    }
    old = pd.DataFrame()
    if dest.exists():
        if not marker.exists() or json.loads(marker.read_text()) != method:
            raise ValueError("Existing sentiment cache has different shared code/model")
        old = (
            pd.read_parquet(dest)
            .drop_duplicates("text_sha256")
            .set_index("text_sha256")
        )
    todo = frame.loc[~frame.text_sha256.isin(old.index)].drop_duplicates("text_sha256")
    scored = scorer.score(todo.text.tolist())
    renamed = scored.rename(
        columns={
            "sentiment_pos": "positive",
            "sentiment_neg": "negative",
            "sentiment_neu": "neutral",
        }
    )
    fresh = pd.concat(
        [
            todo[["text_sha256"]].reset_index(drop=True),
            renamed[["positive", "negative", "neutral"]],
        ],
        axis=1,
    ).set_index("text_sha256")
    combined = pd.concat([old, fresh]).loc[lambda x: ~x.index.duplicated(keep="last")]
    for name in ["positive", "negative", "neutral"]:
        frame[name] = frame.text_sha256.map(combined[name])
    frame["sentiment"] = frame.positive - frame.negative
    frame["characters"] = frame.text.str.len()
    frame = frame.drop(columns="text")
    if (
        not np.isfinite(frame[["positive", "negative", "neutral", "sentiment"]])
        .all()
        .all()
    ):
        raise ValueError("Nonfinite FinBERT result")
    frame.to_parquet(dest, index=False)
    marker.write_text(json.dumps(method, indent=2) + "\n")
    summary = method | {
        "records": len(frame),
        "tickers": int(frame.ticker.nunique()),
        "new_texts_scored": len(todo),
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "data_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "missing_text_policy": "Missing additions remain missing; never neutral zero",
    }
    out = ROOT / "results/hk/week4/finbert_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    return summary


def main():
    local = os.environ.get("HK_FINBERT_MODEL_DIR")
    score_additions(Path(local) if local else None)


if __name__ == "__main__":
    main()
