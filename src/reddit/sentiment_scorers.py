"""Four sentiment scorers behind one interface (Week 2, Step 5).

Each scorer maps texts to a label (positive / negative / neutral) and a score in [-1, 1]:

  vader     VADER compound score; +-0.05 cutoffs (the VADER authors' standard)
  lm        Loughran-McDonald finance word lists: tone = (pos - neg) / (pos + neg + 1); sign -> label
  finbert   ProsusAI/finbert (Hugging Face); label = argmax, score = p(positive) - p(negative)
  llm       Claude (pinned model) with a fixed, versioned prompt and JSON output; score = +1 / 0 / -1

All cutoffs are fixed here before any scorer sees the hand labels. Text is title + body after
`match_tickers.clean_text`. The LLM is also told which company the post was matched to, since the
label is about that company; the other three read the text only.

The Loughran-McDonald master dictionary is not bundled: download the CSV from
https://sraf.nd.edu/loughranmcdonald-master-dictionary/ into data/reddit/raw/lexicons/.
The LLM scorer needs ANTHROPIC_API_KEY (environment or .env) and caches every answer in
data/reddit/processed/llm_sentiment_cache.jsonl, so reruns cost nothing and give the same labels.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.reddit import settings
from src.reddit.utils import get_logger

log = get_logger("sentiment_scorers", "pipeline.log")

LABELS = ["positive", "negative", "neutral"]
VADER_CUTOFF = 0.05
LM_DIR = settings.RAW / "lexicons"
FINBERT_MODEL = "ProsusAI/finbert"
FINBERT_MAX_TOKENS = 512           # BERT input limit
FINBERT_BATCH = 32
LLM_MODEL = "claude-haiku-5-5"
LLM_PROMPT_PATH = Path(__file__).with_name("prompts") / "sentiment_v1.txt"
LLM_MAX_TEXT_CHARS = 4000          # longer posts are cut here, and the cut is noted in the prompt
LLM_MAX_TOKENS = 256               # the JSON answer is a few tokens
LLM_CACHE = settings.PROCESSED / "llm_sentiment_cache.jsonl"
LLM_SCHEMA = {"type": "object", "properties": {"label": {"type": "string", "enum": LABELS}},
              "required": ["label"], "additionalProperties": False}


def label_from_score(score: np.ndarray | pd.Series, cutoff: float) -> np.ndarray:
    """positive if score >= cutoff, negative if <= -cutoff, else neutral."""
    s = np.asarray(score, dtype=float)
    return np.where(s >= cutoff, "positive", np.where(s <= -cutoff, "negative", "neutral"))


# ----------------------------------------------------------------------------- VADER
def score_vader(texts: list[str]) -> pd.DataFrame:
    """VADER compound score per text."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    s = np.array([sia.polarity_scores(t)["compound"] for t in texts])
    return pd.DataFrame({"label": label_from_score(s, VADER_CUTOFF), "score": s})


# ----------------------------------------------------------------------------- Loughran-McDonald
def load_lm_words(lm_dir: Path = LM_DIR) -> tuple[set[str], set[str]]:
    """Positive and negative word sets from the LM master dictionary CSV (non-zero year = in list)."""
    files = sorted(lm_dir.glob("Loughran-McDonald_MasterDictionary*.csv"))
    if not files:
        raise FileNotFoundError(f"no Loughran-McDonald master dictionary CSV in {lm_dir}")
    d = pd.read_csv(files[-1], usecols=["Word", "Positive", "Negative"], keep_default_na=False)
    return set(d.loc[d["Positive"] != 0, "Word"].str.upper()), set(d.loc[d["Negative"] != 0, "Word"].str.upper())


WORD_RE = re.compile(r"[A-Za-z]+")


def score_lm(texts: list[str], words: tuple[set[str], set[str]] | None = None) -> pd.DataFrame:
    """Net LM tone per text; a text with no list words is neutral (tone 0)."""
    pos, neg = words or load_lm_words()
    tones = []
    for t in texts:
        toks = [w.upper() for w in WORD_RE.findall(t)]
        p, n = sum(w in pos for w in toks), sum(w in neg for w in toks)
        tones.append((p - n) / (p + n + 1))
    s = np.array(tones)
    return pd.DataFrame({"label": np.where(s > 0, "positive", np.where(s < 0, "negative", "neutral")), "score": s})


# ----------------------------------------------------------------------------- FinBERT
def score_finbert(texts: list[str], batch_size: int = FINBERT_BATCH) -> pd.DataFrame:
    """FinBERT class probabilities per text (first 512 tokens), on Apple MPS when available."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(FINBERT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL).to(device).eval()
    id2label = {i: lab.lower() for i, lab in model.config.id2label.items()}
    probs = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            enc = tok(texts[i:i + batch_size], padding=True, truncation=True, max_length=FINBERT_MAX_TOKENS,
                      return_tensors="pt").to(device)
            probs.append(torch.softmax(model(**enc).logits, dim=-1).cpu().numpy())
    p = np.vstack(probs) if probs else np.zeros((0, len(id2label)))
    cols = [id2label[i] for i in range(p.shape[1])]
    pdf = pd.DataFrame(p, columns=cols)
    return pd.DataFrame({"label": pdf[LABELS].idxmax(axis=1).to_numpy(),
                         "score": (pdf["positive"] - pdf["negative"]).to_numpy()})


# ----------------------------------------------------------------------------- LLM
def llm_prompt(text: str, company: str) -> str:
    """The fixed prompt (prompts/sentiment_v1.txt) filled with one post."""
    cut = len(text) > LLM_MAX_TEXT_CHARS
    body = text[:LLM_MAX_TEXT_CHARS] + ("\n[post truncated]" if cut else "")
    return LLM_PROMPT_PATH.read_text(encoding="utf-8").format(company=company, post=body)


def cache_key(prompt: str) -> str:
    return hashlib.sha256(f"{LLM_MODEL}\n{LLM_PROMPT_PATH.name}\n{prompt}".encode()).hexdigest()


def load_cache() -> dict[str, str]:
    if not LLM_CACHE.exists():
        return {}
    with open(LLM_CACHE, encoding="utf-8") as f:
        return {r["key"]: r["label"] for r in map(json.loads, f)}


def request_params(prompt: str) -> dict:
    """One classification request: pinned model, no thinking, low effort, JSON schema output."""
    return {"model": LLM_MODEL, "max_tokens": LLM_MAX_TOKENS, "thinking": {"type": "disabled"},
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": LLM_SCHEMA}},
            "messages": [{"role": "user", "content": prompt}]}


def parse_label(message) -> str:
    """Label from a structured-output response; refusals and odd stops are recorded, not guessed."""
    if message.stop_reason != "end_turn":
        return f"error:{message.stop_reason}"
    text = next((b.text for b in message.content if b.type == "text"), "")
    return json.loads(text)["label"]


def make_client():
    import anthropic
    from dotenv import load_dotenv
    load_dotenv(settings.ROOT / ".env", override=False)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("set ANTHROPIC_API_KEY in .env to run the LLM scorer")
    return anthropic.Anthropic()


def score_llm(texts: list[str], companies: list[str]) -> pd.DataFrame:
    """One synchronous request per uncached post (fine for the ~300 labelled posts)."""
    cache = load_cache()
    prompts = [llm_prompt(t, c) for t, c in zip(texts, companies)]
    todo = [p for p in dict.fromkeys(prompts) if cache_key(p) not in cache]
    if todo:
        client = make_client()
        with open(LLM_CACHE, "a", encoding="utf-8") as f:
            for i, p in enumerate(todo, 1):
                label = parse_label(client.messages.create(**request_params(p)))
                cache[cache_key(p)] = label
                f.write(json.dumps({"key": cache_key(p), "label": label, "model": LLM_MODEL,
                                    "prompt": LLM_PROMPT_PATH.name}) + "\n")
                if i % 50 == 0:
                    log.info("llm: %d/%d scored", i, len(todo))
    labels = [cache[cache_key(p)] for p in prompts]
    score = [1.0 if lab == "positive" else -1.0 if lab == "negative" else 0.0 for lab in labels]
    return pd.DataFrame({"label": labels, "score": score})


SCORERS = {"vader": score_vader, "lm": score_lm, "finbert": score_finbert, "llm": score_llm}


def run_scorer(name: str, texts: list[str], companies: list[str]) -> pd.DataFrame:
    """Dispatch by scorer name; only the LLM needs the company names."""
    return score_llm(texts, companies) if name == "llm" else SCORERS[name](texts)
