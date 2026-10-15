"""LG-022 reverify R2 — service-proxy level persistent-ledger + fail-closed proof.

Exercises the REAL product pieces (no product code changes, NO DeepSeek):
  * a real ``LocalAuthProxy`` (loopback auth proxy) pointed at a CONTROLLED local
    fake OpenAI-compatible upstream (``allow_loopback_upstream=True``);
  * the REAL ``configure_generation_ledger`` / ``GenerationCounter`` used by the
    app (same functions the API diagnostics endpoint reads);
  * ``GET /api/v1/diagnostics/generation`` shape via ``global_generation_counter().snapshot()``.

Proves:
  P1  a forwarded proxy request increments the persistent count (reserve BEFORE forward).
  P2  the count is persisted at ``<data_dir>/generation/`` and a FRESH process
      rebuild via ``configure_generation_ledger`` reads the same count (no reset).
  P3  limit reached => proxy returns 429 and forwards NOTHING (fake upstream call count frozen).
  P4  corrupt ledger => snapshot reports ``corrupt``/unknown, reserve refused, no forward.

Two-process restart is done with a real subprocess (see ``--phase read``).

Run:
  .venv/bin/python service_ledger_proof.py forward <workdir> <out_json>
  .venv/bin/python service_ledger_proof.py read    <workdir> <out_json>
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

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter.credentials import Secret  # noqa: E402

FAKE_UPSTREAM_CALLS = 0


class _FakeUpstream(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa: D102
        return

    def do_POST(self):  # noqa: N802
        global FAKE_UPSTREAM_CALLS
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length)
        FAKE_UPSTREAM_CALLS += 1
        body = json.dumps(
            {
                "id": "fake-1",
                "object": "chat.completion",
                "model": "fake",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_fake_upstream() -> tuple[http.server.ThreadingHTTPServer, int, threading.Thread]:
    port = free_port()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _FakeUpstream)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port, t


def proxy_call(proxy_url: str) -> int:
    req = urllib.request.Request(
        proxy_url,
        data=json.dumps({"model": "fake", "messages": [{"role": "user", "content": "hi"}]}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            _ = resp.read()
            return resp.status
    except urllib.error.HTTPError as exc:
        _ = exc.read()
        return exc.code


def do_forward(work: Path, out: Path) -> int:
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = "3"
    from lightgravity.adapter.proxy import LocalAuthProxy, configure_generation_ledger
    from lightgravity.adapter.proxy import global_generation_counter  # noqa: F401

    data_dir = work / "restart"
    srv, fake_port, _ = start_fake_upstream()
    upstream = f"http://127.0.0.1:{fake_port}/v1/chat/completions"

    counter = configure_generation_ledger(data_dir, limit=3)
    proxy = LocalAuthProxy(
        credential=Secret("fake-key"),  # fake loopback upstream ignores auth
        upstream_url=upstream,
        max_calls=64,
        allow_loopback_upstream=True,
        generation_budget=counter,
    )
    proxy.start()
    result: dict[str, object] = {}
    try:
        url = f"http://127.0.0.1:{proxy.port}/{proxy.session_token}/v1/chat/completions"
        # P1: three allowed forwards (limit=3)
        p1_statuses = [proxy_call(url) for _ in range(3)]
        snap_after_3 = global_generation_counter().snapshot()
        # P3: 4th is denied at the global cap -> 429, upstream NOT called
        upstream_before_4th = FAKE_UPSTREAM_CALLS
        p3_status = proxy_call(url)
        upstream_after_4th = FAKE_UPSTREAM_CALLS
        result = {
            "phase": "forward",
            "data_dir": str(data_dir),
            "p1_statuses_3_allowed": p1_statuses,
            "snapshot_after_3": snap_after_3,
            "P1_count_increments": snap_after_3.get("count") == 3,
            "P3_status_4th": p3_status,
            "P3_upstream_calls_delta_for_denied": upstream_after_4th - upstream_before_4th,
            "P3_denied_no_forward": p3_status == 429 and upstream_after_4th == upstream_before_4th,
            "total_fake_upstream_calls": FAKE_UPSTREAM_CALLS,
            "real_model_calls": 0,
        }
    finally:
        if hasattr(proxy, "stop"):
            proxy.stop()
        srv.shutdown()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"phase": "forward", "P1": result["P1_count_increments"], "P3": result["P3_denied_no_forward"], "snapshot": result["snapshot_after_3"]}, sort_keys=True))
    return 0 if result["P1_count_increments"] and result["P3_denied_no_forward"] else 1


def do_read(work: Path, out: Path) -> int:
    from lightgravity.adapter.proxy import configure_generation_ledger
    data_dir = work / "restart"
    counter = configure_generation_ledger(data_dir, limit=3)  # rebuild from SAME ledger
    snap = counter.snapshot()
    result = {
        "phase": "read_fresh_process",
        "snapshot": snap,
        "P2_persisted": snap.get("count") == 3 and snap.get("persistent") is True,
        "real_model_calls": 0,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["P2_persisted"] else 1


def do_corrupt(work: Path, out: Path) -> int:
    """P4: corrupt the ledger then confirm the proxy refuses to forward."""
    os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = "3"
    from lightgravity.adapter.proxy import LocalAuthProxy, configure_generation_ledger, global_generation_counter
    data_dir = work / "corrupt"
    data_dir.mkdir(parents=True, exist_ok=True)
    counter = configure_generation_ledger(data_dir, limit=3)
    counter.reserve()  # create ledger files
    # corrupt history
    (data_dir / "generation" / "generation.jsonl").write_text("{ not json\n", encoding="utf-8")
    snap = global_generation_counter().snapshot()
    srv, fake_port, _ = start_fake_upstream()
    proxy = LocalAuthProxy(
        credential=Secret("fake-key"),
        upstream_url=f"http://127.0.0.1:{fake_port}/v1/chat/completions",
        max_calls=64, allow_loopback_upstream=True, generation_budget=counter,
    )
    proxy.start()
    try:
        url = f"http://127.0.0.1:{proxy.port}/{proxy.session_token}/v1/chat/completions"
        status = proxy_call(url)
    finally:
        if hasattr(proxy, "stop"):
            proxy.stop()
        srv.shutdown()
    result = {
        "phase": "corrupt",
        "snapshot": snap,
        "corrupt_status": status,
        "upstream_calls": FAKE_UPSTREAM_CALLS,
        "P4_corrupt_unknown_not_zero": snap.get("count") is None and snap.get("corrupt") is True,
        "P4_refused_forward": status == 429 and FAKE_UPSTREAM_CALLS == 0,
        "real_model_calls": 0,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("snapshot", "corrupt_status", "upstream_calls", "P4_corrupt_unknown_not_zero", "P4_refused_forward")}, sort_keys=True))
    return 0 if result["P4_corrupt_unknown_not_zero"] and result["P4_refused_forward"] else 1


def main() -> int:
    mode = sys.argv[1]
    work = Path(sys.argv[2])
    out = Path(sys.argv[3])
    if mode == "forward":
        return do_forward(work, out)
    if mode == "read":
        return do_read(work, out)
    if mode == "corrupt":
        return do_corrupt(work, out)
    print("unknown mode", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
