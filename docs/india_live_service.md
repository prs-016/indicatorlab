# Local India live-data service

`src/live/india.py` implements the Week 3 pages 16–17 polling/storage core. It is
local code, not an activated feed or AWS deployment. It imports no broker SDK or
boto3, discovers no credentials, and starts no threads or network requests on import.
The historical acquisition/backtesting modules and existing data are unchanged.

## Components and configuration

- `load_nifty100_symbols(path)` reads exactly 100 unique EQ names from a separately
  reviewed local official-style constituent CSV and normalizes them to `.NS`.
  It does not download a roster or substitute the eight-stock research basket.
- `QuoteProvider` declares `name`, permitted `max_batch_size` and `fetch(symbols)`.
  Return one normalized quote or error per requested symbol; omission is an error.
  Provider adapters must enforce authorized usage/rate limits and bounded request
  timeouts. The offline `MockQuoteProvider` and explicitly constructed Dhan adapter are
  available; neither is activated automatically.
- `SessionCalendar.from_file(path)` reads a local JSON with `source`, timezone
  `Asia/Kolkata` and `sessions`. Each date maps to local opening/closing pairs,
  such as `[["09:15", "15:30"]]`; explicit closures use `[]`. Special sessions can
  use other times. Unknown dates stop polling. No weekday/holiday inference or
  calendar download occurs. Supply a reviewed current operational calendar before
  real use; the fixture calendar is intentionally synthetic.
- `IndiaLiveService` takes the roster, provider, calendar, latest store and snapshot
  store explicitly. Default interval is five seconds. A 60-second interval requires
  `fallback_authorized=True`; that flag records a caller decision, not provider
  permission. No active `config.yaml` changes were made.
- `step()` performs one gated cycle. `run(stop_event=..., max_cycles=...)` runs
  sequential cycles, avoiding overlap/catch-up bursts and supporting graceful stop.
  A slow provider cannot be promised five-second refreshes; measure it later.

## Quote and storage contracts

Provider rows contain `symbol`, `price`, `change_pct`, `volume`, `ts_exchange` and
`source`. The service validates them and stamps `ts_received` at batch receipt.
Output has exactly these seven fields, in the official order:

`symbol, price, change_pct, volume, ts_exchange, ts_received, source`

Timestamps are timezone-aware ISO 8601, normalized to UTC. Exchange time must come
from the provider; missing/naive/future exchange timestamps are rejected, never
replaced with receipt time. `change_pct` is percentage points (1.25 means 1.25%),
price is INR, volume is nonnegative integral shares fitting int64. Real adapters
must verify those units. Zero volume is retained. Old last-trade timestamps remain
visible; a successful request does not prove a fresh exchange trade.

`DynamoLatestStore(client)` requires an explicitly supplied low-level DynamoDB client
in `us-east-2`. It writes `indicatorlab-live-india` with symbol as the key, using
low-level DynamoDB number/string attributes and batches of at most 25. Only
unprocessed items are retried, with bounded exponential backoff.

`S3MinuteStore(client)` similarly requires an explicit regional S3 client. It writes
real PyArrow Parquet to:

`s3://indicatorlab-data/raw/live/india/date=YYYY-MM-DD/HHMM.parquet`

**Partitions use UTC receipt minutes.** Each snapshot contains the last successful
quote for each symbol observed during that minute; it does not carry earlier-minute
rows forward or create empty snapshots. Completed minutes flush on the next cycle,
including the closing tick. Graceful shutdown also flushes a partial minute.
Repeated upload attempts reuse the same serialized body/key.

The explicit bootstrap in `src/live/india_app.py` creates low-level boto3 clients
only under `--run`, using the standard AWS credential chain and bounded SDK
timeouts/retries. Boto3 is now declared in requirements.txt; it is not installed
in the inspected project .venv. Offline tests inject clients and require no AWS
SDK, credentials or access. No resource is created by the bootstrap.

## Failures and operational limits

Provider batches use bounded retries; bad/missing symbols do not kill other symbols
or subsequent batches. PermissionError blocks further provider access until restart.
Adapters must map authorization failures to that exception and must not silently
change sources. The session gate is rechecked before every retry/request.

Latest-store failures are logged; snapshots remain independently recoverable.
Snapshot failures retain the in-memory minute buffer and pause acquisition until
the snapshot is written. This bounds accumulation and makes storage gaps visible.
It is backpressure, not durable spooling. A crash can lose an unfinished minute;
use one writer instance, and review restart/idempotence requirements before deployment.
The DynamoDB adapter does not prevent an unrelated writer overwriting a newer quote.

Configure the application logger at INFO. Every cycle logs outcome, accepted count,
source and total cycle latency in the message; structured fields also include
calendar source and maximum exchange timestamp age. Individual failures log symbol
and exception type, never raw exception messages, tokens or provider responses.
No alarm, EventBridge schedule or production logging configuration is installed.

## Offline verification

With IndicatorLab's project environment:

```bash
.venv/bin/python -B -m pytest tests/test_live_india.py tests/test_config.py -v -p no:cacheprovider
```

Fixtures in `tests/fixtures/live_india/` are explicitly **synthetic**, including the
holiday/special-session calendar. Tests deny socket/DNS access and use fake AWS
clients. They exercise the full 100-name path, DynamoDB batch/retry behavior, actual
Parquet decoding, cadence, holiday/close/unknown-date gates, symbol isolation,
snapshot backpressure, timestamp/number validation and graceful stopping.
PyArrow was already declared in requirements.txt; its missing installation was
completed in `.venv` for these tests. No broker or AWS credentials are needed.

## Remaining Week 3 work

Choose and authorize a real provider; measure three-ticker delay/rate feasibility
during NSE hours; supply reviewed current roster/security-ID/calendar files and
their review record. The bootstrap is implemented and fixture-tested; authorized
live validation and deployment remain outstanding. Coordinate with Joshua for AWS resources,
SSM/IAM/budget and with James for `/live/india`. The inactive image, IST schedules and independent ingestion alarm
are now defined in `infra/india_live/`. Complete template/image validation and
deploy only with approval; verify DynamoDB, minute S3 output and the deployed API. Share the service layout with
Jack without changing his HK implementation. These steps are not claimed complete.

Operational/live data is separate from research. This module neither loads the
unapproved historical snapshot nor relaxes any research holdout restriction.


## Dhan adapter: authorized activation only

`src/live/dhan.py::DhanQuoteProvider` uses the existing `requests` dependency,
not a broker SDK or imports from Vibe-Trading. It implements `QuoteProvider` with
one bulk `POST https://api.dhan.co/v2/marketfeed/quote` for 1–100 configured stocks.
No requests, account discovery or credential reads occur on import. Construction
reads credentials but performs no network I/O; only `fetch` makes a request.

Prerequisites: an authorized Dhan account with active Data API entitlement,
valid `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` environment variables, a reviewed
current NSE_EQ security-ID mapping, and the service's reviewed operational
calendar. Supply secrets through your authorized local environment/secret manager;
do not put them in JSON mappings, logs, Git, shell command history or reports.
No credential refresh, subscription purchase or instrument-master download is
performed. The entitlement and any storage/team-display rights need confirmation
before live use. Account access alone is not proof of Data API entitlement.

A local mapping JSON should have this shape (IDs below are placeholders, not
verified Dhan identifiers; replace them before use):

```json
{
  "RELIANCE.NS": {"security_id": "<verified numeric ID>", "exchange_segment": "NSE_EQ"},
  "TCS.NS": {"security_id": "<verified numeric ID>", "exchange_segment": "NSE_EQ"},
  "INFY.NS": {"security_id": "<verified numeric ID>", "exchange_segment": "NSE_EQ"}
}
```

Inject the adapter into the existing service setup:

```python
import json
from pathlib import Path
from src.live.dhan import DhanQuoteProvider

instruments = json.loads(Path("/path/to/reviewed-dhan-instruments.json").read_text())
provider = DhanQuoteProvider.from_env(instruments, timeout_seconds=5.0)
# Pass provider to IndiaLiveService with the reviewed roster/calendar and
# explicitly supplied stores. Only an authorized service.step()/run() polls.
```

Use one provider instance and one worker per account; other applications sharing
that account consume the same quota. The adapter enforces at least one second
between request starts, including failures, matching Dhan's market-quote limit.
It never sleeps inside `fetch`: cooldown raises a retryable `DhanRateLimitError`,
so the existing service rechecks sessions before retries. HTTP 429 and documented
805/DH-904 errors honor a valid Retry-After (seconds or HTTP date), with a minimum
one-second delay. The service bounds retry attempts; a longer cooldown can leave
a cycle without quotes, and the next cycle tries again without filling gaps.
Five seconds remains the polling default; no automatic 60-second fallback is added.

HTTP 401/403 and documented authentication/entitlement errors permanently deny
further requests from that instance and raise `PermissionError`, which also blocks
the service until restart. Fix authorization before constructing a new instance.
Transport/5xx errors are retryable; malformed/rejected payloads are not retried in
the same cycle. Raw error messages, response bodies and credentials are never
included in adapter errors. Environment proxies/.netrc and redirects are disabled;
TLS verification stays enabled. Requests have a finite timeout, not a guaranteed
end-to-end latency deadline. No fallback quote provider is selected.

Dhan fields are normalized as follows:

- `last_price`: positive INR price; `volume`: nonnegative integral daily shares.
- `net_change`: absolute change from previous close, not percent. Percentage
  points are `100 * net_change / (last_price - net_change)`; a nonpositive or
  invalid implied previous close is rejected. OHLC close is not silently assumed
  to be the previous close.
- `last_trade_time`: explicit exchange-local `DD/MM/YYYY HH:MM:SS`, interpreted
  as Asia/Kolkata and converted to UTC. Missing/malformed/future dates and the
  documented 1980 sentinel are rejected; older real last-trade times remain
  visible. Timestamp format/timezone must still be confirmed on authorized live
  payloads; receipt time never replaces exchange time.
- The adapter returns the exact seven-field schema using receipt time after the
  response. The service validates it again and stamps batch `ts_received` itself.
  Missing/invalid individual quotes become sanitized per-symbol errors; valid
  peers survive. Unexpected exchanges or unrequested security IDs reject the batch.

Offline representative fixtures are **synthetic API-shaped responses**, not
recorded live quotes or validated security IDs. Tests cover 100-name batching,
normalization, partial data, auth denial, cooldowns, redirects, sanitized errors
and service integration, with sockets/DNS forbidden:

```bash
.venv/bin/python -B -m pytest tests/test_live_dhan.py tests/test_live_india.py tests/test_config.py -q -p no:cacheprovider
```

Contract references: [Dhan market quotes](https://dhanhq.co/docs/v2/market-quote/),
[error codes](https://dhanhq.co/docs/v2/annexure/), and
[Data API entitlement](https://dhan.co/support/platforms/dhanhq-api/is-a-data-api-subscription-required/).
No live three-stock/ten-minute test, measured delay, full roster-ID certification,
AWS wiring or deployment is claimed. Operational quotes remain separate from
historical research and do not change holdout rules.


## Executable India bootstrap (inactive until explicitly run)

For the Ohio deployment, set `"provider": "yahoo"` and
`"poll_interval_seconds": 60` in the reviewed runtime JSON. The Yahoo path uses
the existing Vibe Yahoo quoteSummary loader and requires the reviewed roster
and calendar only. The instrument mapping and Dhan credentials described below
apply to the optional Dhan configuration. See the
[Ohio deployment instructions](../infra/india_live/README.md) for packaging,
isolation, and open-session cadence verification.

`python -m src.live.india_app` validates local inputs and environment credentials
only. `--run` additionally creates clients for existing DynamoDB/S3 resources
and enters the service loop. This task did not execute either against live data
or AWS. No shared template is copied, imported, deployed or reprovisioned.

The bootstrap follows the explicit AWS activation/graceful-stop pattern inspected
on `origin/Jack:src/hk/live.py`, and the shared resource contract on
`origin/reddit:infra/shared/template.yaml`. It does not copy or modify HK code.
The fixed resource targets are `us-east-2`, table `indicatorlab-live-india` and
bucket `indicatorlab-data`. Confirm these with Joshua before activation; a different
actual bucket name needs a separately reviewed configuration change.

Prepare three local operational files:

1. Official-style NIFTY 100 CSV (`Symbol,Series`), exactly 100 unique EQ rows.
2. Dhan instrument JSON described above, with exactly the same 100 `.NS` names,
   unique valid numeric security IDs and `NSE_EQ`. Review against an authorized
   current instrument master; synthetic test IDs are never operational evidence.
3. Existing session-calendar JSON schema, with a source and explicit session or
   closure entries for **every day** in the proposed operational review window.

Bind them in a local runtime JSON. All paths are relative to this JSON's directory;
absolute paths and `..` references are rejected. This illustrative document is
intentionally unapproved and uses invalid checksum placeholders:

```json
{
  "review": {
    "approved": false,
    "reviewed_by": "<responsible reviewer>",
    "reviewed_at": "<timezone-aware actual review timestamp>",
    "source": "<instrument identity, roster and NSE calendar verification evidence>",
    "valid_from": "<YYYY-MM-DD>",
    "valid_until": "<YYYY-MM-DD>"
  },
  "roster": {"path": "nifty100.csv", "sha256": "<actual file SHA-256>"},
  "instruments": {"path": "dhan-instruments.json", "sha256": "<actual file SHA-256>"},
  "calendar": {"path": "nse-calendar.json", "sha256": "<actual file SHA-256>"},
  "poll_interval_seconds": 5,
  "fallback_authorized": false
}
```

A responsible reviewer must verify all three inputs before marking the review
approved and recording real evidence/dates/hashes. The record is an **operator
attestation**, not cryptographic proof of external approval or confirmation that
Dhan accepts the IDs. Hashes detect changed files; they do not establish factual
identity or entitlement. Review expiry stops acquisition, including after midnight.
Unknown calendar dates also fail closed. Explicit closures validate but do not poll.

Configure `INDIA_LIVE_CONFIG` with the local runtime JSON path and inject
`DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN`. ECS task-definition `Secrets` can map
SSM SecureString parameter ARNs into these environment variables. The bootstrap
neither fetches secrets itself nor discovers/creates parameters. The task execution
role needs the corresponding secret-read permissions (and key decrypt permissions
if applicable); use an ECS **task role** for DynamoDB/S3 access. No explicit AWS
access keys belong in runtime JSON, images, documentation or source code.

Commands for a later authorized operator, not executed as live validation here:

```bash
# Validate only, after installing declared requirements in the target runtime:
.venv/bin/python -B -m src.live.india_app
# Only with separate live/AWS authorization:
.venv/bin/python -B -m src.live.india_app --run
```

The bootstrap constructs Dhan only after local validation, and AWS clients only
after that. It cannot prove credential validity, table existence, bucket ownership,
IAM permissions or broker entitlements offline. Missing Boto3 prevents AWS startup.
AWS SDK credentials use the normal chain, including ECS task-role credentials.
SDK settings: 3-second connect timeout, 5-second read timeout and at most three
standard-mode attempts. SIGTERM/SIGINT request a stop; the existing service flushes
its pending minute on exit. Existing sink failures are logged under the service's
retry/backpressure behavior; the bootstrap adds no durable queue or health monitor.
Startup errors log exception types only, not file contents, paths or secret values.

Focused offline verification:

```bash
.venv/bin/python -B -m pytest tests/test_live_india_app.py tests/test_live_dhan.py tests/test_live_india.py tests/test_config.py -q -p no:cacheprovider
```

Deployment definitions are now prepared in [infra/india_live](../infra/india_live/README.md):
image/task/service, scoped roles, secret injection, IST schedules and independent
receipt monitoring. Remaining work is full template/image validation, authorized
secret provisioning, confirmed cluster/network/shared resources, approved special-
session schedule overrides, SNS delivery verification, provider authorization/live
test and James's endpoint integration. No infrastructure deployment or resource
discovery occurs as part of validation.
