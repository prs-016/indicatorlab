# Hong Kong in the shared IndicatorLab website

The existing website now has isolated Hong Kong pages for Home, This week,
Stock, Spikes, Strategies and Data status. Default US routing, data functions
and research commands are unchanged. The existing disabled India control is
unchanged. No Vibe Trading clone or India module is part of this change.

## Open it on Jack's Mac

Double-click `start_hk_dashboard.command` in this checkout. Keep its Terminal
window open while using the site. Open:

http://127.0.0.1:8879/?market=hk#home

The launcher uses this checkout's `.venv`, or this Mac's existing sibling
`indicatorlab-clean/.venv`. It never installs packages or stops another process.
Set `INDICATORLAB_PYTHON` for a different interpreter. The equivalent command
from the repo root, with the environment activated, is:

```bash
python -B -m src.hk_dashboard.launch --port 8879
```

The original site hides its market selector on the US Home page: visit
This week to select Hong Kong, or use the direct link above. On Hong Kong Home
the selector remains visible. Switching back to US restores the previous US
page. HK requests, charts, filters and quote polling are separate from US state.

## Inputs and refresh

For another computer or AWS, first create a Python virtual environment and
install `requirements.txt`. The added `exchange-calendars` dependency supplies
the XHKG session clock, including lunch, holidays and half days. This is a
local mode uses a running Python service. CloudFront uses the build-time
shared-storage snapshot described below.
The default US-only export keeps its existing behavior. A build with
`--hk-root-uri s3://indicatorlab-data` includes all HK static JSON/assets and
keeps HK enabled without a live API or personal checkout. See
[the shared-storage static export guide](hk_static_export.md).

| Input | Configuration / location | Behavior |
| --- | --- | --- |
| HK quote and USD cost service | `INDICATORLAB_HK_API_BASE_URL`, default `http://127.0.0.1:8765` | Reuses the existing `/live/hk` API; never starts another collector. |
| Quote-file fallback | `INDICATORLAB_LIVE_HK_DIR` pointing to a directory containing `latest.json` | Reads a bounded retained snapshot if the API is down. A file alone does not provide updates. |
| Existing HK research checkout / data mount | `INDICATORLAB_HK_SOURCE_ROOT` | On this Mac automatically discovers sibling `indicatorlab-Jack`; read-only. |
| Fresh display cache | `INDICATORLAB_HK_DISPLAY_DIR`, default `data/hk_dashboard/display/` | Separate ignored Wikipedia JSON and Yahoo price Parquets; never research input. |
| Operational universe | `config/hsi_constituents_2026-11-04.csv` and `config/hk_final_symbol_metadata.json` | Dated 95-stock snapshot; not reconstructed historical membership. |
| Saved strategy statistics / curves | `results/hk_dashboard/saved_research.json` | Small tracked export of Jack's own archived results, including source hashes. No execution. |

The quote service must remain running for continuously updating prices and
the USD calculator. A snapshot fallback retains prices with their actual
timestamps; it cannot replace the local service. For the hosted static site,
use `--hk-root-uri` to read shared S3 exports instead of configuring a localhost
backend or mounting this Mac's files. No AWS deployment was performed.

To refresh only daily display data, run from the repo root:

```bash
python -B -m src.hk_dashboard.refresh
python -B -m src.hk_dashboard.refresh_prices
```

These commands work without the old research checkout. They retrieve public
Wikimedia article counts/revision metadata and one full Yahoo historical price
vintage per stock. They update only the display directory and preserve prior
usable data when a provider fails. Run them again when a new daily observation
is needed. No scheduler, strategy run or research rebuild is triggered by the
site. The page's Refresh display button reloads current stored observations;
it does not download or retrain anything.

The full local display cache is intentionally ignored, rather than added as
large raw market-data files to Git. Transfer a permitted cache to a deployment
or run the two commands there. No HKEX board-lot table is redistributed: the
USD form uses the existing cost service and reports unknown broker/FX fees as
unknown. Blank editable fees do not imply zero charges or a complete estimate.

## Source and interpretation boundaries

- Live prices are nominal HKD. Exchange time, receipt time and HK session status
  remain separate. The browser requests quote updates every five seconds;
  provider latency is measured, not guaranteed. It retains displayed prices and
  reports a lost connection if a request fails.
- Daily charts use Yahoo's split/dividend-adjusted close in HKD. Each refresh
  replaces the entire per-stock display vintage; adjusted histories are never
  spliced across vintages. Volumes are not rescaled. Intraday quotes are separate.
- Attention is Wikipedia views and edits, not Reddit. The collector follows
  MediaWiki redirects to the resolved article. Counts are from one current
  article identity, not sums of alias/redirect traffic. Current title mappings
  and article-level counts are not point-in-time historical company mappings.
- 94 stocks have English mappings; Laopu Gold uses Chinese. BYD Electronic
  (`0285.HK`) and BYD (`1211.HK`) share the BYD Company article: activity is broad
  parent-entity attention and those series are not independent evidence.
- Missing source days/weeks stay missing. Before evidenced article creation,
  counts are unavailable. The newest displayed week must be observed for at
  least half the stocks with attention records; view/edit dates may differ.
  A current partial week is projected by daily rate for comparison only;
  raw counts remain raw and incomplete older weeks are excluded from baselines.
- The unchanged shared `flag_spikes` rule uses strictly prior observations.
  These display flags do not authorize research beyond the November 1, 2026
  holdout boundary. Research files and results are not updated.
- FinBERT is available only from saved Wikipedia-addition scores for the original
  five stocks, with matching language/title and latest revision for that week.
  New scores are not inferred or generated. Other sentiment is unavailable.
- Strategies displays the three frozen five-stock Week 4 results, all DROP,
  with their saved IC, Sharpe, explanation and saved HKD equity curves. These
  are not new tests of the 95-stock display. Existing native-confirmation
  differences remain disclosed; no candidate is promoted by this dashboard.

Wikimedia sources: [pageview API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html),
[access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html),
[revision API](https://www.mediawiki.org/wiki/API:Revisions).

## Verification

Run `python -B -m pytest -q` from the repo root. HK synthetic tests cover symbol
validation, missingness, creation boundaries, baselines, adjusted-price vintage,
revision-matched sentiment, quote timestamps/fallbacks, XHKG sessions, API
isolation, read-only HK POST handling, and the unchanged India control.
Browser checks include all six HK and US routes, all 95 stock options, search,
USD cost submission, direct links, mobile layout and switching back to US.
