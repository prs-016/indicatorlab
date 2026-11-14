"""Score pre-cutoff, dated Wikipedia net additions with the specified FinBERT."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from src.hk.week3.public_data import CUTOFF, DATA, ROOT


def main() -> None:
    """Run local MPS/CPU inference; absent additions remain missing observations."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    destination = DATA / "wiki_sentiment.parquet"
    rows = []
    for path in sorted((DATA / "wikipedia").glob("*.json")):
        article = json.loads(path.read_text())
        if article.get("week_definition") != "Monday-Sunday UTC":
            raise ValueError("Article cache uses an obsolete week definition")
        for row in article["weeks"]:
            if pd.Timestamp(row["week"], tz="UTC") + pd.Timedelta(days=7) > CUTOFF:
                raise ValueError("Partial or future attention week")
            text = row.get("added_text")
            if text and len(text.strip()) >= 20:
                rows.append(
                    {
                        "ticker": article["ticker"],
                        "week": row["week"],
                        "text": text,
                        "last_revision": row["last_revision"],
                        "available_at": row["ts_last_revision"],
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
    if not rows:
        raise ValueError("No dated additions available")
    frame = pd.DataFrame(rows)
    if destination.exists():
        old = pd.read_parquet(destination)
        old = old.drop_duplicates("text_sha256").set_index("text_sha256")
    else:
        old = pd.DataFrame()
    todo = frame.loc[~frame.text_sha256.isin(old.index)].drop_duplicates("text_sha256")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model_dir = DATA / "models/finbert"
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = (
        AutoModelForSequenceClassification.from_pretrained(
            model_dir, local_files_only=True
        )
        .to(device)
        .eval()
    )
    labels = [model.config.id2label[index].lower() for index in range(3)]
    if set(labels) != {"positive", "negative", "neutral"}:
        raise ValueError(f"Unexpected model labels: {labels}")
    predictions = {}
    batch_size = 8
    with torch.inference_mode():
        for offset in range(0, len(todo), batch_size):
            batch = todo.iloc[offset : offset + batch_size]
            encoded = tokenizer(
                batch.text.tolist(),
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(device)
            probabilities = torch.softmax(model(**encoded).logits, dim=-1).cpu().numpy()
            for (_, row), values in zip(batch.iterrows(), probabilities):
                predictions[row.text_sha256] = {
                    label: float(value) for label, value in zip(labels, values)
                }
            if offset % 80 == 0:
                print(
                    f"finbert={min(offset+batch_size,len(todo))}/{len(todo)} device={device}",
                    flush=True,
                )
    for label in labels:
        frame[label] = [
            (
                predictions[key][label]
                if key in predictions
                else float(old.loc[key, label])
            )
            for key in frame.text_sha256
        ]
    frame["sentiment"] = frame.positive - frame.negative
    frame["characters"] = frame.text.str.len()
    frame = frame.drop(columns="text")
    if (
        not np.isfinite(frame[["positive", "negative", "neutral", "sentiment"]])
        .all()
        .all()
    ):
        raise ValueError("Nonfinite FinBERT inference")
    frame.to_parquet(destination, index=False)
    summary = {
        "model": "ProsusAI/finbert",
        "device": device,
        "records": len(frame),
        "tickers": int(frame.ticker.nunique()),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "max_tokens": 512,
        "missing_text_policy": "No addition is missing sentiment, never neutral zero",
        "data_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }
    output = ROOT / "results/hk/week3/finbert_summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
