#!/usr/bin/env python3
# Copyright 2026 LightGravity Bot project (LG-003 probe).
#
# Local OpenAI-compatible endpoint used only by the LG-003 Antigravity probe.
#
# Why this exists: Antigravity's `LocalOpenAIAgentConfig` ("Gemma endpoint")
# speaks the OpenAI `/v1/chat/completions` protocol but its endpoint config
# carries only `base_url` -- there is no api_key field (see the frozen
# GemmaEndpoint proto). Real hosted providers such as DeepSeek require a
# bearer token, so this probe fronts the real provider and injects the
# credential from the process environment. The model that answers is the real
# remote model; this proxy is transport/auth plumbing, not a model mock.
#
# Modes:
#   --mode canned   : answer locally with a fixed SSE completion (offline
#                     self-test of the SDK event parser).
#   --mode deepseek : forward to the real DeepSeek OpenAI-compatible API with
#                     an injected bearer token. Requires DEEPSEEK_API_KEY.
#
# The credential is read from the environment and is never logged or written.
# Every upstream request is counted and the process stops accepting after
# --max-calls to keep real-model usage bounded.

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_UPSTREAM = "https://api.deepseek.com/v1/chat/completions"


def _sse(payload: dict) -> bytes:
    return ("data: " + json.dumps(payload, separators=(",", ":")) + "\n\n").encode()


class _State:
    def __init__(self, mode: str, log_path: str, max_calls: int) -> None:
        self.mode = mode
        self.log_path = log_path
        self.max_calls = max_calls
        self.calls = 0
        self.lock = threading.Lock()

    def next_call(self) -> int | None:
        with self.lock:
            self.calls += 1
            if self.calls > self.max_calls:
                return None
            return self.calls

    def log(self, record: dict) -> None:
        # Never record headers that may carry credentials.
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "LG003Probe/0.1"
    state: _State

    def log_message(self, *args: object) -> None:  # silence default logging
        pass

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        body = self._read_body()
        call_no = self.state.next_call()
        if call_no is None:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"probe max-calls reached"}}')
            return
        try:
            request_json = json.loads(body.decode("utf-8"))
        except ValueError:
            request_json = None
        self.state.log({
            "call": call_no,
            "path": self.path,
            "stream": (request_json or {}).get("stream"),
            "model": (request_json or {}).get("model"),
            "message_count": len((request_json or {}).get("messages", [])),
            "has_tools": bool((request_json or {}).get("tools")),
            "tool_names": [
                (t.get("function") or {}).get("name")
                for t in (request_json or {}).get("tools", [])
            ],
            "has_response_format": bool((request_json or {}).get("response_format")),
        })
        if self.state.mode == "canned":
            self._serve_canned(call_no)
        else:
            self._serve_upstream(body)

    def _serve_canned(self, call_no: int) -> None:
        now = int(time.time())
        chunks = [
            _sse({
                "id": "chatcmpl-probe", "object": "chat.completion.chunk",
                "created": now, "model": "canned",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "pong"},
                             "finish_reason": None}],
            }),
            _sse({
                "id": "chatcmpl-probe", "object": "chat.completion.chunk",
                "created": now, "model": "canned",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            }),
            b"data: [DONE]\n\n",
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(chunk)
        self.wfile.flush()

    def _serve_upstream(self, body: bytes) -> None:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"DEEPSEEK_API_KEY not set"}}')
            return
        req = urllib.request.Request(
            DEFAULT_UPSTREAM,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "Accept": "text/event-stream",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as upstream:
                status = upstream.status
                ctype = upstream.headers.get("Content-Type", "")
                self.send_response(status)
                self.send_header("Content-Type", ctype or "text/event-stream")
                self.end_headers()
                while True:
                    chunk = upstream.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                self.wfile.flush()
        except urllib.error.HTTPError as exc:
            detail = exc.read()
            self.state.log({"upstream_error": exc.code, "body": detail[:500].decode("utf-8", "replace")})
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(detail)
        except Exception as exc:  # noqa: BLE001 - probe diagnostics
            self.state.log({"upstream_exception": type(exc).__name__, "message": str(exc)[:500]})
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": type(exc).__name__}}).encode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["canned", "deepseek"], default="canned")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--log", default="/tmp/lg003_proxy_log.jsonl")
    parser.add_argument("--max-calls", type=int, default=8)
    args = parser.parse_args()

    state = _State(args.mode, args.log, args.max_calls)
    handler = type("BoundHandler", (Handler,), {"state": state})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"lg003 proxy mode={args.mode} port={args.port} max_calls={args.max_calls}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
