#!/usr/bin/env python3
"""LG-040 QUALITY-R1: counting + hard-cap loopback proxy in front of the LAN endpoint.

* Forwards ``/v1/embeddings`` and ``/v1/chat/completions`` POSTs to the authorized
  LAN endpoint only (``http://192.168.8.12:11434``).
* Maintains a **persistent pre-forward reservation**: a POST is rejected with 429
  *before* any upstream connection when it would exceed the frozen cap.
* Counts every POST (success or failure) — never only successes.
* Records method/path/status/latency to a JSONL ledger.  Never logs request or
  response bodies or headers as secrets (there are no credentials here).
* No automatic retry; one upstream attempt per request; no other endpoint.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "http://192.168.8.12:11434"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
LEDGER = EVIDENCE / "proxy_ledger.jsonl"
RAW_DIR = EVIDENCE / "raw_responses"

# Frozen caps (persistent reservation counters)
CAPS = {"embedding": 18, "ocr": 2, "health_get": 2, "other_post": 0, "inference_total": 20}

_lock = threading.Lock()
_counts = {"embedding": 0, "ocr": 0, "health_get": 0, "other_post": 0, "inference_total": 0}


def _classify(method: str, path: str) -> str | None:
    if method == "GET" and path.split("?")[0] in ("/v1/models", "/v1/health", "/health"):
        return "health_get"
    if method == "POST" and path.split("?")[0] == "/v1/embeddings":
        return "embedding"
    if method == "POST" and path.split("?")[0] == "/v1/chat/completions":
        return "ocr"
    if method == "POST":
        return "other_post"
    return None


def _reserve(kind: str) -> tuple[bool, str]:
    """Atomically reserve a slot before forwarding; return (ok, reason)."""
    with _lock:
        if kind == "health_get":
            if _counts["health_get"] >= CAPS["health_get"]:
                return False, f"health_get cap {CAPS['health_get']} reached"
            _counts["health_get"] += 1
            return True, "ok"
        # inference POST kinds also count against the combined inference cap
        if kind in ("embedding", "ocr", "other_post"):
            if _counts["inference_total"] >= CAPS["inference_total"]:
                return False, f"inference_total cap {CAPS['inference_total']} reached"
        cap = CAPS[kind]
        if _counts[kind] >= cap:
            return False, f"{kind} cap {cap} reached"
        _counts[kind] += 1
        if kind in ("embedding", "ocr", "other_post"):
            _counts["inference_total"] += 1
        return True, "ok"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence default noisy logging
        return

    def _record(self, row: dict) -> None:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _forward(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        path = self.path
        kind = _classify(method, path)
        started = time.monotonic()
        if kind is None:
            self.send_error(405, "unsupported method/path")
            self._record({"ts": time.time(), "method": method, "path": path, "kind": None,
                          "status": 405, "forwarded": False, "reason": "unsupported"})
            return
        ok, reason = _reserve(kind)
        if not ok:
            self.send_response(429)
            payload = json.dumps({"error": {"message": reason, "type": "cap_exceeded"}}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self._record({"ts": time.time(), "method": method, "path": path, "kind": kind,
                          "status": 429, "forwarded": False, "reason": reason})
            return
        req = urllib.request.Request(UPSTREAM + path, data=body if method == "POST" else None,
                                     method=method)
        for key in ("Content-Type", "Accept"):
            if self.headers.get(key):
                req.add_header(key, self.headers.get(key))
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            data = exc.read()
            status = exc.code
            ctype = exc.headers.get("Content-Type", "application/json") if exc.headers else "application/json"
        except Exception as exc:  # timeout/conn error: no retry
            self.send_error(502, f"upstream error: {type(exc).__name__}")
            self._record({"ts": time.time(), "method": method, "path": path, "kind": kind,
                          "status": 502, "forwarded": True, "reason": type(exc).__name__,
                          "latency_s": round(time.monotonic() - started, 3)})
            return
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        # Persist raw response bodies for embeddings (vectors, never secrets);
        # enables an independent cosine-order recomputation off the wire bytes.
        seq = None
        with _lock:
            _counts["resp_seq"] = _counts.get("resp_seq", 0) + 1
            seq = _counts["resp_seq"]
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / f"{seq:02d}_{kind}_{method}.json").write_bytes(data)
        self._record({"ts": time.time(), "method": method, "path": path, "kind": kind,
                      "status": status, "forwarded": True, "latency_s": round(time.monotonic() - started, 3),
                      "resp_bytes": len(data), "raw_file": f"raw_responses/{seq:02d}_{kind}_{method}.json"})

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18140
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"proxy listening on 127.0.0.1:{port} -> {UPSTREAM}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
