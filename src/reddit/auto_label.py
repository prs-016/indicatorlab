"""Claude-written sentiment answer key for the label sample (Week 3; replaces hand labels).

Joshua decided not to hand-label the sample. FinBERT cannot label its own test (it would score 100%),
so a stronger model than any contestant writes the key: Claude Opus (config.yaml
`sentiment.labeler_model`), reading each post with its ticker, subreddit and a labelling rubric
(prompts/label_v1.txt) and answering positive / negative / neutral / skip plus a one-line rationale.
FinBERT, VADER and the Claude Haiku LLM scorer are then graded against it by label_eval, exactly as
they would have been against hand labels:

    python -m src.reddit.auto_label                      # prints the cost estimate, sends nothing
    python -m src.reddit.auto_label --confirm-cost       # labels every sampled item not yet labelled
    python -m src.reddit.label_eval sentiment --rater claude-opus --second james

Labels go to data/reddit/validation/labels/sentiment_claude-opus.csv in the label_server format, so
label_eval reads them unchanged. Every answer is cached by (model, prompt), so reruns cost nothing.
Caveats for the report: the key is model-made, and the Haiku scorer shares a model family with it.
Needs Anthropic credentials (ANTHROPIC_API_KEY in .env or the environment).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.label_samples import SENTIMENT_OUT
from src.reddit.label_server import append_label, latest_labels
from src.reddit.sentiment_scorers import make_client
from src.reddit.utils import get_logger

log = get_logger("auto_label", "pipeline.log")

RATER = "claude-opus"
CHOICES = ["positive", "negative", "neutral", "skip"]
PROMPT_PATH = settings.ROOT / "src" / "reddit" / "prompts" / "label_v1.txt"
CACHE = settings.VALIDATION / "auto_label_cache.jsonl"
SCHEMA = {"type": "object",
          "properties": {"label": {"type": "string", "enum": CHOICES}, "rationale": {"type": "string"}},
          "required": ["label", "rationale"], "additionalProperties": False}
MAX_TOKENS = 16_000            # room for adaptive thinking plus the short JSON answer
WORKERS = 6                    # concurrent requests
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # on a policy decline, the API retries on a fallback model
# Cost estimate only (Claude Opus 5.5 list price per million tokens, Oct 2026).
PRICE_PER_MTOK = {"input": 4.00, "output": 20.00}
CHARS_PER_TOKEN = 4
EST_OUTPUT_TOKENS = 1_500      # thinking + answer per item at medium effort, rough
SUBREDDIT_KIND = {"product": "a community for the company's products or services",
                  "stock": "an investor community for this stock",
                  "general": "a general investing / trading community",
                  "sector": "a community about the company's industry"}
_lock = threading.Lock()


def params() -> dict:
    """Labeller model and effort from config.yaml `sentiment`."""
    p = config.load()["sentiment"]
    return {"model": p["labeler_model"], "effort": p["labeler_effort"]}


def label_prompt(item: dict, company: str) -> str:
    """The rubric prompt filled with one sampled post."""
    return PROMPT_PATH.read_text(encoding="utf-8").format(
        company=company, ticker=item["ticker"], subreddit=item["subreddit"],
        subreddit_kind=SUBREDDIT_KIND.get(item["subreddit_type"], "a Reddit community"),
        title=item["title"].strip() or "(no title)", body=item["body"].strip() or "(no body)")


def cache_key(prompt: str, model: str) -> str:
    """Stable key of one request: model, prompt file and the filled prompt."""
    return hashlib.sha256(f"{model}\n{PROMPT_PATH.name}\n{prompt}".encode()).hexdigest()


def load_cache() -> dict[str, dict]:
    """key -> {label, rationale, served_by}; the cache file is append-only."""
    if not CACHE.exists():
        return {}
    with open(CACHE, encoding="utf-8") as f:
        return {r["key"]: r for r in map(json.loads, f)}


def request_params(prompt: str, model: str, effort: str) -> dict:
    """One labelling request: adaptive thinking (always on for Opus 5.5), explicit effort, JSON output."""
    return {"model": model, "max_tokens": MAX_TOKENS,
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            "messages": [{"role": "user", "content": prompt}],
            "betas": [FALLBACK_BETA], "fallbacks": "default"}


def parse_answer(message) -> dict:
    """Label, rationale and serving model; a refusal or cut-off answer becomes `skip`, never a guess."""
    served = getattr(message, "model", "")
    if message.stop_reason == "refusal":
        cat = getattr(getattr(message, "stop_details", None), "category", None)
        return {"label": "skip", "rationale": f"refused ({cat})", "served_by": served}
    if message.stop_reason != "end_turn":
        return {"label": "skip", "rationale": f"no answer (stop_reason={message.stop_reason})", "served_by": served}
    text = next((b.text for b in message.content if b.type == "text"), "")
    ans = json.loads(text)
    return {"label": ans["label"], "rationale": ans["rationale"].strip(), "served_by": served}


def estimate_cost(prompts: list[str]) -> dict:
    """Rough token and dollar estimate for labelling `prompts`."""
    in_tok = sum(len(p) for p in prompts) / CHARS_PER_TOKEN
    out_tok = EST_OUTPUT_TOKENS * len(prompts)
    usd = (in_tok * PRICE_PER_MTOK["input"] + out_tok * PRICE_PER_MTOK["output"]) / 1e6
    return {"items": len(prompts), "input_tokens": int(in_tok), "output_tokens_est": out_tok, "usd": round(usd, 2)}


def _items() -> list[dict]:
    """Sampled items with the company name, in item order."""
    items = pd.read_csv(SENTIMENT_OUT, dtype=str, keep_default_na=False).to_dict("records")
    names = {t: c["name"] for t, c in config.stocks(settings.MARKET).items()}
    for it in items:
        it["company"] = names[it["ticker"]]
    return items


def run(confirm_cost: bool, workers: int = WORKERS, client=None) -> pd.DataFrame:
    """Label every sampled item without a claude-opus label; returns this run's new label rows."""
    p = params()
    done = latest_labels("sentiment", RATER)
    todo = [it for it in _items() if it["item_id"] not in done]
    prompts = {it["item_id"]: label_prompt(it, it["company"]) for it in todo}
    cache = load_cache()
    uncached = [pr for pr in prompts.values() if cache_key(pr, p["model"]) not in cache]
    est = estimate_cost(uncached)
    log.info("auto-label: %d items to label, %d need the API; estimate %s", len(todo), len(uncached), est)
    if uncached and not confirm_cost:
        raise SystemExit(f"labelling {len(uncached)} posts with {p['model']} costs about ${est['usd']} ({est}); "
                         "rerun with --confirm-cost")
    if uncached:
        client = client or make_client()

        def ask(prompt: str) -> None:
            ans = parse_answer(client.beta.messages.create(**request_params(prompt, p["model"], p["effort"])))
            with _lock, open(CACHE, "a", encoding="utf-8") as f:
                cache[cache_key(prompt, p["model"])] = ans
                f.write(json.dumps({"key": cache_key(prompt, p["model"]), "model": p["model"], **ans}) + "\n")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(ask, pr) for pr in uncached]
            for i, fut in enumerate(as_completed(futures), 1):
                fut.result()
                if i % 50 == 0:
                    log.info("auto-label: %d/%d answered", i, len(uncached))
    rows = []
    for it in todo:
        ans = cache[cache_key(prompts[it["item_id"]], p["model"])]
        note = ans["rationale"] if ans["served_by"] in ("", p["model"]) else f"[{ans['served_by']}] {ans['rationale']}"
        rows.append(append_label("sentiment", RATER, {"item_id": it["item_id"], "post_id": it["post_id"],
                                                      "ticker": it["ticker"], "label": ans["label"], "note": note}))
    out = pd.DataFrame(rows)
    if len(out):
        log.info("auto-label: wrote %d labels %s", len(out), out["label"].value_counts().to_dict())
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirm-cost", action="store_true", help="actually send the requests")
    ap.add_argument("--workers", type=int, default=WORKERS)
    a = ap.parse_args()
    run(a.confirm_cost, a.workers)
