# Code Review — IndicatorLab India live Ohio and Yahoo correction

Reviewed November 23, 2026 Pacific
Files reviewed: 13 changed implementation, infrastructure, documentation, and test files

## Summary

The correction follows the DS3 project structure and keeps operational inputs
out of version control. The Ohio template scopes the collector writes to India,
uses a separate ECS cluster, and disables schedules by default. The Yahoo
bootstrap no longer requires Dhan credentials. Offline results support
publication of the correction. Full-roster cadence requires an open-session check.

## Repo Structure

- Present: README, requirements, src, tests, notebooks and infrastructure.
- Scope: India live service, its deployment configuration, focused tests and
  operating documentation. The existing Dhan adapter and frozen research remain
  outside the diff.

## Test Coverage

200 focused tests passed. The suite exercises review gates, Roster/Calendar
validation, Yahoo quote conversion and access errors, Dhan compatibility,
the India writes and Parquet snapshots, the watchdog, and template boundaries.
Black, Ruff, Ohio cfn-lint and shell syntax checks passed.
The ARM64 container imported both handlers and validated a synthetic Yahoo
configuration with networking disabled and no Dhan credentials. A closed-day
collector step also completed in the network-disabled container.
No coverage percentage was collected.

## Findings

### `src/live/yahoo.py` (lines 8–12)

**Issue:** Cadence verification
**Severity:** Should fix before activation

```python
    name = "yahoo"
    max_batch_size = 1
```

The pinned Vibe loader starts requests at least 0.6 seconds apart. A 100-name
sweep consumes nearly the entire minute even before network overhead. Slow
sweeps can trip the existing strict receipt watchdog. Measure the sweep and
receipt ages before enabling the production schedules.

## Checklist for the student

- [ ] Run the approved Ohio Yahoo open-session probe and verify full-roster
  readiness and watchdog behavior before enabling schedules.
- [ ] Review the disabled Ohio change set and image digest with the team.

---

## Previous review record

# Code Review — India live service and inactive deployment infrastructure

Reviewed: 2026-11-23
Files reviewed: 19 contribution files, plus this review record
Base: origin/main at 13c58bcf28f9eb995b223499fc8549dfc6ca2a3e

## Summary

Ready for publication as an offline-tested, inactive implementation. The reviewed
collector, Dhan adapter, bootstrap and watchdog are reused without changes to
their behavior. No AWS resources were created, provider calls made, historical
data acquired or collection activated. This review does not approve deployment.

The contribution preserves the current shared infrastructure, existing boto3
dependency and global holdout_start of 2026-11-01. It changes no historical
strategy, historical cutoff, AGENTS.md or another contributor's implementation.

## Repo Structure

- Reusable service code is under src/live/.
- Four focused test modules and three explicitly synthetic fixtures are under tests/.
- India-specific deployment files are under infra/india_live/; the shared infra
  README is extended, not replaced.
- Setup, provider entitlement, secret injection, operational inputs, validation,
  costs and rollback are documented in docs/india_live_service.md and the India
  infrastructure README.
- Runtime instrument/calendar files, credentials and generated datasets are not
  included. No shared table, bucket or ECS cluster is recreated by this template.

## Test Coverage

192 focused tests passed in 1.39 seconds on the updated upstream base:

```bash
python -B -m pytest -q -p no:cacheprovider \
  tests/test_live_india.py tests/test_live_dhan.py \
  tests/test_live_india_app.py tests/test_india_live_infra.py tests/test_config.py
```

Tests exercise quote normalization and timestamps, five-second polling and the
explicitly authorized fallback, retries, batch limits, per-symbol isolation,
minute Parquet snapshots, session/closure gating, credential redaction, reviewed
input validation, original AWS sink contracts, watchdog freshness and disabled
infrastructure defaults. Networking is denied during the focused test run.
These are synthetic/offline tests, not live-provider or deployment evidence.

Ruff passes on the five service modules and four new test modules. All nine
Python files pass Black. Offline cfn-lint validation for us-west-2 passes.
No coverage percentage is claimed; no coverage dependency was installed.
A clean detached checkout of implementation commit
75146045148e7e8b4f50c1fecae42adccfd814a9 passed all 192 focused tests in 1.22
seconds. Offline cfn-lint also passed again there, and the checkout stayed clean.
The final review-record update changes no tested service, test or template bytes.

## Findings

### infra/india_live/README.md — Offline validation and limits

**Issue:** Stale validation documentation.
**Severity:** Should fix — resolved.

The previous statement that cfn-lint was unavailable has been replaced with the
actual successful offline schema-validation command. Container and operational
validation remain separate prerequisites; publication does not claim deployment.

### Deployment readiness — source and template are intentionally inactive

**Issue:** External operational inputs and authorization are not provisioned here.
**Severity:** Informational — not a publication blocker.

Existing AWS resource ownership, Dhan entitlement, verified security IDs, reviewed
calendar/roster hashes, SSM parameters, image digest and notification routing must
be established before enabling acquisition. Test fixtures are not operational
inputs. Schedule and desired-count defaults keep the service disabled.

### Security and publication scope

No hardcoded real credentials were found in the contribution. Provider secrets
come from environment/SSM injection; runtime errors are sanitized. IAM task and
execution roles have separate scoped responsibilities, and the watchdog receives
no Dhan secrets. Private runtime files and historical data are excluded.

No outstanding Must fix code finding remains for this publication scope.
No unrelated repository cleanup was performed.

## Checklist for the student

- [x] Preserve upstream config, requirements and shared-resource definitions.
- [x] Keep historical studies, AGENTS.md and unrelated working changes out.
- [x] Run focused offline tests, Ruff, Black and CloudFormation validation.
- [x] Correct the obsolete cfn-lint documentation.
- [x] Complete the post-commit clean-checkout regression gate before push.
- [ ] Obtain separate authorization and operational evidence before deployment.

## Additional operational verification — 2026-11-23 Pacific

The existing ARM64 image now builds and passes network-disabled dependency,
entrypoint and inactive-default validation. Offline cfn-lint passes again. No
service/test/template source changed, so the prior 192-test clean-checkout result
remains applicable; these documentation/evidence additions do not claim a rerun.
Public S3 response metadata confirms us-east-2, while the guide/template remain
us-west-2. Authentication and region alignment block deployment; no resources
were created. The bounded Yahoo source check ran on an official NSE holiday,
so open-session freshness and operational acceptance remain unverified.
