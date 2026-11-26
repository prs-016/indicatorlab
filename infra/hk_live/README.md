# HK collector: reviewable AWS handoff

**Not deployed. Get the team's approval before building/pushing an image,
creating/updating the stack, enabling schedules or starting Fargate.** The
project has a spend limit. This PR only prepares code and offline checks.

The supported region is **us-east-2 (Ohio)**. The shared stack already owns
`indicatorlab-live-hk` and `indicatorlab-data`; this stack references them using
`QuoteTableName` and `DataBucket`. It never creates/deletes a DynamoDB table or
the shared bucket. IAM is scoped to that table and `raw/live/hk/*`.

The Fargate service has desired count **0**. `SchedulesState` defaults to
`DISABLED` for start/stop schedules and the independent watchdog timer; alarm
actions are disabled with them. Enabling collection is a separate approved
operation. No credentials or account identifiers belong in Git.

## Components and data

- `src.hk.live`: deployed collector entry point. It reads the dated 95-name CSV,
  polls Tencent at five-second intervals during HK continuous sessions, and
  writes the existing latest-state table. Imports never start collection.
- `src.live.hk`: opt-in shared polling CLI (`python -m src.live.hk`). The small
  `src.live.base` prerequisite is included. It uses the same parsing/calendar
  and AWS destinations. Run one collector, not both.
- `src.hk.calendar`: calendar prerequisite, including lunch, half days and
  evidenced exceptional closures. The roster is not historical membership.
- `src.hk.cloud.watchdog`: independent receipt-age check with calendar and
  reopening grace. It measures ingestion, not time since the last trade. The
  oldest provided receipt exposes partial staleness.

Both AWS sinks write complete retained minute Parquet snapshots under
`raw/live/hk/date=.../` and a stable `raw/live/hk/current/latest.json` once per
minute. The latter is the dashboard's build-time quote input. DynamoDB rows
update each successful poll. Provider quantities and exchange/receipt times
are retained; no latency guarantee or unverified volume conversion is added.
The two CLIs use their documented historical partitions; the current object
has the same seven-field quote contract in both.

## Offline setup and tests

```bash
pip install -r requirements.txt
pytest tests/test_hk_live.py tests/test_hk_cloud.py tests/test_hk_week4_live.py tests/test_hk_live_infra.py -q
```

`exchange-calendars` is required by the session tests. Docker uses a separate
minimal requirements file and the legacy HK CLI. The shared CLI/tests also
use the root requirements' PyYAML dependency.

## Read-only checks for a teammate with AWS access

```bash
aws s3api get-bucket-location --bucket indicatorlab-data --region us-east-2
aws dynamodb describe-table --table-name indicatorlab-live-hk --region us-east-2 --query 'Table.{Name:TableName,KeySchema:KeySchema,Status:TableStatus}'
aws s3 ls s3://indicatorlab-data/raw/live/hk/ --region us-east-2
```

Confirm the shared table's string partition key is `symbol`. These checks were
not run against AWS on Jack's Mac because no profile is configured. Local tests
mock AWS and check the template; they do not certify a deployment.

## Only after approval

Build the ARM64 image with the team's ECR process, then review a change set
for `infra/hk_live/template.yaml` in us-east-2 with real image/VPC/subnet values.
Leave `SchedulesState=DISABLED`, `QuoteTableName=indicatorlab-live-hk` and
`DataBucket=indicatorlab-data` during review. The template has a region
assertion, and Python AWS entry points reject another region.

After separate activation approval, the schedules start at 09:20 HKT and stop
at 16:10 HKT on weekdays; code suppresses polling at lunch/holidays. Verify all
95 symbols, source/receipt times, minute S3 writes and watchdog behavior in a
real session. Rebuild/publish the static dashboard to expose new snapshots;
the collector does not deploy the website.

To pause collection, disable start schedules and set the ECS desired count to
zero; review watchdog/alarm settings too. Do not remove the shared table or
bucket as rollback. No deployment command has been run here.
