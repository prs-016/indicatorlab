# Infrastructure (AWS, us-west-2)

Everything the team runs on AWS is defined here, so a clean checkout plus two commands brings it all up.
The account is currently Joshua's (free plan); the same templates deploy unchanged into the DS3 account
later (see [Moving to the DS3 account](#moving-to-the-ds3-account)).

## Shared resources (`infra/shared/`)

| Resource | Name | Used by |
|---|---|---|
| S3 bucket (versioned, private, SSE) | `indicatorlab-data` | everyone: `raw/`, `processed/`, `backtests/` |
| DynamoDB table (key `symbol`, on-demand) | `indicatorlab-live-india` | Jamal writes (live_india), James reads (`/live/india`) |
| DynamoDB table (key `symbol`, on-demand) | `indicatorlab-live-hk` | Jack writes (live_hk), James reads (`/live/hk`) |
| SSM SecureStrings | `/indicatorlab/vibe_api_key`, `anthropic_api_key`, `reddit_*` | James's API (Vibe key), Reddit/LLM jobs |
| AWS Budget | `indicatorlab-monthly`, $20, email at 80% and 100% | everyone: post in the chat if it fires |
| IAM group | `indicatorlab-team` | Jamal, Jack, James log in as IAM users in this group |

The team group has PowerUserAccess plus permission to create IAM roles named `indicatorlab-*`, so each person
can `sam deploy` their own service. It cannot delete the bucket or the live tables, change bucket privacy, or
touch billing and account settings.

### S3 layout

```
raw/live/<market>/date=YYYY-MM-DD/HHMM.parquet     live snapshots (Jamal: india, Jack: hk)
raw/reddit/date=YYYY-MM-DD/HHMM.parquet            hourly Reddit posts (Joshua)
raw/reddit/_state.json                             hourly high-water marks
raw/reddit/arctic_shift/, raw/reddit/manifest.csv  complete-day archive the weekly job rebuilds from
raw/wikipedia/                                     James
processed/reddit_weekly.parquet                    research weeks only (before 2025-10-01)
processed/reddit_weekly_by_type.parquet            same, split investor / product subreddits
processed/reddit_top_posts.parquet                 top posts per ticker-week
processed/*_recent.parquet                         weeks from 2025-10-01 on (display only, e.g. baselines)
processed/reddit_current.parquet                   in-progress week + trailing 7 days ("Hot right now")
processed/reddit_hourly/date=.../                  scored hourly rows
processed/reddit_state/                            weekly job's corpus state (posts, matches, scores)
processed/sentiment_cache/                         FinBERT scores keyed by (post_id, ticker, model_version)
processed/wiki_*.parquet                           James
backtests/
```

Live quote item (both tables, one per symbol, overwritten each poll): `symbol` (e.g. `RELIANCE.NS`,
`0700.HK`), `price`, `change_pct`, `volume`, `ts_exchange` (ISO 8601, exchange time), `ts_received`
(ISO 8601 UTC), `source` (e.g. `tencent`).

## Dashboard hosting (`infra/dashboard/`)

The Week 1 Reddit dashboard, published as a static snapshot. `src/reddit/dashboard_export.py`
writes every endpoint the page reads as JSON. The files go to a private S3 bucket served over
HTTPS by CloudFront (origin access control).

- **Publish or refresh:** `infra/dashboard/deploy.sh`. It exports, deploys the stack, syncs the
  files and invalidates the cache, then prints the URL.
- **Not on AWS:** the Rebuild and Run-strategies buttons only work on a laptop
  (`python -m src.reddit.dashboard_server`).
- **Sentiment:** added after the FinBERT rescore. James's Dashboard v1 later replaces this page.

## Reddit pipeline (`infra/reddit/`)

One arm64 image (`infra/reddit/Dockerfile`, FinBERT baked in) runs both jobs from `src/reddit/pipeline.py`:

| Job | Runs on | Schedule (EventBridge Scheduler) | Writes |
|---|---|---|---|
| hourly | container Lambda `indicatorlab-reddit-hourly` (3 GB, 15 min) | every hour | `raw/reddit/date=…`, `processed/reddit_current.parquet` |
| weekly | Fargate task `indicatorlab-reddit-weekly` (2 vCPU, 16 GB, 40 GB disk) | Mondays 08:00 UTC | `processed/reddit_weekly*.parquet`, `reddit_top_posts*.parquet` |

Alarms email `AlertEmail` (confirm the SNS subscription email first): the hourly run errors, two hours in a
row with zero posts (or no run), no successful weekly run in 7 days, and a weekly task that exits non-zero.

## Deploy, in order (Joshua)

Prerequisites: `brew install awscli aws-sam-cli colima docker docker-buildx`, then `colima start`.

1. **Stop using the root user.**
   - In the console, create an IAM user for yourself with `AdministratorAccess`.
   - On that user's page, choose **Create access key → Command Line Interface (CLI)**.
   - Run `aws configure`: paste the key yourself, region `us-west-2`, output `json`.
   - `aws sts get-caller-identity` must end in `user/<you>`, not `root`.
2. **Shared stack:** `infra/shared/deploy.sh you@example.com`. If the bucket name is taken, pass a second
   argument (e.g. `indicatorlab-data-ucsd`) and tell the team; code reads it from `INDICATORLAB_BUCKET`.
3. **Secrets:** fill `.env` (from `.env.example`), then `infra/scripts/put_secrets.sh`. Empty values are
   skipped, so rerun it when a key (e.g. the Vibe-Trading key) arrives.
4. **Teammates:** `infra/scripts/create_team_users.sh`.
   - It creates `jamal`, `jack` and `james` in `indicatorlab-team` with one-time passwords.
   - DM each person their username and password. Then post in the chat (text below).
5. **Seed the Reddit corpus** (once, from your laptop, about 3 GB):
   `INDICATORLAB_BUCKET=indicatorlab-data .venv/bin/python -m src.reddit.pipeline --mode seed`
6. **Fill the trailing week** (optional; otherwise the first hourly runs catch up over a few hours):
   `INDICATORLAB_BUCKET=indicatorlab-data .venv/bin/python -m src.reddit.pipeline --mode hourly`
7. **Reddit stack:** `infra/reddit/deploy.sh you@example.com` (builds and pushes the image, then `sam deploy`).
8. **Check:** `aws lambda invoke --function-name indicatorlab-reddit-hourly out.json`, then wait for an
   unattended hourly run and look for a new `raw/reddit/date=…` object; run the weekly task once with
   `aws ecs run-task` (or the console) and check `processed/reddit_weekly.parquet` was updated.

## First login (Jamal, Jack, James)

1. Open the sign-in URL from Joshua's DM (`https://<account-id>.signin.aws.amazon.com/console`).
2. Sign in with your username and one-time password, then set your own password.
3. Optional but recommended: add MFA under **IAM → Users → you → Security credentials**.
4. For scripts and deploys, use **Create access key → Command Line Interface (CLI)** on the same page,
   then `aws configure` with region `us-west-2`.
5. Check with `aws sts get-caller-identity` and `aws s3 ls s3://indicatorlab-data/`.

Keys go in your own `~/.aws` and in `.env`, never in the repo. Shared secrets are read from SSM, e.g.
`aws ssm get-parameter --name /indicatorlab/vibe_api_key --with-decryption`.

## Chat post (when the shared stack is up)

> AWS shared resources are up (us-west-2):
> - S3: `indicatorlab-data` (raw/, processed/, backtests/)
> - DynamoDB: `indicatorlab-live-india`, `indicatorlab-live-hk` (key `symbol`, on-demand)
> - Secrets: SSM `/indicatorlab/*`
> - Budget alert: $20/month
>
> Your login is in your DM. First-login steps and who uses what: `infra/README.md` on the `reddit` branch.
> Please sign in today and run `aws s3 ls s3://indicatorlab-data/` to confirm access. Tell me if anything
> is denied.

## Cost on the free plan

Live services run only during market hours (Jamal's and Jack's schedules). The hourly Lambda uses about
a minute a run, inside the free tier; the weekly Fargate task is roughly an hour a week; S3 holds a few GB.
Expect a few dollars a month at most. The $20 budget alert is the backstop: if it fires, post in the chat.
Check that Fargate, ECR and EventBridge Scheduler are available on the free plan before step 7; if not,
run the weekly job from a laptop (`--mode weekly`) until the DS3 account.

## Moving to the DS3 account

1. Deploy `infra/shared` there (S3 names are global: either delete the old bucket first, after copying, or
   pick a new name and set `INDICATORLAB_BUCKET` everywhere).
2. Rerun `infra/scripts/put_secrets.sh` against the new account.
3. Copy the data: `aws s3 sync s3://<old-bucket> s3://<new-bucket>` (with credentials that can read both).
4. Deploy `infra/reddit` (and each teammate's service) with the new bucket name, recreate the team users.
5. Delete the old stacks; the bucket and tables have `Retain`, so delete them by hand once copied.

## Validating changes

```bash
uv venv /tmp/cfnlint && uv pip install --python /tmp/cfnlint/bin/python cfn-lint
/tmp/cfnlint/bin/cfn-lint --regions us-west-2 -- infra/shared/template.yaml infra/reddit/template.yaml
bash -n infra/scripts/*.sh infra/*/deploy.sh
.venv/bin/python -m pytest tests/reddit/test_pipeline.py tests/test_storage.py
```
