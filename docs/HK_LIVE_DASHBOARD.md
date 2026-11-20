# HK live display

November 19 connection repair: the API and existing collector were stopped.
The collector was restored through its existing controls, with 95 quotes and
no provider errors. The launcher now starts/reuses a persistent loopback API
and the known collector; closing Terminal no longer disconnects the page.
`src/hk/dashboard_runtime.py` controls the API, with state/logs under ignored
`data/hk_dashboard/`. `Stop HK Dashboard.command` stops only its owned API.

The API and CLI now share receipt-based source discovery via
`src/hk/live_paths.py`, including late collector startup. The browser gives
startup instructions for file opening and distinguishes API, feed and missing
market errors. All mode keeps HK connected when India/US are absent.

The original November 18 implementation scope follows.

Entry point: [`frontend/live_markets/README.md`](../frontend/live_markets/README.md).
Run `Start HK Dashboard.command` from the root, or
`python -B -m src.hk.dashboard start --with-feed --open-browser` from an
activated project environment. Manual `serve` is still a foreground API-only mode.

## Guide scope

Week 3 assigns Jack the Hong Kong collector and latest-quote handoff to James.
Week 4 pages 16–19 assign James the shared API and full dashboard. Jack asked
for the local Hong Kong live frontend now, so this extension implements that
panel and a small read-only API adapter in IndicatorLab. It is separate from
the Vibe-Trading HSI benchmark contribution; no original Vibe app is copied.

| Guide requirement | Implementation / integration limit |
|---|---|
| Keep existing frontend framework | Plain HTML/CSS/JS, matching `frontend/reddit_dashboard`; no added chart library is needed for quote cards |
| `/live/{market}` every 5 seconds | HK endpoint, read from existing local latest JSON or opt-in DynamoDB; no browser calls to Tencent |
| Price and daily change, green/red | HKD cards, with numeric change, volume and stock details |
| HK local time, closed last prices | Exchange clock; existing XHKG session/lunch/holiday gate; explicit last update/next open |
| `/health` as-of; loading/error | Header timestamp, skeletons, initial unavailable state, retained quotes on outage, delayed receipt warning |
| Global market filter | US/India/HK/All selector; other feeds report not connected until supplied by the team API |
| Attention badge from `/hot` | Implemented as an opt-in hook; disabled locally because this API does not implement the team's attention aggregate |
| Pages 5–6 | Strategy results and Cross-market comparison placeholders, “coming Nov 22” |
| API URL from environment; exact CORS | Generated public `config.js`, optional explicit CORS list; no client secrets |
| GitHub then AWS | Portable static build and AWS handoff documented; nothing pushed or deployed |

This does not mark James's Hot/Stock/Spikes pages, `/runs`, the full team health
aggregation, AWS service acceptance, shared URL or feedback collection complete.
It does not change any frozen strategy rules, datasets or results.

## Files for review

- `frontend/live_markets/`: actual browser UI, build script, public defaults,
  Node tests and README. There are no npm runtime dependencies.
- `src/api/live_data.py`: bounded local JSON / paginated DynamoDB reader;
  dated roster, alias handling, invalid-row isolation and session metadata.
- `src/api/live_routes.py`: read-only `/live/hk` and `/health`.
- `src/api/main.py`: mounts the new router/static panel; preserves Joshua's
  existing router unchanged. James can reuse the reader/route contract in
  his team service without replacing his full API.
- `src/hk/dashboard.py`, `Start HK Dashboard.command`: local launcher and
  portable static build. The managed launcher reuses known workers; manual serve is API-only.
- `tests/test_hk_dashboard.py`: offline API, malformed data, calendars,
  DynamoDB pagination, build/secrets and existing-router regression checks.
- `.env.example`, `.gitignore`, `frontend/README.md`, root navigation,
  `AGENTS.md`, Week 4 status and `code_review.md`: setup and review metadata.

Only these dashboard files and navigation/setup additions belong to this change.
Previous uncommitted Week 4 work is retained; review `git diff` before making
your own commit. Generated `dist/`, current quotes and `.env` are ignored.

## Verification

The working display read the existing 95-stock Tencent snapshot from
`../indicatorlab-clean/data/live_hk/current/latest.json` without starting a
worker. Browser checks cover search, watchlist, detail dialog, pause/refresh,
outage with retained prices, recovery, desktop/mobile layouts, placeholders
and the unconnected India state. Automated contract and UI helper tests use
fixtures; they do not claim live AWS or full team integration acceptance.

Operational quotes, research adjusted prices and strict benchmark membership
remain separate. See the frontend README for price/volume/membership conventions
and the AWS boundary. No trading or portfolio evaluation was run for this UI.
