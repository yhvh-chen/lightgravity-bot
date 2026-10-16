#!/usr/bin/env python3
"""LG-047 E-QA — dedicated durable campaign guard in front of the DeepSeek upstream.

Purpose
-------
The LG-047 budget is **12 real product requests for the ENTIRE campaign** (all
attempts, reviewer turns and retries).  The product already ships a persistent,
pre-forward generation ledger (``LIGHTGRAVITY_MAX_GENERATION_CALLS`` +
``PersistentGenerationLedger``) that every worker/reviewer/dialogue call must
pass.  This module is a **second, independent** guard that sits in front of the
*actual upstream host* and refuses to forward unless the durable campaign
ledger has a free slot.

Two independent gates
---------------------
1. **Product gate** (inside the app process): ``LIGHTGRAVITY_MAX_GENERATION_CALLS=12``
   -> the product's ``PersistentGenerationLedger`` reserves atomically before
   its own proxy forwards.
2. **Campaign guard** (this file): the SDK's loopback auth proxy is pointed at
   *this* guard (via a base-URL override), so literally every SDK/worker/
   reviewer product call travels through it.  It reserves against its **own**
   append-only JSONL ledger (never reset) *before* opening a socket to the real
   upstream.  A failed request still counts; a denial returns 429 and never
   connects.

The app process is launched with ``LIGHTGRAVITY_DEEPSEEK_BASE_URL`` pointing at
this guard (see ``launch_app.py``); the product's own proxy then forwards to the
guard, and the guard forwards to ``https://api.deepseek.com``.  Credentials are
only ever held in memory and injected as the ``Authorization`` header toward the
real upstream — this guard logs **redacted metadata only** (kind, model, byte
size, status, latency, ledger count), never the secret or the request body.

Ledger layout (durable, append-only, rebuildable):
    evidence/ledger/history.jsonl   -- one JSON object per reservation
    evidence/ledger/count.json      -- atomic snapshot reconciled against history

A corrupt ledger is treated as **deny**, never as zero.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REAL_UPSTREAM = os.environ.get("LG_QA_REAL_UPSTREAM", "https://api.deepseek.com")

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
LEDGER_DIR = EVIDENCE / "ledger"
HISTORY = LEDGER_DIR / "history.jsonl"
COUNT_FILE = LEDGER_DIR / "count.json"
GUARD_LOG = EVIDENCE / "guard_calls.jsonl"

CAP = int(os.environ.get("LG_QA_CAMPAIGN_CAP", "12"))

_MODEL_RE = re.compile(rb'"model"\s*:\s*"([^"]+)"')
_lock = threading.Lock()


class Corrupt(RuntimeError):
    pass


def _read_count() -> int:
    hist = 0
    if HISTORY.exists():
        try:
            raw = HISTORY.read_text(encoding="utf-8")
        except OSError as exc:
            raise Corrupt(f"history unreadable: {exc}") from exc
        for i, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError as exc:
                raise Corrupt(f"history line {i} invalid json") from exc
            if isinstance(obj, dict) and obj.get("kind") == "reserve":
                hist += 1
    snap = 0
    if COUNT_FILE.exists():
        try:
            data = json.loads(COUNT_FILE.read_text(encoding="utf-8"))
            snap = int(data.get("count"))
            if snap < 0:
                raise Corrupt("negative count")
        except (OSError, ValueError, TypeError) as exc:
            raise Corrupt(f"count unreadable: {exc}") from exc
    return max(hist, snap)


def _append_reserve(count: int) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "kind": "reserve",
        "count": count,
        "pid": os.getpid(),
        "ts": time.time(),
        "campaign": "LG-047",
    }
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp = COUNT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"count": count}), encoding="utf-8")
    os.replace(tmp, COUNT_FILE)


def reserve() -> tuple[bool, int, str]:
    """Atomically reserve one slot before forwarding. Never resets."""

    with _lock:
        try:
            current = _read_count()
        except Corrupt as exc:
            return False, -1, f"corrupt ledger: {exc}"
        if current >= CAP:
            return False, current, f"campaign cap {CAP} reached"
        new_count = current + 1
        try:
            _append_reserve(new_count)
        except OSError as exc:
            return False, current, f"ledger write failed: {exc}"
        return True, new_count, "ok"


def _log(row: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with GUARD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa: D401 - silence
        return

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        path = self.path
        method = self.command
        is_product = method == "POST" and path.split("?")[0].endswith("/chat/completions")

        if not is_product:
            # health/models probes do not consume the product budget and are
            # never forwarded to the real upstream (no credential spend).
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            _log({"ts": time.time(), "method": method, "path": path, "kind": "non_product",
                  "forwarded": False})
            return

        # Reserve BEFORE any upstream connection.
        ok, count, reason = reserve()
        if not ok:
            self.send_response(429)
            payload = json.dumps({"error": {"message": reason, "type": "campaign_cap_exceeded"}}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            _log({"ts": time.time(), "method": method, "path": path, "kind": "product",
                  "count": count, "forwarded": False, "status": 429, "reason": reason})
            return

        model = None
        m = _MODEL_RE.search(body)
        if m:
            model = m.group(1).decode("utf-8", "replace")
        started = time.monotonic()

        # The SDK proxy already injects Authorization; pass it through untouched
        # (we never read/log it).
        auth = self.headers.get("Authorization")
        upstream = REAL_UPSTREAM.rstrip("/") + path
        req = urllib.request.Request(upstream, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("Authorization", auth)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            data = exc.read()
            status = exc.code
            ctype = "application/json"
        except Exception as exc:  # timeout/conn: no retry, still counted
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            _log({"ts": time.time(), "method": method, "path": path, "kind": "product",
                  "count": count, "model": model, "status": 502, "forwarded": True,
                  "reason": type(exc).__name__, "latency_s": round(time.monotonic() - started, 3)})
            return

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        _log({"ts": time.time(), "method": method, "path": path, "kind": "product",
              "count": count, "model": model, "status": status, "forwarded": True,
              "req_bytes": len(body), "resp_bytes": len(data),
              "latency_s": round(time.monotonic() - started, 3)})

    def do_POST(self):  # noqa: N802
        self._forward()

    def do_GET(self):  # noqa: N802
        self._forward()


def snapshot() -> dict:
    try:
        count = _read_count()
        return {"count": count, "cap": CAP, "remaining": max(0, CAP - count), "corrupt": False}
    except Corrupt as exc:
        return {"count": None, "cap": CAP, "remaining": None, "corrupt": True, "reason": str(exc)}


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18247
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"campaign guard on 127.0.0.1:{port} -> {REAL_UPSTREAM} (cap={CAP}); "
          f"snapshot={snapshot()}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
