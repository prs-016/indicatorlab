# India live deployment in Ohio

The India collector and independent receipt watchdog share a reviewed ARM64 image.
The deployment uses the existing Ohio table `indicatorlab-live-india` and writes
versioned snapshots under `s3://indicatorlab-data/raw/live/india/`. It references
the existing public VPC and subnets. Deploy only as `indicatorlab-india-live` in
`us-east-2` with the `Jamaal-IndicatorLab` profile and explicit activation approval.

The stack owns a separate ECS cluster. Joshua's `indicatorlab-reddit-weekly-failed`
rule filters on the shared `indicatorlab` cluster ARN, so India task failures do
not match that rule. The template derives the image URI and pull policy from this
project's dedicated `indicatorlab-india-live` ECR repository and the supplied
digest. Its write permissions cover only the India table and prefix. The stack
does not manage the shared bucket, table, VPC, repositories, or teammate workloads.

## Reviewed runtime input

Use the existing dated approval and SHA-256 checks. Stage flat, relative files in
`runtime/`: `india-live.json`, the reviewed NIFTY 100 roster CSV, and the reviewed
NSE session calendar. Set `"provider": "yahoo"` and `"poll_interval_seconds": 60`
in the runtime JSON. The calendar must explicitly cover each date in the review
window, including holidays and any special sessions. Yahoo needs neither a Dhan
instrument mapping nor Dhan credentials. `QuoteProvider=yahoo` is the stack
default. The collector rejects a mismatch between the stack and runtime provider.
See the [dated input validation](validation/dated_input_review.md) for the
November 24 roster and the continuous-session window through December 4, 2026.

The Yahoo adapter calls the existing Vibe `get_quote_summary(symbol, ["price"])`
loader. It uses the returned exchange timestamp and daily volume and converts the
explicit formatted percent into percentage points. A request is gated by the reviewed
market session. The loader requests one symbol at a time and retains its default
0.6-second spacing. The loop targets one sweep per minute without overlapping sweeps. The loader
reuses a session and caches cookies and the crumb, but provides neither a
multi-symbol quote call nor a quote cache. The shared throttle adds up to
0.4 seconds of jitter when a request has to wait. A warm sweep needs at least
59.4 seconds between its first and last request starts, before jitter and the
last response. With the two cold handshake requests the floor is 60.6 seconds.
Concurrent callers share that same gate. A compliant full-roster one-minute
deployment remains blocked pending an authorized bulk route or demonstrated
provider capacity. The three-stock holiday probe does not establish either.

The collector persists each group of 25 valid Yahoo quotes during the sweep.
The watchdog allows two polling intervals for Yahoo receipts and opening grace,
while the Dhan receipt check remains at 60 seconds. The ingestion alarm still
detects missing or late collector receipts after grace. Separately,
`MaxExchangeAgeSeconds` reports the age since the oldest actual exchange
timestamp across a complete roster, even if the receipts arrived recently.
It is absent during closures, opening grace, incomplete reads or invalid
timestamps. A high value can reflect delayed data or a stock that has not
traded recently. It does not trigger the ingestion alarm. Rate limiting and
access denial still stop further requests from that collector process.

For an optional Dhan deployment, use `provider=dhan` and `QuoteProvider=dhan`,
provide the reviewed instrument file, and set `DhanClientIdParameterName` and
`DhanAccessTokenParameterName` to Ohio SecureStrings under `/indicatorlab/india/`.
The template injects the two secrets and includes their read policy only in Dhan
mode. Supply `SecretKmsKeyArn` only if a customer-managed key is used. Dhan still
defaults to five seconds and requires explicit fallback authorization for 60 seconds.

## Build and validation

Use a dedicated build context with the existing Dockerfile, Dockerfile-specific
ignore file, requirements, the explicitly copied `src` files, and the reviewed
non-secret runtime files. Stage the pinned upstream Vibe loader, its two
dependencies, and upstream license into the context using:

```bash
bash infra/india_live/stage_vibe_loader.sh /path/to/vibe-Trading /path/to/context
docker buildx build --platform linux/arm64 --provenance=false --load \
  -f /path/to/context/infra/india_live/Dockerfile \
  -t india-live:reviewed /path/to/context
```

Use network-disabled synthetic inputs for startup validation. Run the collector
without `--run` to validate a reviewed configuration without creating AWS
clients or starting requests. The production ECS entry point supplies `--run`;
Lambda uses the image's watchdog handler. Never put secret values or operational
test credentials in the build context.

## Deployment and activation prerequisites

- With approval, create the dedicated Ohio ECR repository and push the reviewed
  image. Allow Lambda image retrieval and supply the resulting `ImageDigest`.
- Set `VpcId` to `vpc-0296a8f62662230d9` and select the verified public subnets
  `subnet-048c660a61c790a4a`, `subnet-080ce02880de051ae`, and
  `subnet-08eece60495cf9d2e`. Confirm the network inputs at deployment time.
- Review a CloudFormation change set for `indicatorlab-india-live` with
  `CAPABILITY_IAM`. Keep the default `SchedulesState=DISABLED` and desired count
  zero. Use an approved India SNS topic and confirmed subscriber for notifications.
- During an approved trading-session check, verify one writer, the seven-field
  schema, DynamoDB receipts, Parquet snapshots, James's reader, and alarm delivery.
  Resolve any measured cadence issue before enabling schedules. Confirm special
  session coverage outside the default 09:05–15:40 IST window.
- To stop after activation, disable all schedules and explicitly set desired count
  to zero. Verify the task has stopped before starting another writer.

At 30 scheduled days, 22 regular sessions, and 100 rows per successful minute,
budget approximately **$5–7/month before credits**. That includes about $3.29 in
Fargate and public IPv4, $0.62 for DynamoDB, and a usage allowance for ECR,
S3, Lambda, CloudWatch and notifications. The estimate assumes modest log and
snapshot volume and no NAT gateway. Confirm usage against the existing
`indicatorlab-monthly` budget. No Dhan subscription is required for Yahoo.

Previous local ARM64 and three-stock closure probe results remain in
`validation/`. The probe observed the prior-close exchange timestamps and
establishes access only. It does not establish production latency or open-session
coverage.
