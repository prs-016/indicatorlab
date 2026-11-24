# India live deployment — prepared, not deployed

This CloudFormation template reuses the shared infrastructure documented on
Joshua's `origin/reddit` (`infra/shared/`, `infra/reddit/`) and the independent
watchdog/start-stop pattern on Jack's `origin/Jack` (`infra/hk_live/`). No HK files
or tables are copied. Existing India collector, Dhan adapter and bootstrap are
unchanged. No AWS calls, images, secrets or resources were created by this work.

## Resources and defaults

- **References only:** existing ECS cluster `indicatorlab`, DynamoDB table
  `indicatorlab-live-india` and S3 bucket `indicatorlab-data` in `us-west-2`.
  Confirm existence/ownership with Joshua; local templates do not prove deployment.
  If shared names differ, stop: the current bootstrap also targets these names.
- **Creates on a future approved deployment:** a 0.25-vCPU/1-GB ARM64 Fargate task
  and service, outbound HTTPS security group, four scoped IAM roles, two log groups
  (14-day retention), two Scheduler schedules, Lambda watchdog/minute timer and alarm.
  No bucket, table, cluster, VPC, subnet, NAT gateway, SSM parameter or SNS topic
  is created. No public inbound endpoint or load balancer is required.
- **Inactive by default:** service desired count is zero; `SchedulesState=DISABLED`
  disables both collector schedules, watchdog timer and alarm actions. No dummy
  credentials, fabricated prices or mock-provider production option exist.
- **Schedule:** daily 09:05–15:40 **Asia/Kolkata**, covering regular NSE hours with
  startup/shutdown margin. Weekends are included so daytime special sessions are
  not automatically missed; the reviewed NSE calendar prevents holiday polling.
  Closed-day compute still incurs cost within that window. Evening/Muhurat or
  sessions outside this window require preapproved adjusted schedules or dated
  start/stop operations. The template does not discover special sessions.
- **Single writer:** rolling deployment percentages 0/100 favor replacement gaps
  over overlapping scheduled writers. Do not run a second local/manual collector
  against these targets. ECS is not a distributed lock/exactly-once guarantee.
- **Secrets:** inject existing SSM SecureString ARNs as `DHAN_CLIENT_ID` and
  `DHAN_ACCESS_TOKEN`; never pass their values in template parameters. Only the
  execution role reads those two parameters. An optional customer-managed KMS key
  allows decryption through SSM. Task role only writes the India table/prefix.
  Execution image-pull rights are scoped to the supplied ECR repository ARN;
  authorization-token retrieval necessarily uses `Resource: '*'`.

## Independent receipt watchdog

The same digest-pinned image runs `src.live.india_watchdog.handler` in Lambda,
with **no Dhan credentials**. Every minute it reads the reviewed roster/calendar
and up to 100 DynamoDB receipt timestamps with `BatchGetItem`. All reviewed names
must have timezone-aware, non-future receipts aged **at most 60 seconds**. Missing
rows, unprocessed keys, expired review, unknown calendar dates or malformed inputs
publish unhealthy. Declared closures publish healthy without table reads; the first
60 seconds of each declared session is an acquisition grace period.

The `IndicatorLab/India` metric `IngestionHealthy` (dimension
`Service=indicatorlab-live-india`) alarms on a value below one in one 60-second
period. Missing watchdog metrics also breach; the collector cannot suppress an
alarm by crashing. Minute sampling and CloudWatch evaluation mean notification is
**not guaranteed exactly at second 61**. This checks receipt freshness, not last
exchange-trade freshness or successful S3 delivery. Inspect minute objects and
collector storage-error logs separately. With an authorized 60-second polling
fallback, jitter can cause strict 60-second alerts; do not silently relax the limit.

## Preconditions before deployment

1. User/PM approval, Joshua's AWS account/resource/access confirmation, budget and
   service ownership. Existing public subnets need an Internet Gateway route, DNS
   and appropriate network ACLs. Collector gets a billed public IPv4 address;
   HTTPS egress is not restricted to specific hostnames. No private credentials
   or network configuration are discovered by this template.
2. Authorized Dhan Data API entitlement, valid token and verified current NSE_EQ
   security IDs. Confirm any provider geographic/IP/storage/display restrictions.
   Complete the separately authorized three-stock live test; offline tests are
   not broker validation.
3. Reviewed non-secret runtime files under `runtime/`, including
   `india-live.json`, roster CSV, instruments JSON and session calendar. Follow
   [bootstrap configuration](../../docs/india_live_service.md#executable-india-bootstrap-inactive-until-explicitly-run).
   Use flat relative filenames for this Docker build context. The approved,
   dated review binds actual file hashes; test fixtures are not operational inputs.
   Update the image and both workloads before review expiry or index changes.
4. Existing ECR repository and ARM64 image-build tooling; image digest and matching
   repository ARN. Ensure the repository permits Lambda image retrieval (including
   cross-account policy if applicable). No registry is provisioned here.
5. Existing Dhan SecureStrings and optional KMS key with appropriate key policy.
   The collector execution role needs access; no secrets are baked into images.
   Rotating SSM values does **not** update running tasks: replace/restart the
   collector after rotation. The watchdog never needs these secrets.
6. Existing SNS topic ARN and confirmed recipient subscription for notifications;
   topic/key policies must permit CloudWatch alarm delivery. An empty ARN creates
   an alarm with **no notification action**. Do not call that operational alerting.

## Build and deployment procedure — instructions only

Never send the entire working tree or private runtime files to an unreviewed
build service. Assemble a temporary context containing only the Dockerfile,
Dockerfile-specific ignore file, deployment requirements, the explicitly listed
`src` files from Dockerfile, and reviewed **non-secret** `runtime/*.json,*.csv`.
Preserve directory paths. Inspect the context before building; exclude `.env`,
credentials, snapshots, notebooks and test fixtures. Docker's sibling
`Dockerfile.dockerignore` is deny-by-default as a second boundary.

After authorization and with placeholders replaced:

```bash
# Build locally; do not run a collector merely to build its image.
docker buildx build --platform linux/arm64 --provenance=false --load \
  -f /path/to/context/infra/india_live/Dockerfile \
  -t india-live:reviewed /path/to/context
# Review image contents, record base/dependency versions, then use the team's
# authorized ECR login/tag/push workflow. Obtain the resulting image digest.
```

Prepare a CloudFormation parameter file containing `ImageUri` (ECR digest URI),
`ImageRepositoryArn`, `ClusterName`, `VpcId`, `PublicSubnets` (comma-separated),
`DhanClientIdParameterArn`, `DhanAccessTokenParameterArn`, optional `SecretKmsKeyArn`,
`AlertTopicArn` and `SchedulesState=DISABLED`. These are identifiers, not secrets.
Do not create replacement shared resources when an identifier is missing.

```bash
# These commands contact AWS: only a separately authorized operator runs them.
aws cloudformation deploy --region us-west-2 \
  --stack-name indicatorlab-india-live \
  --template-file infra/india_live/template.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides file:///path/to/approved-parameters.json
```

Inspect the change set/outputs before enabling. Once permissions, runtime inputs,
secret injection and notification routing are validated, explicitly update
`SchedulesState=ENABLED`. Enabling schedules during a trading day does not itself
start a task until the next start trigger; an approved manual desired-count change
may be needed. Creating the disabled stack still creates billable supporting
resources and is **not authorized by this implementation task**.

## Verification, costs and rollback

- Validate the built image offline, then prove in an authorized NSE session:
  exactly one task, 100 expected table keys updating around five seconds,
  seven-field schema, timezone/receipt semantics, actual Parquet minute keys,
  closures suppressing polls and James's `/live/india` reader compatibility.
- Exercise the independent alarm with an approved collector stop; confirm recovery,
  opening/closure suppression, unknown-date failure and actual SNS delivery.
  Check SSM/KMS failures do not print secrets. Capture logs and deployment outputs.
- Budget compute as 0.25 vCPU + 1 GB for each scheduled hour/day, plus public IPv4,
  ECR storage, DynamoDB writes, S3 puts, logs, Lambda/minute table reads, metrics,
  alarms, Scheduler and any provider subscription. Watchdog runs all day when
  enabled. Do not assume free-tier eligibility or quote an unverified monthly price.
  Coordinate with Joshua's existing `indicatorlab-monthly` budget; no duplicate
  budget is created. [Fargate pricing](https://aws.amazon.com/fargate/pricing/).
- **Stop:** disable both start/stop schedules and the watchdog timer (update
  `SchedulesState=DISABLED`), explicitly set service desired count to zero and
  verify no task remains. Disabling schedules alone does not stop a running task.
  Keep the existing bucket/table, secrets and team cluster intact.
- **Rollback image:** keep schedules disabled, select a prior reviewed digest and
  still-valid runtime review, update the stack, then reactivate only with approval.
  Preserve logs/evidence. Deleting this stack does not delete the shared storage
  because it never owns it; do not delete shared resources as a rollback.

## Offline validation and limits

```bash
.venv/bin/python -B -m pytest tests/test_india_live_infra.py tests/test_live_india_app.py tests/test_live_dhan.py tests/test_live_india.py tests/test_config.py -q -p no:cacheprovider
```

Tests parse CloudFormation intrinsics, check resource/reference/IAM/schedule/image
contracts, and exercise watchdog closures, special sessions, 60-second boundaries,
partial reads and failures without sockets. These tests do not prove deployment.

Offline CloudFormation schema validation with
`cfn-lint -t infra/india_live/template.yaml -r us-west-2` passes. Container image
build/runtime validation and authorized live-provider/AWS verification remain
separate deployment prerequisites. No image build is repeated by this publication
step, and no AWS `validate-template` or deployment command was called.

Upstream pattern references: [ECS service](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html),
[Lambda Python images](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html).
