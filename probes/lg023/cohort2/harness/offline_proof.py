#!/usr/bin/env python3
"""LG-023 cohort-2 OFFLINE hard-gate prover (zero DeepSeek generation).

Proves, before any real request, that the cohort-2 harness is correctly wired:

* **P1 fixtures**: ``initial/`` must FAIL acceptance; ``reference/`` must PASS
  (6/6) for both samples, from the cohort-2 copied fixtures.
* **P2 frozen plans**: the arm-A (1 write node) and arm-B (2 dependent write
  nodes) frozen proposals pass the real product ``PlanValidator`` with a real
  catalog; arm B has a real dependency.
* **P3 roles/tools compile**: the worker agent compiles through the real
  ``ResourceCompiler`` with the frozen tool refs (view/create/edit), same for
  both arms.
* **P4 measurement**: a real ``LocalAuthProxy`` against a LOCAL fake SSE
  upstream proves (a) the per-attempt cap of 12 is enforced **before
  forwarding** (13th -> 429, ledger unchanged) and (b) a reviewer-style proxy
  with no explicit budget shares the SAME global counter/ledger (count is not
  0).  The guard returns ``bool`` (audited defect D2 fixed).
* **P5 stop gate**: real ``GraphDispatcher`` + real ``StoreResourceStopper`` +
  the real executor-shaped teardown record reach ``awaiting_acceptance`` when
  teardown facts are complete, and stay ``unconfirmed`` when a fact is missing
  (audited defect D1 fixed).

Writes ``../evidence/offline/offline_proof.json``.  Never contacts DeepSeek
(P5/P4 use the local fake upstream / fake session-lifecycle executor).

Usage::

    .venv/bin/python probes/lg023/cohort2/harness/offline_proof.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "backend"))

import cohort2_config as C  # noqa: E402

SCRATCH = C.COHORT2 / "offline_scratch"
OUT = C.EVIDENCE_DIR / "offline" / "offline_proof.json"


# ------------------------------------------------------------------ P1 fixtures
def _tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(root)).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def _run_acceptance(sample: str, workspace: Path) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    proc = subprocess.run(
        [sys.executable, str(C.FIXTURES_DIR / sample / "acceptance.py"),
         "--workspace", str(workspace)],
        capture_output=True, text=True, timeout=60, env=env,
    )
    lines = proc.stdout.strip().splitlines()
    try:
        report = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        report = {"raw": proc.stdout, "stderr": proc.stderr}
    report["exit_code"] = proc.returncode
    return report


def prove_fixtures() -> dict[str, Any]:
    results: dict[str, Any] = {}
    ok = True
    for sample in C.SAMPLES:
        fix = C.FIXTURES_DIR / sample
        ws_init = SCRATCH / "p1" / sample / "initial"
        ws_ref = SCRATCH / "p1" / sample / "reference"
        for ws, extra in ((ws_init, None), (ws_ref, fix / "reference")):
            if ws.exists():
                shutil.rmtree(ws)
            ws.mkdir(parents=True)
            shutil.copytree(fix / "initial", ws, dirs_exist_ok=True)
            if extra is not None:
                shutil.copytree(extra, ws, dirs_exist_ok=True)
        init_report = _run_acceptance(sample, ws_init)
        ref_report = _run_acceptance(sample, ws_ref)
        entry = {
            "initial_hash": _tree_hash(fix / "initial"),
            "reference_hash": _tree_hash(fix / "reference"),
            "initial": init_report,
            "initial_fails": init_report.get("passed", -1) < init_report.get("total", -1),
            "reference": ref_report,
            "reference_passes": ref_report.get("passed") == ref_report.get("total") == 6,
        }
        if not (entry["initial_fails"] and entry["reference_passes"]):
            ok = False
        results[sample] = entry
    return {"ok": ok, "samples": results}


# ------------------------------------------------------------- P2/P3 plan+compile
def prove_plans_and_compile() -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location("cohort2_run_attempt", HERE / "run_attempt.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    from lightgravity.coordinator.planner import PlanValidator, RuleBasedPlanner
    from lightgravity.coordinator import RoleCatalog, DispatchContext
    from lightgravity.coordinator.recruiter import Recruiter
    from lightgravity.adapter.compiler import ResourceCompiler
    from lightgravity.store import FileStore

    catalog = RoleCatalog({"implementation": ["cohort2-worker"],
                           "verification": ["cohort2-worker"]})
    results: dict[str, Any] = {}
    ok = True
    for sample in C.SAMPLES:
        for arm in C.ARMS:
            planner = mod._FrozenPlanner(arm, sample)
            ctx = DispatchContext(
                task_id="task_probe", run_id="run_probe", attempt=1,
                objective=mod.SAMPLE_SPEC[sample]["objective"],
                acceptance_criteria=tuple(mod.SAMPLE_SPEC[sample]["acceptance"]),
                instructions="x", workspace_path=str(SCRATCH / "p2ws"),
                allowed_tools=("view-file", "create-file", "edit-file"),
                agent_ref="cohort2-worker", budget={},
            )
            proposal = asyncio.run(planner.plan(ctx))
            plan = PlanValidator(known_capabilities=catalog.capabilities).validate(
                proposal, workspace_path=str(SCRATCH / "p2ws")
            )
            b_dep = (
                arm == "B"
                and len(plan.subtasks) == 2
                and plan.subtasks[1].depends_on == (plan.subtasks[0].key,)
            )
            a_nodes = arm == "A" and len(plan.subtasks) == 1
            entry = {
                "nodes": len(plan.subtasks),
                "keys": list(plan.order),
                "arm_a_single_node": a_nodes,
                "arm_b_two_dependent_nodes": b_dep,
                "plan_hash": plan.plan_hash,
                "capabilities": list(plan.required_capabilities),
            }
            if not (a_nodes or b_dep):
                ok = False
            results[f"{sample}__{arm}"] = entry

    # P3: compile the frozen worker agent through the real compiler.
    ws = SCRATCH / "p3ws"
    ws.mkdir(parents=True, exist_ok=True)
    store_dir = SCRATCH / "p3store"
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = FileStore(store_dir, SCRATCH / "p3workspaces")
    for tool_id in ("view-file", "create-file", "edit-file"):
        store.create("tool", tool_id, {"title": tool_id, "enabled": True, "implementation": tool_id},
                     actor="probe", request_id=f"p3-{tool_id}")
    store.create("connection", "cohort2-worker",
                 {"title": "c", "enabled": True, "backend": "openai-compat", "model": C.MODEL,
                  "base_url": C.BASE_URL, "credential_ref": C.CREDENTIAL_REF},
                 actor="probe", request_id="p3-conn")
    store.create("agent", "cohort2-worker",
                 {"title": "w", "enabled": True, "connection_ref": "cohort2-worker",
                  "skills": {"source": "inline", "refs": []},
                  "tool_refs": ["view-file", "create-file", "edit-file"],
                  "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": []},
                 actor="probe", request_id="p3-agent", body=mod.WORKER_PROMPT_BODY)
    compiler = ResourceCompiler(store)
    try:
        compiled = compiler.compile_agent("cohort2-worker")
        compile_info = {
            "ok": True,
            "tools": [t.ref for t in compiled.tools],
            "executable": compiled.executable,
            "config_hash": compiled.config_hash,
        }
    except Exception as exc:  # noqa: BLE001
        compile_info = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        ok = False
    return {"ok": ok, "plans": results, "compile": compile_info}


# ------------------------------------------------------------- P4 measurement
class _FakeUpstream(BaseHTTPRequestHandler):
    served = 0

    def log_message(self, *args: Any) -> None:  # noqa: D102
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        type(self).served += 1
        payload = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


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


def prove_measurement() -> dict[str, Any]:
    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.generation_ledger import PersistentGenerationLedger
    from lightgravity.adapter.proxy import GenerationCounter, LocalAuthProxy

    ledger_dir = SCRATCH / "p4ledger"
    if ledger_dir.exists():
        shutil.rmtree(ledger_dir)
    ledger = PersistentGenerationLedger(ledger_dir, limit=C.PHASE_GENERATION_LIMIT)
    counter = GenerationCounter(C.PHASE_GENERATION_LIMIT, ledger=ledger)

    import lightgravity.adapter.proxy as proxy_mod

    orig = counter.reserve
    used = [0]

    def guarded() -> bool:
        if used[0] >= C.ATTEMPT_GENERATION_LIMIT:
            return False
        granted = orig()
        if granted:
            used[0] += 1
        return granted

    counter.reserve = guarded  # type: ignore[method-assign]
    proxy_mod._GLOBAL_GENERATION_COUNTER = counter

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"

    worker = LocalAuthProxy(credential=Secret("fake"), upstream_url=upstream_url,
                            max_calls=64, allow_loopback_upstream=True, generation_budget=counter)
    worker.start()
    reviewer = LocalAuthProxy(credential=Secret("fake"), upstream_url=upstream_url,
                              max_calls=64, allow_loopback_upstream=True)
    reviewer.start()
    result: dict[str, Any] = {}
    try:
        result["worker_codes_6"] = _post_codes(worker, 6)
        result["ledger_after_worker"] = ledger.count()
        result["reviewer_codes_6"] = _post_codes(reviewer, 6)
        result["ledger_after_reviewer"] = ledger.count()
        result["attempt_used"] = used[0]
        result["worker_13th_code"] = _post_codes(worker, 1)[0]
        result["ledger_after_13th"] = ledger.count()
        result["upstream_served"] = _FakeUpstream.served
        result["reviewer_shares_global"] = result["ledger_after_reviewer"] == 12
        result["attempt_cap_enforced"] = (
            result["attempt_used"] == C.ATTEMPT_GENERATION_LIMIT
            and result["worker_13th_code"] == 429
            and result["ledger_after_13th"] == 12
        )
        result["count_is_not_zero"] = used[0] == 12 and ledger.count() == 12
        result["reserve_before_forward"] = (
            result["ledger_after_worker"] == 6 and result["upstream_served"] == 12
        )
        result["ok"] = bool(result["attempt_cap_enforced"] and result["reviewer_shares_global"]
                            and result["count_is_not_zero"] and result["reserve_before_forward"])
    finally:
        worker.stop()
        reviewer.stop()
        upstream.shutdown()
    return result


# --------------------------------------------------------------- P5 stop gate
def prove_stopgate() -> dict[str, Any]:
    from lightgravity.store import FileStore, new_id
    from lightgravity.coordinator import DispatchContext, GraphDispatcher, RoleCatalog
    from lightgravity.coordinator.state import StateWriter
    from lightgravity.verify.service import VerificationService
    from lightgravity.verify.stopgate import StoreResourceStopper

    def run_case(*, close_ok: bool) -> dict[str, Any]:
        root = SCRATCH / "p5" / ("ok" if close_ok else "missing")
        if root.exists():
            shutil.rmtree(root)
        ws = root / "ws"
        ws.mkdir(parents=True)
        (ws / "out.txt").write_text("x\n", encoding="utf-8")
        store = FileStore(root / "data", root / "workspaces")
        _seed_p5(store)
        task_id = new_id("task")
        run_id = new_id("run")
        store.create("task", task_id, _task_fields(run_id), actor="probe", request_id="t",
                     body="# t\n")
        store.create("run", run_id, _run_fields(task_id), actor="probe", request_id="r",
                     body="# r\n")
        writer = StateWriter(store, actor="probe")
        from lightgravity.coordinator import RunController

        controller = RunController(writer, task_id, run_id)

        executor = _FakeExecutor(close_ok=close_ok)
        dispatcher = GraphDispatcher(store, executor, catalog=RoleCatalog.single_agent(
            ("implementation", "verification"), "cohort2-worker"))
        context = DispatchContext(
            task_id=task_id, run_id=run_id, attempt=1, objective="write out.txt",
            acceptance_criteria=("out.txt exists",), instructions="x",
            workspace_path=str(ws), allowed_tools=("create-file",), agent_ref="cohort2-worker",
            budget={"max_model_calls": 1, "max_tool_calls": 2},
        )
        events: list[dict[str, Any]] = []
        outcome = asyncio.run(dispatcher.dispatch(context, controller, events.append))
        if outcome.state != "succeeded":
            errs = [e for e in events if str(e.get("type", "")) == "error.recorded"]
            return {
                "dispatch_state": outcome.state,
                "summary": getattr(outcome, "summary", None),
                "failure_code": getattr(outcome, "failure_code", None),
                "failure_message": getattr(outcome, "failure_message", None),
                "errors": errs[-3:],
                "ok": False,
            }
        # The real product delivery path: verifying -> verify_and_prepare with the
        # real executor's confirm_stopped as the stopper's session confirmer.
        from lightgravity.contracts import TaskPhase

        writer.transition_run(run_id, "verifying", task_ref=task_id)
        writer.transition_task(task_id, TaskPhase.VERIFYING, run_ref=run_id)
        stopper = StoreResourceStopper(store, session_confirmer=executor)
        service = VerificationService(store, stopper=stopper)
        try:
            prepared = service.verify_and_prepare(task_id, request_id="v")
        except Exception as exc:  # noqa: BLE001
            return {"dispatch_state": outcome.state,
                    "verify_error": f"{type(exc).__name__}: {exc}", "ok": False}
        phase = str(store.read("task", task_id).entity.get("phase", ""))
        return {
            "dispatch_state": outcome.state,
            "verify_state": prepared.state,
            "confirmed": prepared.confirmed,
            "messages": list(prepared.messages),
            "phase_after_verify": phase,
            "accept_reachable": prepared.confirmed and phase == "awaiting_acceptance",
        }

    ok_case = run_case(close_ok=True)
    miss_case = run_case(close_ok=False)
    return {
        "teardown_complete_reaches_awaiting_acceptance": ok_case.get("accept_reachable") is True,
        "missing_fact_stays_unconfirmed": miss_case.get("confirmed") is False,
        "case_ok": ok_case,
        "case_missing": miss_case,
        "ok": bool(ok_case.get("accept_reachable") and miss_case.get("confirmed") is False),
    }


def _seed_p5(store: Any) -> None:
    for tool_id in ("view-file", "create-file", "edit-file"):
        store.create("tool", tool_id, {"title": tool_id, "enabled": True, "implementation": tool_id},
                     actor="p", request_id=f"t-{tool_id}")
    store.create("connection", "cohort2-worker",
                 {"title": "c", "enabled": True, "backend": "openai-compat", "model": C.MODEL,
                  "base_url": C.BASE_URL, "credential_ref": C.CREDENTIAL_REF},
                 actor="p", request_id="conn")
    store.create("agent", "cohort2-worker",
                 {"title": "w", "enabled": True, "connection_ref": "cohort2-worker",
                  "skills": {"source": "inline", "refs": []},
                  "tool_refs": ["view-file", "create-file", "edit-file"],
                  "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": []},
                 actor="p", request_id="agent", body="worker\n")


def _task_fields(run_id: str) -> dict[str, Any]:
    return {
        "title": "p5", "objective": "write out.txt", "acceptance_criteria": ["out.txt exists"],
        "status": "in-progress", "phase": "planning", "requirements_revision": 1,
        "project_ref": None, "repository_ref": None, "workspace_ref": "ws",
        "agent_ref": "cohort2-worker", "depends_on": [], "active_run": run_id,
        "deliverable_revision": 0,
        "queue": {"state": "not_queued", "order": None, "queued_at": None, "owner": None,
                  "lease_expires_at": None},
        "acceptance": {"status": "pending", "requirements_revision": None,
                       "deliverable_revision": None, "evidence_refs": [], "decided_at": None,
                       "decision_ref": None},
        "budget": {"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 0,
                   "max_collab_requests": 0},
        "checks": ["evidence-present"], "archived": False,
    }


def _run_fields(task_id: str) -> dict[str, Any]:
    return {
        "task_ref": task_id, "attempt": 1, "state": "planning", "plan_ref": "PLAN.md",
        "plan": None, "plan_hash": "a" * 64, "plan_source": "rules", "team_refs": [],
        "subtask_refs": [], "session_refs": [], "cleanup": {"status": "pending"},
        "ended_at": None, "fail_reason": None,
    }


class _FakeExecutor:
    """Executor-shaped fake exposing the real ``confirm_stopped`` stop facts."""

    name = "cohort2-offline-fake"

    def __init__(self, *, close_ok: bool) -> None:
        #: Mirror AntigravityExecutor's real stop-fact bookkeeping exactly.
        self._sessions: dict[str, Any] = {}
        self._closed_sessions: dict[str, str] = {}
        self._proxy_stopped_runs: set[str] = set()
        self._close_ok = close_ok

    async def execute(self, request: Any, emit: Any) -> Any:
        from lightgravity.adapter.execution import ExecutionRef, ExecutorResult, SessionRef

        session_id = f"sess_{request.subtask_id}"
        (Path(request.workspace_path) / "out.txt").write_text("done\n", encoding="utf-8")
        if self._close_ok:
            self._closed_sessions[session_id] = request.run_id
        else:
            # Missing stop fact: keep the session in-flight/unknown so the real
            # confirm_stopped semantics stay unconfirmed.
            self._sessions[session_id] = object()
        self._proxy_stopped_runs.add(request.run_id)
        return ExecutorResult(
            state="succeeded", summary="ok", artifact_refs=("workspace:out.txt",),
            session_ref=SessionRef(session_id=session_id, conversation_id="c1",
                                   state="closed", save_dir="/persistent/fake"),
            execution_ref=ExecutionRef(execution_id="e1", task_id=request.task_id,
                                       run_id=request.run_id, subtask_id=request.subtask_id),
        )

    def confirm_stopped(self, run_id: str, session_refs: Any) -> Any:
        from lightgravity.adapter.execution import StopConfirmation

        unknown: list[str] = []
        stopped = 0
        for session_id in session_refs:
            if session_id in self._sessions:
                unknown.append(session_id)
                continue
            if self._closed_sessions.get(session_id) == run_id:
                stopped += 1
                continue
            unknown.append(session_id)
        proxy_stopped = run_id in self._proxy_stopped_runs
        problems: list[str] = []
        if unknown:
            problems.append(f"{len(unknown)} session(s) not confirmed closed by the adapter")
        if not proxy_stopped:
            problems.append("loopback auth proxy not confirmed stopped")
        return StopConfirmation(
            run_id=run_id,
            confirmed=not unknown and proxy_stopped,
            sessions_total=len(session_refs),
            sessions_stopped=stopped,
            proxy_stopped=proxy_stopped,
            unknown_sessions=tuple(unknown),
            problems=tuple(problems),
        )

    # Protocol completeness (unused offline).
    def capabilities(self) -> Any:  # pragma: no cover
        return {}

    async def cancel(self, execution_ref: Any) -> Any:  # pragma: no cover
        from lightgravity.adapter.execution import CancelResult
        return CancelResult(confirmed=True, state="cancelled", reason="fake")

    async def close(self, session_ref: Any) -> None:  # pragma: no cover
        return None

    def record_teardown(self, run_id: str, session_id: str) -> None:  # pragma: no cover
        return None


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    payload["p1_fixtures"] = prove_fixtures()
    payload["p2p3_plans_compile"] = prove_plans_and_compile()
    payload["p4_measurement"] = prove_measurement()
    payload["p5_stopgate"] = prove_stopgate()
    payload["ok"] = all(
        payload[k].get("ok") for k in ("p1_fixtures", "p2p3_plans_compile",
                                        "p4_measurement", "p5_stopgate")
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"],
                      "p1": payload["p1_fixtures"]["ok"],
                      "p2p3": payload["p2p3_plans_compile"]["ok"],
                      "p4": payload["p4_measurement"].get("ok"),
                      "p5": payload["p5_stopgate"].get("ok")}, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
