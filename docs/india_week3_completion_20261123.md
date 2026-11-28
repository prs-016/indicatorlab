# Week 3 India acceptance — 2026-11-23 Pacific

Completed issue [2351](https://github.com/HKUDS/Vibe-Trading/issues/2351) remains unchanged.
NIFTY [PR 2352](https://github.com/HKUDS/Vibe-Trading/pull/2352) is open at ab847ef4;
CI and Desktop Windows require upstream approval, with no jobs executed.

Published team-review deliverables:

- Reddit [PR 5](https://github.com/prs-016/indicatorlab/pull/5): qualifying sources,
  100-company matching and market propagation; 174 tests pass from committed checkout.
- Wikipedia [PR 6](https://github.com/prs-016/indicatorlab/pull/6): adapter and all
  100 dispositions; 88 English/67 Hindi/12 historical mappings preserved, 12 English
  and 33 Hindi gaps explicit; 16 clean-checkout tests pass. No James pipeline changes.
- Live [PR 7](https://github.com/prs-016/indicatorlab/pull/7): completed service/IaC,
  previous 192-test verification, successful ARM64 build/network-disabled runtime
  checks and fresh offline cfn-lint. Runtime configuration remains unapproved;
  no AWS deployment or live collection was activated.
- [Research package](../india_research/submission/week3_complex_v1_2_20261123/README.md):
  unchanged runtime modules/frozen rules, actual US metrics and ablations, all
  1,200 completed null metrics, 1,653 current trial records including failures,
  checksums, input provenance and exact seven-column Strategy Log import.
  Independent committed checkout: 171 passed, one private-input join skipped.

## Operational blockers

Unauthenticated HeadBucket returned HTTP 403 and region us-east-2 for
indicatorlab-data, corroborating Joshua's report but not verifying ownership/IAM.
The guide/service/template specify us-west-2. Joshua/Prakhar must confirm account
and intended region before alignment/deployment; do not duplicate or migrate
shared resources. No AWS credentials/profile were configured in WSL, local .env
or the checked Windows/WSL AWS locations. Regional DynamoDB, ECS/ECR, SSM, IAM,
Scheduler, budget and alarms could not be authenticated or operationally tested.
Dhan also needs authorized credentials/entitlement and reviewed IDs/calendar.

The authorized one-minute Yahoo/Vibe probe returned 33 responses over 11 polls.
November 24, 2026 is an [official NSE holiday](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf),
so unchanged previous-session quotes establish availability only, not successful
open-session latency or provider failure. The open-session source test, actual
DynamoDB/S3 delivery, alarms and James's /live/india verification remain pending.
Docker Desktop was started for the successful local ARM64 validation; no cloud
resources, image registry pushes or deployment costs were incurred by this task.

## Strategies and registration

WATM: 202/119 entries; Sharpe 1.817279/.368955; null percentiles 98.5%/33.5%; DROP.
WVB: 15/15 entries; Sharpe .369312/-.159678; INSUFFICIENT TRADES.
WCR: 3/5 entries; Sharpe -.565819/1.178539; INSUFFICIENT TRADES.
All have IC, benchmark/cost/ablation outputs and 200 completed nulls per split.
DSR is N/A: global prior-trial/dependence evidence is incomplete, not invented.

India remains NOT EVALUATED: 0/1,496 recovered 2025 rows accepted. Eight March 18
rows have zero volume; original retrieval, adjustment, volume, session and timing
criteria are unmet. Required stock/benchmark extension: 2025-01-01..2025-09-30;
reference-gap dates and prior special-session candidates are included in the
package. No quarantined prices were promoted or exhausted providers retried.

WATM's prior registration was user-confirmed, but exact sheet timestamp is unknown.
WVB/WCR ran under explicit execution waivers and are not claimed registered.
No official sheet URL/authenticated interface or connected document session was
available. Import-ready rows preserve real outcomes and do not backdate entries.

## PR 1303 summary prepared for team posting

PR 1303 attempted a NIFTY 50 Alpha Zoo universe plus process-pool robustness.
It closed; retained evidence does not establish a definitive reason, so none is
invented. Our NIFTY 100 PR uses current shared India loading, explicit fallback/
provenance, sector/VWAP disclosures and offline routing tests, with the broader
design separated into Issue 2351. Chat posting remains unverified; no private
conversation or handoff document was accessed.

## Final-week readiness

NO: code/research delivery has advanced, but operational and external acceptance
remains incomplete. Required actions are upstream workflow approval, team AWS
account/region/access and reviewed provider inputs, an open NSE-session test,
validated India historical inputs and actual shared-sheet delivery. Frozen
thresholds need no retroactive changes merely to preserve honest failed outcomes.
No unrelated final-week implementation or main merge was undertaken.
