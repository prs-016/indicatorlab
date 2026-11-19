# A1 PR: optional FinBERT scorer (draft, not posted)

Branch: `feat/sentiment-finbert-scorer` in `vibe-trading-fork`, one commit on `upstream/main` (0025531f).
Open it from **your fork** (Joshuaamm7/Vibe-Trading) into HKUDS/Vibe-Trading `main`.

## Before you push (Joshua)

1. Create the fork on GitHub, then:
   `git -C vibe-trading-fork remote add origin https://github.com/Joshuaamm7/Vibe-Trading.git`
2. Co-author lines. Upstream `CONTRIBUTING.md` says *"Do NOT add `Co-Authored-By:` trailers"*; the team
   guide wants four. The commit currently has only your sign-off. If Anay says to add them, run:
   `git -C vibe-trading-fork commit --amend -s` and paste this block at the end of the message:
   ```
   Co-authored-by: Jamal <188647228+Jampip@users.noreply.github.com>
   Co-authored-by: James <238608756+james-mulyono@users.noreply.github.com>
   Co-authored-by: Jack <234474744+jaz024@users.noreply.github.com>
   Co-authored-by: Prakhar Shah <195330099+prs-016@users.noreply.github.com>
   ```
3. Fill the two `TODO` parts below after the human label check (Tue Nov 17), then
   `git -C vibe-trading-fork fetch upstream && git -C vibe-trading-fork rebase upstream/main`,
   rerun the tests, and `git push -u origin feat/sentiment-finbert-scorer`.

---

**Title:** feat(sentiment): optional FinBERT scorer for the sentiment tool

**Authors:** @Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016

Design issue: TODO(Joshua): link the A0 issue once posted.

## What it adds and why

`sentiment_tool.py` scores text with a short positive/negative word list. That misses finance phrasing
("closed the probe without any penalty" counts as negative; "free cash flow doubled" as neutral). This PR
adds an optional finance-tuned scorer to the **same** tool:

- `scorer` parameter on `sentiment_score`: `"lexicon"` (default, unchanged) or `"finbert"`.
- FinBERT = `ProsusAI/finbert` pinned to revision `0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031`. All three
  probabilities are returned; `score = P(positive) - P(negative)`, on the existing [-1, 1] scale.
- `score_texts(texts, scorer)` for batch use (duplicates scored once, shortest first, batch size 32,
  512-token truncation) and `prepare_text(title, body)`.
- New optional extra: `sentiment = ["transformers>=4.40", "torch>=2.2"]`, lazy-imported. Without it,
  `scorer="finbert"` returns a named error with `pip install "vibe-trading-ai[sentiment]"`, the same way
  the `zerodha` and `upbit` extras behave.

## Design choices

- One tool, not a second one: the agent keeps a single `sentiment` tool and picks the scorer.
- Every result has `scorer`, `score` and `label`; the lexicon keeps its `positive`/`negative` word counts,
  FinBERT adds `probabilities` and `model`. Existing lexicon output only gains `scorer` and `label`.
- Pinned revision so scores are reproducible when the model repo changes.
- No silent fallback: asking for FinBERT without the extra is an error, so a user never gets lexicon
  numbers they think came from FinBERT.

## Comparison on labelled Reddit posts

TODO(Joshua): paste the table from `docs/reddit/week3_report.md` (FinBERT vs lexicon vs VADER vs LLM:
accuracy, macro-F1, per-class recall, 95% CIs, graded against human labels; n and kappa stated), plus
three labelled posts where the lexicon is wrong and FinBERT is right.

Smoke test with the real pinned model (my own sentences, not labelled data):

| Text | Lexicon | FinBERT |
|---|---|---|
| Regulators closed the probe without any penalty | negative (-1.00) | neutral (-0.18) |
| Free cash flow doubled and buybacks resume | neutral (0.00) | positive (0.91) |
| Shares rose despite the company cutting its full-year outlook | neutral (0.00) | positive (0.15) |
| Debt costs are climbing faster than sales | neutral (0.00) | positive (0.87), wrong |

The last row is a known FinBERT weakness: it is not a perfect scorer, which is why it is optional.

## Tests

```
cd agent
pytest tests/test_sentiment_tool.py tests/test_packaging_dependencies.py -q     # 45 passed
pytest tests/ -q -k "sentiment or packaging or tool_registry or tools_schema"     # 82 passed, 9 skipped
ruff check src/tools/sentiment_tool.py tests/test_sentiment_tool.py tests/test_packaging_dependencies.py
bash tools/ci_grep_gates.sh                                                       # all gates passed
```

New tests stub the Hugging Face pipeline (no downloads): default is still the lexicon and never loads the
model; FinBERT returns the net score and all three probabilities; FinBERT output has every shared key of
the lexicon output; batching (unique texts once, shortest first, pinned limits); missing-extra error names
the install command; the pipeline loads at the pinned revision; unknown scorer rejected; `prepare_text`.

## Known limits

- FinBERT was trained on financial news; Reddit and product-forum text is out of domain (see the table).
- First use downloads about 440 MB of model weights.
- Licence: TODO(Joshua): confirm the weights' licence from the A0 issue check (the A0 session reported
  CC BY-NC-SA 4.0 on the model card). If so, say here that the weights are non-commercial and are only
  downloaded by users who opt in to the extra; nothing is vendored.

## Scope

Only the tool and its extra. The Reddit and Wikipedia attention loaders (A2, A3) and the `attention`
factor family (A4) follow as separate PRs, as laid out in the design issue.
