"""Evaluating the hand labels: label storage, match precision, rater agreement and the scorer comparison."""
import json
import math

import pandas as pd
import pytest

from src.reddit import label_eval as le
from src.reddit import label_server as srv

NEXT_WRONG = {"positive": "negative", "negative": "neutral", "neutral": "positive"}


@pytest.fixture
def tables(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "LABEL_DIR", tmp_path / "labels")
    monkeypatch.setattr(le.settings, "TABLES", tmp_path)
    monkeypatch.setattr(le, "N_BOOT", 20)
    return tmp_path


def _label(task, rater, labels):
    for item, label in labels.items():
        srv.append_label(task, rater, {"item_id": item, "label": label})


def _match_sample(path, monkeypatch):
    pd.DataFrame({"item_id": [f"m{i}" for i in range(6)], "ticker": ["AAA"] * 3 + ["BBB"] * 3}).to_csv(
        path / "match.csv", index=False)
    (path / "match.meta.json").write_text(json.dumps({"strata": [["AAA", 75], ["BBB", 25]]}))
    monkeypatch.setattr(le, "MATCH_OUT", path / "match.csv")


def _sentiment_sample(path, monkeypatch):
    """Eight posts whose title is their true label, so a stub scorer can be right or wrong on purpose."""
    truth = ["positive", "negative", "neutral", "neutral", "positive", "negative", "neutral", "positive"]
    pd.DataFrame({"item_id": [f"s{i}" for i in range(8)], "post_id": [f"p{i}" for i in range(8)], "ticker": "AAPL",
                  "source": ["reddit_product"] * 4 + ["reddit_stock"] * 4, "title": truth, "body": ""}).to_csv(
        path / "sentiment.csv", index=False)
    monkeypatch.setattr(le, "SENTIMENT_OUT", path / "sentiment.csv")
    return truth


def test_the_latest_label_for_an_item_wins(tables):
    _label("match", "joshua", {"m0": "incorrect"})
    _label("match", "joshua", {"m0": "correct"})
    assert srv.latest_labels("match", "joshua")["m0"]["label"] == "correct"
    assert srv.latest_labels("match", "james") == {}


def test_a_label_outside_the_task_choices_is_rejected(tables):
    with pytest.raises(ValueError, match="label must be one of"):
        srv.append_label("sentiment", "joshua", {"item_id": "s0", "label": "correct"})


def test_second_rater_sees_only_the_double_labelled_posts(tmp_path, monkeypatch):
    pd.DataFrame({"item_id": ["s1", "s2"], "double": ["True", "False"], "title": ["a", "b"]}).to_csv(
        tmp_path / "s.csv", index=False)
    monkeypatch.setitem(srv.TASKS["sentiment"], "items", tmp_path / "s.csv")
    assert [r["item_id"] for r in srv.load_items("sentiment", double_only=True)] == ["s1"]
    assert len(srv.load_items("sentiment", double_only=False)) == 2


def test_match_precision_weights_by_population_and_leaves_out_unsure(tables, monkeypatch):
    _match_sample(tables, monkeypatch)
    _label("match", "joshua", {"m0": "correct", "m1": "correct", "m2": "incorrect", "m3": "correct", "m4": "unsure"})
    out = le.match_precision("joshua").set_index("ticker")
    assert out.loc["AAA", "precision"] == pytest.approx(2 / 3)
    assert out.loc["BBB", ["checked", "unsure", "unlabelled"]].tolist() == [1, 1, 1]
    total = out.loc["ALL (weighted)"]
    assert total["precision"] == pytest.approx(0.75)       # 0.75 x 2/3 + 0.25 x 1
    se = math.sqrt(0.75 ** 2 * (2 / 3) * (1 / 3) / 3)      # BBB is 1/1, so its variance term is 0
    assert total["ci_high"] - total["ci_low"] == pytest.approx(2 * le.Z95 * se)
    assert (tables / "match_precision.csv").exists()


def test_match_precision_before_any_labels_stops_without_writing_a_table(tables, monkeypatch):
    _match_sample(tables, monkeypatch)
    with pytest.raises(SystemExit, match="no match checks"):
        le.match_precision("joshua")
    assert not (tables / "match_precision.csv").exists()


def test_agreement_leaves_out_skips_and_matches_a_hand_computed_kappa(tables):
    _label("sentiment", "joshua", {"s0": "positive", "s1": "negative", "s2": "neutral", "s3": "skip"})
    _label("sentiment", "james", {"s0": "positive", "s1": "negative", "s2": "positive", "s3": "negative"})
    res = le.agreement("joshua", "james")
    assert res["n_overlap"] == 3 and res["raw_agreement"] == pytest.approx(2 / 3)
    assert res["cohen_kappa"] == pytest.approx(0.5)        # observed 2/3, chance 1/3


def test_compare_scorers_picks_per_source_and_names_a_scorer_that_could_not_run(tables, monkeypatch):
    truth = _sentiment_sample(tables, monkeypatch)
    labels = {f"s{i}": lab for i, lab in enumerate(truth)}
    labels["s3"] = "skip"
    _label("sentiment", "joshua", labels)

    def stub(name, texts, companies):
        if name == "llm":
            raise RuntimeError("set ANTHROPIC_API_KEY in .env to run the LLM scorer")
        # s3 is skipped, so the first 3 texts are product posts: vader gets those right, finbert the stock posts
        pred = [t if (i < 3) == (name == "vader") else NEXT_WRONG[t] for i, t in enumerate(texts)]
        return pd.DataFrame({"label": pred, "score": 0.0})

    monkeypatch.setattr(le, "run_scorer", stub)
    table, meta = le.compare_scorers("joshua", ["vader", "finbert", "llm"])
    assert meta["choice"] == {"reddit_product": "vader", "reddit_stock": "finbert"}
    assert meta["scorers_compared"] == ["vader", "finbert"] and meta["scorers_skipped"] == ["llm"]
    assert meta["n_labelled"] == 7 and meta["n_skipped"] == 1
    best = table[(table["scorer"] == "vader") & (table["source"] == "reddit_product")].iloc[0]
    assert best["n"] == 3 and best["macro_f1"] == pytest.approx(1.0) and best["accuracy"] == pytest.approx(1.0)
    assert json.loads((tables / "sentiment_choice.json").read_text())["scorers_skipped"] == ["llm"]
    assert (tables / "sentiment_confusion_vader_reddit_product.csv").exists()
    saved = pd.read_csv(tables / "sentiment_predictions_on_labels.csv")
    assert "pred_vader" in saved and "pred_llm" not in saved


def test_compare_scorers_before_any_labels_stops_with_a_clear_message(tables, monkeypatch):
    _sentiment_sample(tables, monkeypatch)
    with pytest.raises(SystemExit, match="no sentiment labels"):
        le.compare_scorers("joshua", ["vader"])
