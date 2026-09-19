"""Run the extraction agent directly against local sample images.

For prompt tuning before anything is deployed — no S3, no API Gateway, no
Lambda, just the agent against real Bedrock. Requires Bedrock model access
to be live (`aws bedrock-runtime invoke-model ...`) before it will work.

Usage (from the repo root):
    python3 backend/local_test.py [samples/notice-01.jpg ...]
    python3 backend/local_test.py                  # runs all of samples/
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent import extract_events  # noqa: E402
from schema import validate_events  # noqa: E402

MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
REGION = "ap-south-1"

FORMAT_BY_SUFFIX = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}


def run_one(path: str) -> None:
    image_bytes = Path(path).read_bytes()
    image_format = FORMAT_BY_SUFFIX.get(Path(path).suffix.lower(), "jpeg")

    print(f"\n=== {path} ===")
    try:
        raw_events = extract_events(image_bytes, image_format, MODEL_ID, REGION)
    except Exception as exc:
        print(f"FAILED: {exc}")
        return

    events, warnings = validate_events(raw_events)
    print(json.dumps({"events": events, "warnings": warnings}, indent=2))


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(glob.glob("samples/*.jpg"))
    if not paths:
        print("No sample images found. Pass paths explicitly or add files to samples/.")
        sys.exit(1)
    for path in paths:
        run_one(path)
