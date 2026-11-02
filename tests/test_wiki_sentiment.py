import numpy as np
import pandas as pd

from src import wiki_sentiment
from src.wiki_sentiment import (
    added_sentences,
    clean_wikitext,
    score,
    sentiment_returns,
    week_pairs,
    week_sentences,
    weekly_sentiment,
)


def _row(added: str) -> str:
    return f'<tr><td class="diff-marker"></td><td class="diff-addedline diff-side-added"><div>{added}</div></td></tr>'


def test_week_pairs_compare_the_revision_live_at_each_week_boundary():
    revs = pd.DataFrame({"revid": [1, 2, 3, 4],
                         "timestamp": pd.to_datetime(["2024-01-03", "2024-01-09", "2024-01-11", "2024-01-24"])})
    weeks = pd.date_range("2024-01-08", periods=3, freq="7D")
    out = week_pairs(revs, weeks)
    assert out["week"].tolist() == [pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-22")]   # no edits Jan 15
    assert out[["from_rev", "to_rev"]].values.tolist() == [[1, 3], [3, 4]]


def test_clean_wikitext_keeps_only_the_prose():
    raw = ("'''Alphabet''' shares [[Stock|fell]] 12%<ref name=x>{{cite web|url=a}}</ref> "
           "after {{nowrap|{{abbr|Q3}}}} results.<!-- note --> [https://x.org the report]")
    assert clean_wikitext(raw) == "Alphabet shares fell 12% after results. the report"


def test_added_sentences_keeps_new_lines_and_changed_sentences_only():
    body = "".join([
        _row("Revenue grew 15% to a record high this quarter. The board approved a buyback plan."),
        _row("The company is based in California today. Shares <ins class=\"diffchange\">fell 12% after "
             "earnings</ins> missed estimates badly."),
        _row("|revenue = <ins>US$350 billion</ins>"),                                  # infobox field
        _row('<a class="mw-diff-movedpara-right"></a>An old paragraph that only moved somewhere.'),
        _row("Too short."),
    ])
    assert added_sentences(body) == ["Revenue grew 15% to a record high this quarter.",
                                     "The board approved a buyback plan.",
                                     "Shares fell 12% after earnings missed estimates badly."]


def test_added_sentences_follow_an_insertion_across_sentences():
    body = _row("Old text stays the same here. <ins>New sentence one is here. New sentence two is "
                "here.</ins> Old ending stays the same too.")
    assert added_sentences(body) == ["New sentence one is here.", "New sentence two is here."]


def test_week_sentences_caches_and_resumes(tmp_path, monkeypatch):
    calls = []

    def fake_compare(a, b, lang="en"):
        calls.append((a, b))
        return _row("Shares fell sharply after the earnings report.") if b == 2 else ""

    monkeypatch.setattr(wiki_sentiment, "compare", fake_compare)
    revs = pd.DataFrame({"revid": [1, 2, 3], "timestamp": pd.to_datetime(["2024-01-03", "2024-01-09", "2024-01-16"])})
    weeks = pd.date_range("2024-01-08", periods=2, freq="7D")
    f = tmp_path / "X.csv"
    out = week_sentences("X", revs, weeks[:1], f)
    assert out["sentence"].tolist() == ["Shares fell sharply after the earnings report."]
    out = week_sentences("X", revs, weeks, f)                     # second week is new, first is cached
    assert calls == [(1, 2), (2, 3)] and out["sentence"].tolist()[-1] == ""


def test_score_maps_model_output_to_labels(monkeypatch):
    def fake_clf(texts, **kw):
        return [[{"label": "negative", "score": 0.8}, {"label": "positive", "score": 0.1},
                 {"label": "neutral", "score": 0.1}] for _ in texts]

    monkeypatch.setattr(wiki_sentiment, "_classifier", lambda model: fake_clf)
    out = score(["a", "b"])
    assert out["label"].tolist() == ["negative", "negative"] and np.isclose(out["p_negative"], 0.8).all()


def test_weekly_sentiment_counts_and_net():
    w = pd.Timestamp("2024-01-08")
    scored = pd.DataFrame({"ticker": ["A", "A", "A", "B"], "week": [w] * 4,
                           "sentence": ["x", "y", "z", ""], "label": ["positive", "negative", "negative", None],
                           "p_positive": [0.9, 0.1, 0.0, np.nan], "p_negative": [0.0, 0.8, 0.9, np.nan]})
    out = weekly_sentiment(scored).set_index("ticker")
    assert out.loc["A", ["n_sent", "n_pos", "n_neg"]].tolist() == [3, 1, 2]
    assert np.isclose(out.loc["A", "net"], -1 / 3) and np.isclose(out.loc["A", "tone"], (0.9 - 0.7 - 0.9) / 3)
    assert out.loc["B", "n_sent"] == 0 and np.isnan(out.loc["B", "net"])


def test_sentiment_returns_finds_lower_returns_after_negative_edits():
    rng = np.random.default_rng(0)
    weeks = pd.date_range("2020-01-06", periods=200, freq="7D")
    neg = rng.random(200) < 0.3
    weekly = pd.DataFrame({"ticker": "A", "week": weeks, "n_sent": 3, "n_pos": np.where(neg, 0, 2),
                           "n_neg": np.where(neg, 2, 0)})
    abn = rng.normal(0, 0.01, 200) - np.where(neg, 0.03, 0)
    prices = pd.DataFrame({"ticker": "A", "week": weeks, "abn_ret": abn,
                           **{f"abn_ret_next{k}": rng.normal(0, 0.01, 200) for k in range(1, 5)}})
    spikes = pd.DataFrame({"ticker": "A", "week": weeks, "spike": True})
    out = sentiment_returns(weekly, prices, spikes, n_resamples=200).set_index(["comparison", "value"])
    same = out.loc[("negative edits vs rest", "abn_ret")]
    assert same["ci_high"] < 0 and np.isclose(same["diff"], -0.03, atol=0.01)
    assert out.loc[("negative edits vs rest", "abn_ret_next3"), "block_weeks"] == 3
    assert len(out) == 15


def test_added_sentences_do_not_split_at_abbreviations():
    body = _row("Google has worked with the U.S. Department of Defense on drones. Alphabet Inc. later sold it.")
    assert added_sentences(body) == ["Google has worked with the U.S. Department of Defense on drones.",
                                     "Alphabet Inc. later sold it."]
