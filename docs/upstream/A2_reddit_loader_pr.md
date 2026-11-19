# A2 PR: Reddit attention loader (draft, not posted)

Branch: `feat/reddit-attention-loader` in `vibe-trading-fork`, stacked on A1
(`feat/sentiment-finbert-scorer`, commit 3fe19ca6) because it uses A1's `score_texts`.
Open it after A1, from your fork. If A1 merges first, rebase onto `upstream/main` so only the A2
commit remains. Co-author lines: same open question as A1 (see `A1_finbert_pr.md`).

---

**Title:** feat(loaders): point-in-time weekly Reddit attention panels

**Authors:** @Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016

Design issue: TODO(Joshua): link A0. Depends on #TODO (A1).

## What it adds and why

Vibe has no social-attention data. This adds `load_reddit_attention_panel(symbols, start, end, index=...)`,
which returns weekly Reddit attention as date-by-symbol frames, built like the SEC `fund:*` panels:

| Field | Meaning |
|---|---|
| `mentions` | posts that mention the ticker that week |
| `mentions_ratio` | `(mentions + 1) / (median of the previous 8 weeks + 1)` |
| `sentiment_pos/neg/neu` | mean class probabilities (FinBERT, or one-hot lexicon labels) |
| `sentiment_net` | mean of positive minus negative |
| `n_scored` | posts with a sentiment score |

## Design choices

- **Point in time.** Week W (Mon-Sun UTC) is visible from the first trading day after it ends, taken from
  the caller's price index (no calendar dependency), plus an optional `lag_bars`. A week with no posts
  has NaN sentiment instead of repeating an older week.
- **Data.** Arctic Shift (Reddit archive, no auth). Title search (`title=`), 100 per page; `query=` times
  out on busy subreddits. Calls go through `backtest/loaders/_http.py`'s host throttle (1 s spacing).
  Finished windows are cached as JSON under `get_runtime_root()/cache/arctic_shift`.
- **Matching from config** (`reddit_attention_tickers.yaml`): company subreddits count every post;
  investor subreddits are title-searched, then confirmed by `$TICKER`, the bare symbol, company names, or
  an ambiguous word ("Apple", "Meta", "Amazon") only next to a context word.
- **Sentiment** through A1's `score_texts` (FinBERT with the `sentiment` extra, lexicon otherwise; the
  panel's `attrs["sentiment_scorer"]` records which ran).
- No new environment variables; the rules file ships as package data.

## Tests

```
cd agent
pytest tests/test_reddit_attention_loader.py -q                                  # 7 passed
pytest tests/test_reddit_attention_loader.py tests/test_sentiment_tool.py tests/test_fundamentals_pit.py tests/test_packaging_dependencies.py -q   # 61 passed
ruff check backtest/loaders/reddit_attention_loader.py backtest/loaders/arctic_shift_client.py tests/test_reddit_attention_loader.py
bash tools/ci_grep_gates.sh                                                       # all gates passed
```

All HTTP is mocked: panel shape; a week never appears before the first trading day after it ends (and
`lag_bars`); adding future posts does not change past values; ambiguity rules; the ratio uses only past
weeks; missing-FinBERT fallback to the lexicon; cache round-trip, and unfinished windows are not cached.

## Known limits

- Survivorship and coverage: the archive misses removed posts and has gaps on some days; title search
  misses posts that name the company only in the body.
- Fetching many tickers over many years is slow the first time (1 request per second); later runs hit
  the cache.
- The rules file ships seven large US tickers as examples; other markets need their own rules.
- TODO(Joshua): state Arctic Shift's terms of use from the A0 check.

## Scope

Loader only. Registering an `attn:` column prefix in the factor gate and the `attention` factor family
are A4.
