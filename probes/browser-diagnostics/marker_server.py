#!/usr/bin/env python3
"""Minimal loopback HTTP marker server for browser diagnostics.

No SSE, no framework, no secrets. Logs every request line with a monotonic
timestamp and the peer address to stderr so we can prove whether the browser
actually reached the server. Bounded: exits after --lifetime seconds.

Writes a ready file with the bound port so the caller can wait deterministically.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

START = time.monotonic()


def log(msg: str) -> None:
    print(f"t={time.monotonic() - START:8.3f} {msg}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence default; we log our own
        pass

    def _record(self) -> None:
        log(f"REQ {self.command} {self.path} from={self.client_address[0]}:{self.client_address[1]} ua={self.headers.get('User-Agent','')[:40]}")

    def _cors(self) -> None:
        """Permit cross-origin reads so a data:/file: shell can fetch() the marker.

        Without this a renderer fetch from an opaque/file origin fails CORS
        *after* the response arrives, which is easily mistaken for "HTTP is
        blocked". Optional: enabled with --cors.
        """
        if getattr(self.server, "cors", False):
            self.send_header("Access-Control-Allow-Origin", "*")

    def do_GET(self):  # noqa: N802
        self._record()
        if self.path == "/marker":
            body = b"<html><body><div id='lg-marker'>MARKER-OK</div></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            log("RESP 200 /marker")
        elif self.path == "/health":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            log("RESP 200 /health")
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            log("RESP 404")

    def do_HEAD(self):  # noqa: N802
        self._record()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--ready-file", required=True)
    ap.add_argument("--lifetime", type=float, default=60.0)
    ap.add_argument("--cors", action="store_true", help="send Access-Control-Allow-Origin: * (for data:/file: shell fetches)")
    args = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.cors = args.cors  # type: ignore[attr-defined]
    port = srv.server_address[1]
    with open(args.ready_file, "w") as fh:
        json.dump({"port": port, "pid": __import__("os").getpid()}, fh)
    log(f"LISTEN 127.0.0.1:{port} pid={__import__('os').getpid()}")

    def shutdown():
        time.sleep(args.lifetime)
        log("LIFETIME reached, shutting down")
        srv.shutdown()

    threading.Thread(target=shutdown, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        log("CLOSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
