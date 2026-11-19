"""Shared FinBERT scorer: probabilities, ordering, caching and the weekly roll-up (model is stubbed)."""
import numpy as np
import pandas as pd
import pytest

from src.sentiment import finbert_scorer as fs

# Fake class probabilities per text: (positive, negative, neutral)
FAKE = {
    "great beat, guidance raised": (0.90, 0.02, 0.08),
    "guidance cut, stock tanks": (0.03, 0.92, 0.05),
    "earnings call is on tuesday": (0.05, 0.05, 0.90),
}


class FakeClassifier:
    """Stands in for the Hugging Face pipeline and records every text it was asked to score."""

    def __init__(self):
        self.seen: list[str] = []

    def __call__(self, texts, batch_size, truncation, max_length):
        self.seen.extend(texts)
        return [[{"label": lab, "score": s} for lab, s in zip(("Positive", "Negative", "Neutral"), FAKE[t])]
                for t in texts]


@pytest.fixture
def fake(monkeypatch):
    clf = FakeClassifier()
    monkeypatch.setattr(fs, "_classifier", lambda *a, **k: clf)
    return clf


@pytest.fixture
def scorer():
    return fs.FinbertScorer("ProsusAI/finbert", "0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031", 4, 512, "cpu")


def test_prepare_text_joins_title_and_body_and_collapses_space():
    assert fs.prepare_text("  Apple  beats ", "guidance\n\nraised ") == "Apple beats guidance raised"
    assert fs.prepare_text("Title only", None) == "Title only"
    assert fs.prepare_text(None, float("nan")) == ""


def test_model_version_uses_short_revision(scorer):
    assert scorer.model_version == "ProsusAI/finbert@0bc2ac1"


def test_from_config_reads_pinned_revision():
    s = fs.FinbertScorer.from_config(device="cpu")
    assert s.model_id == "ProsusAI/finbert" and len(s.revision) == 40


def test_score_keeps_all_probabilities_in_input_order(fake, scorer):
    texts = ["guidance cut, stock tanks", "great beat, guidance raised", "earnings call is on tuesday"]
    out = scorer.score(texts)
    assert list(out.columns) == fs.OUTPUT_COLS
    assert out["sentiment_label"].tolist() == ["negative", "positive", "neutral"]
    np.testing.assert_allclose(out[["sentiment_pos", "sentiment_neg", "sentiment_neu"]].sum(axis=1), 1.0)
    assert out.loc[1, "sentiment_pos"] == pytest.approx(0.90)


def test_score_dedupes_and_skips_empty_text(fake, scorer):
    texts = ["great beat, guidance raised", "", "great beat, guidance raised", None]
    out = scorer.score(texts)
    assert fake.seen == ["great beat, guidance raised"]      # scored once, empties never sent
    assert out["sentiment_label"].tolist() == ["positive", "", "positive", ""]
    assert out.loc[[1, 3], "sentiment_pos"].isna().all()


def test_score_empty_list(fake, scorer):
    out = scorer.score([])
    assert out.empty and list(out.columns) == fs.OUTPUT_COLS


def _items(*rows):
    return pd.DataFrame(rows, columns=["post_id", "ticker", "text"])


def test_cache_hit_skips_model_and_text_change_rescores(fake, scorer, tmp_path):
    cache = fs.ScoreCache(str(tmp_path / "cache"))
    items = _items(("p1", "AAPL", "great beat, guidance raised"), ("p2", "TSLA", "guidance cut, stock tanks"))
    first = fs.score_items(items, scorer, cache)
    assert len(fake.seen) == 2 and set(first["sentiment_label"]) == {"positive", "negative"}

    again = fs.score_items(items, scorer, fs.ScoreCache(str(tmp_path / "cache")))   # fresh object reads disk
    assert len(fake.seen) == 2                                    # zero new model calls
    assert again.sort_values("post_id")["sentiment_label"].tolist() == ["positive", "negative"]

    changed = _items(("p1", "AAPL", "earnings call is on tuesday"))
    out = fs.score_items(changed, scorer, cache)
    assert fake.seen[-1] == "earnings call is on tuesday" and out["sentiment_label"].item() == "neutral"


def test_new_model_version_is_a_cache_miss(fake, scorer, tmp_path):
    cache = fs.ScoreCache(str(tmp_path / "cache"))
    items = _items(("p1", "AAPL", "great beat, guidance raised"))
    fs.score_items(items, scorer, cache)
    bumped = fs.FinbertScorer(scorer.model_id, "ffffffffffffffffffffffffffffffffffffffff", 4, 512, "cpu")
    out = fs.score_items(items, bumped, cache)
    assert len(fake.seen) == 2 and out["model_version"].item() == "ProsusAI/finbert@fffffff"


def test_score_items_without_cache(fake, scorer):
    out = fs.score_items(_items(("p1", "AAPL", "great beat, guidance raised")), scorer)
    assert out[["post_id", "ticker", "sentiment_label"]].values.tolist() == [["p1", "AAPL", "positive"]]


def test_weekly_rollup_means_net_and_count():
    scored = pd.DataFrame({
        "ticker": ["AAPL", "AAPL", "AAPL", "TSLA"],
        "sentiment_pos": [0.8, 0.2, np.nan, 0.1],
        "sentiment_neg": [0.1, 0.6, np.nan, 0.7],
        "sentiment_neu": [0.1, 0.2, np.nan, 0.2],
    })
    out = fs.weekly_rollup(scored, ["ticker"]).set_index("ticker")
    assert out.loc["AAPL", "n_scored"] == 2
    assert out.loc["AAPL", "sentiment_pos"] == pytest.approx(0.5)
    assert out.loc["AAPL", "sentiment_net"] == pytest.approx(((0.8 - 0.1) + (0.2 - 0.6)) / 2)
    assert out.loc["TSLA", "sentiment_net"] == pytest.approx(-0.6)
