#!/usr/bin/env bash
# Rebuild, redeploy, sync the frontend, and invalidate the CDN cache.
# Run `sam deploy --guided` once by hand first; this assumes samconfig.toml exists.
set -euo pipefail

STACK_NAME="notice-to-calendar"
REGION="ap-south-1"

sam build
deploy_output=$(sam deploy 2>&1) && echo "$deploy_output" || {
  # "No changes to deploy" isn't a real failure — everything past this point
  # (frontend sync, config.js, invalidation) should still run.
  echo "$deploy_output"
  echo "$deploy_output" | grep -q "No changes to deploy" || exit 1
}

API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)
SITE_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue" --output text)
DISTRIBUTION_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" --output text)
CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomain'].OutputValue" --output text)

echo "window.API_BASE = \"${API_ENDPOINT}\";" > frontend/config.js

aws s3 sync frontend/ "s3://${SITE_BUCKET}" --delete --region "$REGION"

if [ "$DISTRIBUTION_ID" != "none" ]; then
  aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" > /dev/null
fi

echo ""
echo "Deployed."
echo "  API:  ${API_ENDPOINT}"
echo "  Site: ${CLOUDFRONT_DOMAIN}"
