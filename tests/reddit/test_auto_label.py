"""Claude answer key: prompt filling, request shape, parsing, label file format and the cost gate (no API calls)."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src.reddit import auto_label as al
from src.reddit import label_server as ls


def _msg(label=None, rationale="", stop="end_turn", model="claude-opus-5-5", category=None):
    content = [SimpleNamespace(type="text", text=json.dumps({"label": label, "rationale": rationale}))] if label else []
    return SimpleNamespace(stop_reason=stop, content=content, model=model,
                           stop_details=SimpleNamespace(category=category) if category else None)


class FakeClient:
    """Answers by ticker and records every request it receives."""

    def __init__(self, answers):
        self.answers, self.requests = answers, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        prompt = kw["messages"][0]["content"]
        return next(a for t, a in self.answers.items() if f"(ticker {t})" in prompt)


@pytest.fixture
def sample(tmp_path, monkeypatch):
    items = pd.DataFrame({
        "item_id": ["s001", "s002", "s003"], "post_id": ["p1", "p2", "p3"], "ticker": ["AAPL", "TSLA", "NVDA"],
        "subreddit": ["iphone", "wallstreetbets", "stocks"], "subreddit_type": ["product", "general", "general"],
        "title": ["Battery died again", "TSLA puts printing", "NVDA earnings Wednesday"],
        "body": ["Third time this month.", "", "What time is the call?"]})
    path = tmp_path / "sentiment_sample.csv"
    items.to_csv(path, index=False)
    monkeypatch.setattr(al, "SENTIMENT_OUT", path)
    monkeypatch.setattr(al, "CACHE", tmp_path / "auto_label_cache.jsonl")
    monkeypatch.setattr(ls, "LABEL_DIR", tmp_path / "labels")
    return tmp_path


ANSWERS = {"AAPL": _msg("negative", "Complains the battery keeps dying."),
           "TSLA": _msg("negative", "Bearish puts position on Tesla."),
           "NVDA": _msg(stop="refusal", category="general_harms")}


def test_prompt_names_company_ticker_and_subreddit_kind():
    item = {"ticker": "AAPL", "subreddit": "iphone", "subreddit_type": "product", "title": "Hi", "body": ""}
    p = al.label_prompt(item, "Apple")
    assert "Apple (ticker AAPL)" in p and "r/iphone" in p and "products or services" in p
    assert "Body: (no body)" in p


def test_request_uses_effort_json_schema_and_fallbacks_without_disabling_thinking():
    r = al.request_params("x", "claude-opus-5-5", "medium")
    assert r["output_config"]["effort"] == "medium" and r["output_config"]["format"]["schema"] == al.SCHEMA
    assert "thinking" not in r                         # Opus 5.5 rejects thinking: disabled
    assert r["fallbacks"] == "default" and r["betas"] == [al.FALLBACK_BETA]


def test_refusal_and_cutoff_become_skip():
    assert al.parse_answer(_msg(stop="refusal", category="cyber"))["label"] == "skip"
    assert al.parse_answer(_msg(stop="max_tokens"))["rationale"].startswith("no answer")
    assert al.parse_answer(_msg("positive", " good ")) == {"label": "positive", "rationale": "good",
                                                           "served_by": "claude-opus-5-5"}


def test_nothing_is_sent_without_cost_confirmation(sample):
    client = FakeClient(ANSWERS)
    with pytest.raises(SystemExit, match="--confirm-cost"):
        al.run(confirm_cost=False, client=client)
    assert client.requests == [] and not (sample / "labels").exists()


def test_labels_land_in_label_server_format_and_reruns_are_free(sample):
    client = FakeClient(ANSWERS)
    out = al.run(confirm_cost=True, workers=2, client=client)
    assert len(client.requests) == 3
    labels = pd.read_csv(sample / "labels" / "sentiment_claude-opus.csv", dtype=str, keep_default_na=False)
    assert list(labels.columns) == ls.LABEL_FIELDS
    got = dict(zip(labels["item_id"], labels["label"], strict=True))
    assert got == {"s001": "negative", "s002": "negative", "s003": "skip"}
    assert set(labels["rater"]) == {"claude-opus"} and len(out) == 3
    assert al.run(confirm_cost=False, client=client).empty          # all labelled: no gate, no requests
    assert len(client.requests) == 3


def test_cache_answers_survive_a_lost_label_file(sample):
    client = FakeClient(ANSWERS)
    al.run(confirm_cost=True, client=client)
    (sample / "labels" / "sentiment_claude-opus.csv").unlink()
    al.run(confirm_cost=False, client=client)                       # every answer is cached: no gate
    assert len(client.requests) == 3


def test_answer_from_a_fallback_model_is_marked_in_the_note(sample):
    answers = {**ANSWERS, "AAPL": _msg("negative", "Battery complaint.", model="claude-opus-5")}
    al.run(confirm_cost=True, client=FakeClient(answers))
    labels = ls.latest_labels("sentiment", al.RATER)
    assert labels["s001"]["note"] == "[claude-opus-5] Battery complaint."


def test_cost_estimate_arithmetic(monkeypatch):
    monkeypatch.setattr(al, "PRICE_PER_MTOK", {"input": 1e6, "output": 1e6})
    monkeypatch.setattr(al, "EST_OUTPUT_TOKENS", 10)
    assert al.estimate_cost(["x" * 400, "y" * 400]) == {"items": 2, "input_tokens": 200, "output_tokens_est": 20,
                                                         "usd": 220.0}
