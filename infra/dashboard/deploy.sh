#!/usr/bin/env bash
# Export the dashboard as a static site, deploy its hosting stack, upload, and refresh the CDN.
#   infra/dashboard/deploy.sh          (re-run any time to publish fresh data)
set -euo pipefail
REGION="${AWS_REGION:-us-west-2}"
STACK="indicatorlab-dashboard"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

(cd "$ROOT" && .venv/bin/python -m src.reddit.dashboard_export)
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file "$ROOT/infra/dashboard/template.yaml" --no-fail-on-empty-changeset
out() { aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET="$(out BucketName)"; DIST="$(out DistributionId)"; URL="$(out Url)"
aws s3 sync "$ROOT/build/reddit_dashboard" "s3://$BUCKET" --delete --region "$REGION"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query Invalidation.Id --output text
echo "dashboard: $URL"
