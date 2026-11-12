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


def test_labelled_sample_is_never_redrawn(tmp_path, monkeypatch):
    from src.reddit import label_samples as ls
    monkeypatch.setattr(ls.settings, "VALIDATION", tmp_path)
    sample = tmp_path / "sentiment_sample.csv"
    sample.write_text("item_id\ns001\n")
    ls._guard(sample, "sentiment", force=False)                 # no labels yet: fine
    (tmp_path / "labels").mkdir()
    (tmp_path / "labels" / "sentiment_joshua.csv").write_text("item_id,label\ns001,positive\n")
    with pytest.raises(SystemExit, match="already has labels"):
        ls._guard(sample, "sentiment", force=False)
    ls._guard(sample, "sentiment", force=True)                  # explicit override


def test_metric_row_has_per_class_recall_and_wilson_ci():
    import numpy as np

    from src.reddit import label_eval as le
    y = np.array(["positive"] * 4 + ["negative"] * 4 + ["neutral"] * 2)
    p = np.array(["positive", "positive", "positive", "neutral", "negative", "negative", "neutral", "neutral",
                  "neutral", "positive"])
    row = le._metric_row(y, p, np.random.default_rng(0))
    assert row["recall_positive"] == 0.75 and row["recall_negative"] == 0.5 and row["recall_neutral"] == 0.5
    assert row["n_positive"] == 4 and row["n_neutral"] == 2
    assert row["accuracy"] == 0.6
    assert (row["accuracy_wilson_low"], row["accuracy_wilson_high"]) == le.wilson(6, 10)
    for lab in le.LABELS:
        assert row[f"recall_{lab}_ci_low"] <= row[f"recall_{lab}"] <= row[f"recall_{lab}_ci_high"]


def test_recall_of_an_absent_class_is_nan_and_ci_skips_undefined_resamples():
    import math

    import numpy as np

    from src.reddit import label_eval as le
    y, p = np.array(["positive", "positive"]), np.array(["positive", "negative"])
    assert math.isnan(le._recall("neutral")(y, p))
    lo, hi = le._boot_ci(y, p, le._recall("neutral"), np.random.default_rng(0))
    assert math.isnan(lo) and math.isnan(hi)
