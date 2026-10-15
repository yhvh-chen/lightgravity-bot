#!/usr/bin/env python3
"""Offline transport self-test for llm_client (no real model calls).

Local HTTP server with canned SSE. Checks:
  1. normal stream -> content + usage parsed; finish_reason + model echo captured;
  2. usage missing  -> usage_unknown + conservative estimate;
  3. keep-alive-only stall -> bounded by first_event_timeout, infra_failure;
  4. HTTP 500 -> infra_failure (retryable);
  5. HTTP 400 -> fatal (config rejection, not retried);
  6. reasoning_content / reasoning_tokens captured;
  7. thinking.type=disabled present in the request payload;
  8. JSON extraction from fenced/prose text.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_client import chat_completion  # noqa: E402
from run_experiment import extract_json_object  # noqa: E402

SEEN_PAYLOADS: list[dict] = []
SEEN_AUTH_HEADER: list[bool] = []


def _sse(obj: dict) -> bytes:
    return ("data: " + json.dumps(obj) + "\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
        if "Authorization" in self.headers:
            SEEN_AUTH_HEADER.append(True)
        SEEN_PAYLOADS.append(payload)
        mode = self.path.strip("/")
        if mode == "http500":
            self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"boom"}'); return
        if mode == "http400":
            self.send_response(400); self.end_headers()
            self.wfile.write(b'{"error":{"message":"unknown parameter thinking"}}'); return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if mode == "stall":
            try:
                for _ in range(1000):
                    self.wfile.write(b": keep-alive\n\n"); self.wfile.flush(); time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if mode == "ok":
            self.wfile.write(b": keep-alive\n\n")
            self.wfile.write(_sse({"model": "deepseek-v4-flash",
                                   "choices": [{"delta": {"content": '{"a": '}}]}))
            self.wfile.write(_sse({"choices": [{"delta": {"content": "1}"}}]}))
            self.wfile.write(_sse({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                                             "total_tokens": 18,
                                             "completion_tokens_details": {"reasoning_tokens": 0}}}))
            self.wfile.write(b"data: [DONE]\n\n")
        elif mode == "reasoning":
            self.wfile.write(_sse({"choices": [{"delta": {"reasoning_content": "hmm"}, "finish_reason": None}]}))
            self.wfile.write(_sse({"choices": [{"delta": {"content": "{}"}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 5, "completion_tokens": 9, "total_tokens": 14,
                                             "completion_tokens_details": {"reasoning_tokens": 4}}}))
            self.wfile.write(b"data: [DONE]\n\n")
        elif mode == "length":
            self.wfile.write(_sse({"choices": [{"delta": {"content": '{"edits": ['},
                                                "finish_reason": "length"}],
                                   "usage": {"prompt_tokens": 5, "completion_tokens": 8192,
                                             "total_tokens": 8197}}))
            self.wfile.write(b"data: [DONE]\n\n")
        elif mode == "nousage":
            self.wfile.write(_sse({"choices": [{"delta": {"content": "hello world"}}]}))
            self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    failures = 0

    def report(name, ok, detail=""):
        nonlocal failures
        print(f"{name}: {'OK' if ok else 'FAIL'} {detail}")
        if not ok:
            failures += 1

    def call(path, **kw):
        return chat_completion("test-key", [{"role": "user", "content": "hi"}], model="x",
                               host="127.0.0.1", path=f"/{path}", scheme="http", port=port,
                               first_event_timeout=kw.pop("first_event_timeout", 5),
                               total_timeout=kw.pop("total_timeout", 10), **kw)

    r = call("ok")
    report("normal", r.ok and '{"a": 1}' in r.content and r.usage and r.usage["total_tokens"] == 18
           and r.finish_reason == "stop" and r.response_model == "deepseek-v4-flash",
           f"finish={r.finish_reason} model={r.response_model}")

    r = call("nousage")
    report("nousage", r.ok and r.usage is None and r.usage_unknown and r.estimated_tokens > 0,
           f"estimated={r.estimated_tokens}")

    t0 = time.monotonic()
    r = call("stall", first_event_timeout=1.5, total_timeout=20)
    report("stall", (not r.ok) and r.infra_failure and time.monotonic() - t0 < 6,
           f"elapsed={time.monotonic() - t0:.2f}s")

    r = call("http500")
    report("http500", (not r.ok) and r.infra_failure and (not r.fatal) and r.http_status == 500)

    r = call("http400")
    report("http400", (not r.ok) and r.fatal and r.http_status == 400)

    r = call("reasoning")
    report("reasoning", r.ok and r.reasoning_tokens == 4 and r.reasoning_content == "hmm",
           f"rtok={r.reasoning_tokens}")

    r = call("length")
    report("length", r.ok and r.finish_reason == "length")

    payload = SEEN_PAYLOADS[0]
    report("thinking.payload", payload.get("thinking") == {"type": "disabled"}
           and payload.get("max_tokens") == 8192,
           f"thinking={payload.get('thinking')} max_tokens={payload.get('max_tokens')}")
    report("no-auth-in-payload", "Authorization" not in payload and "Authorization" not in json.dumps(payload),
           "auth header never serialized into the request body; header itself was sent")
    report("auth.header.sent", bool(SEEN_AUTH_HEADER) and all(SEEN_AUTH_HEADER),
           f"authorization header present on {len(SEEN_AUTH_HEADER)} requests")

    j1 = extract_json_object('text\n```json\n{"summary": "x", "edits": [{"path": "a"}]}\n```\n')
    j2 = extract_json_object('{"a": {"b": "}"}}')
    j3 = extract_json_object("no json here")
    report("json", j1 is not None and j1["summary"] == "x" and j2 == {"a": {"b": "}"}} and j3 is None)

    server.shutdown()
    print(f"\noffline llm self-test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
