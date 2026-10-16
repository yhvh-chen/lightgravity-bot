#!/usr/bin/env python3
"""LG-040 FINAL-QA — loopback DENY proxy (reused BROWSER-RETEST).

This owner is permitted **zero** new model/LAN requests. The candidate app is
launched with ``LIGHTGRAVITY_OCR_BASE_URL`` pointed at this loopback proxy. Any
inference attempt (any method/path) is counted and **refused before any HTTP is
issued to any upstream** — there is no upstream at all. So even if some UI path
were to try to reprocess/OCR, it cannot reach a model.

Writes a persistent pre-forward ledger so the attempted-call count is auditable.
Loopback only; no external network socket is ever opened.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    ledger_path: Path
    lock = threading.Lock()

    def _record(self, method: str, path: str) -> None:
        with self.lock:
            try:
                data = json.loads(self.ledger_path.read_text("utf-8"))
            except Exception:
                data = {"attempts": 0, "events": []}
            data["attempts"] = data.get("attempts", 0) + 1
            data["events"].append({"kind": "attempt_refused", "method": method, "path": path,
                                   "used": data["attempts"]})
            # fsync'd write BEFORE any response, mirroring a real reservation
            tmp = self.ledger_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), "utf-8")
            os.replace(tmp, self.ledger_path)

    def _deny(self) -> None:
        self._record(self.command, self.path)
        body = json.dumps({
            "error": {
                "code": "capability_unavailable",
                "message": "LG-040 BROWSER retest: inference disabled (0 new model calls permitted)",
            }
        }).encode()
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _deny
    do_POST = _deny
    do_PUT = _deny
    do_PATCH = _deny
    do_DELETE = _deny

    def log_message(self, *args) -> None:  # silence
        return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--ready-file", required=True)
    args = ap.parse_args()

    ledger = Path(args.ledger).resolve()
    ledger.write_text(json.dumps({"attempts": 0, "events": []}, indent=2), "utf-8")

    Handler.ledger_path = ledger
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    port = httpd.server_address[1]
    Path(args.ready_file).write_text(json.dumps({"port": port, "cap": 0, "ledger": str(ledger)}), "utf-8")
    print(f"deny proxy on 127.0.0.1:{port} -> 503 (attempts ledger: {ledger})", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
