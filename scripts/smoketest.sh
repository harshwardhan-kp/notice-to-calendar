#!/usr/bin/env bash
# Quick sanity check against the live API after a deploy: upload-url,
# presigned PUT, CORS preflight on both, and extract. Doesn't replace
# actually trying the site in a browser before recording the demo.
set -euo pipefail

STACK_NAME="notice-to-calendar"
REGION="ap-south-1"
SAMPLE="${1:-samples/notice-01.jpg}"

API=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)
echo "API: $API"

echo -n "upload-url CORS preflight: "
curl -s -o /dev/null -w "%{http_code}\n" -X OPTIONS "$API/upload-url" \
  -H "Origin: https://example.com" -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"

RESP=$(curl -s -X POST "$API/upload-url" -H "Content-Type: application/json" \
  -d '{"filename":"smoketest.jpg","contentType":"image/jpeg"}')
KEY=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['key'])" "$RESP")
UPLOAD_URL=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['uploadUrl'])" "$RESP")
echo "upload-url: OK (key=$KEY)"

echo -n "S3 CORS preflight on presigned PUT: "
curl -s -o /dev/null -w "%{http_code}\n" -X OPTIONS "$UPLOAD_URL" \
  -H "Origin: https://example.com" -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"

echo -n "presigned PUT ($SAMPLE): "
curl -s -o /dev/null -w "%{http_code}\n" -X PUT "$UPLOAD_URL" -H "Content-Type: image/jpeg" --data-binary "@$SAMPLE"

echo "extract:"
curl -s -X POST "$API/extract" -H "Content-Type: application/json" -d "{\"key\":\"$KEY\"}" | python3 -m json.tool

echo -n "extract (missing key -> expect 404): "
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/extract" -H "Content-Type: application/json" -d '{"key":"uploads/does-not-exist.jpg"}'
