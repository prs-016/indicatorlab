"""Week 2, Step 5.5: score every matched post with the chosen scorer and write post_sentiment.parquet.

Sentiment is stored per (post, ticker): text-only scorers give every ticker of a post the same
score, while the LLM is asked about each company separately. The scorer per source comes from
results/reddit/tables/sentiment_choice.json (written by `label_eval sentiment`), or from --scorer
to force one. Posts are scored one subreddit at a time and
saved under data/reddit/processed/post_sentiment/<subreddit>.parquet, so an interrupted run resumes.
Removed posts and posts with no text are not scored (they still count as posts).

FinBERT goes through the shared scorer (src/sentiment/finbert_scorer.py): all three probabilities are
kept, every score is cached by (post_id, ticker, model_version) under processed/sentiment_cache/, and a
post naming several tracked stocks is scored per ticker on the sentences that mention that ticker
(falling back to the whole post when the match is only implicit).

If the LLM is chosen, posts go through the Message Batches API (half price). The run first prints a
token and dollar estimate and only sends anything with --confirm-llm-cost.

    python -m src.reddit.score_posts               # uses the choice from label_eval
    python -m src.reddit.score_posts --scorer finbert
"""
from __future__ import annotations

import argparse
import json
import re
import time

import pandas as pd
import pyarrow.parquet as pq

from src import config
from src.reddit import settings
from src.reddit.match_tickers import clean_text, match_text
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
from src.sentiment import finbert_scorer

log = get_logger("score_posts", "pipeline.log")

PARTS = settings.PROCESSED / "post_sentiment"
CHOICE = settings.TABLES / "sentiment_choice.json"
CHARS_PER_TOKEN = 4             # rough English average, for the cost estimate only
LLM_PRICE_PER_MTOK = {"input": 0.10, "output": 0.50}   # Claude Haiku 5.5, before the 50% batch discount
BATCH_DISCOUNT = 0.5
LLM_OUTPUT_TOKENS = 10
BATCH_SIZE = 50_000             # requests per batch (API limit 100,000)
POLL_S = 60
FINBERT_CACHE = settings.PROCESSED / "sentiment_cache"
FINBERT_CHUNK = 20_000          # rows scored and cached at a time, so an interrupted run loses at most one chunk
SCORE_COLS = ["post_id", "ticker", "sentiment_label", "sentiment_score", "sentiment_pos", "sentiment_neg",
              "sentiment_neu", "scorer", "model_version"]
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def ticker_snippet(title: str, body: str, ticker: str) -> str:
    """The sentences of a post that mention `ticker` (whole post if none do on their own)."""
    full = title + "\n" + body
    sents = [x.strip() for x in SENTENCE_SPLIT.split(full) if x.strip()]
    keep = [x for x in sents if ticker in match_text(x, full)]
    return finbert_scorer.prepare_text(" ".join(keep), None) if keep else finbert_scorer.prepare_text(title, body)


def _posts_to_score(sub_file) -> pd.DataFrame:
    """Rows to score for one subreddit file (see `rows_to_score`)."""
    matches = settings.PROCESSED / "post_ticker_matches.parquet"
    cols = ["post_id", "ticker", "subreddit_type"]
    if "n_tickers_in_post" in pq.read_schema(matches).names:
        cols.append("n_tickers_in_post")
    mt = pd.read_parquet(matches, filters=[("subreddit", "==", sub_file.stem)], columns=cols)
    posts = pd.read_parquet(sub_file, columns=["id", "title", "selftext", "removed_flag"])
    return rows_to_score(posts, mt)


def rows_to_score(posts: pd.DataFrame, mt: pd.DataFrame, market: str = settings.MARKET) -> pd.DataFrame:
    """One row per matched (post, ticker): non-removed posts with text, plus the company name.

    `posts` has id, title, selftext, removed_flag; `mt` has post_id, ticker, subreddit_type and
    optionally n_tickers_in_post. A post that names two tracked stocks gets two rows, because the label
    is about one company. `text` is the whole post (title + " " + body); `score_text` is what text-only
    scorers read: the sentences naming that ticker when the post names several stocks, else the whole post.
    """
    mt = mt.copy()
    if "n_tickers_in_post" not in mt:
        mt["n_tickers_in_post"] = 1
    posts = posts[~posts["removed_flag"].astype(bool) & posts["id"].isin(mt["post_id"])]
    title, body = posts["title"].map(clean_text), posts["selftext"].map(clean_text)
    text = [finbert_scorer.prepare_text(t, b) for t, b in zip(title, body, strict=True)]
    out = pd.DataFrame({"post_id": posts["id"].to_numpy(), "text": text, "_title": title.to_numpy(),
                        "_body": body.to_numpy()}).merge(mt.drop_duplicates(["post_id", "ticker"]), on="post_id")
    multi = out["n_tickers_in_post"].fillna(0) >= 2
    out["score_text"] = out["text"]
    out.loc[multi, "score_text"] = [ticker_snippet(t, b, tk) for t, b, tk in
                                    out.loc[multi, ["_title", "_body", "ticker"]].itertuples(index=False)]
    names = {t: c["name"] for t, c in config.stocks(market).items()}
    out["company"] = out["ticker"].map(names)
    out["source"] = out["subreddit_type"].map(SOURCE_OF_TYPE)
    out = out[out["text"].str.len() > 0].drop(columns=["subreddit_type", "n_tickers_in_post", "_title", "_body"])
    return out.reset_index(drop=True)


def _score_finbert(g: pd.DataFrame, cache_uri: str | None = None) -> pd.DataFrame:
    """FinBERT probabilities per (post, ticker) through the shared scorer and its cache (local or s3://)."""
    scorer = finbert_scorer.FinbertScorer.from_config()
    cache = finbert_scorer.ScoreCache(cache_uri or str(FINBERT_CACHE))
    items = g[["post_id", "ticker", "score_text"]].rename(columns={"score_text": "text"})
    parts = []
    for i in range(0, len(items), FINBERT_CHUNK):
        parts.append(finbert_scorer.score_items(items.iloc[i:i + FINBERT_CHUNK], scorer, cache))
        log.info("finbert: %d/%d rows", min(i + FINBERT_CHUNK, len(items)), len(items))
    s = pd.concat(parts, ignore_index=True).drop(columns="text")
    s = g[["post_id", "ticker"]].merge(s, on=["post_id", "ticker"], how="left").set_axis(g.index)
    return s.assign(label=s["sentiment_label"], score=s["sentiment_pos"] - s["sentiment_neg"])


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
                    continue   # errored/expired requests stay uncached; --rescore retries just those
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
            elif scorer == "finbert":
                s = _score_finbert(g)
            else:
                # text-only scorers give the same answer for identical text: score each distinct text once
                once = g.drop_duplicates("score_text")
                sc = run_scorer(scorer, once["score_text"].tolist(), once["company"].tolist())
                sc.index = once["score_text"].to_numpy()
                s = sc.loc[g["score_text"]].set_axis(g.index)
            part = pd.DataFrame({"post_id": g["post_id"], "ticker": g["ticker"], "sentiment_label": s["label"],
                                 "sentiment_score": s["score"], "scorer": scorer})
            for c in ["sentiment_pos", "sentiment_neg", "sentiment_neu", "model_version"]:
                part[c] = s.get(c)
            parts.append(part[SCORE_COLS])
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
