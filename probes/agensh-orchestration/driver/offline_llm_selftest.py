#!/usr/bin/env python3
"""Offline transport self-test for llm_client (no real model calls).

Starts a local HTTP server that emits canned SSE and checks:
  1. normal stream -> content + usage parsed;
  2. usage missing  -> usage_unknown + conservative estimate;
  3. keep-alive-only stall -> bounded by first_event_timeout, infra_failure;
  4. HTTP 500 -> infra_failure;
  5. JSON extraction from fenced/prose text.

Usage: python3 driver/offline_llm_selftest.py
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_client import chat_completion, estimate_tokens  # noqa: E402
from run_pilot import extract_json_object  # noqa: E402


def _sse(obj: dict) -> bytes:
    return ("data: " + json.dumps(obj) + "\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        mode = self.path.strip("/")
        if mode == "http500":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"boom"}}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if mode == "stall":
            try:
                for _ in range(1000):
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if mode == "ok":
            self.wfile.write(b": keep-alive\n\n")
            self.wfile.write(_sse({"choices": [{"delta": {"content": '{"a": '}}]}))
            self.wfile.write(_sse({"choices": [{"delta": {"content": "1}"}}]}))
            self.wfile.write(_sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                                             "total_tokens": 18}}))
            self.wfile.write(b"data: [DONE]\n\n")
        elif mode == "nousage":
            self.wfile.write(_sse({"choices": [{"delta": {"content": "hello world"}}]}))
            self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    failures = 0

    def report(name, ok, detail=""):
        nonlocal failures
        print(f"{name}: {'OK' if ok else 'FAIL'} {detail}")
        if not ok:
            failures += 1

    # 1. normal
    r = chat_completion("test-key", [{"role": "user", "content": "hi"}], model="x",
                        host="127.0.0.1", path="/ok", scheme="http", port=port, first_event_timeout=5,
                        total_timeout=10)
    report("normal", r.ok and "{\"a\": 1}" in r.content and r.usage and r.usage["total_tokens"] == 18,
           f"content={r.content!r} usage={r.usage}")

    # 2. usage missing
    r = chat_completion("test-key", [{"role": "user", "content": "hi"}], model="x",
                        host="127.0.0.1", path="/nousage", scheme="http", port=port, first_event_timeout=5,
                        total_timeout=10)
    report("nousage", r.ok and r.usage is None and r.usage_unknown and r.estimated_tokens > 0,
           f"estimated={r.estimated_tokens}")

    # 3. keep-alive stall bounded
    t0 = time.monotonic()
    r = chat_completion("test-key", [{"role": "user", "content": "hi"}], model="x",
                        host="127.0.0.1", path="/stall", scheme="http", port=port, first_event_timeout=1.5,
                        total_timeout=20)
    elapsed = time.monotonic() - t0
    report("stall", (not r.ok) and r.infra_failure and elapsed < 6,
           f"elapsed={elapsed:.2f}s error={r.error}")

    # 4. http 500
    r = chat_completion("test-key", [{"role": "user", "content": "hi"}], model="x",
                        host="127.0.0.1", path="/http500", scheme="http", port=port, first_event_timeout=5,
                        total_timeout=10)
    report("http500", (not r.ok) and r.infra_failure and r.http_status == 500, f"status={r.http_status}")

    # 5. json extraction
    j1 = extract_json_object('text before\n```json\n{"summary": "x", "edits": [{"path": "a"}]}\n```\ntrailing')
    j2 = extract_json_object('{"a": {"b": "}"}}')
    j3 = extract_json_object("no json here")
    report("json", j1 is not None and j1["summary"] == "x" and j2 == {"a": {"b": "}"}} and j3 is None,
           f"j1={j1} j2={j2}")

    server.shutdown()
    print(f"\noffline llm self-test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
