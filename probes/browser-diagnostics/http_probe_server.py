#!/usr/bin/env python3
"""Real loopback HTTP acceptance server for browser diagnostics (LG-013/021/027).

This is a *real* HTTP/1.1 server, not a mock: a real HTML document, a real
JSON API, and a real Server-Sent-Events stream. It logs every request with a
monotonic timestamp, peer address, method, path, the ``Origin`` request header
and a truncated ``User-Agent`` so an acceptance run can prove what the browser
actually sent on the wire.

Nothing here injects fake business data into a product server and nothing here
turns off browser security. It is a standalone QA transport fixture.

Endpoints
---------
GET /health        -> {"ok":true}
GET /api/echo      -> {"ok":true,"source":"server","path":"/api/echo",...}
GET /sse           -> text/event-stream, N real events then one ``done`` event
GET /page          -> a real HTML document that (a) renders a marker and
                      (b) fetches /api/echo and opens /sse, so a browser that
                      can reach this origin exercises API + SSE from the page.
GET /marker        -> tiny HTML marker used by the older smoke helper.

Usage
-----
  python3 http_probe_server.py --ready-file /tmp/ready.json [--port 0]
      [--lifetime 60] [--cors] [--sse-events 3] [--sse-interval-ms 150]

Writes ``{"port":<int>,"pid":<int>}`` to ``--ready-file`` so callers can wait
deterministically, and exits after ``--lifetime`` seconds.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

START = time.monotonic()
SSE_EVENTS = 3
SSE_INTERVAL_MS = 150


def log(msg: str) -> None:
    print(f"t={time.monotonic() - START:8.3f} {msg}", file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence default; we log our own
        pass

    # -- helpers -----------------------------------------------------------
    def _record(self) -> None:
        log(
            "REQ {m} {p} from={a}:{b} origin={o} ua={u!r}".format(
                m=self.command,
                p=self.path,
                a=self.client_address[0],
                b=self.client_address[1],
                o=self.headers.get("Origin", "-"),
                u=self.headers.get("User-Agent", "")[:48],
            )
        )

    def _cors(self) -> None:
        """Cross-origin read access for a file:// / about:blank QA shell.

        This is only about the *renderer origin* of the QA shell, not about
        disabling web security: the browser still enforces CORS and the server
        still decides. Enabled with --cors.
        """
        if getattr(self.server, "cors", False):
            self.send_header("Access-Control-Allow-Origin", "*")

    def _send(self, code: int, ctype: str, body: bytes, extra=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    # -- routes ------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        self._record()
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, "application/json", b'{"ok":true}')
        elif path == "/api/echo":
            body = json.dumps(
                {"ok": True, "source": "server", "path": "/api/echo", "t": round(time.monotonic() - START, 3)},
                separators=(",", ":"),
            ).encode()
            self._send(200, "application/json", body)
        elif path == "/sse":
            self._sse()
        elif path == "/page":
            self._send(200, "text/html; charset=utf-8", PAGE_HTML.encode())
        elif path == "/marker":
            self._send(200, "text/html; charset=utf-8", b"<html><body><div id='lg-marker'>MARKER-OK</div></body></html>")
        else:
            self._send(404, "text/plain", b"")

    def _sse(self) -> None:
        """Emit N real events, then a terminal ``done`` event, then close.

        Real streaming: headers flushed first, one chunk per event, with a
        short interval so a reader can observe incremental delivery.
        """
        n_events = getattr(self.server, "sse_events", SSE_EVENTS)
        interval = getattr(self.server, "sse_interval_ms", SSE_INTERVAL_MS) / 1000.0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        self.wfile.flush()
        log(f"SSE open path={self.path} events={n_events} interval_ms={int(interval * 1000)}")
        try:
            for i in range(1, n_events + 1):
                payload = json.dumps({"n": i, "t": round(time.monotonic() - START, 3)}, separators=(",", ":"))
                self.wfile.write(f"event: tick\ndata: {payload}\n\n".encode())
                self.wfile.flush()
                log(f"SSE tick n={i}")
                time.sleep(interval)
            self.wfile.write(b'event: done\ndata: {"n":%d}\n\n' % n_events)
            self.wfile.flush()
            log("SSE done")
        except (BrokenPipeError, ConnectionResetError):
            log("SSE client disconnected early")

    def do_HEAD(self):  # noqa: N802
        self._record()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>LG HTTP acceptance page</title></head>
<body>
<div id="lg-origin">LOADING</div>
<div id="lg-api">PENDING</div>
<div id="lg-sse">PENDING</div>
<script>
document.getElementById('lg-origin').textContent = location.origin;
fetch('/api/echo')
  .then(function (r) { return r.json(); })
  .then(function (j) { document.getElementById('lg-api').textContent = 'API:' + j.source + ':' + j.ok; })
  .catch(function (e) { document.getElementById('lg-api').textContent = 'APIERR:' + e.message; });
try {
  var got = [];
  var es = new EventSource('/sse');
  es.addEventListener('tick', function (e) { got.push(JSON.parse(e.data).n); });
  es.addEventListener('done', function () {
    document.getElementById('lg-sse').textContent = 'SSE:' + got.join(',');
    es.close();
  });
  es.onerror = function () { document.getElementById('lg-sse').textContent = 'SSEERR'; };
} catch (e) {
  document.getElementById('lg-sse').textContent = 'SSEERR:' + e.message;
}
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--ready-file", required=True)
    ap.add_argument("--lifetime", type=float, default=60.0)
    ap.add_argument("--cors", action="store_true", help="send Access-Control-Allow-Origin: * (for file:// / about:blank QA shells)")
    ap.add_argument("--sse-events", type=int, default=SSE_EVENTS)
    ap.add_argument("--sse-interval-ms", type=int, default=SSE_INTERVAL_MS)
    args = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.cors = args.cors  # type: ignore[attr-defined]
    srv.sse_events = args.sse_events  # type: ignore[attr-defined]
    srv.sse_interval_ms = args.sse_interval_ms  # type: ignore[attr-defined]
    port = srv.server_address[1]
    with open(args.ready_file, "w") as fh:
        json.dump({"port": port, "pid": os.getpid()}, fh)
    log(f"LISTEN 127.0.0.1:{port} pid={os.getpid()} cors={args.cors}")

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
