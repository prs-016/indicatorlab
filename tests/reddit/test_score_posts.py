"""Scoring every post: which rows get scored, per-ticker storage, resuming and the LLM cost gate."""
import json

import numpy as np
import pandas as pd
import pytest

from src import config
from src.reddit import score_posts as sp


def _write_corpus(root):
    """r/stocks (one post names two stocks, one is removed) and r/iphone (one post has no text)."""
    posts = root / "posts"
    posts.mkdir()
    pd.DataFrame({"id": ["s1", "s2", "s3"], "title": ["AAPL and NVDA look great", "AAPL earnings", "Gone"],
                  "selftext": ["", "Nice beat", "[removed]"], "removed_flag": [False, False, True]}).to_parquet(
        posts / "stocks.parquet")
    pd.DataFrame({"id": ["i1", "i2"], "title": ["Love this phone", ""], "selftext": ["", ""],
                  "removed_flag": [False, False]}).to_parquet(posts / "iphone.parquet")
    rows = [("s1", "AAPL", "stocks", "general"), ("s1", "NVDA", "stocks", "general"),
            ("s2", "AAPL", "stocks", "general"), ("s2", "AAPL", "stocks", "general"),   # two match methods, one post
            ("s3", "AAPL", "stocks", "general"), ("i1", "AAPL", "iphone", "product"),
            ("i2", "AAPL", "iphone", "product")]
    pd.DataFrame(rows, columns=["post_id", "ticker", "subreddit", "subreddit_type"]).to_parquet(
        root / "post_ticker_matches.parquet")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    _write_corpus(tmp_path)
    monkeypatch.setattr(sp.settings, "PROCESSED", tmp_path)
    monkeypatch.setattr(sp.settings, "POSTS", tmp_path / "posts")
    monkeypatch.setattr(sp, "PARTS", tmp_path / "post_sentiment")
    monkeypatch.setattr(sp, "CHOICE", tmp_path / "sentiment_choice.json")
    monkeypatch.setattr(sp, "SENTIMENT_PATH", tmp_path / "post_sentiment.parquet")
    return tmp_path


def _stub_scorer(calls):
    def run(name, texts, companies):
        calls.append((name, list(texts)))
        return pd.DataFrame({"label": ["positive"] * len(texts), "score": [0.5] * len(texts)})
    return run


def test_only_live_posts_with_text_are_scored_once_per_ticker(corpus):
    df = sp._posts_to_score(corpus / "posts" / "stocks.parquet")
    assert sorted(zip(df["post_id"], df["ticker"], strict=True)) == [("s1", "AAPL"), ("s1", "NVDA"), ("s2", "AAPL")]
    names = config.stocks("US")
    assert df.set_index(["post_id", "ticker"]).loc[("s1", "NVDA"), "company"] == names["NVDA"]["name"]
    assert set(df["source"]) == {"reddit_stock"}


def test_a_post_with_no_text_is_not_scored(corpus):
    df = sp._posts_to_score(corpus / "posts" / "iphone.parquet")
    assert df["post_id"].tolist() == ["i1"] and df["source"].tolist() == ["reddit_product"]


def test_text_scorer_reads_each_post_once_and_saves_one_row_per_ticker(corpus, monkeypatch):
    calls = []
    monkeypatch.setattr(sp, "run_scorer", _stub_scorer(calls))
    out = sp.run("vader", confirm_llm_cost=False, rescore=False)
    assert sum(len(texts) for _, texts in calls) == 3      # s1, s2, i1
    assert len(out) == 4 and set(out["scorer"]) == {"vader"}
    assert len(pd.read_parquet(sp.SENTIMENT_PATH)) == 4


def _stub_finbert(g):
    """FinBERT stand-in: every row positive with fixed probabilities."""
    return pd.DataFrame({"label": "positive", "score": 0.7, "sentiment_pos": 0.8, "sentiment_neg": 0.1,
                         "sentiment_neu": 0.1, "model_version": "ProsusAI/finbert@test"}, index=g.index)


def test_the_choice_file_picks_a_scorer_per_source(corpus, monkeypatch):
    sp.CHOICE.write_text(json.dumps({"choice": {"reddit_product": "vader", "reddit_stock": "finbert"}}))
    calls = []
    monkeypatch.setattr(sp, "run_scorer", _stub_scorer(calls))
    monkeypatch.setattr(sp, "_score_finbert", _stub_finbert)
    out = sp.run(None, confirm_llm_cost=False, rescore=False).set_index("post_id")
    assert out.loc["i1", "scorer"] == "vader" and out.loc["s2", "scorer"] == "finbert"
    assert list(out.reset_index().columns) == sp.SCORE_COLS
    assert out.loc["s2", "sentiment_pos"] == 0.8 and out.loc["s2", "model_version"] == "ProsusAI/finbert@test"
    assert pd.isna(out.loc["i1", "sentiment_pos"])          # VADER has no class probabilities


def test_finbert_path_caches_probabilities(corpus, monkeypatch):
    from src.sentiment import finbert_scorer as fs
    seen = []

    def fake_classifier(*a, **k):
        def clf(texts, **kw):
            seen.extend(texts)
            return [[{"label": "positive", "score": 0.6}, {"label": "negative", "score": 0.3},
                     {"label": "neutral", "score": 0.1}] for _ in texts]
        return clf
    monkeypatch.setattr(fs, "_classifier", fake_classifier)
    monkeypatch.setattr(sp, "FINBERT_CACHE", corpus / "sentiment_cache")
    out = sp.run("finbert", confirm_llm_cost=False, rescore=False)
    assert out["sentiment_score"].round(6).eq(0.3).all() and out["model_version"].str.startswith("ProsusAI/").all()
    n = len(seen)
    sp.run("finbert", confirm_llm_cost=False, rescore=True)     # rescore reads the cache, not the model
    assert len(seen) == n


def test_multi_ticker_posts_are_scored_on_their_own_sentences():
    title, body = "AAPL vs NVDA", "AAPL guidance was cut. NVDA crushed it and raised guidance!"
    assert sp.ticker_snippet(title, body, "NVDA") == "AAPL vs NVDA NVDA crushed it and raised guidance!"
    assert sp.ticker_snippet(title, body, "AAPL") == "AAPL vs NVDA AAPL guidance was cut."
    assert sp.ticker_snippet("Big tech", "they all look cheap", "MSFT") == "Big tech they all look cheap"


def test_saved_subreddits_are_not_scored_again_unless_asked(corpus, monkeypatch):
    calls = []
    monkeypatch.setattr(sp, "run_scorer", _stub_scorer(calls))
    sp.run("vader", confirm_llm_cost=False, rescore=False)
    first = len(calls)
    sp.run("vader", confirm_llm_cost=False, rescore=False)
    assert len(calls) == first
    sp.run("vader", confirm_llm_cost=False, rescore=True)
    assert len(calls) == 2 * first


def test_llm_sends_nothing_without_the_cost_confirmation(corpus, monkeypatch):
    def not_allowed(df):
        raise AssertionError("the LLM was called without --confirm-llm-cost")
    monkeypatch.setattr(sp, "score_llm_batched", not_allowed)
    with pytest.raises(SystemExit, match="confirm-llm-cost"):
        sp.run("llm", confirm_llm_cost=False, rescore=False)
    assert not list(sp.PARTS.glob("*.parquet"))


def test_llm_labels_stay_per_company_and_a_refusal_stays_unscored(corpus, monkeypatch):
    answers = {("s1", "AAPL"): "positive", ("s1", "NVDA"): "negative", ("s2", "AAPL"): "error:refusal",
               ("i1", "AAPL"): "neutral"}
    monkeypatch.setattr(sp, "score_llm_batched", lambda df: pd.Series(
        [answers[k] for k in zip(df["post_id"], df["ticker"], strict=True)], index=df.index))
    out = sp.run("llm", confirm_llm_cost=True, rescore=False).set_index(["post_id", "ticker"])
    assert out.loc[("s1", "AAPL"), "sentiment_score"] == 1.0 and out.loc[("s1", "NVDA"), "sentiment_score"] == -1.0
    assert out.loc[("i1", "AAPL"), "sentiment_score"] == 0.0
    assert np.isnan(out.loc[("s2", "AAPL"), "sentiment_score"])


def test_llm_cost_estimate_arithmetic(monkeypatch):
    monkeypatch.setattr(sp, "llm_prompt", lambda text, company: "x" * 400)     # 100 tokens at 4 chars per token
    monkeypatch.setattr(sp, "LLM_PRICE_PER_MTOK", {"input": 1e6, "output": 1e6})
    est = sp.estimate_llm_cost(["a", "b"], ["Apple", "Apple"])
    assert est == {"posts": 2, "input_tokens": 200, "output_tokens": 20, "usd": 110.0}   # half of 220 with the batch
