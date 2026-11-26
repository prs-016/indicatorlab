#!/usr/bin/env bash
# Export the dashboard as a static site, deploy its hosting stack, upload, and refresh the CDN.
#   infra/dashboard/deploy.sh          (re-run any time to publish fresh data)
set -euo pipefail
REGION="${AWS_REGION:-$(aws configure get region)}"   # your AWS CLI Region (us-east-2 on the free-plan project)
STACK="indicatorlab-dashboard"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Build HK from shared storage; no collector/deployment is started by the export.
HK_ROOT="${INDICATORLAB_HK_EXPORT_URI:-s3://${INDICATORLAB_BUCKET:-indicatorlab-data}}"
(cd "$ROOT" && .venv/bin/python -m src.reddit.dashboard_export --hk-root-uri "$HK_ROOT")
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file "$ROOT/infra/dashboard/template.yaml" --no-fail-on-empty-changeset
out() { aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET="$(out BucketName)"; DIST="$(out DistributionId)"; URL="$(out Url)"
aws s3 sync "$ROOT/build/reddit_dashboard" "s3://$BUCKET" --delete --region "$REGION"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query Invalidation.Id --output text
echo "dashboard: $URL"
