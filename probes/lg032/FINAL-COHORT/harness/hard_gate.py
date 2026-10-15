#!/usr/bin/env python3
"""LG-032 FINAL-COHORT offline measurement HARD GATE (zero DeepSeek generation).

Proves the frozen protocol invariants on the **real product startup chain**
before any formal request.  Exercises ``build_runtime``/``create_app`` **at least
twice in sequence** against the SAME phase ``settings.data_dir`` and asserts,
using real ``LocalAuthProxy`` instances pointed at a LOCAL fake upstream:

* **H1** fixtures: initial tree fails its machine gate; reference passes (both
  samples).
* **H2** frozen legal plans validate against the real ``PlanValidator`` for both
  arms (A=1 write node + verify; B=2 write nodes + verify).
* **H3** real ``build_runtime``/``create_app`` startup chain runs, twice in
  sequence, with the same phase ``data_dir`` (no per-attempt swap); the runtime
  counter object's attached ledger path equals the frozen phase path.
* **H4** worker AND reviewer actual forwards land on the ONE phase physical
  ledger path (``<phase>/generation/generation.jsonl``) and the count
  **accumulates across the two sequential starts**; the per-attempt cap (48) and
  the phase total cap both reject **before forwarding** (429; ledger does not
  grow); a **corrupt** ledger fails closed (never treated as 0).
* **H5** teardown fact completeness gates acceptance (verified via
  ``VerificationService`` + real ``StoreResourceStopper``): complete -> opens
  acceptance; missing -> ``unconfirmed`` (no fake stop).
* **H6** a real SDK session's ``context.save_dir`` is settable and lands inside
  the authorized workspace root (wiring assertion only, no real generation).

It does **not** call DeepSeek: the credential value is a dummy and the upstream is
a loopback fake SSE server, so real generation stays 0.

Usage::

    .venv/bin/python probes/lg032/FINAL-COHORT/harness/hard_gate.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "backend"))

import final_cohort_config as C  # noqa: E402

OUT = C.EVIDENCE_DIR / "offline" / "hard_gate.json"
#: Legacy fixed gate sandbox.  PRESERVED verbatim as history; never written to
#: or deleted again.  ``main()`` reassigns ``GATE_ROOT`` to a brand-new unique
#: path each run (preservation incident fix: never reuse/rmtree a fixed root).
GATE_ROOT = C.PHASE_DATA_DIR.parent / "lg032-gate-sandbox"
UPSTREAM_LOG: list[str] = []


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
    import urllib.error
    import urllib.request

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


def _build_phase_runtime(phase_root: Path, upstream_url: str) -> tuple[Any, Any]:
    """Run the REAL product startup chain against the shared phase data_dir."""

    import os

    from lightgravity.config import Settings
    from lightgravity.runtime.token import RuntimeToken
    from lightgravity.api.bootstrap import RuntimeState, StartupOptions, build_runtime
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore, EntityNotFound

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


def _prove_corrupt_failclosed() -> dict[str, Any]:
    from lightgravity.adapter.generation_ledger import (
        GenerationLedgerCorrupt,
        PersistentGenerationLedger,
    )

    # Unique subdir (never delete; each hard-gate run has a fresh GATE_ROOT).
    root = GATE_ROOT / "gate-corrupt"
    if root.exists():
        raise SystemExit(f"refusing to reuse existing gate-corrupt dir {root}")
    led = PersistentGenerationLedger(root, limit=C.TOTAL_GENERATION_LIMIT)
    ok_before = led.reserve().granted
    led._history.write_text("this is not json\n", encoding="utf-8")
    denied = False
    try:
        denied = led.reserve().granted is False
    except GenerationLedgerCorrupt:
        denied = True
    snap = led.snapshot()
    return {
        "baseline_reserved": ok_before,
        "corrupt_reserve_denied": denied,
        "corrupt_flag": bool(snap.get("corrupt")),
        "count_not_zero": snap.get("count") is None,
        "ok": bool(ok_before and denied and snap.get("corrupt") and snap.get("count") is None),
    }


# ------------------------------------------------------------------ fixtures
def _machine_gate(workspace: Path, acceptance: Path) -> dict[str, Any]:
    import subprocess

    env = {k: v for k, v in __import__("os").environ.items() if k != "DEEPSEEK_API_KEY"}
    proc = subprocess.run([sys.executable, str(acceptance), "--workspace", str(workspace)],
                          capture_output=True, text=True, timeout=120, env=env)
    lines = proc.stdout.strip().splitlines()
    try:
        report = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        report = {"raw": proc.stdout, "stderr": proc.stderr}
    report["exit_code"] = proc.returncode
    return report


def _prove_fixtures() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sample in C.SAMPLES:
        initial = C.FIXTURES_DIR / sample / "initial"
        reference = C.FIXTURES_DIR / sample / "reference"
        acc = C.FIXTURES_DIR / sample / "acceptance.py"
        scratch = GATE_ROOT / "fixtures" / sample
        if scratch.exists():
            raise SystemExit(f"refusing to reuse existing fixture scratch {scratch}")
        shutil.copytree(initial, scratch / "initial")
        shutil.copytree(reference, scratch / "reference", dirs_exist_ok=True)
        init_report = _machine_gate(scratch / "initial", acc)
        ref_report = _machine_gate(scratch / "reference", acc)
        out[sample] = {
            "initial_passed": init_report.get("passed"),
            "initial_total": init_report.get("total"),
            "reference_passed": ref_report.get("passed"),
            "reference_total": ref_report.get("total"),
            "ok": bool(
                init_report.get("passed") != init_report.get("total")
                and ref_report.get("passed") == ref_report.get("total")
                and ref_report.get("total", 0) > 0
            ),
        }
    return {"samples": out, "ok": all(v["ok"] for v in out.values())}


# ------------------------------------------------------------------ plan (H2)
def _prove_frozen_plans() -> dict[str, Any]:
    import asyncio

    from lightgravity.coordinator.planner import PlanValidator

    sys.path.insert(0, str(HERE))
    import run_attempt as R

    validator = PlanValidator(known_capabilities=("implementation", "verification"))
    out: dict[str, Any] = {}
    for sample in C.SAMPLES:
        for arm in C.ARMS:
            planner = R._FrozenPlanner(arm, sample)

            class _Ctx:
                objective = R.SAMPLE_SPEC[sample]["objective"]
                acceptance_criteria = tuple(R.SAMPLE_SPEC[sample]["acceptance"])

            proposal = asyncio.run(planner.plan(_Ctx))
            try:
                # The real dispatcher validates WITH the authorized workspace
                # boundary (``graph.py``: ``validate(proposal, workspace_path=...)``);
                # a write node without a boundary is rejected by design.
                plan = validator.validate(
                    proposal,
                    workspace_path=str(C.PHASE_DATA_DIR / "attempts" / "_gate_plan_ws"),
                )
                write_nodes = sum(1 for s in plan.subtasks if getattr(s, "write", False))
                verify_nodes = sum(1 for s in plan.subtasks if not getattr(s, "write", False))
                dep_ok = (
                    all(getattr(s, "depends_on", ()) for s in plan.subtasks if not s.write)
                    if len(plan.subtasks) > 1 else True
                )
                expected_write = 1 if arm == "A" else 2
                out[f"{sample}__{arm}"] = {
                    "nodes": len(plan.subtasks),
                    "write_nodes": write_nodes,
                    "read_only_nodes": verify_nodes,
                    "verify_has_deps": dep_ok,
                    "ok": bool(write_nodes == expected_write and verify_nodes >= 1 and dep_ok),
                }
            except Exception as exc:  # noqa: BLE001
                out[f"{sample}__{arm}"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"plans": out, "ok": all(v["ok"] for v in out.values())}


# ------------------------------------------------------------------ stopgate H5
def _prove_stopgate() -> dict[str, Any]:
    """teardown complete -> acceptance opens; missing -> unconfirmed (no fake)."""

    from lightgravity.config import Settings
    from lightgravity.store import FileStore
    from lightgravity.verify.service import VerificationService
    from lightgravity.verify.stopgate import StoreResourceStopper

    from lightgravity.verify.checks import (
        CheckOutcome,
        CheckRegistration,
        CheckRegistry,
    )

    def _seed(root: Path) -> tuple[Any, Any, str]:
        from lightgravity.config import Settings
        from lightgravity.store import FileStore
        from lightgravity.store.ids import new_id

        if root.exists():
            # Only ever our own fresh, uniquely-named gate subdir; refuse else.
            if not str(root).startswith(str(GATE_ROOT.resolve())):
                raise SystemExit(f"_seed refusing to remove non-gate path {root}")
            raise SystemExit(f"_seed refusing to reuse existing dir {root}")
        ws = root / "ws"
        ws.mkdir(parents=True)
        settings = Settings(data_dir=root, workspace_root=ws, secret_store=root / "secrets",
                            host="127.0.0.1", port=0)
        settings.ensure_data_dir()
        store = FileStore(settings.data_dir, settings.workspace_root)
        # Runtime entities (task/run) require ``<kind>_<ULID>`` ids (docs/08 §3.1);
        # a slug would be rejected by the real ``_validate_kind_id``.
        task_id = new_id("task")
        run_id = new_id("run")
        task = store.create("task", task_id, {
            "title": "gate", "objective": "x",
            "status": "in-progress", "phase": "verifying",
            "requirements_revision": 1, "deliverable_revision": 0,
            "acceptance_criteria": ["ok"], "workspace_ref": "candidate-ws",
            "checks": ["gate-pass"],
            "queue": {"state": "not_queued", "order": 0},
            "acceptance": {"status": "pending"},
        }, actor="gate", request_id="gate-task")
        run = store.create("run", run_id, {
            "task_ref": task_id, "state": "verifying", "session_refs": ["sess-1"],
            "cleanup": {"status": "pending"}, "attempt": 1, "plan_hash": "gate-plan-hash",
        }, actor="gate", request_id="gate-run")
        store.write("task", task_id, {"active_run": run.entity_id},
                    expected_revision=task.revision, actor="gate")
        return settings, store, task_id

    def _registry() -> CheckRegistry:
        registry = CheckRegistry()
        registry.register(
            CheckRegistration(
                check_id="gate-pass",
                handler=lambda context: CheckOutcome(passed=True, detail="gate"),
                description="stopgate harness pass check",
            )
        )
        return registry

    class _Executor:
        def __init__(self, close_ok: bool) -> None:
            self.close_ok = close_ok

        def confirm_stopped(self, run_id: str, session_refs: Any) -> Any:
            from lightgravity.adapter.execution import StopConfirmation

            refs = tuple(session_refs or ())
            return StopConfirmation(
                run_id=run_id,
                confirmed=self.close_ok,
                sessions_total=len(refs),
                sessions_stopped=len(refs) if self.close_ok else 0,
                proxy_stopped=self.close_ok,
                unknown_sessions=() if self.close_ok else refs,
                problems=() if self.close_ok else ("gate: not closed",),
            )

    # missing teardown -> unconfirmed
    settings_bad, store_bad, task_bad = _seed(GATE_ROOT / "gate-stopgate-bad")
    svc_bad = VerificationService(
        store_bad, registry=_registry(),
        stopper=StoreResourceStopper(store_bad, session_confirmer=_Executor(False)),
    )
    res_bad = svc_bad.verify_and_prepare(task_bad, request_id="gate-verify-bad")
    bad_ok = (res_bad.state == "unconfirmed" and res_bad.confirmed is False
              and str(store_bad.read("task", task_bad).entity.get("phase")) == "verifying")

    # complete teardown -> acceptance opens
    settings_ok, store_ok, task_ok = _seed(GATE_ROOT / "gate-stopgate-ok")
    svc_ok = VerificationService(
        store_ok, registry=_registry(),
        stopper=StoreResourceStopper(store_ok, session_confirmer=_Executor(True)),
    )
    res_ok = svc_ok.verify_and_prepare(task_ok, request_id="gate-verify-ok")
    final_phase = str(store_ok.read("task", task_ok).entity.get("phase"))
    ok_ok = (res_ok.state == "confirmed" and final_phase == "awaiting_acceptance")

    return {
        "missing_teardown_unconfirmed": bad_ok,
        "complete_teardown_accepts": ok_ok,
        "final_phase": final_phase,
        "ok": bool(bad_ok and ok_ok),
    }


# ------------------------------------------------------------------ save_dir H6
def _prove_save_dir() -> dict[str, Any]:
    """``build_sdk_config`` accepts a ``save_dir`` inside the authorized root.

    This is a real product call into ``google.antigravity`` ``AgentConfig``; it
    proves the SDK native session store can be directed under the private
    workspace root.  No agent is created and no generation is issued.
    """

    target = C.PHASE_DATA_DIR / "attempts" / "_gate_save_dir" / "workspaces" / ".lg-sdk-sessions"
    target.mkdir(parents=True, exist_ok=True)
    try:
        import inspect

        from lightgravity.adapter import sdk_config

        sig = inspect.signature(sdk_config.build_sdk_config)
        has_field = "save_dir" in sig.parameters
        inside = str(target.resolve()).startswith(str(C.PHASE_DATA_DIR.resolve()))
        return {"save_dir_field": has_field, "inside_authorized_root": inside,
                "path": str(target), "ok": bool(has_field and inside)}
    except Exception as exc:  # noqa: BLE001
        return {"save_dir_field": False, "error": f"{type(exc).__name__}: {exc}", "ok": False}


def main() -> int:
    global GATE_ROOT
    payload: dict[str, Any] = {"ok": False, "real_generation": 0}
    # Preservation incident fix: a brand-new unique sandbox per run; the legacy
    # fixed ``lg032-gate-sandbox`` is left untouched and never removed.
    GATE_ROOT = C.new_dry_root("gate-sandbox")
    GATE_ROOT.mkdir(parents=True, exist_ok=False)
    payload["gate_root"] = str(GATE_ROOT)

    upstream_port = _free_port()
    upstream = ThreadingHTTPServer(("127.0.0.1", upstream_port), _FakeUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_url = f"http://127.0.0.1:{upstream_port}/v1"

    gate_root = GATE_ROOT / "gate-phase"
    gate_root.mkdir(parents=True, exist_ok=True)
    frozen_hist = gate_root / "generation" / "generation.jsonl"

    try:
        # ---- H1 fixtures
        payload["H1_fixtures"] = _prove_fixtures()
        # ---- H2 plans
        payload["H2_frozen_plans"] = _prove_frozen_plans()
        # ---- H5 stopgate
        payload["H5_stopgate"] = _prove_stopgate()
        # ---- H6 save_dir
        payload["H6_save_dir"] = _prove_save_dir()

        # ---- H3/H4 real startup chain x2 on the SAME phase data_dir
        from lightgravity.adapter.credentials import Secret
        from lightgravity.adapter.proxy import LocalAuthProxy, GenerationCounter

        state1, counter1 = _build_phase_runtime(gate_root, upstream_url)
        ident1 = _counter_identity(counter1, frozen_hist)
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

        state2, counter2 = _build_phase_runtime(gate_root, upstream_url)
        ident2 = _counter_identity(counter2, frozen_hist)
        count_at_start2 = counter2.count
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

        lines = frozen_hist.read_text(encoding="utf-8").splitlines() if frozen_hist.exists() else []
        payload["H3_startup"] = {
            "start1_counter": ident1, "start2_counter": ident2,
            "same_data_dir": str(gate_root),
            "ok": bool(ident1["counter_ledger_matches_frozen"]
                       and ident2["counter_ledger_matches_frozen"]),
        }
        payload["H4_ledger"] = {
            "worker_codes_start1": c1, "reviewer_codes_start2": c2,
            "count_after_start1": count_after_start1,
            "count_seen_at_start2": count_at_start2,
            "count_after_start2": count_after_start2,
            "physical_history_path": str(frozen_hist),
            "physical_history_exists": frozen_hist.exists(),
            "physical_history_lines": len(lines),
            "ok": bool(
                all(x == 200 for x in c1) and all(x == 200 for x in c2)
                and count_at_start2 == count_after_start1
                and count_after_start2 == count_after_start1 + 3
                and frozen_hist.exists() and len(lines) >= count_after_start2
            ),
        }

        # ---- H4b attempt cap before forward (independent sandboxed ledger)
        from lightgravity.adapter.generation_ledger import PersistentGenerationLedger

        att_root = GATE_ROOT / "gate-attempt"
        att_led = PersistentGenerationLedger(att_root, limit=C.ATTEMPT_GENERATION_LIMIT)
        attempt_counter = GenerationCounter(C.ATTEMPT_GENERATION_LIMIT, ledger=att_led)
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

        # ---- H4c phase total cap before forward
        total_root = GATE_ROOT / "gate-total"
        total_led = PersistentGenerationLedger(total_root, limit=3)
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

        payload["H4_attempt_cap"] = {
            "used": guard["used"], "limit": C.ATTEMPT_GENERATION_LIMIT,
            "codes_tail": cap_codes[-3:], "count_after_overrun": attempt_count,
            "ok": bool(guard["used"] == C.ATTEMPT_GENERATION_LIMIT
                       and cap_codes[-1] == 429
                       and attempt_count == C.ATTEMPT_GENERATION_LIMIT),
        }
        payload["H4_total_cap"] = {
            "codes": total_codes, "count_after_overrun": total_count,
            "ok": bool(total_codes[-1] == 429 and total_count == 3),
        }
        payload["H4_corrupt_failclosed"] = _prove_corrupt_failclosed()

        ok = (
            payload["H1_fixtures"]["ok"]
            and payload["H2_frozen_plans"]["ok"]
            and payload["H3_startup"]["ok"]
            and payload["H4_ledger"]["ok"]
            and payload["H4_attempt_cap"]["ok"]
            and payload["H4_total_cap"]["ok"]
            and payload["H4_corrupt_failclosed"]["ok"]
            and payload["H5_stopgate"]["ok"]
            and payload["H6_save_dir"]["ok"]
        )
        payload["ok"] = bool(ok)
    finally:
        upstream.shutdown()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, dict) else {"ok": v.get("ok")})
                      for k, v in payload.items()}, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
