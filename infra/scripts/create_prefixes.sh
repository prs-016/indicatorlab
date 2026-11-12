#!/usr/bin/env bash
# Create the top-level folders of the data bucket (S3 has no real folders; these are empty marker objects).
#   infra/scripts/create_prefixes.sh indicatorlab-data
set -euo pipefail
BUCKET="${1:?usage: create_prefixes.sh <bucket>}"
for p in raw/ processed/ backtests/ raw/live/india/ raw/live/hk/ raw/reddit/ raw/wikipedia/; do
  aws s3api put-object --bucket "$BUCKET" --key "$p" >/dev/null
  echo "s3://$BUCKET/$p"
done
