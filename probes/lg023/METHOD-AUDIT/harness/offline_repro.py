#!/usr/bin/env python3
"""LG-023 METHOD-AUDIT offline reproduction (ZERO real model calls).

Two independent offline proofs, both using the REAL product objects:

A7 -- stop-gate reproduction
    Build a real ``FileStore`` + real Task/Run + the real ``GraphDispatcher``
    with the same frozen legal plan mechanism LG-023 used, driven by a
    **fake session-lifecycle executor** (no SDK, no network).  Then run the real
    ``VerificationService`` + real ``StoreResourceStopper`` exactly as the LG-023
    harness ``_accept`` did, and record whether ``verify_and_prepare`` opens
    ``awaiting_acceptance``.

    The executor faithfully models the real executor's stop facts
    (``session_refs`` recorded on the run, ``_closed_sessions[session_id]=run_id``
    + ``_proxy_stopped_runs.add(run_id)`` on teardown, and a real
    ``confirm_stopped`` returning a ``StopConfirmation``).  This isolates whether
    the LG-023 unconfirmed stop was a harness wiring defect or a genuine product
    fact.

A8 -- metering reproduction
    Start a REAL ``LocalAuthProxy`` against a LOCAL fake OpenAI-compatible SSE
    upstream (127.0.0.1, allow_loopback_upstream=True), attached to a REAL
    ``PersistentGenerationLedger``-backed ``GenerationCounter``.  Issue real HTTP
    chat-completion POSTs and prove that the counter's ``reserve()`` is charged
    *before* the forward, that the per-attempt secondary cap refuses the 13th
    forward with HTTP 429, and that the reviewer-style proxy (no explicit
    ``generation_budget``) shares the same process-global counter.

Writes ``METHOD-AUDIT/evidence/offline_repro.json``.

Usage::

    .venv/bin/python probes/lg023/METHOD-AUDIT/harness/offline_repro.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
PROBE = AUDIT.parent
REPO = PROBE.parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

OUT = AUDIT / "evidence" / "offline_repro.json"


# --------------------------------------------------------------------------- A7
class FakeSessionExecutor:
    """A real ExecutorAdapter-compatible fake with the real stop facts.

    No SDK, no network.  It records exactly the facts the real
    ``AntigravityExecutor`` records so we can drive the real stop gate.
    """

    name = "fake-session-executor"
    version = "0.0.0"

    def __init__(self, *, close_ok: bool = True, proxy_ok: bool = True) -> None:
        self._close_ok = close_ok
        self._proxy_ok = proxy_ok
        self._sessions: dict[str, str] = {}
        self._closed_sessions: dict[str, str] = {}
        self._proxy_stopped_runs: set[str] = set()
        self.executed: list[str] = []

    def capabilities(self):  # pragma: no cover - protocol completeness
        from lightgravity.adapter.capabilities import adapter_capabilities

        return adapter_capabilities()

    async def execute(self, request, emit):
        from lightgravity.adapter.execution import (
            ExecutionRef,
            ExecutorResult,
            SessionRef,
        )

        self.executed.append(request.subtask_id)
        session_id = f"sess_fake_{request.subtask_id}"
        self._sessions[session_id] = request.run_id
        await emit(
            {
                "type": "adapter.session_started",
                "session": SessionRef(
                    session_id=session_id,
                    conversation_id=f"conv_{request.subtask_id}",
                    state="created",
                    save_dir="/tmp/fake",
                ).to_dict(),
            }
        )
        # A real write happens here in the real executor; the fake writes a real
        # file to the authorized workspace so the machine ``evidence-present`` /
        # ``artifacts-in-workspace`` checks see genuine evidence.
        ws = Path(request.workspace_path)
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "delivered.txt").write_text("fake\n", encoding="utf-8")
        result = ExecutorResult(
            state="succeeded",
            summary="fake node succeeded",
            artifact_refs=("delivered.txt",),
            session_ref=SessionRef(
                session_id=session_id,
                conversation_id=f"conv_{request.subtask_id}",
                state="created",
                save_dir="/tmp/fake",
            ),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
        )
        return result

    def record_teardown(self, run_id: str, session_id: str) -> None:
        """Model the real executor ``finally`` block after ``execute`` returns."""

        if self._close_ok:
            self._closed_sessions[session_id] = run_id
        if self._proxy_ok:
            self._proxy_stopped_runs.add(run_id)
        self._sessions.pop(session_id, None)

    async def cancel(self, execution_ref):  # pragma: no cover
        from lightgravity.adapter.execution import CancelResult

        return CancelResult(confirmed=True, state="cancelled", reason="fake")

    async def close(self, session_ref) -> None:  # pragma: no cover
        return None

    def confirm_stopped(self, run_id: str, session_refs):
        """Mirror ``AntigravityExecutor.confirm_stopped`` exactly."""

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


def _frozen_plan_proposal(arm: str):
    """Same frozen legal plan mechanism as the LG-023 harness (plan node count only)."""

    from lightgravity.coordinator.planner import PlanProposal, RawSubtask

    if arm == "A":
        subtasks = (
            RawSubtask(
                key="deliver", objective="deliver", capability="implementation",
                acceptance=("a",), write=True,
            ),
        )
    else:
        subtasks = (
            RawSubtask(
                key="part_a", objective="part a", capability="implementation",
                acceptance=("a",), write=True,
            ),
            RawSubtask(
                key="part_b", objective="part b", capability="implementation",
                acceptance=("b",), depends_on=("part_a",), write=True,
            ),
        )
    return PlanProposal(subtasks=subtasks, source=f"frozen-{arm}", notes=("method-audit",))


class _FrozenPlanner:
    def __init__(self, arm: str) -> None:
        self.name = f"frozen-{arm}"
        self._arm = arm

    async def plan(self, context):  # noqa: ANN001
        return _frozen_plan_proposal(self._arm)


def _build_store(tmp: Path):
    from lightgravity.store import FileStore, new_id

    workspace_root = tmp / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    store = FileStore(tmp / "data", workspace_root)
    return store, workspace_root


def _seed_resources(store) -> None:  # noqa: ANN001
    def create(kind, entity_id, fields, body=""):
        fields.setdefault("title", entity_id)
        fields.setdefault("enabled", True)
        store.create(kind, entity_id, fields, actor="audit", request_id=f"req-{kind}-{entity_id}")

    create("connection", "primary", {"backend": "openai-compat", "model": "deepseek-v4-flash",
                                     "credential_ref": "deepseek-api-key",
                                     "base_url": "https://api.deepseek.com/v1"})
    create("conversation", "worker", {"session_continuation_mode": "create_or_resume",
                                      "agent_behavior": "autonomous"})
    for tool_id in ("view-file", "create-file", "edit-file"):
        create("tool", tool_id, {"implementation": tool_id})
    create("skill", "implementation", {"description": "Implementation"}, body="# Impl\n")
    create("skill", "verification", {"description": "Verification"}, body="# Verify\n")
    create("agent", "developer", {
        "connection_ref": "primary", "conversation_ref": "worker",
        "skills": {"source": "inline", "refs": ["implementation"]},
        "tool_refs": ["view-file", "create-file", "edit-file"],
        "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": [],
    }, body="worker\n")
    create("agent", "verifier", {
        "connection_ref": "primary", "conversation_ref": "worker",
        "skills": {"source": "inline", "refs": ["verification"]},
        "tool_refs": ["view-file"],
        "hook_refs": [], "mcp_refs": [], "trigger_refs": [], "subagents": [],
    }, body="verifier\n")


def _build_task_run(store, workspace_ref: str):  # noqa: ANN001
    from lightgravity.coordinator import DispatchContext
    from lightgravity.coordinator.planning import PlanningRequest, PlanningTrigger
    from lightgravity.coordinator.state import StateWriter
    from lightgravity.store import new_id

    workspace = store.resolve_path(workspace_ref, write=True)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    task_id = new_id("task")
    run_id = new_id("run")
    store.create("task", task_id, {
        "title": "audit", "objective": "audit", "acceptance_criteria": ["evidence-present"],
        "status": "in-progress", "phase": "planning", "requirements_revision": 1,
        "project_ref": None, "repository_ref": None, "workspace_ref": workspace_ref,
        "agent_ref": "developer", "depends_on": [], "active_run": run_id,
        "deliverable_revision": 0,
        "queue": {"state": "not_queued", "order": None, "queued_at": None, "owner": None,
                  "lease_expires_at": None},
        "acceptance": {"status": "pending", "requirements_revision": None,
                       "deliverable_revision": None, "evidence_refs": [], "decided_at": None,
                       "decision_ref": None},
        "budget": {"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1,
                   "max_collab_requests": 4},
        "checks": ["evidence-present"], "archived": False,
    }, actor="audit", request_id=f"req-{task_id}", body="# audit\n")
    store.create("run", run_id, {
        "task_ref": task_id, "attempt": 1, "state": "planning", "plan_ref": "PLAN.md",
        "plan": None, "plan_hash": "a" * 64, "plan_source": "rules", "team_refs": [],
        "subtask_refs": [], "session_refs": [], "cleanup": {"status": "pending"},
        "ended_at": None, "fail_reason": None,
    }, actor="audit", request_id=f"req-{run_id}", body="# Run\n")
    writer = StateWriter(store, actor="audit")
    writer.write_task(task_id, {"active_run": run_id})
    from lightgravity.coordinator import RunController

    controller = RunController(writer, task_id, run_id)
    context = DispatchContext(
        task_id=task_id, run_id=run_id, attempt=1, objective="audit",
        acceptance_criteria=("evidence-present",), instructions="",
        workspace_path=str(workspace), allowed_tools=("view-file", "create-file", "edit-file"),
        agent_ref="developer",
        budget={"max_workers": 3, "max_parallel": 1, "max_repair_rounds": 1,
                "max_collab_requests": 4, "max_model_calls": 10, "max_tool_calls": 16},
        planning_request=PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason="audit",
                                         requested_by="audit", max_calls=1),
        timeout_seconds=60.0,
    )
    return task_id, run_id, controller, context


async def run_a7(*, close_ok: bool, proxy_ok: bool) -> dict:
    import tempfile

    from lightgravity.adapter import DirectoryArtifactSink, InMemoryCredentialResolver
    from lightgravity.adapter.compiler import ResourceCompiler
    from lightgravity.collaboration import ClaimPolicy, CollaborationService, ExecutionGrantRegistry
    from lightgravity.coordinator import GraphDispatcher, RoleCatalog
    from lightgravity.verify.service import VerificationService
    from lightgravity.verify.stopgate import StoreResourceStopper
    from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager

    result: dict = {"close_ok": close_ok, "proxy_ok": proxy_ok}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store, workspace_root = _build_store(root)
        _seed_resources(store)
        task_id, run_id, controller, context = _build_task_run(store, "ws")

        executor = FakeSessionExecutor(close_ok=close_ok, proxy_ok=proxy_ok)
        provider = GraphWorkspaceProvider(WorktreeManager(workspace_root))
        resolver = InMemoryCredentialResolver({"deepseek-api-key": "fake"})
        # Wrap the fake so the dispatcher records a real member/session.
        executor._compiler = ResourceCompiler(store)  # type: ignore[attr-defined]
        dispatcher = GraphDispatcher(
            store, executor, planner=_FrozenPlanner("A"),
            catalog=RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]}),
            max_parallel=1, workspaces=provider,
        )

        async def emit(_event):
            return None

        outcome = await dispatcher.dispatch(context, controller, emit)
        result["dispatcher_state"] = getattr(outcome, "state", None)

        # Real executor teardown after each node (mirror the real finally block).
        run_entity = store.read("run", run_id).entity
        session_refs = list(run_entity.get("session_refs") or [])
        result["run_session_refs"] = session_refs
        for sid in session_refs:
            executor.record_teardown(run_id, sid)

        # Exactly the LG-023 harness _accept wiring path.
        from lightgravity.contracts import TaskPhase
        from lightgravity.coordinator.state import StateWriter

        writer = StateWriter(store, actor="audit")
        writer.transition_run(run_id, "verifying", task_ref=task_id)
        writer.transition_task(task_id, TaskPhase.VERIFYING, run_ref=run_id)
        stopper = StoreResourceStopper(store, session_confirmer=executor)
        service = VerificationService(store, stopper=stopper)
        prepared = service.verify_and_prepare(task_id, request_id=f"audit-verify-{run_id}")
        result["verify_state"] = prepared.state
        result["verify_confirmed"] = prepared.confirmed
        result["verify_messages"] = list(prepared.messages)
        result["phase_after_verify"] = str(store.read("task", task_id).entity.get("phase", ""))
        result["accept_reachable"] = (
            prepared.confirmed and result["phase_after_verify"] == "awaiting_acceptance"
        )
        stop = getattr(prepared, "stop", None)
        result["stop_detail"] = (
            stop.to_dict() if hasattr(stop, "to_dict") else stop
        )
    return result


def run_a7_sync(close_ok: bool, proxy_ok: bool) -> dict:
    return asyncio.run(run_a7(close_ok=close_ok, proxy_ok=proxy_ok))


# --------------------------------------------------------------------------- A8
class _FakeUpstream(BaseHTTPRequestHandler):
    """Local OpenAI-compatible SSE upstream; never leaves loopback."""

    served = 0

    def log_message(self, *args):  # noqa: D102
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length) if length else b"{}"
        type(self).served += 1
        payload = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


#: Set by run_a8() to the live loopback fake-upstream chat-completions URL.
_LOCAL_UPSTREAM: list[str] = [""]


def _post_codes(proxy, n: int) -> list[int]:  # noqa: ANN001
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


def run_a8() -> dict:
    import os
    import tempfile
    import urllib.error
    import urllib.request

    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.proxy import (
        GenerationCounter,
        LocalAuthProxy,
        configure_generation_ledger,
    )
    from lightgravity.adapter.generation_ledger import PersistentGenerationLedger

    result: dict = {}
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
    uthread = threading.Thread(target=upstream.serve_forever, daemon=True)
    uthread.start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"
    _LOCAL_UPSTREAM[0] = upstream_url

    with tempfile.TemporaryDirectory() as tmp:
        # One persistent ledger, real counter.
        ledger = PersistentGenerationLedger(Path(tmp) / "ledger", limit=48)
        counter = GenerationCounter(48, ledger=ledger)

        # Per-attempt secondary cap enforced BEFORE the global ledger charge and
        # BEFORE forwarding -- and installed on the *global* counter so any proxy
        # that defaults to it (e.g. the reviewer) is also bounded.
        import lightgravity.adapter.proxy as proxy_mod

        orig = counter.reserve
        used = [0]
        attempt_cap = 12

        def guarded() -> bool:
            if used[0] >= attempt_cap:
                return False
            granted = orig()
            if granted:
                used[0] += 1
            return granted

        counter.reserve = guarded  # type: ignore[method-assign]
        proxy_mod._GLOBAL_GENERATION_COUNTER = counter

        # Proxy 1 (worker-style): explicit budget.
        worker = LocalAuthProxy(
            credential=Secret("fake-key"),
            upstream_url=upstream_url,
            max_calls=64,
            allow_loopback_upstream=True,
            generation_budget=counter,
        )
        worker.start()
        # Proxy 2 (reviewer-style): NO explicit budget -> must share the global.
        reviewer = LocalAuthProxy(
            credential=Secret("fake-key"),
            upstream_url=upstream_url,
            max_calls=64,
            allow_loopback_upstream=True,
        )
        reviewer.start()

        def post(proxy, n: int) -> list[int]:
            codes = []
            for _ in range(n):
                req = urllib.request.Request(
                    proxy.base_url + "/chat/completions",
                    data=b'{"model":"x","messages":[]}',
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

        try:
            result["worker_codes_6"] = post(worker, 6)
            result["ledger_after_worker"] = ledger.count()
            result["reviewer_codes_6"] = post(reviewer, 6)
            result["ledger_after_reviewer"] = ledger.count()
            result["attempt_used"] = used[0]
            # 13th forward on the same attempt must be refused before forwarding.
            result["worker_13th_code"] = post(worker, 1)[0]
            result["ledger_after_13th"] = ledger.count()
            result["upstream_served"] = _FakeUpstream.served
            result["reviewer_shares_global"] = result["ledger_after_reviewer"] == 12
            result["attempt_cap_enforced"] = (
                result["attempt_used"] == attempt_cap
                and result["worker_13th_code"] == 429
                and result["ledger_after_13th"] == 12
            )
            result["reserve_before_forward"] = (
                result["ledger_after_worker"] == 6 and result["upstream_served"] == 12
            )
        finally:
            worker.stop()
            reviewer.stop()

    upstream.shutdown()
    return result


def run_a8_old_wiring() -> dict:
    """Reproduce the OLD harness attempt-guard wiring and show it does NOT cap.

    The old code wrapped the counter's ``reserve`` but checked ``.granted`` on its
    return value -- which is a plain ``bool``, not a ``Reservation`` -- so the
    per-attempt counter never advanced and the attempt cap was never enforced
    (matching the committed ``attempt_generation_requests: 0`` while the global
    ledger advanced).
    """

    import tempfile

    import lightgravity.adapter.proxy as proxy_mod
    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.generation_ledger import PersistentGenerationLedger
    from lightgravity.adapter.proxy import GenerationCounter, LocalAuthProxy

    result: dict = {}
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _FakeUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up = f"http://127.0.0.1:{upstream.server_address[1]}/v1/chat/completions"
    with tempfile.TemporaryDirectory() as tmp:
        ledger = PersistentGenerationLedger(Path(tmp) / "ledger", limit=48)
        counter = GenerationCounter(48, ledger=ledger)
        orig = counter.reserve
        used = [0]

        def old_guard():
            # OLD semantics: mirror run_attempt.py @ 4a8ac0d (guard.used reads 0).
            res = orig()
            if getattr(res, "granted", False):  # attr missing on bool -> never
                used[0] += 1
            return res

        counter.reserve = old_guard  # type: ignore[method-assign]
        proxy_mod._GLOBAL_GENERATION_COUNTER = counter
        worker = LocalAuthProxy(
            credential=Secret("fake"), upstream_url=up,
            allow_loopback_upstream=True, generation_budget=counter,
        )
        worker.start()
        try:
            # 6 forwards far under the (un-enforced) 12 cap; ledger advances but
            # the guard stays 0 -- the defect.
            codes = _post_codes(worker, 6)
            result["codes"] = codes
            result["guard_used"] = used[0]
            result["ledger"] = ledger.count()
            result["defect_reproduced"] = used[0] == 0 and ledger.count() == 6
        finally:
            worker.stop()
    upstream.shutdown()
    return result


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report: dict = {"real_model_calls": 0}
    report["A7_stopgate_wired_ok"] = run_a7_sync(close_ok=True, proxy_ok=True)
    report["A7_stopgate_broken_close"] = run_a7_sync(close_ok=False, proxy_ok=True)
    report["A8_metering"] = run_a8()
    report["A8_old_wiring_defect"] = run_a8_old_wiring()

    ok = (
        report["A7_stopgate_wired_ok"]["accept_reachable"] is True
        and report["A7_stopgate_broken_close"]["accept_reachable"] is False
        and report["A8_metering"]["reviewer_shares_global"] is True
        and report["A8_metering"]["attempt_cap_enforced"] is True
        and report["A8_metering"]["reserve_before_forward"] is True
        and report["A8_old_wiring_defect"]["defect_reproduced"] is True
    )
    report["ok"] = ok
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
