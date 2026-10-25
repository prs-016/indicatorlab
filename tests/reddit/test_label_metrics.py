"""Hand-label metrics and the offline sentiment scorers."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.reddit import label_eval as le
from src.reddit import sentiment_scorers as ss


def test_wilson_interval_matches_known_value():
    lo, hi = le.wilson(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3) and hi == pytest.approx(0.9433, abs=1e-3)
    assert np.isnan(le.wilson(0, 0)[0])


def test_choice_rule_breaks_ties_toward_the_cheaper_scorer():
    t = pd.DataFrame({"scorer": ["llm", "finbert", "vader", "llm", "lm"],
                      "source": ["reddit_product", "reddit_product", "reddit_product", "reddit_stock", "reddit_stock"],
                      "macro_f1": [0.70, 0.70, 0.50, 0.66, 0.60]})
    assert le.choose_scorers(t) == {"reddit_product": "finbert", "reddit_stock": "llm"}


def test_label_from_score_cutoffs():
    out = ss.label_from_score(np.array([0.05, 0.049, -0.05, 0.0]), ss.VADER_CUTOFF)
    assert out.tolist() == ["positive", "neutral", "negative", "neutral"]


def test_lm_tone_with_a_small_word_list():
    words = ({"GOOD", "STRONG"}, {"LOSS", "WEAK"})
    out = ss.score_lm(["Strong quarter, good margins", "weak guidance and a loss", "nothing here", "good but weak"],
                      words)
    assert out["label"].tolist() == ["positive", "negative", "neutral", "neutral"]
    assert out["score"].iloc[0] == pytest.approx(2 / 3)   # (2 - 0) / (2 + 0 + 1)


def test_llm_refusal_is_recorded_not_guessed():
    refused = SimpleNamespace(stop_reason="refusal", content=[])
    ok = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"label": "negative"}')])
    assert ss.parse_label(refused) == "error:refusal" and ss.parse_label(ok) == "negative"


def test_prompt_names_the_company_and_marks_truncation():
    p = ss.llm_prompt("x" * (ss.LLM_MAX_TEXT_CHARS + 10), "Netflix")
    assert "Netflix" in p and "[post truncated]" in p
