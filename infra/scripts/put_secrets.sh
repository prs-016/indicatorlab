#!/usr/bin/env bash
# Copy the team's API keys from a local .env into SSM Parameter Store as SecureStrings under /indicatorlab/.
# Only keys the team shares go up. ANTHROPIC_API_KEY is personal and pay-per-use, and no AWS job needs it
# (the pipeline scores with FinBERT), so it stays in the local .env and is never uploaded.
# CloudFormation cannot create SecureStrings, so this is the one secret step; values are never printed.
#
#   infra/scripts/put_secrets.sh            # reads ./.env
#   infra/scripts/put_secrets.sh path/.env
set -euo pipefail

ENV_FILE="${1:-.env}"
REGION="${AWS_REGION:-$(aws configure get region)}"   # the Region your AWS CLI is set to
PREFIX="/indicatorlab"
[[ -f "$ENV_FILE" ]] || { echo "no $ENV_FILE (copy .env.example and fill it in)" >&2; exit 1; }

# .env variable -> SSM parameter name
MAP=(
  "VIBE_API_KEY:vibe_api_key"
  "REDDIT_CLIENT_ID:reddit_client_id"
  "REDDIT_CLIENT_SECRET:reddit_client_secret"
  "REDDIT_USER_AGENT:reddit_user_agent"
)

value_of() {   # last assignment of $1 in the env file, surrounding quotes removed
  grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

for pair in "${MAP[@]}"; do
  var="${pair%%:*}"; name="$PREFIX/${pair##*:}"
  val="$(value_of "$var" || true)"
  if [[ -z "$val" ]]; then
    echo "skip  $name ($var is empty in $ENV_FILE)"
    continue
  fi
  # The value goes in on stdin (printf is a shell builtin), so it never appears in a process list.
  printf '%s' "$val" | aws ssm put-parameter --region "$REGION" --name "$name" --type SecureString \
    --value file:///dev/stdin --overwrite --output text --query Version >/dev/null
  echo "set   $name"
done
