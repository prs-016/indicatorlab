# HK static CloudFront export

The existing US export is retained. HK is included when a shared source root
is supplied; no personal checkout or localhost API is accessed by this build
or the hosted HK browser module.

## Build only (no deployment)

```bash
pip install -r requirements.txt
python -m src.reddit.dashboard_export --hk-root-uri s3://indicatorlab-data --out build/reddit_dashboard
```

Use an already-authorized AWS profile in us-east-2. This reads the data bucket
and writes local files; it does not create resources, start a collector, upload
the website or invalidate CloudFront. A local directory with the same
`processed/` and `raw/` layout also works for offline QA.

`infra/dashboard/deploy.sh` supplies this root before its existing hosting and
upload steps. **Do not run that deployment script until the team approves
publication.** Merging alone does not publish files. The hosting stack and
existing US data/research functions are unchanged.

## Shared input contract

| Key | Required? | Use |
| --- | --- | --- |
| `processed/wiki_current.parquet` | Yes | Current trailing-seven-published-day views, baseline, ratio and flag. |
| `processed/wiki_weekly.parquet` | Optional | Attention history, edits and published scored sentiment. |
| `processed/prices_weekly.parquet` | Optional | Weekly price charts; adjustment basis is not inferred. |
| `processed/wiki_edit_summaries.parquet` | Optional | Published source evidence. |
| `raw/live/hk/current/latest.json` | Optional | Saved quotes from the separately approved collector. |

Rows are filtered by `market=hk`; US rows are excluded. Required columns and
duplicate records are checked. Missing optional sources stay unavailable;
permission failures stop the build. No Mac data or public-provider call is used
as fallback. Saved strategy summaries are the existing tracked research export.

The browser reads `api/hk/*.json` and `api/hk/stock/<ticker>.json`, with relative
assets suitable for S3/CloudFront. Static pages make no localhost/API polling
requests. They are labelled **Hosted snapshot** with build and quote times.
Rebuilding and publishing refreshes them; a browser reload does not collect
prices. The USD calculator remains available locally; its controls are disabled
with an explanation in static mode because no cost API is hosted.

The real downloaded input checked on November 26, 2026 has 95 distinct HK
stocks, source as-of November 25, with no duplicated HK ticker. It contains
current views but no edit counts or scored sentiment. Missing values are not
fabricated. Raw Parquets are not committed; the sanitized validation report
records their digests and observed coverage. Live S3/IAM validation still needs
a teammate's AWS access.

## Publication check (after approval)

Use the existing process to upload the complete build and refresh the CDN.
Check all six HK pages from the hosted URL, plus the US pages and existing
India control. Requests should be static JSON/assets only. New price snapshots
also require the separately approved collector and a subsequent site rebuild;
a DynamoDB table alone cannot make a static site stream.
