"""Run the whole app locally: serves frontend/ and the two API routes from
one process on one origin, so there's no CORS to configure for local use.

Reuses backend/app.py's lambda_handler directly (not a reimplementation) —
same code path as prod, minus API Gateway/Lambda in front of it. Talks to
the real deployed S3 uploads bucket (S3 itself isn't blocked), so uploads
work for real; the Bedrock call still goes through the real Bedrock service
and will fail exactly as it does in the deployed stack until AWS's account
verification hold clears — this doesn't route around that, nothing local
could.

Usage: python3 scripts/run_local.py [port]
"""
import http.server
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("UPLOADS_BUCKET", "notice-to-calendar-uploadsbucket-mijszvxqexy5")
os.environ.setdefault("BEDROCK_REGION", "ap-south-1")
os.environ.setdefault("MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
os.environ.setdefault("AWS_REGION", "ap-south-1")

import app as backend_app  # noqa: E402

FRONTEND_DIR = ROOT / "frontend"
LOCAL_CONFIG_JS = b'window.API_BASE = "";\n'  # same-origin: no CORS needed locally


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def log_message(self, fmt, *args):
        print(f"{self.command} {self.path} -> {args[-2] if len(args) >= 2 else ''}")

    def do_GET(self):
        if self.path == "/config.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(LOCAL_CONFIG_JS)))
            self.end_headers()
            self.wfile.write(LOCAL_CONFIG_JS)
            return
        super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        event = {"requestContext": {"http": {"method": "POST", "path": self.path}}, "body": body}
        result = backend_app.lambda_handler(event, None)
        payload = result["body"].encode("utf-8")
        self.send_response(result["statusCode"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Notice-to-Calendar running locally: http://localhost:{port}")
    print("Uploads go to the real S3 bucket; extraction still hits the real Bedrock")
    print("(and will fail until AWS's account verification hold clears). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
