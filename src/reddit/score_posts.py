"""Week 2, Step 5.5: score every matched post with the chosen scorer and write post_sentiment.parquet.

Sentiment is stored per (post, ticker): text-only scorers give every ticker of a post the same
score, while the LLM is asked about each company separately. The scorer per source comes from
results/reddit/tables/sentiment_choice.json (written by `label_eval sentiment`), or from --scorer
to force one. Posts are scored one subreddit at a time and
saved under data/reddit/processed/post_sentiment/<subreddit>.parquet, so an interrupted run resumes.
Removed posts and posts with no text are not scored (they still count as posts).

If the LLM is chosen, posts go through the Message Batches API (half price). The run first prints a
token and dollar estimate and only sends anything with --confirm-llm-cost.

    python -m src.reddit.score_posts               # uses the choice from label_eval
    python -m src.reddit.score_posts --scorer finbert
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from src import config
from src.reddit import settings
from src.reddit.match_tickers import clean_text
from src.reddit.reddit_weekly import SENTIMENT_PATH, SOURCE_OF_TYPE
from src.reddit.sentiment_scorers import (
    LLM_MODEL,
    cache_key,
    llm_prompt,
    load_cache,
    make_client,
    parse_label,
    request_params,
    run_scorer,
)
from src.reddit.utils import get_logger

log = get_logger("score_posts", "pipeline.log")

PARTS = settings.PROCESSED / "post_sentiment"
CHOICE = settings.TABLES / "sentiment_choice.json"
CHARS_PER_TOKEN = 4             # rough English average, for the cost estimate only
LLM_PRICE_PER_MTOK = {"input": 0.10, "output": 0.50}   # Claude Haiku 5.5, before the 50% batch discount
BATCH_DISCOUNT = 0.5
LLM_OUTPUT_TOKENS = 10
BATCH_SIZE = 50_000             # requests per batch (API limit 100,000)
POLL_S = 60


def _posts_to_score(sub_file) -> pd.DataFrame:
    """One row per matched (post, ticker) of one subreddit: non-removed posts with text, plus the company name.

    A post that names two tracked stocks gets two rows, because the LLM label is about one company.
    """
    mt = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet",
                         filters=[("subreddit", "==", sub_file.stem)], columns=["post_id", "ticker", "subreddit_type"])
    posts = pd.read_parquet(sub_file, columns=["id", "title", "selftext", "removed_flag"])
    posts = posts[~posts["removed_flag"] & posts["id"].isin(mt["post_id"])]
    text = (posts["title"].map(clean_text) + "\n\n" + posts["selftext"].map(clean_text)).str.strip()
    out = pd.DataFrame({"post_id": posts["id"].to_numpy(), "text": text.to_numpy()}).merge(
        mt.drop_duplicates(["post_id", "ticker"]), on="post_id")
    names = {t: c["name"] for t, c in config.stocks(settings.MARKET).items()}
    out["company"] = out["ticker"].map(names)
    out["source"] = out["subreddit_type"].map(SOURCE_OF_TYPE)
    return out[out["text"].str.len() > 0].drop(columns="subreddit_type").reset_index(drop=True)


def estimate_llm_cost(texts: list[str], companies: list[str]) -> dict:
    """Rough token and dollar estimate for scoring `texts` with the batched LLM."""
    in_tok = sum(len(llm_prompt(t, c)) for t, c in zip(texts, companies, strict=True)) / CHARS_PER_TOKEN
    out_tok = LLM_OUTPUT_TOKENS * len(texts)
    usd = BATCH_DISCOUNT * (in_tok * LLM_PRICE_PER_MTOK["input"] + out_tok * LLM_PRICE_PER_MTOK["output"]) / 1e6
    return {"posts": len(texts), "input_tokens": int(in_tok), "output_tokens": out_tok, "usd": round(usd, 2)}


def score_llm_batched(df: pd.DataFrame) -> pd.Series:
    """LLM labels through the Message Batches API, reusing and extending the response cache."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    cache = load_cache()
    prompts = [llm_prompt(t, c) for t, c in zip(df["text"], df["company"], strict=True)]
    todo = {cache_key(p): p for p in prompts if cache_key(p) not in cache}
    client = make_client()
    keys = list(todo)
    for i in range(0, len(keys), BATCH_SIZE):
        chunk = keys[i:i + BATCH_SIZE]
        requests = [Request(custom_id=k[:64], params=MessageCreateParamsNonStreaming(**request_params(todo[k])))
                    for k in chunk]
        batch = client.messages.batches.create(requests=requests)
        log.info("llm batch %s: %d requests", batch.id, len(chunk))
        while client.messages.batches.retrieve(batch.id).processing_status != "ended":
            time.sleep(POLL_S)
        by_id = {k[:64]: k for k in chunk}
        with open(settings.PROCESSED / "llm_sentiment_cache.jsonl", "a", encoding="utf-8") as f:
            for res in client.messages.batches.results(batch.id):
                if res.result.type != "succeeded":
                    continue   # errored/expired requests stay uncached and are retried next run
                key = by_id[res.custom_id]
                cache[key] = parse_label(res.result.message)
                f.write(json.dumps({"key": key, "label": cache[key], "model": LLM_MODEL}) + "\n")
    return pd.Series([cache.get(cache_key(p)) for p in prompts], index=df.index)


def run(force_scorer: str | None, confirm_llm_cost: bool, rescore: bool) -> pd.DataFrame:
    """Score every subreddit file that has no saved part yet (or all with `rescore`)."""
    choice = {s: force_scorer for s in ("reddit_product", "reddit_stock")} if force_scorer else \
        json.loads(CHOICE.read_text())["choice"]
    PARTS.mkdir(parents=True, exist_ok=True)
    for sub_file in sorted(settings.POSTS.glob("*.parquet")):
        out = PARTS / sub_file.name
        if out.exists() and not rescore:
            continue
        df = _posts_to_score(sub_file)
        if df.empty:
            continue
        parts = []
        for src, g in df.groupby("source"):
            scorer = choice[src]
            if scorer == "llm":
                est = estimate_llm_cost(g["text"].tolist(), g["company"].tolist())
                if not confirm_llm_cost:
                    raise SystemExit(f"r/{sub_file.stem}: LLM scoring would cost about ${est['usd']} ({est}); "
                                     "rerun with --confirm-llm-cost")
                labels = score_llm_batched(g)
                s = pd.DataFrame({"label": labels, "score": labels.map({"positive": 1.0, "negative": -1.0,
                                                                        "neutral": 0.0})})
            else:
                # text-only scorers give the same answer for every ticker of a post: score each post once
                once = g.drop_duplicates("post_id")
                sc = run_scorer(scorer, once["text"].tolist(), once["company"].tolist())
                sc.index = once["post_id"].to_numpy()
                s = sc.loc[g["post_id"]].set_axis(g.index)
            parts.append(pd.DataFrame({"post_id": g["post_id"], "ticker": g["ticker"], "sentiment_label": s["label"],
                                       "sentiment_score": s["score"], "scorer": scorer}))
        pd.concat(parts).to_parquet(out, index=False)
        log.info("scored r/%s: %d posts", sub_file.stem, len(df))
    allp = pd.concat([pd.read_parquet(f) for f in sorted(PARTS.glob("*.parquet"))], ignore_index=True)
    allp.to_parquet(SENTIMENT_PATH, index=False)
    log.info("post_sentiment.parquet: %d posts (%s)", len(allp), allp["scorer"].value_counts().to_dict())
    return allp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scorer", choices=["vader", "lm", "finbert", "llm"])
    ap.add_argument("--confirm-llm-cost", action="store_true")
    ap.add_argument("--rescore", action="store_true", help="score again even where a saved part exists")
    a = ap.parse_args()
    run(a.scorer, a.confirm_llm_cost, a.rescore)
