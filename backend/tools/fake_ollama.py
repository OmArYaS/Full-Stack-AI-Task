"""Tiny deterministic fake Ollama server for offline demos.

Implements just enough of Ollama's ``POST /api/generate`` endpoint to exercise
the frontend → API → extraction flow without installing or running Ollama.

Usage:
    python backend/tools/fake_ollama.py --port 11434

Set ``OLLAMA_BASE_URL=http://localhost:<port>`` in ``.env`` for the backend.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# A schema-valid payload with reasoning tags and fences to exercise the
# extractor's stripping and repair paths.
DEMO_RESPONSE = (
    "<think>The user wants structured data. I will output valid JSON.</think>\n"
    "```json\n"
    + json.dumps(
        {
            "summary": "Ada Lovelace wrote the first algorithm for the Analytical Engine in 1843.",
            "entities": ["Ada Lovelace", "Analytical Engine", "1843"],
            "sentiment": "positive",
            "key_points": [
                "First algorithm written in 1843",
                "Recognized as the first computer programmer",
            ],
        }
    )
    + "\n```"
)


class FakeOllamaHandler(BaseHTTPRequestHandler):
    """Handle ``/api/generate`` with a canned, schema-valid extraction."""

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path.rstrip("/") != "/api/generate":
            self.send_error(404, "Only /api/generate is supported")
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload: dict[str, Any] = json.loads(self.rfile.read(length) or b"{}")
        model = payload.get("model", "fake-model")

        body = json.dumps({"model": model, "response": DEMO_RESPONSE, "done": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path.rstrip("/") == "/api/tags":
            body = json.dumps(
                {"models": [{"name": "fake-model", "model": "fake-model"}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Keep demo output quiet."""
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), FakeOllamaHandler)
    print(f"Fake Ollama listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
