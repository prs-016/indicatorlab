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
The same focused suite is a required post-commit check in a clean detached
checkout before this branch is pushed; the publication handoff records its result.

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
- [ ] Complete the post-commit clean-checkout regression gate before push.
- [ ] Obtain separate authorization and operational evidence before deployment.
