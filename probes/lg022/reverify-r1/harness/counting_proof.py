"""LG-022 reverify R1 — counting-gate proof with a LOCAL FAKE upstream.

Purpose (计量先行, hard gate): prove the shared persistent forward counter
behaves correctly BEFORE any real DeepSeek generation request is made.  Uses a
loopback fake OpenAI-compatible upstream so this script makes **0 real
generation requests**.

Proves:
  C1 counting: every forwarded chat completion increments the shared counter
     (counter.count == number of forwards).
  C2 cap reject: once the shared limit is exhausted, `reserve()` denies and the
     request is answered 429 WITHOUT being forwarded upstream.
  C3 cross-session share: two Independent proxies over different sessions share
     one counter (one global limit across sessions/roles).
  C4 restart semantics: read the counter from a *fresh interpreter* to see
     whether a service restart resets it (persistence claim check).  This
     script records the observed fact; it does not fake it.

Run: uv run python probes/lg022/reverify-r1/harness/counting_proof.py <out_json>
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter.proxy import (  # noqa: E402
    GenerationCounter,
    LocalAuthProxy,
    global_generation_counter,
)


class _FakeUpstream(http.server.BaseHTTPRequestHandler):
    """Tiny OpenAI-compatible SSE upstream; counts what actually reached it."""

    protocol_version = "HTTP/1.1"
    received: list[dict] = []

    def log_message(self, *a):  # noqa: D102
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).received.append({"path": self.path, "bytes": len(body)})
        payload = (
            'data: {"id":"x","object":"chat.completion.chunk","choices":'
            '[{"index":0,"delta":{"role":"assistant","content":"OK"}}]}\n\n'
            "data: [DONE]\n\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_fake() -> tuple[http.server.ThreadingHTTPServer, int, threading.Thread]:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1], t


def _post(proxy: LocalAuthProxy, token: str) -> int:
    url = f"{proxy.base_url}/chat/completions"
    data = json.dumps({"model": "fake", "messages": [{"role": "user", "content": "hi"}], "stream": True}).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
            return resp.status
    except urllib.error.HTTPError as exc:
        _ = exc.read()
        return exc.code


from lightgravity.adapter.credentials import Secret  # noqa: E402


def main() -> int:
    out_path = Path(sys.argv[1])
    results: dict = {"evidence_kind": "local-fake-upstream", "real_generation_calls": 0, "checks": {}}

    srv, fake_port, _ = _start_fake()
    fake_url = f"http://127.0.0.1:{fake_port}/v1"
    cred = Secret("sk-fake-not-real")

    try:
        # ---- C1 counting + C2 cap reject (limit=2), C3 cross-session share
        counter = GenerationCounter(limit=2)
        p1 = LocalAuthProxy(credential=cred, upstream_url=fake_url, max_calls=64,
                            allow_loopback_upstream=True, generation_budget=counter)
        p1.start()
        s1 = _post(p1, p1.session_token)
        s2 = _post(p1, p1.session_token)
        s3 = _post(p1, p1.session_token)  # denied by shared cap, not forwarded
        forwarded_after_cap = len(_FakeUpstream.received)
        p1.stop()

        # cross-session: a fresh proxy with the same counter must also be capped
        p2 = LocalAuthProxy(credential=cred, upstream_url=fake_url, max_calls=64,
                            allow_loopback_upstream=True, generation_budget=counter)
        p2.start()
        s4 = _post(p2, p2.session_token)
        forwarded_after_second_session = len(_FakeUpstream.received)
        p2.stop()

        results["checks"]["C1_counting"] = {
            "counter_count": counter.count,
            "expected": 2,
            "ok": counter.count == 2,
            "first_two_status": [s1, s2],
            "forwarded_upstream_calls": forwarded_after_cap,
        }
        results["checks"]["C2_cap_reject"] = {
            "third_status": s3,
            "ok": s3 == 429 and forwarded_after_cap == 2,
            "snapshot": counter.snapshot(),
        }
        results["checks"]["C3_cross_session_share"] = {
            "second_session_status": s4,
            "ok": s4 == 429 and forwarded_after_second_session == 2
            and counter.count == 2,
        }

        # ---- C4 restart semantics: fresh interpreter, same env limit
        env = dict(os.environ)
        env["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = "10"
        code = (
            "import sys;sys.path.insert(0,%r);"
            "from lightgravity.adapter.proxy import global_generation_counter as g;"
            "print(g().snapshot())" % str(REPO / "backend")
        )
        proc = subprocess.run([sys.executable, "-c", code], env=env,
                              capture_output=True, text=True, timeout=30)
        fresh_snapshot = proc.stdout.strip()
        results["checks"]["C4_restart_persistence"] = {
            "fresh_interpreter_snapshot": fresh_snapshot,
            "persisted_across_restart": "count': 0" not in fresh_snapshot,
            "observed": (
                "counter is a process-global in-memory object; a fresh process "
                "starts from count=0 (limit re-read from env)"
            ),
            "ok": False,  # honest: no persistence implemented
        }
        results["checks"]["env_limit_default"] = {
            "global_limit_after_env_read": global_generation_counter().snapshot(),
        }
    finally:
        srv.shutdown()

    results["all_ok"] = all(
        c.get("ok") for c in results["checks"].values() if "ok" in c
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print("WROTE", out_path)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if results["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
