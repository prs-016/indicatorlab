# Hong Kong live markets

A plain HTML/CSS/JavaScript panel for the existing HK collector. Prices, daily
change, volume and exchange timestamps come from your feed, not sample data.
Search, gainers/losers, sorting, pagination, a saved watchlist and stock details
work on desktop and mobile. There are no npm dependencies.

## Open it on this Mac

Double-click **`Start HK Dashboard.command` in the repository root**. It opens
<http://127.0.0.1:8765/live-markets/> after starting or reusing one local API and
the existing HK collector. **You can close its Terminal window**; the API runs
as a background process. Repeated clicks reuse it instead of starting duplicates.
After a Mac restart, open the launcher again. No login daemon is installed.

To stop the display/API, double-click **`Stop HK Dashboard.command`**. The quote
collector remains independent and keeps updating while the Mac is awake.

From a project Python environment, the equivalent commands are:

```bash
python -B -m src.hk.dashboard start --with-feed --open-browser
python -B -m src.hk.dashboard status
python -B -m src.hk.dashboard stop
```

For a foreground, API-only development server, use
`python -B -m src.hk.dashboard serve`; keep that Terminal running. This manual
mode does not start a collector. `--data-dir /path/to/collector/output` chooses
an explicit source. Direct `uvicorn src.api.main:app` uses the same discovery.

Automatic discovery reads the newest valid receipt among `data/live_hk_week4/`,
`data/live_hk/current/` and `../indicatorlab-clean/data/live_hk/current/`. It can
find a collector that starts after the API. An explicit
`INDICATORLAB_LIVE_HK_DIR` is respected. The launcher checks known collectors
before starting one; cloud/custom stores are left to their own operators.

Open the page through its HTTP URL. Opening `index.html` as a file shows startup
instructions because the page needs the API. The interface distinguishes an API
outage, unavailable quote snapshot, invalid response and an unconnected market.
In All mode, missing India/US feeds do not mark a working HK feed disconnected.
Local API failures point back to the launcher; hosted failures refer to the
configured service. Missing data never produces fabricated quotes.

On a fresh clone, create a dedicated Python environment and install the root
`requirements.txt`. Supply an existing collector output, or follow
[`HK_WEEK4_LIVE_LOCAL.md`](../../docs/HK_WEEK4_LIVE_LOCAL.md) to configure a
collector on the intended host. Do not start a duplicate worker on this Mac.
GitHub carries the application code; it does not run the collector or API.

## What it reads

- `GET /live/hk`: quotes plus `market_open`, `next_open`, roster/coverage and
  freshness metadata. Polled every **5 seconds**, with manual refresh and pause.
- `GET /health`: actual live-source timestamps, shown in the header. It does
  not invent Reddit/Wikipedia service health.
- `GET /hot?market=hk`: optional attention badges, disabled until the team's
  real endpoint is configured. Enable with `INDICATORLAB_ATTENTION_ENABLED=true`.

The HK response has the team's seven quote fields (`symbol`, `price`,
`change_pct`, `volume`, `ts_exchange`, `ts_received`, `source`) plus names and
display metadata. Prices are nominal HKD live quotes, not adjusted research
prices. Volume is displayed in the collector's provider units, unchanged; it
is not silently converted to board lots. This is a display, not an order entry
or strategy evaluation interface.

The operational roster is the **dated November 4, 2026 snapshot of 95 stocks**
in `config/hsi_constituents_2026-11-04.csv`. It is not a continuously refreshed
or historical membership service and does not replace the separate strict
Wikipedia benchmark loader. The page shows its roster date and missing quotes.

During trading, receipt age above 60 seconds warns that updates are delayed.
Last-trade time and receipt time remain separate. Lunch, holidays and closed
sessions keep the latest prices and show the next opening from the existing
XHKG calendar. A 5-second poll is **not a guarantee of sub-minute provider
latency**. An API outage retains already loaded prices and displays an error.

The market selector accepts HK/India/US/All. This extension only supplies HK.
Other feeds show an explicit unconnected state until the team API supplies
them. The guide's pages 5–6 exist as the requested “coming Nov 22” placeholders.
James's attention/spike pages and trading execution are outside this HK panel.

## Configuration and AWS handoff

Export environment values before serving/building; these commands do not load
`.env` automatically. Examples with empty values are in the root `.env.example`.

| Variable | Used by | Default / purpose |
|---|---|---|
| `INDICATORLAB_API_BASE_URL` | Server/build → browser | Empty means same-origin API; set an HTTPS API URL for AWS static hosting |
| `INDICATORLAB_ATTENTION_ENABLED` | Server/build → browser | `false`; turn on only when `/hot` exists |
| `INDICATORLAB_CORS_ORIGINS` | API only | Comma-separated exact dashboard origins; no wildcard or credentials |
| `INDICATORLAB_LIVE_SOURCE` | API only | `local`, or explicitly `dynamodb` |
| `INDICATORLAB_LIVE_HK_DIR` | API only | Directory containing local `latest.json` |
| `INDICATORLAB_HSI_ROSTER` | API only | Override the dated operational roster CSV |
| `INDICATORLAB_LIVE_HK_TABLE` | API only | `indicatorlab-live-hk` |
| `AWS_REGION` | API only | `us-west-2` |

Build static assets for later S3/CloudFront hosting:

```bash
cd frontend/live_markets
INDICATORLAB_API_BASE_URL=https://your-team-api.example.org npm run build
```

That example API domain must be replaced with your actual HTTPS service.
`dist/` contains only five public assets, including the generated `config.js`.
There is no `npm install` step. Alternatively, from the root run
`python -B -m src.hk.dashboard build --api-base-url https://your-team-api.example.org`.

For AWS, upload **the contents of `frontend/live_markets/dist/`** to a private
S3 bucket behind CloudFront, set `index.html` as the default root object, and
use appropriate JavaScript MIME types for `.mjs` files. Configure the API with
the exact CloudFront/custom dashboard origin in `INDICATORLAB_CORS_ORIGINS`.
The API is a separate running service; static S3 hosting cannot read DynamoDB
or run Python. The API can use `INDICATORLAB_LIVE_SOURCE=dynamodb` and an IAM
role with read access to the specific HK table. No AWS keys belong in the
frontend, static build, or Git. Disable caching for live/health API requests;
revalidate `index.html` and `config.js` when deploying new settings. Hash routes
work without SPA path rewrites.

Follow the official [CloudFront + S3 setup guide](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/GettingStarted.SimpleDistribution.html)
when deploying. **No AWS resource, deployment or remote push was made by this
frontend implementation.** The existing collector remains independent.

## Validate and commit

From this folder: `npm test`, `npm run check`, `npm run build`.
From the root: `python -B -m pytest tests/test_hk_dashboard.py
tests/test_hk_dashboard_startup.py -q -p no:cacheprovider`.
The backend tests use temporary snapshots and mocked DynamoDB, not AWS calls.

The exact code/docs scope and guide mapping are in
[`docs/HK_LIVE_DASHBOARD.md`](../../docs/HK_LIVE_DASHBOARD.md).
Commit the source, tests, configuration examples and documentation on **Jack**.
`dist/`, local live quotes, environments and secrets stay ignored. No files
need to be copied into the separate HKVT Vibe contribution package.
