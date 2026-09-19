#!/usr/bin/env bash
# Rebuild, redeploy, sync the frontend, and invalidate the CDN cache.
# Run `sam deploy --guided` once by hand first; this assumes samconfig.toml exists.
set -euo pipefail

STACK_NAME="notice-to-calendar"

sam build
sam deploy

API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)
SITE_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue" --output text)
DISTRIBUTION_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" --output text)
CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomain'].OutputValue" --output text)

echo "window.API_BASE = \"${API_ENDPOINT}\";" > frontend/config.js

aws s3 sync frontend/ "s3://${SITE_BUCKET}" --delete
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" > /dev/null

echo ""
echo "Deployed."
echo "  API:  ${API_ENDPOINT}"
echo "  Site: ${CLOUDFRONT_DOMAIN}"
