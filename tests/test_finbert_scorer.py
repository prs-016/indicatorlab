import numpy as np
import pandas as pd

from src.sentiment import finbert_scorer
from src.sentiment.finbert_scorer import OUT_COLS, score


def _fake(calls):
    def probabilities(texts, model, batch_size):
        calls.append(list(texts))
        pos = [0.9 if "beat" in t else 0.05 for t in texts]
        neg = [0.05 if "beat" in t else 0.9 for t in texts]
        return pd.DataFrame({"positive": pos, "negative": neg, "neutral": 0.05})
    return probabilities


def test_score_returns_the_shared_columns_in_input_order(monkeypatch):
    monkeypatch.setattr(finbert_scorer, "probabilities", _fake([]))
    out = score(["Guidance  was\ncut.", "Revenue beat estimates."])
    assert list(out.columns) == OUT_COLS and out["label"].tolist() == ["negative", "positive"]
    assert np.allclose(out["sentiment_net"], [-0.85, 0.85])


def test_score_caches_by_text_and_model_revision(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(finbert_scorer, "probabilities", _fake(calls))
    monkeypatch.setattr(finbert_scorer, "revision", lambda model: "abc")
    f = tmp_path / "cache.csv"
    first = score(["a beat", "b", "a beat"], f)
    again = score(["b", "a  beat", "c"], f)              # whitespace is collapsed before the cache lookup
    assert calls == [["a beat", "b"], ["c"]]
    assert first["label"].tolist() == ["positive", "negative", "positive"]
    assert again["label"].tolist() == ["negative", "positive", "negative"]
    monkeypatch.setattr(finbert_scorer, "revision", lambda model: "new")
    score(["b"], f)                                      # a new model revision rescores
    assert calls[-1] == ["b"]
