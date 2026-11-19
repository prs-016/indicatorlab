Title: Proposal: social attention and finance-tuned sentiment layer

<!--
NOT POSTED. Delete this comment and resolve every TODO before posting.
How to post: upstream allows blank issues, so open a blank issue, use the title
above and paste everything below this comment. (The "Feature Request" form has
only Problem / Proposed Solution / Area / Alternatives fields and prefixes the
title with "[Feature] "; if you use it, put sections 1-2 in "Problem or
Motivation", sections 3-7 in "Proposed Solution", and pick Area "Data Sources".)
Code pointers checked against upstream/main at 0025531f (2026-11-12).
Related closed upstream issues you could link: #172 (RSSHub event/sentiment
provider) and #920 (market sentiment tools).
-->

## 1. Authors

@Jampip, @Joshuaamm7, @james-mulyono, @jaz024, @prs-016 (UCSD DS3 Indicator Lab, a student team)

## 2. Problem

Vibe-Trading has no social or attention data.

- The only text signal is `agent/src/tools/sentiment_tool.py`. Its `sentiment_score` mode calls `_score_text`: a list of 54 positive and 77 negative words, scored as (pos − neg) / hits. It ignores negation and context, and text with no listed word scores 0.0. The other mode, `fear_greed_index`, is the crypto Fear & Greed index.
- No factor can read attention data: `validate_columns_required` in `agent/src/factors/registry.py` accepts only price columns, `fund:*` and `val:*`.

Abnormal retail attention tends to come before short-term price pressure that later reverses (Barber & Odean 2008; Da, Engelberg & Gao 2011). Reddit posts and Wikipedia page views and edits measure it for free.

## 3. Proposal, as staged PRs

Four small PRs, each usable alone. None touches the protected areas (`src/agent/`, `src/session/`, `src/providers/`).

**A1. Optional FinBERT scorer.** A `scorer` parameter on the existing `sentiment` tool: `"lexicon"` (default, unchanged) or `"finbert"`. No second tool.

- `"finbert"` runs `ProsusAI/finbert`, pinned to revision `0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031`, in batches. It returns the three class probabilities and keeps the existing `score` in [-1, 1] as P(positive) − P(negative).
- New extra in `pyproject.toml`: `sentiment = ["transformers>=4.40", "torch>=2.2"]`, imported lazily. Without it, `"finbert"` returns an error naming `pip install "vibe-trading-ai[sentiment]"`, as the `zerodha` and `upbit` extras do. The lexicon path needs nothing extra.

**A2. Reddit attention loader.** New `agent/backtest/loaders/reddit_attention_loader.py`, modelled on `fundamentals_loader.py`. For a list of tickers and a date range it returns one row per ticker and week: mentions, mentions over their 8-week median, sentiment probabilities and net sentiment (A1, falling back to the lexicon), and `n_scored`.

- Ticker matching comes from config: subreddits per ticker, name patterns, `$TICKER`, and ambiguity rules ("Apple" the fruit, "Meta" the word).
- Posts come from Arctic Shift, paged. Responses are cached under the runtime root (`get_runtime_root()`), never in the repo.

**A3. Wikipedia attention loader.** New `agent/backtest/loaders/wikipedia_attention_loader.py`, same output style as A2: weekly page views, weekly edit count and an edit-burst flag.

> TODO(James): loader details (endpoints, `agent=user`, renamed titles, 404 handling, backoff, and the User-Agent: Wikimedia requires a descriptive one with contact information).

**A4. `attention` factor family.** New `agent/src/factors/zoo/attention/`, laid out like `agent/src/factors/zoo/fundamental/`: one file per factor with the same `__alpha_meta__` block, plus a `LICENSE.md`.

| id | Definition (weekly) |
|---|---|
| `att_abn_views` | log(views / 8-week median) |
| `att_buzz` | log(mentions / 8-week median) |
| `att_sent_dev` | net sentiment − its 26-week mean |
| `att_edit_burst` | edit burst: weekly edits ≥ 2× their 8-week median |
| `att_gated_rev` | −(last week's return), only for names in the top 30% of abnormal attention |

Every baseline uses past weeks only (the current week is excluded). `universe` is `equity_us`, `equity_in` and `equity_hk`.

A4 needs three small core changes, mirroring how `fund:*` is wired:

- a new column prefix (we suggest `attn:`) in `validate_columns_required`;
- a panel-injection step next to `_inject_fundamental_panel` in `agent/backtest/runner.py` (NaN frames and a warning when a load fails, as today) and in `_prepare_bench_panel` (`agent/src/tools/alpha_bench_tool.py`);
- `"attention"` added to `Theme`, to `_VALID_THEMES` (`agent/src/api/alpha_routes.py`) and to the frontend zoo and theme labels. We can reuse existing themes if you prefer no new one.

## 4. Data sources and terms

- **Reddit, via Arctic Shift** (`arctic-shift.photon-reddit.com`). An independent third-party archive of public Reddit posts. Its API documents no key or login, promises no uptime and rate-limits dynamically (HTTP 429). Its repository has no licence file and states no terms for the data. Reddit's Public Content Policy allows non-commercial use of public content, asks commercial users to contact Reddit, and treats bulk collection outside its licensing arrangements as unauthorized; we found no statement that Arctic Shift has such an arrangement. The loader fetches only when a user opts in and ships no Reddit text (tests use synthetic fixtures).
  - TODO(Joshua): verify Reddit's User Agreement and Data API Terms (redditinc.com/policies) for anything further on third-party archives. Not checked yet.
- **Wikimedia page views** (Analytics API). The data is CC0 1.0 and starts 2015-07-01. Requests must send a descriptive User-Agent with contact information; generic agents can be blocked. An identified, unauthenticated client currently gets 200 requests per minute (limits are new in 2026 and may change).
- **MediaWiki revisions** (Action API). Same User-Agent rule and rate limits; requests should run in series. Article text is CC BY-SA 4.0 (and GFDL). The first version uses edit counts only, no article text.
- **Hugging Face `ProsusAI/finbert`.** At the pinned revision the model card licenses the weights under **CC BY-NC-SA 4.0 (non-commercial, share-alike)**. Vibe-Trading is MIT. The weights would never be vendored: they download from the Hub only when a user installs `[sentiment]` and passes `scorer="finbert"`. See question 1.

## 5. Point-in-time design

A week (Monday to Sunday, UTC) is usable only from the first trading day after it ends, plus a configurable ingestion lag. The loaders never return a week before that availability date.

This mirrors the existing `fund:*` panels. In `agent/backtest/loaders/fundamentals_loader.py`, a value becomes visible on its SEC `filed` date, never on `period_end`, and `_ffill_pit` forward-fills from that date onto the price index. For factors, weekly attention values are forward-filled the same way from their availability date, giving the same shape as `load_fundamental_panel`: `field -> DataFrame(index=dates, columns=symbols)`.

Two source-specific rules:

- Arctic Shift refreshes `score` and `num_comments` about 36 hours after posting, so they are not point-in-time. The loader uses post counts and text only.
- Page views for day D are usable from D+1.

## 6. Testing

- **No network or model downloads in CI.** HTTP is mocked and the Hugging Face pipeline is stubbed. Factor tests already run with sockets disabled (`agent/tests/factors/conftest.py`).
- **A1 to A3:** tests cover the output schema, the missing-extra error and lexicon fallback, ticker ambiguity rules, cache round-trips, and that week W never appears before its availability date.
- **A4:** every factor passes `agent/tests/factors/test_alpha_purity.py` and `agent/tests/factors/test_lookahead.py`.
  - One gap: `_baseline_panel` in `test_lookahead.py` builds only price columns, so an alpha that declares `attn:*` (or `fund:*` / `val:*` today) raises `SkipAlpha` and is skipped, not tested. We would add synthetic `attn:*` frames so the gate really runs on these factors.

## 7. Questions for maintainers

1. Is an optional extra (`[sentiment]`) acceptable, given the size of `torch` and the model's non-commercial licence? If not, would you prefer a different checkpoint, or the scorer kept out of tree?
2. Where should the loaders live: in `agent/backtest/loaders/` next to `fundamentals_loader.py` and `rsshub_events.py`, or somewhere else? They return weekly attention panels, not OHLCV, so we assume they stay out of the loader registry and the weekly loader-health lane, like those two.
3. The Attribution section of `CONTRIBUTING.md` rules out `Co-Authored-By:` trailers. All five of us work on these PRs and want each author credited. Would you accept human-only `Co-authored-by:` trailers next to the DCO sign-off, or should we use an Authors line in the PR description only?
