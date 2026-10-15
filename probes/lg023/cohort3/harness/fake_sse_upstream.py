#!/usr/bin/env python3
"""Local OpenAI-compatible fake SSE upstream for the cohort-3 DRY-RUN only.

Never contacts DeepSeek.  It answers every chat-completion with a minimal
non-streaming-style SSE body so the real SDK/proxy path can be exercised end to
end without spending any real generation.  The dry-run is a *wiring* check: it
does not write the fixture files, so the machine gate is expected to fail.

Usage::

    .venv/bin/python fake_sse_upstream.py <port>
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            payload = {}
        stream = bool(payload.get("stream"))
        if not stream:
            reply = {
                "id": "chatcmpl-fake", "object": "chat.completion", "model": "fake",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "offline-dry-run"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        chunks = [
            {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": "fake",
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": "offline-dry-run"}}]},
            {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": "fake",
             "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        out = b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks)
        out += b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
        self.close_connection = True


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"fake upstream on 127.0.0.1:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
