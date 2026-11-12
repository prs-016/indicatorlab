#!/usr/bin/env bash
# Build the Reddit pipeline image (linux/arm64), push it to ECR, and deploy the schedules, Lambda,
# Fargate task and alarms with SAM. Run from anywhere; needs Docker (colima) and AWS credentials.
#   infra/reddit/deploy.sh you@example.com [bucket-name]
set -euo pipefail
EMAIL="${1:?usage: deploy.sh <alert-email> [bucket-name]}"
BUCKET="${2:-indicatorlab-data}"
REGION="${AWS_REGION:-us-west-2}"
REPO_NAME="indicatorlab-reddit"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
TAG="$(git -C "$ROOT" rev-parse --short HEAD)$(git -C "$ROOT" diff --quiet || echo -dirty)"
IMAGE="$REGISTRY/$REPO_NAME:$TAG"

aws ecr describe-repositories --region "$REGION" --repository-names "$REPO_NAME" >/dev/null 2>&1 \
  || aws ecr create-repository --region "$REGION" --repository-name "$REPO_NAME" \
       --image-scanning-configuration scanOnPush=true >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 --provenance=false -f "$ROOT/infra/reddit/Dockerfile" \
  -t "$IMAGE" --push "$ROOT"

# Default VPC: its public subnets and default security group (the Fargate task only makes outbound calls).
VPC="$(aws ec2 describe-vpcs --region "$REGION" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
SUBNETS="$(aws ec2 describe-subnets --region "$REGION" --filters Name=vpc-id,Values="$VPC" \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')"
SG="$(aws ec2 describe-security-groups --region "$REGION" --filters Name=vpc-id,Values="$VPC" \
  Name=group-name,Values=default --query 'SecurityGroups[0].GroupId' --output text)"

sam deploy --region "$REGION" --stack-name indicatorlab-reddit \
  --template-file "$ROOT/infra/reddit/template.yaml" --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset --resolve-s3 \
  --parameter-overrides "ImageUri=$IMAGE" "BucketName=$BUCKET" "AlertEmail=$EMAIL" \
  "SubnetIds=$SUBNETS" "SecurityGroupId=$SG"
echo "deployed $IMAGE"
