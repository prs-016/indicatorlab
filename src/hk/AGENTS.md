# HK live collector handoff (November 26, 2026)

`infra/hk_live`, `src/hk/live.py`, `src/hk/cloud` and `src/live/hk.py` provide an
explicitly invoked collector. The small `src/live/base.py`, HK calendar and
dated 95-name CSV are required dependencies. No research archive or backtest
result is part of this PR. Keep India services and research unchanged.

The team project is us-east-2. The stack references the existing shared
indicatorlab-live-hk table and indicatorlab-data bucket; never recreate or
delete them. Fargate desired count is zero and schedules/watchdog are disabled
by default. Get team deployment/budget approval before creating a stack,
pushing an image or enabling collection. No deployment is authorized here.

Latest state is upserted in DynamoDB; complete retained minute snapshots and
`raw/live/hk/current/latest.json` are written to S3. Preserve exchange/receipt
times and provider quantities; no guaranteed quote latency is claimed. Run
`pip install -r requirements.txt` and the HK cloud/live/infra tests before review.
Place review notes in the PR description, leaving shared code_review.md intact.
