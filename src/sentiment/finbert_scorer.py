"""FinBERT sentiment shared by Reddit and Wikipedia (Week 3: same model, preprocessing and output columns).

`score(texts)` returns one row per text with the three class probabilities, as the attention record
names them, plus the argmax label and net = pos - neg:

    label  sentiment_pos  sentiment_neg  sentiment_neu  sentiment_net

Texts are whitespace-collapsed and cut at FinBERT's 512-token limit; nothing else is changed, so callers
choose what to score (a post's title + body, a sentence that names the ticker, a sentence added to an
article). With `cache_file`, scores are stored keyed by text hash and model revision, so reruns only
score new texts and a model update rescores everything.

    from src.sentiment.finbert_scorer import score
    score(["Revenue beat estimates.", "Guidance was cut."])
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

MODEL = "ProsusAI/finbert"
MAX_TOKENS = 512        # BERT input limit
BATCH = 32
COLS = {"positive": "sentiment_pos", "negative": "sentiment_neg", "neutral": "sentiment_neu"}
OUT_COLS = ["label", *COLS.values(), "sentiment_net"]


def preprocess(text: str) -> str:
    """Collapse whitespace; the one clean-up both sources share."""
    return re.sub(r"\s+", " ", str(text)).strip()


@lru_cache(maxsize=2)
def load_model(model: str = MODEL):
    """(tokenizer, model, device) on Apple MPS or CUDA when available, else CPU."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model)
    m = AutoModelForSequenceClassification.from_pretrained(model).to(device).eval()
    return tok, m, device


def revision(model: str = MODEL) -> str | None:
    """The downloaded snapshot's commit hash (its Hugging Face cache folder name).

    'local' when `model` is a folder on disk; None when the model has not been downloaded yet.
    """
    if Path(model).is_dir():
        return "local"
    from huggingface_hub import try_to_load_from_cache
    path = try_to_load_from_cache(model, "config.json")
    return Path(path).parent.name if isinstance(path, str) else None


def probabilities(texts: list[str], model: str = MODEL, batch_size: int = BATCH) -> pd.DataFrame:
    """Class probabilities per text, columns positive / negative / neutral."""
    import torch
    tok, m, device = load_model(model)
    id2label = {i: lab.lower() for i, lab in m.config.id2label.items()}
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            enc = tok(texts[i:i + batch_size], padding=True, truncation=True, max_length=MAX_TOKENS,
                      return_tensors="pt").to(device)
            out.append(torch.softmax(m(**enc).logits, dim=-1).float().cpu().numpy())
    p = np.vstack(out) if out else np.zeros((0, len(id2label)))
    return pd.DataFrame(p, columns=[id2label[i] for i in range(p.shape[1])])[list(COLS)]


def to_output(p: pd.DataFrame) -> pd.DataFrame:
    """Probabilities (positive / negative / neutral) -> the shared output columns."""
    out = p.rename(columns=COLS)
    out.insert(0, "label", p.idxmax(axis=1) if len(p) else pd.Series(dtype=str))
    out["sentiment_net"] = out["sentiment_pos"] - out["sentiment_neg"]
    return out[OUT_COLS]


def text_key(text: str) -> str:
    """Cache key of a preprocessed text."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def score(texts: list[str], cache_file: Path | str | None = None, model: str = MODEL,
          batch_size: int = BATCH) -> pd.DataFrame:
    """FinBERT label and probabilities per text, in input order (see module docstring)."""
    clean = [preprocess(t) for t in texts]
    if cache_file is None:
        return to_output(probabilities(clean, model, batch_size))
    rev = revision(model)                # no model load when the snapshot is already on disk
    if rev is None:                      # first use on this machine: download, then read the real snapshot
        load_model(model)
        rev = revision(model)
    rev = f"{model}@{rev}"
    f = Path(cache_file)
    cache = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["key", "model", *COLS])
    cache = cache[cache["model"] == rev].drop_duplicates("key").set_index("key")[list(COLS)].astype(float)
    keys = [text_key(t) for t in clean]
    todo = sorted({k: t for k, t in zip(keys, clean) if k not in cache.index}.items())
    if todo:
        new = probabilities([t for _, t in todo], model, batch_size)
        new.index = [k for k, _ in todo]
        cache = pd.concat([cache, new])
        f.parent.mkdir(parents=True, exist_ok=True)
        cache.assign(model=rev).rename_axis("key").reset_index()[["key", "model", *COLS]].to_csv(f, index=False)
    return to_output(cache.loc[keys, list(COLS)].reset_index(drop=True))
