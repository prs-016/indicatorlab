"""FinBERT sentiment, shared by Reddit posts and Wikipedia edits so both use identical code.

Same model, same preprocessing, same output columns everywhere::

    from src.sentiment.finbert_scorer import FinbertScorer, prepare_text
    scorer = FinbertScorer.from_config()            # model + pinned revision from config.yaml `sentiment`
    scored = scorer.score([prepare_text(title, body), ...])
    # -> sentiment_label, sentiment_pos, sentiment_neg, sentiment_neu (one row per text, input order)

The classifier is ProsusAI/finbert (financial news; labels positive / negative / neutral). All three
probabilities are kept because downstream tables want their weekly means, not just the top label.
`ScoreCache` keys every score by (post_id, ticker, model_version), so reruns never rescore a post
and a model bump rescores everything. Built from James's `src/wiki_sentiment.py` classifier.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from src import config, storage

LABELS = ("positive", "negative", "neutral")
PROB_COLS = {"positive": "sentiment_pos", "negative": "sentiment_neg", "neutral": "sentiment_neu"}
OUTPUT_COLS = ["sentiment_label", *PROB_COLS.values()]
KEY_COLS = ["post_id", "ticker", "model_version"]
CACHE_COLS = [*KEY_COLS, "text_sha1", *OUTPUT_COLS, "scored_at_utc"]
REVISION_SHORT = 7      # characters of the Hugging Face commit kept in `model_version`
_SPACE = re.compile(r"\s+")


def params() -> dict:
    """The `sentiment` block of config.yaml."""
    return dict(config.load()["sentiment"])


def prepare_text(title: str | None, body: str | None) -> str:
    """Input text for every scorer: title + " " + body, whitespace collapsed and trimmed."""
    parts = [p for p in (title, body) if isinstance(p, str) and p.strip()]
    return _SPACE.sub(" ", " ".join(parts)).strip()


def text_sha1(text: str) -> str:
    """Hash of the exact text scored, so a cached score is reused only for identical input."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def pick_device() -> str:
    """Apple MPS, then CUDA, else CPU (AWS containers run on CPU)."""
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=2)
def _classifier(model_id: str, revision: str, device: str):
    """The Hugging Face text-classification pipeline, loaded once per (model, revision, device)."""
    from transformers import pipeline
    return pipeline("text-classification", model=model_id, revision=revision, top_k=None, device=device)


@dataclass(frozen=True)
class FinbertScorer:
    """Batched FinBERT scoring that returns all three class probabilities."""

    model_id: str
    revision: str
    batch_size: int
    max_tokens: int
    device: str | None = None

    @classmethod
    def from_config(cls, device: str | None = None) -> FinbertScorer:
        """Scorer with model, pinned revision, batch size and token limit from config.yaml."""
        p = params()
        return cls(p["model"], str(p["revision"]), int(p["batch_size"]), int(p["max_tokens"]), device)

    @property
    def model_version(self) -> str:
        """Model id plus short revision, e.g. 'ProsusAI/finbert@0bc2ac1'; part of every cache key."""
        return f"{self.model_id}@{self.revision[:REVISION_SHORT]}"

    def score(self, texts: list[str]) -> pd.DataFrame:
        """One row per text, in input order: label (argmax) and the three probabilities.

        Empty texts get NaN probabilities and an empty label. Identical texts are scored once, and
        texts are run shortest-first so each batch pads less.
        """
        texts = [t if isinstance(t, str) else "" for t in texts]
        out = pd.DataFrame(np.nan, index=range(len(texts)), columns=list(PROB_COLS.values()))
        unique = sorted({t for t in texts if t.strip()}, key=len)
        if unique:
            clf = _classifier(self.model_id, self.revision, self.device or pick_device())
            res = clf(unique, batch_size=self.batch_size, truncation=True, max_length=self.max_tokens)
            probs = {t: {PROB_COLS[d["label"].lower()]: d["score"] for d in r} for t, r in zip(unique, res, strict=True)}
            filled = [i for i, t in enumerate(texts) if t in probs]
            out.loc[filled, list(PROB_COLS.values())] = [[probs[texts[i]][c] for c in PROB_COLS.values()] for i in filled]
        p = out[list(PROB_COLS.values())]
        has = p.notna().all(axis=1)
        label = pd.Series("", index=out.index, dtype=object)
        if has.any():
            reverse = {v: k for k, v in PROB_COLS.items()}
            label[has] = p[has].idxmax(axis=1).map(reverse)
        out.insert(0, "sentiment_label", label)
        return out[OUTPUT_COLS]


class ScoreCache:
    """Scores stored as parquet parts under one directory (local path or s3:// URI).

    A row is reused when (post_id, ticker, model_version) match and the text hash is unchanged;
    anything else is a miss and gets rescored. New scores are appended as a new part file, so
    concurrent readers never see a half-written table.
    """

    def __init__(self, uri: str):
        self.uri = uri.rstrip("/")
        self._table: pd.DataFrame | None = None

    def load(self) -> pd.DataFrame:
        """Every cached row (latest score wins for a repeated key)."""
        if self._table is None:
            t = storage.read_parquet_dir(self.uri, columns=CACHE_COLS)
            if t is None or t.empty:
                t = pd.DataFrame(columns=CACHE_COLS)
            self._table = t.drop_duplicates(KEY_COLS, keep="last").reset_index(drop=True)
        return self._table

    def split(self, items: pd.DataFrame, model_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(hits with score columns, misses) for `items` with post_id, ticker and text_sha1 columns."""
        keyed = items.assign(model_version=model_version)
        cached = self.load()[[*KEY_COLS, "text_sha1", *OUTPUT_COLS]].rename(columns={"text_sha1": "_cached_sha1"})
        m = keyed.merge(cached, on=KEY_COLS, how="left")
        hit = m["_cached_sha1"].eq(m["text_sha1"])
        return m[hit].drop(columns="_cached_sha1"), keyed[~hit.to_numpy()]

    def add(self, scored: pd.DataFrame) -> None:
        """Append newly scored rows (CACHE_COLS minus `scored_at_utc`, which is stamped here)."""
        if scored.empty:
            return
        now = datetime.now(UTC)
        rows = scored.assign(scored_at_utc=now.isoformat(timespec="seconds"))[CACHE_COLS]
        storage.write_parquet(rows, f"{self.uri}/part-{now:%Y%m%dT%H%M%S%f}.parquet")
        self._table = pd.concat([self.load(), rows], ignore_index=True).drop_duplicates(KEY_COLS, keep="last")


def score_items(items: pd.DataFrame, scorer: FinbertScorer, cache: ScoreCache | None = None) -> pd.DataFrame:
    """Score (post_id, ticker, text) rows, reusing cached scores; returns items + OUTPUT_COLS + model_version."""
    items = items.assign(text_sha1=items["text"].map(text_sha1))
    if cache is None:
        hits, todo = items.iloc[0:0].assign(model_version=scorer.model_version), items.assign(
            model_version=scorer.model_version)
    else:
        hits, todo = cache.split(items, scorer.model_version)
    new = pd.concat([todo.reset_index(drop=True), scorer.score(todo["text"].tolist())], axis=1) if len(todo) else None
    if new is not None and cache is not None:
        cache.add(new)
    parts = [hits] + ([new] if new is not None else [])
    keep = [*items.columns, "model_version", *OUTPUT_COLS]
    return pd.concat(parts, ignore_index=True)[keep].drop(columns="text_sha1")


def weekly_rollup(scored: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per group: mean of each probability, sentiment_net = mean(pos - neg), and n_scored (rows with a score)."""
    p = scored.assign(_net=scored["sentiment_pos"] - scored["sentiment_neg"])
    g = p.groupby(keys, dropna=False)
    out = g[list(PROB_COLS.values())].mean()
    out["sentiment_net"] = g["_net"].mean()
    out["n_scored"] = g["sentiment_pos"].count()
    return out.reset_index()
