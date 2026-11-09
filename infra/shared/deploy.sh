#!/usr/bin/env bash
# Deploy the shared stack (bucket, live tables, budget, team group) and create the bucket folders.
#   infra/shared/deploy.sh you@example.com [bucket-name]
set -euo pipefail
EMAIL="${1:?usage: deploy.sh <budget-alert-email> [bucket-name]}"
BUCKET="${2:-indicatorlab-data}"
REGION="${AWS_REGION:-us-west-2}"
HERE="$(cd "$(dirname "$0")" && pwd)"

aws cloudformation deploy --region "$REGION" --stack-name indicatorlab-shared \
  --template-file "$HERE/template.yaml" --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "BudgetEmail=$EMAIL" "BucketName=$BUCKET"
"$HERE/../scripts/create_prefixes.sh" "$BUCKET"
aws cloudformation describe-stacks --region "$REGION" --stack-name indicatorlab-shared \
  --query "Stacks[0].Outputs" --output table
