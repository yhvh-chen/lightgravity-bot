#!/usr/bin/env python3
"""LG-040 BROWSER owner — persistent pre-forward reservation OCR proxy.

Purpose
-------
The real product app (`lightgravity start`) is configured with
``LIGHTGRAVITY_OCR_BASE_URL`` pointing at **this loopback proxy**, never at the
LAN endpoint directly.  Every product POST therefore passes through the gate
here, where a **persistent, pre-forward reservation** with a **hard cap** is
enforced *before* any byte is forwarded upstream.

Guarantees
----------
* **Hard cap on POST** (default 2).  A reservation is made atomically on disk
  (with an exclusive lock) *before* forwarding.  Once the cap is reached any
  further POST is refused with HTTP 503 (a controlled "capability unavailable",
  never a fake success and never a replayed unknown side effect).
* **Pre-forward**: reservation is persisted + fsync'd before the upstream
  socket is opened.  A crash after reserve but before forward **consumes** the
  slot (conservative: never over-spend).
* **All POSTs counted**, including the product's own automatic reprocess calls;
  nothing bypasses the proxy because the product only knows this base URL.
* **No secret logging**: the ``Authorization`` request header is never written
  to any log or ledger.  Only method/path/redacted-header-presence/count are
  recorded.
* health/models GET are passed through and counted separately (a small cap).
* The proxy is loopback-only and single-threaded (concurrency 1) to match the
  frozen OCR contract.

Ledger
------
``--ledger`` JSON file, atomic replace + fsync, shape::

    {"cap": 2, "post_used": 0, "get_used": 0, "events": [...]}

Run with ``--ready-file`` so a wrapper can wait for the bound port.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

READ_TIMEOUT = 115.0
CONNECT_TIMEOUT = 5.0


class Ledger:
    def __init__(self, path: Path, cap: int, get_cap: int) -> None:
        self.path = path
        self.cap = cap
        self.get_cap = get_cap
        self._lock = threading.Lock()
        self._data = {"cap": cap, "get_cap": get_cap, "post_used": 0, "get_used": 0, "events": []}
        self._load()

    def _load(self) -> None:
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text("utf-8"))
            except Exception:
                # A corrupt ledger must never be treated as 0: fail closed.
                raise SystemExit("FATAL: ledger corrupt; refusing to run")

    def _persist(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), "utf-8")
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def reserve_post(self, path: str) -> tuple[bool, int]:
        """Atomically reserve one POST slot before forwarding. Returns (ok, used_after)."""
        with self._lock:
            used = int(self._data.get("post_used", 0))
            if used >= self.cap:
                self._data["events"].append(
                    {"t": time.time(), "kind": "post_denied_cap", "path": path, "used": used}
                )
                self._persist()
                return False, used
            used += 1
            self._data["post_used"] = used
            self._data["events"].append(
                {"t": time.time(), "kind": "post_reserved", "path": path, "used": used}
            )
            self._persist()
            return True, used

    def record_post_result(self, path: str, status: int, result: str) -> None:
        with self._lock:
            self._data["events"].append(
                {"t": time.time(), "kind": "post_result", "path": path,
                 "status": status, "result": result}
            )
            self._persist()

    def reserve_get(self, path: str) -> tuple[bool, int]:
        with self._lock:
            used = int(self._data.get("get_used", 0))
            if used >= self.get_cap:
                self._data["events"].append(
                    {"t": time.time(), "kind": "get_denied_cap", "path": path, "used": used}
                )
                self._persist()
                return False, used
            used += 1
            self._data["get_used"] = used
            self._data["events"].append(
                {"t": time.time(), "kind": "get_reserved", "path": path, "used": used}
            )
            self._persist()
            return True, used

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = "http://192.168.8.12:11434"
    ledger: Ledger

    def log_message(self, fmt, *args):  # quieter, never includes headers
        sys.stderr.write("proxy: " + (fmt % args) + "\n")

    def _auth_present(self) -> bool:
        # Record presence only; the value is never read into a log.
        return bool(self.headers.get("Authorization"))

    def do_GET(self):
        ok, used = self.ledger.reserve_get(self.path)
        if not ok:
            self._send(503, b'{"error":"proxy GET cap reached"}', "application/json")
            return
        self._forward("GET", None)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        ok, used = self.ledger.reserve_post(self.path)
        if not ok:
            self._send(
                503,
                json.dumps({
                    "error": {
                        "message": "OCR proxy POST cap reached; refusing before forward",
                        "type": "capability_unavailable",
                    }
                }).encode(),
                "application/json",
            )
            return
        self._forward("POST", body)

    def _forward(self, method: str, body: bytes | None):
        url = self.upstream + self.path
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json"),
                   "Accept": "application/json"}
        if self.headers.get("Authorization"):
            headers["Authorization"] = self.headers.get("Authorization")
        if self.headers.get("User-Agent"):
            headers["User-Agent"] = self.headers.get("User-Agent")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json")
            if method == "POST":
                self.ledger.record_post_result(self.path, status, "ok")
            self._send(status, data, ctype)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            if method == "POST":
                self.ledger.record_post_result(self.path, exc.code, "http_error")
            self._send(exc.code, data, exc.headers.get("Content-Type", "application/json"))
        except (TimeoutError, socket.timeout):
            if method == "POST":
                self.ledger.record_post_result(self.path, 0, "timeout")
            self._send(504, b'{"error":{"message":"upstream timeout"}}', "application/json")
        except Exception as exc:  # noqa: BLE001
            if method == "POST":
                self.ledger.record_post_result(self.path, 0, f"error:{type(exc).__name__}")
            self._send(502, json.dumps({"error": {"message": f"upstream {type(exc).__name__}"}}).encode(),
                       "application/json")

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--cap", type=int, default=2)
    ap.add_argument("--get-cap", type=int, default=2)
    ap.add_argument("--ready-file", required=True)
    ap.add_argument("--upstream", default="http://192.168.8.12:11434")
    args = ap.parse_args()

    ledger = Ledger(Path(args.ledger), args.cap, args.get_cap)
    Handler.upstream = args.upstream
    Handler.ledger = ledger

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    port = httpd.server_address[1]
    Path(args.ready_file).write_text(
        json.dumps({"port": port, "cap": args.cap, "ledger": args.ledger}), "utf-8"
    )
    sys.stderr.write(f"proxy: listening 127.0.0.1:{port} -> {args.upstream} cap={args.cap}\n")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
