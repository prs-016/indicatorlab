# Indicator Lab dashboard (v1, James)

A static page (`index.html`, `config.js`) that reads everything from the Indicator Lab API (`src/api/`).
It follows `frontend/reddit_dashboard`: plain HTML/JS, Chart.js 4.4.1 for every chart, the same colour
tokens, light and dark mode. No build step.

| Page | Reads | Notes |
|---|---|---|
| Hot right now | `/hot?market=` | Refreshes every 5 minutes. A row opens its stock view. Today's change appears once the live feeds run (none for US). |
| Stock view | `/attention/{t}`, `/prices/{t}`, `/sentiment/{t}`, `/edits/{t}?week=`, Reddit posts | Price; Reddit mentions, Wikipedia views and Wikipedia edits as ratios to the 8-week baseline (log axis, dashed 1×, dots on spike weeks); net sentiment by group. Clicking a week fills "What happened". The date range defaults to 2 years. |
| This week's spikes | `/spikes?week=&market=` | Defaults to the latest research week. Counts of Reddit only / Wikipedia only / both. A row opens the stock at that week. |
| Live markets | `/live/india`, `/live/hk` | Every 5 seconds while the tab is visible. Open/closed with local time; the last price and its time when closed; "hot" badge. |
| Strategy results | `/runs` | Placeholder until next week. It lists the Vibe-Trading runs when `VIBE_API_URL` is set on the API. |
| Cross-market | none | Placeholder until open-source part B exists. |

Every page has the market filter (All / US / India / HK) and the "data as of" time from `/health`.

## Run locally

From the repo root:

```bash
CORS_ORIGINS=http://localhost:5173 .venv/bin/uvicorn src.api.main:app --port 8000
python -m http.server 5173 -d frontend/dashboard          # in a second terminal
open http://localhost:5173
```

The API URL comes from `config.js`. Add `?api=http://host:port` to the page's address to point one tab
somewhere else, for example at the API running on the test fixtures:

```bash
INDICATORLAB_DATA=tests/fixtures/api .venv/bin/uvicorn src.api.main:app --port 8001
```

The fixtures include India live quotes, which is how page 4 was checked before the feeds exist.

## Open dependency: `/spikes`

In `src/api/main.py`, Joshua's Week 2 Reddit router is mounted first and owns `GET /spikes` and
`GET /sentiment`, which take `?ticker=&start=&end=`. Until those move under `/reddit/` (the guide's
layout: `/reddit/top-posts`), page 3 gets a 422 "ticker required" from his route and says so.

The move is one line in `main.py`, `app.include_router(reddit.router, prefix="/reddit")`, plus the paths
in `tests/test_api_reddit.py`. It is Joshua's call.

The stock view's Reddit posts try `/reddit/top-posts`, then `/reddit/sentiment`, then Joshua's current
`/sentiment`, so they work before and after the move.

## Deploy (when the AWS resources exist)

1. Set `window.INDICATORLAB_API` in `config.js` to the App Runner HTTPS URL.
2. Upload the folder to Amplify, or to S3 + CloudFront (static files; nothing to build).
3. Add the dashboard's URL to the API's `CORS_ORIGINS`.

## Choices

- **Ratios on a log axis:** 2× and 0.5× sit the same distance from the baseline, and one 16× edit burst
  doesn't flatten every other week.
- **Colours:**
  - Wikipedia edits are green in both charts.
  - The attention series are blue/orange/green; the sentiment series are blue/amber/green.
  - Both sets pass the dataviz palette validator, colour-blind checks included, in light and dark mode.
  - The lighter colours are under 3:1 contrast on white, so every chart has a legend, and the attention
    chart has a table view.
- **Sentiment chips:** positive or negative when net sentiment is beyond ±0.05, otherwise neutral, always
  with the word.
- **Untrusted text:** Wikipedia summaries and Reddit titles are escaped, and links are http(s) only.
