"""Lambda entry point. Two routes behind one HTTP API:

  POST /upload-url  {filename, contentType} -> {uploadUrl, key}
  POST /extract     {key}                   -> {events, warnings}

CORS is handled by the HTTP API's CorsConfiguration (template.yaml), not here.
"""
import json
import logging
import os
import uuid

import boto3
from botocore.exceptions import ClientError

from agent import extract_events
from schema import validate_events

logger = logging.getLogger()
logger.setLevel(logging.INFO)

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
BEDROCK_REGION = os.environ["BEDROCK_REGION"]
MODEL_ID = os.environ["MODEL_ID"]
UPLOAD_URL_EXPIRY_SECONDS = 300

# Force the regional endpoint explicitly. boto3's default S3 presigned URL
# uses the global `s3.amazonaws.com` host regardless of region_name, and for
# any region other than us-east-1 that host 307-redirects the actual PUT
# (observed against the deployed stack in ap-south-1) — the fix is to point
# the client at the region's own endpoint, not just set region_name.
_region = os.environ["AWS_REGION"]
s3 = boto3.client("s3", region_name=_region, endpoint_url=f"https://s3.{_region}.amazonaws.com")

CONTENT_TYPE_TO_FORMAT = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _response(status: int, body: dict) -> dict:
    return {"statusCode": status, "body": json.dumps(body)}


def _parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    return json.loads(raw)


def handle_upload_url(event: dict) -> dict:
    body = _parse_body(event)
    filename = body.get("filename", "notice")
    content_type = body.get("contentType", "image/jpeg")

    if content_type not in CONTENT_TYPE_TO_FORMAT:
        return _response(400, {"error": f"Unsupported content type: {content_type}"})

    extension = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    key = f"uploads/{uuid.uuid4()}.{extension}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": UPLOADS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=UPLOAD_URL_EXPIRY_SECONDS,
    )

    return _response(200, {"uploadUrl": upload_url, "key": key})


def handle_extract(event: dict) -> dict:
    body = _parse_body(event)
    key = body.get("key")
    if not key:
        return _response(400, {"error": "Missing key"})

    try:
        head = s3.head_object(Bucket=UPLOADS_BUCKET, Key=key)
    except ClientError as exc:
        # Without s3:ListBucket (deliberately not granted), S3 returns 403 for
        # a missing key instead of 404, to avoid revealing whether it exists.
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "403"):
            return _response(404, {"error": "Uploaded image not found"})
        raise

    content_type = head.get("ContentType", "image/jpeg")
    image_format = CONTENT_TYPE_TO_FORMAT.get(content_type, "jpeg")

    obj = s3.get_object(Bucket=UPLOADS_BUCKET, Key=key)
    image_bytes = obj["Body"].read()

    try:
        raw_events = extract_events(image_bytes, image_format, MODEL_ID, BEDROCK_REGION)
    except Exception:
        logger.exception("Model call failed or returned unparseable output for key=%s", key)
        return _response(200, {"events": [], "warnings": ["Could not read this notice, try a clearer photo"]})

    events, warnings = validate_events(raw_events)
    return _response(200, {"events": events, "warnings": warnings})


ROUTES = {
    ("POST", "/upload-url"): handle_upload_url,
    ("POST", "/extract"): handle_extract,
}


def lambda_handler(event: dict, context) -> dict:
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "")
    path = http.get("path", "")

    route = ROUTES.get((method, path))
    if route is None:
        return _response(404, {"error": f"No route for {method} {path}"})

    try:
        return route(event)
    except json.JSONDecodeError:
        return _response(400, {"error": "Malformed JSON body"})
    except Exception:
        logger.exception("Unhandled error in %s %s", method, path)
        return _response(500, {"error": "Internal error"})
