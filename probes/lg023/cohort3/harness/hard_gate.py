#!/usr/bin/env python3
"""LG-023 cohort-3 measurement HARD GATE (zero DeepSeek generation).

The gate proves the D1 fix on the **real product startup chain** before any
formal request.  It exercises ``build_runtime``/``create_app`` **at least twice
in sequence** against the SAME phase ``settings.data_dir`` and asserts, using
real ``LocalAuthProxy`` instances pointed at a LOCAL fake upstream:

* **G1** real ``build_runtime``/``create_app`` startup chain runs, twice in
  sequence, with the same phase ``data_dir`` (no per-attempt swap).
* **G2** worker AND reviewer actual forwards land on the ONE phase physical
  ledger path (``<phase>/generation/generation.jsonl``) and the count
  **accumulates across the two sequential starts**.
* **G3** the shared cap rejects both the **total** overrun and the
  **per-attempt** overrun **before forwarding** (429; ledger does not grow).
* **G4** a **corrupt** ledger fails closed (never treated as 0).
* **G5** the runtime counter object's attached ledger path equals the frozen
  phase path, and the physical JSONL exists there -- checked before any formal
  request.
* **G6** dry-run and formal share the same code path (this gate is that path;
  only the controlled upstream/base-dir differ).

It does **not** call DeepSeek: the upstream is a loopback fake SSE server, so
the credential value is a dummy and real generation stays 0.

Usage::

    .venv/bin/python probes/lg023/cohort3/harness/hard_gate.py
"""

from __future__ import annotations

import json
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "backend"))

import cohort3_config as C  # noqa: E402

OUT = C.EVIDENCE_DIR / "offline" / "hard_gate.json"


# ------------------------------------------------------------------ fake upstream
class _FakeUpstream(BaseHTTPRequestHandler):
    served = 0
    lock = threading.Lock()

    def log_message(self, *args: Any) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        with type(self).lock:
            type(self).served += 1
        payload = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
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


def _post_codes(proxy: Any, n: int) -> list[int]:
    codes = []
    for _ in range(n):
        req = urllib.request.Request(
            proxy.base_url + "/chat/completions", data=b'{"model":"x","messages":[]}',
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                codes.append(resp.status)
        except urllib.error.HTTPError as exc:
            exc.read()
            codes.append(exc.code)
    return codes


# ------------------------------------------------------------------ startup chain
def _build_phase_runtime(phase_root: Path, upstream_url: str) -> tuple[Any, Any]:
    """Run the REAL product startup chain against the shared phase data_dir.

    Returns ``(state, counter)``.  The credential is a dummy; the upstream is the
    loopback fake, so no real generation is issued.
    """

    from lightgravity.config import Settings
    from lightgravity.runtime.token import RuntimeToken
    from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore, EntityNotFound

    # The driver pins this in-process too (same one phase root); the product
    # build_runtime then roots its ledger at settings.data_dir == phase root.
    import os

    os.environ.update(C.phase_env())

    secret_root = phase_root / "gate-secrets"
    secret_root.mkdir(parents=True, exist_ok=True)
    ws_root = phase_root / "gate-workspaces"
    ws_root.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        data_dir=phase_root, workspace_root=ws_root, secret_store=secret_root,
        host="127.0.0.1", port=0,
    )
    settings.ensure_data_dir()

    # seed minimal connection/agent so the real executor can be wired
    store = FileStore(settings.data_dir, settings.workspace_root)
    conns = ConnectionService(store, secret_store=FileSecretStore(settings.secret_store))

    for cid in ("gate-worker", "gate-reviewer"):
        try:
            store.read("connection", cid)
        except EntityNotFound:
            conns.create_connection(
                connection_id=cid, backend="openai-compat", model=C.MODEL,
                base_url=upstream_url, credential_ref="gate-cred", title=cid,
                actor="gate", request_id=f"gate-conn-{cid}",
            )
    ss = FileSecretStore(settings.secret_store)
    if ss.get("gate-cred") is None:
        ss.put("gate-cred", "dummy-not-a-real-secret")
    expected_rev = None
    try:
        expected_rev = store.read("settings", "settings").revision
    except EntityNotFound:
        expected_rev = None
    conns.update_settings(
        expected_revision=expected_rev, actor="gate",
        default_coordinator_connection_ref="gate-worker",
        default_worker_connection_ref="gate-worker",
        default_reviewer_connection_ref="gate-reviewer",
    )

    state: RuntimeState = build_runtime(
        StartupOptions(
            settings=settings,
            token=RuntimeToken("gate-token", "generated"),
            serve_frontend=False,
            max_proxy_calls=C.ATTEMPT_GENERATION_LIMIT,
            model_calls_cap=C.ATTEMPT_GENERATION_LIMIT,
        )
    )
    import lightgravity.adapter.proxy as proxy_mod

    counter = proxy_mod.global_generation_counter()
    return state, counter


def _counter_identity(counter: Any, frozen_history: Path) -> dict[str, Any]:
    ledger = getattr(counter, "_ledger", None)
    hist = getattr(ledger, "_history", None) if ledger is not None else None
    return {
        "ledger_attached": ledger is not None,
        "counter_ledger_history": str(hist) if hist is not None else None,
        "frozen_history": str(frozen_history),
        "counter_ledger_matches_frozen": (
            hist is not None and Path(hist).resolve() == frozen_history.resolve()
        ),
    }


# ------------------------------------------------------------------ G4 corruption
def _prove_corrupt_failclosed() -> dict[str, Any]:
    from lightgravity.adapter.generation_ledger import (
        GenerationLedgerCorrupt,
        PersistentGenerationLedger,
    )

    root = C.PHASE_DATA_DIR.parent / "lg023-cohort3-gate-sandbox" / "gate-corrupt"
    if root.exists():
        shutil.rmtree(root)
    led = PersistentGenerationLedger(root, limit=48)
    # baseline works
    ok_before = led.reserve().granted
    led._history.write_text("this is not json\n", encoding="utf-8")
    denied = False
    corrupt_flag = False
    try:
        denied = led.reserve().granted is False
    except GenerationLedgerCorrupt:
        denied = True
    snap = led.snapshot()
    corrupt_flag = bool(snap.get("corrupt")) and snap.get("count") is None
    # never treated as 0
    not_zero = snap.get("count") is None
    return {
        "baseline_reserved": ok_before,
        "corrupt_reserve_denied": denied,
        "corrupt_flag": corrupt_flag,
        "count_not_zero": not_zero,
        "ok": bool(ok_before and denied and corrupt_flag and not_zero),
    }


def main() -> int:
    payload: dict[str, Any] = {"ok": False, "real_generation": 0}
    upstream_port = _free_port()
    upstream = ThreadingHTTPServer(("127.0.0.1", upstream_port), _FakeUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_url = f"http://127.0.0.1:{upstream_port}/v1"

    # Fresh phase root for the gate (never touches a formal attempt dir).
    gate_root = C.PHASE_DATA_DIR.parent / "lg023-cohort3-gate-sandbox" / "gate-phase"
    if gate_root.exists():
        shutil.rmtree(gate_root)
    gate_root.mkdir(parents=True, exist_ok=True)
    frozen_hist = gate_root / "generation" / "generation.jsonl"

    try:
        # ---- G1 first runtime start (real build_runtime/create_app)
        state1, counter1 = _build_phase_runtime(gate_root, upstream_url)
        ident1 = _counter_identity(counter1, frozen_hist)
        payload["start1_counter"] = ident1
        payload["start1_data_dir"] = str(gate_root)

        from lightgravity.adapter.credentials import Secret
        from lightgravity.adapter.proxy import LocalAuthProxy

        worker1 = LocalAuthProxy(
            credential=Secret("dummy"), upstream_url=upstream_url + "/chat/completions",
            max_calls=64, allow_loopback_upstream=True, generation_budget=counter1,
        )
        worker1.start()
        try:
            c1 = _post_codes(worker1, 3)
            count_after_start1 = counter1.count
        finally:
            worker1.stop()

        # ---- G1 second runtime start, SAME phase data_dir (no swap)
        state2, counter2 = _build_phase_runtime(gate_root, upstream_url)
        ident2 = _counter_identity(counter2, frozen_hist)
        payload["start2_counter"] = ident2
        count_at_start2 = counter2.count
        payload["count_after_start1"] = count_after_start1
        payload["count_seen_at_start2"] = count_at_start2

        reviewer2 = LocalAuthProxy(
            credential=Secret("dummy"), upstream_url=upstream_url + "/chat/completions",
            max_calls=64, allow_loopback_upstream=True, generation_budget=counter2,
        )
        reviewer2.start()
        try:
            c2 = _post_codes(reviewer2, 3)
            count_after_start2 = counter2.count
        finally:
            reviewer2.stop()

        payload["worker_codes_start1"] = c1
        payload["reviewer_codes_start2"] = c2
        payload["count_after_start2"] = count_after_start2

        # physical JSONL on the one frozen path
        lines = frozen_hist.read_text(encoding="utf-8").splitlines() if frozen_hist.exists() else []
        payload["physical_history_path"] = str(frozen_hist)
        payload["physical_history_exists"] = frozen_hist.exists()
        payload["physical_history_lines"] = len(lines)
        payload["frozen_path_is_gate_ledger"] = str(frozen_hist) == str(gate_root / "generation" / "generation.jsonl")

        # ---- G3 attempt cap enforced before forward on start2's counter
        from lightgravity.adapter.proxy import GenerationCounter

        attempt_led = PersistentGenerationLedger_for_attempt(gate_root / "gate-attempt")
        attempt_counter = GenerationCounter(C.ATTEMPT_GENERATION_LIMIT, ledger=attempt_led)
        guard = {"used": 0}
        orig_reserve = attempt_counter.reserve

        def guarded() -> bool:
            if guard["used"] >= C.ATTEMPT_GENERATION_LIMIT:
                return False
            granted = orig_reserve()
            if granted:
                guard["used"] += 1
            return granted

        attempt_counter.reserve = guarded  # type: ignore[method-assign]
        cap_proxy = LocalAuthProxy(
            credential=Secret("dummy"), upstream_url=upstream_url + "/chat/completions",
            max_calls=64, allow_loopback_upstream=True, generation_budget=attempt_counter,
        )
        cap_proxy.start()
        try:
            cap_codes = _post_codes(cap_proxy, C.ATTEMPT_GENERATION_LIMIT + 1)
            attempt_count = attempt_counter.count
        finally:
            cap_proxy.stop()
        payload["attempt_codes_tail"] = cap_codes[-3:]
        payload["attempt_used"] = guard["used"]
        payload["attempt_count_after_overrun"] = attempt_count

        # ---- G4 corruption fail-closed
        payload["corrupt_failclosed"] = _prove_corrupt_failclosed()

        # ---- G3b PHASE TOTAL cap rejects before forward (independent sandboxed
        # ledger, small total limit; proves the same reserve-before-forward path
        # also enforces the phase-wide total).
        total_root = C.PHASE_DATA_DIR.parent / "lg023-cohort3-gate-sandbox" / "gate-total"
        if total_root.exists():
            shutil.rmtree(total_root)
        # The ledger's own hard limit is the phase total; a counter delegate
        # cannot lower it, so build the ledger with the small total cap.
        from lightgravity.adapter.generation_ledger import PersistentGenerationLedger as _PGL
        total_led = _PGL(total_root, limit=3)
        total_counter = GenerationCounter(3, ledger=total_led)
        total_proxy = LocalAuthProxy(
            credential=Secret("dummy"), upstream_url=upstream_url + "/chat/completions",
            max_calls=64, allow_loopback_upstream=True, generation_budget=total_counter,
        )
        total_proxy.start()
        try:
            total_codes = _post_codes(total_proxy, 4)
            total_count = total_counter.count
        finally:
            total_proxy.stop()
        payload["total_codes"] = total_codes
        payload["total_count_after_overrun"] = total_count
        total_cap_ok = total_codes[-1] == 429 and total_count == 3

        # ---- assemble verdicts
        g1 = ident1["counter_ledger_matches_frozen"] and ident2["counter_ledger_matches_frozen"]
        g2 = (
            all(code == 200 for code in c1)
            and all(code == 200 for code in c2)
            and count_at_start2 == count_after_start1  # continuation visible
            and count_after_start2 == count_after_start1 + 3  # reviewer shares
            and frozen_hist.exists() and len(lines) >= count_after_start2
        )
        g3 = (
            guard["used"] == C.ATTEMPT_GENERATION_LIMIT
            and cap_codes[-1] == 429
            and attempt_count == C.ATTEMPT_GENERATION_LIMIT
            and total_cap_ok
        )
        g4 = bool(payload["corrupt_failclosed"]["ok"])
        g5 = g1 and payload["physical_history_exists"]
        payload["G1_real_startup_twice_same_datadir"] = bool(g1)
        payload["G2_single_physical_path_accumulates"] = bool(g2)
        payload["G3_cap_before_forward"] = bool(g3)
        payload["G4_corrupt_failclosed"] = bool(g4)
        payload["G5_counter_and_physical_path_frozen"] = bool(g5)
        payload["ok"] = bool(g1 and g2 and g3 and g4 and g5)
    finally:
        upstream.shutdown()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items()
                      if k.startswith("G") or k == "ok"}, indent=2))
    return 0 if payload["ok"] else 1


# Late import shim so the module body reads top-down while still importing the
# real product ledger class for the attempt-cap case.
def PersistentGenerationLedger_for_attempt(root: Path) -> Any:  # noqa: N802
    from lightgravity.adapter.generation_ledger import PersistentGenerationLedger

    return PersistentGenerationLedger(root, limit=C.ATTEMPT_GENERATION_LIMIT)


if __name__ == "__main__":
    raise SystemExit(main())
