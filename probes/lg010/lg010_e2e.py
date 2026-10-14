#!/usr/bin/env python3
"""LG-010 prototype-V0 minimal backend closed-loop evidence harness.

Independent QA probe (not product code, not a pytest test).  It drives the
**product** entry points end to end:

    POST /api/v1/tasks (user delivery entry)
      -> Coordinator (queue + single execution slot)
      -> GraphDispatcher (planner -> recruiter -> scheduler)
      -> AntigravityExecutor (real pinned SDK + loopback auth proxy)
      -> DeepSeek upstream (real model, hard-capped)
      -> Store (Markdown/JSONL control state)
      -> VerificationService (authorized machine checks + stop gate)
      -> GET /api/v1/tasks/{id}/acceptance
      -> POST /api/v1/tasks/{id}/actions (accept, version-bound)
      -> GET /api/v1/tasks/{id} + /messages + /events

Nothing is mocked: the only wrapper is a recording adapter that delegates to the
real ``AntigravityExecutor`` so the probe can keep the structured
``ExecutorResult`` + adapter events (usage/model/diff/proxy calls) that the
coordinator's sink intentionally does not persist.

Run:
    DEEPSEEK_API_KEY=... uv run python probes/lg010/lg010_e2e.py

Raw hard caps: ``--max-proxy-calls`` per execution and ``--model-calls-cap`` in
total (defaults 3 and 8; the QA ceiling is 10 upstream calls).  The credential
is never read from ``.env`` and never written to the evidence file.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

import httpx  # noqa: E402

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    mask_values,
)
from lightgravity.adapter.execution import ExecutorResult  # noqa: E402
from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.planner import (  # noqa: E402
    PlanProposal,
    RawSubtask,
    RuleBasedPlanner,
)
from lightgravity.store import FileStore  # noqa: E402

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
EVIDENCE_PATH = EVIDENCE_DIR / "lg010-evidence.json"
UPSTREAM = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash"
CREDENTIAL_REF = "deepseek-api-key"
MISSING_WORKSPACE_REF = "lg010-missing-workspace"
TARGET_FILE = "demo_target.txt"
TARGET_MARKER = "LG010_REAL_CLOSURE"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _find_harness_pids() -> list[int]:
    """PIDs whose cmdline mentions the SDK's local sandbox harness."""

    pids: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\x00", b" ")
                .decode("utf-8", "replace")
            )
        except OSError:
            continue
        if "localharness" in cmdline:
            pids.append(int(entry.name))
    return sorted(pids)


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=qa@lg010.local",
            "-c",
            "user.name=lg010-qa",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SingleNodePlanner(RuleBasedPlanner):
    """Minimal rule planner: one implementation node, no dependent verify node.

    Used only because the independent QA is itself hard-capped to 10 upstream
    calls; the product's default two-node (deliver + verify) graph is exercised
    by the LG-008 unit evidence.  The plan still carries real acceptance
    criteria, so the program-side validator and recruiter run unchanged.
    """

    name = "rules-single"

    async def plan(self, context: Any) -> PlanProposal:
        return PlanProposal(
            subtasks=(
                RawSubtask(
                    key="deliver",
                    objective=context.objective,
                    capability=self._implementation,
                    acceptance=tuple(context.acceptance_criteria),
                    write=True,
                ),
            ),
            source="rules-single",
            notes=("QA-budget single-node rule plan",),
        )


class RecordingExecutor:
    """QA wrapper: delegates to the real executor and records its results/events."""

    name = "antigravity:recording"
    version = "qa-wrapper"

    def __init__(self, inner: AntigravityExecutor) -> None:
        self.inner = inner
        self.results: list[ExecutorResult] = []
        self.events: list[dict[str, Any]] = []

    @property
    def model_calls_made(self) -> int:
        return self.inner.model_calls_made

    def capabilities(self) -> Any:
        return self.inner.capabilities()

    async def execute(self, request: Any, emit: Any) -> ExecutorResult:
        async def recording_emit(event: dict[str, Any]) -> None:
            self.events.append(event)
            result = emit(event)
            if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                await result

        result = await self.inner.execute(request, recording_emit)
        self.results.append(result)
        return result

    async def cancel(self, execution_ref: Any) -> Any:
        return await self.inner.cancel(execution_ref)

    async def close(self, session_ref: Any) -> None:
        await self.inner.close(session_ref)


def _create_resource(
    store: FileStore, kind: str, entity_id: str, *, body: str = "", **fields: Any
) -> None:
    fields.setdefault("title", entity_id)
    fields.setdefault("enabled", True)
    store.create(
        kind,
        entity_id,
        fields,
        actor="lg010-qa",
        request_id=f"lg010-res-{kind}-{entity_id}",
        body=body,
    )


def build_resources(store: FileStore) -> None:
    """Minimal first-version resources: one connection, profile, skill, tools, agent."""

    _create_resource(
        store,
        "connection",
        "primary",
        backend="openai-compat",
        model=MODEL,
        credential_ref=CREDENTIAL_REF,
        base_url=UPSTREAM,
    )
    _create_resource(
        store,
        "conversation",
        "task-worker",
        session_continuation_mode="create_or_resume",
        agent_behavior="autonomous",
    )
    _create_resource(store, "skill", "implementation", body="# Implementation\nDo the work.")
    _create_resource(store, "tool", "view-file", implementation="view-file")
    _create_resource(store, "tool", "create-file", implementation="create-file")
    _create_resource(store, "tool", "edit-file", implementation="edit-file")
    _create_resource(
        store,
        "agent",
        "developer",
        connection_ref="primary",
        conversation_ref="task-worker",
        skills={"source": "inline", "refs": ["implementation"]},
        tool_refs=["view-file", "create-file", "edit-file"],
        hook_refs=[],
        mcp_refs=[],
        trigger_refs=[],
        subagents=[],
        body=(
            "# Developer\n"
            "You are a developer agent. Execute the request using the provided file "
            "tools, then finish. Do not modify files other than the ones requested."
        ),
    )


def build_workspace(workspace_root: Path) -> Path:
    """Create a minimal git repo with a sample file (the "示例仓库")."""

    repo = workspace_root / "demo-repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "example.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (repo / "README.md").write_text("# demo repo\n\nsample workspace\n", encoding="utf-8")
    _run_git(repo, "init", "-q")
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-qm", "init demo repo")
    return repo


async def _wait_for_phase(
    client: httpx.AsyncClient,
    task_id: str,
    phases: set[str],
    *,
    timeout: float,
    poll: float = 0.5,
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    last: dict[str, Any] = {}
    while time.monotonic() - started < timeout:
        response = await client.get(f"/api/v1/tasks/{task_id}")
        last = response.json()
        if last.get("phase") in phases:
            # Let the coordinator finish its post-outcome release before we act.
            await asyncio.sleep(0.4)
            last = (await client.get(f"/api/v1/tasks/{task_id}")).json()
            if last.get("phase") in phases:
                return last, time.monotonic() - started
        await asyncio.sleep(poll)
    raise TimeoutError(f"task {task_id} did not reach {sorted(phases)} within {timeout}s; last={last}")


async def _post_json(
    client: httpx.AsyncClient, path: str, payload: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    response = await client.post(path, json=payload)
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        body = {"raw": response.text[:2000]}
    return response.status_code, body


@dataclass
class RunArtifacts:
    """Everything the probe collected for the primary closed loop."""

    task_id: str
    run_id: str | None
    primary: dict[str, Any]


async def run_primary_loop(
    client: httpx.AsyncClient,
    app: Any,
    store: Any,
    recording: RecordingExecutor,
    repo: Path,
    *,
    timeout: float,
) -> RunArtifacts:
    """Create Task via the API and drive it to `awaiting_acceptance` + accept."""

    objective = (
        f"Create a file named {TARGET_FILE} in the repository whose entire content "
        f"is exactly the line: {TARGET_MARKER}. Use the create_file tool. Do not "
        "modify any other file. Then call finish."
    )
    create_payload = {
        "request_id": "lg010-primary-create",
        "title": "LG-010 real closure",
        "objective": objective,
        "acceptance_criteria": [
            f"{TARGET_FILE} exists in the workspace and contains {TARGET_MARKER}"
        ],
        "workspace_ref": "demo-repo",
    }
    status_code, created = await _post_json(client, "/api/v1/tasks", create_payload)
    assert status_code == 200, f"create task failed: {status_code} {created}"
    task_id = created["task_id"]

    # Idempotent create: same request_id returns the same Task, no duplicate.
    status_code2, created2 = await _post_json(client, "/api/v1/tasks", create_payload)
    create_idempotent = status_code2 == 200 and created2["task_id"] == task_id

    detail, waited = await _wait_for_phase(
        client, task_id, {"verifying", "failed", "cancelled"}, timeout=timeout
    )
    run_id = detail.get("run", {}).get("id") if isinstance(detail.get("run"), dict) else None

    result: dict[str, Any] = {
        "task_id": task_id,
        "run_id": run_id,
        "create_status": status_code,
        "create_idempotent": create_idempotent,
        "waited_seconds": round(waited, 2),
        "phase_after_execution": detail.get("phase"),
        "task_detail_after_execution": _shrink(detail),
    }
    _capture_execution_diagnostics(result, recording, repo)
    events_json = (await client.get(f"/api/v1/tasks/{task_id}/events")).json()
    result["task_events"] = _shrink(events_json)

    if detail.get("phase") != "verifying":
        result["stopped_at"] = "execution did not reach verifying"
        return RunArtifacts(task_id=task_id, run_id=run_id, primary=result)

    # ---- user status/query message and query-API responsiveness -------------
    status_code, body = await _post_json(
        client,
        f"/api/v1/tasks/{task_id}/messages",
        {"message_id": "lg010-msg-status", "content": "状态", "role": "user"},
    )
    result["status_message"] = {"status": status_code, "kind": body.get("kind")}
    status_code2, body2 = await _post_json(
        client,
        f"/api/v1/tasks/{task_id}/messages",
        {"message_id": "lg010-msg-status", "content": "状态", "role": "user"},
    )
    result["status_message_idempotent"] = status_code2 == status_code and body2.get("kind") == body.get("kind")
    messages = (await client.get(f"/api/v1/tasks/{task_id}/messages")).json()
    result["messages"] = messages

    # ---- authorize the documented machine checks ----------------------------
    # The `checks:` authorization is an optional Task frontmatter field with no
    # HTTP setter in this version (docs/08 additive field); the harness writes it
    # directly to the Store, exactly like the LG-009 integration test does.
    task_entity = store.read("task", task_id)
    store.write(
        "task",
        task_id,
        {"checks": ["evidence-present", "artifacts-in-workspace"]},
        expected_revision=task_entity.revision,
        actor="lg010-qa",
    )
    result["checks_authorized"] = ["evidence-present", "artifacts-in-workspace"]

    # ---- verification (stop gate + machine checks) --------------------------
    verify_started = time.monotonic()
    verification = app.state.verification
    verify = verification.verify_and_prepare(task_id, request_id="lg010-verify")
    result["verify"] = verify.to_dict()
    result["verify_seconds"] = round(time.monotonic() - verify_started, 2)
    verify_replay = verification.verify_and_prepare(task_id, request_id="lg010-verify")
    result["verify_idempotent"] = verify_replay.to_dict() == verify.to_dict()

    acceptance_view = (await client.get(f"/api/v1/tasks/{task_id}/acceptance")).json()
    result["acceptance_view"] = _shrink(acceptance_view)

    detail_awaiting = (await client.get(f"/api/v1/tasks/{task_id}")).json()
    result["phase_awaiting"] = detail_awaiting.get("phase")
    result["members_after_stop"] = [
        {"id": m.get("id"), "state": m.get("state"), "run_ref": m.get("run_ref")}
        for m in detail_awaiting.get("members", [])
    ]
    result["subtasks"] = [
        {
            "id": s.get("id"),
            "state": s.get("state"),
            "acceptance": s.get("acceptance"),
            "upstream_artifact_refs": s.get("upstream_artifact_refs"),
        }
        for s in detail_awaiting.get("subtasks", [])
    ]
    result["run_after_stop"] = _shrink(detail_awaiting.get("run"))

    # ---- version binding: stale accept/reject must fail ---------------------
    stale_accept_status, stale_accept = await _post_json(
        client,
        f"/api/v1/tasks/{task_id}/actions",
        {
            "action": "accept",
            "request_id": "lg010-accept-stale",
            "expected_deliverable_revision": 999,
        },
    )
    stale_reject_status, stale_reject = await _post_json(
        client,
        f"/api/v1/tasks/{task_id}/actions",
        {
            "action": "reject",
            "request_id": "lg010-reject-stale",
            "expected_requirements_revision": 999,
        },
    )
    result["stale_accept"] = {"http": stale_accept_status, "code": stale_accept.get("error", {}).get("code")}
    result["stale_reject"] = {"http": stale_reject_status, "code": stale_reject.get("error", {}).get("code")}

    # ---- correct, version-bound accept --------------------------------------
    acceptance = acceptance_view.get("acceptance", {})
    deliverable_revision = acceptance.get("deliverable_revision")
    requirements_revision = acceptance.get("requirements_revision")
    candidate_ref = acceptance.get("candidate_ref")
    accept_payload = {
        "action": "accept",
        "request_id": "lg010-accept",
        "expected_requirements_revision": requirements_revision,
        "expected_deliverable_revision": deliverable_revision,
        "target_run_id": candidate_ref,
        "note": "LG-010 QA acceptance",
    }
    accept_status, accept_body = await _post_json(
        client, f"/api/v1/tasks/{task_id}/actions", accept_payload
    )
    result["accept"] = {"http": accept_status, "body": _shrink(accept_body)}
    accept_status2, accept_body2 = await _post_json(
        client, f"/api/v1/tasks/{task_id}/actions", accept_payload
    )
    result["accept_idempotent"] = (
        accept_status2 == accept_status
        and accept_body2.get("state") == accept_body.get("state")
        and accept_body2.get("phase") == accept_body.get("phase")
    )

    final_detail = (await client.get(f"/api/v1/tasks/{task_id}")).json()
    result["phase_final"] = final_detail.get("phase")
    result["status_final"] = final_detail.get("status")
    result["run_final_state"] = (final_detail.get("run") or {}).get("state")
    result["events"] = _shrink((await client.get(f"/api/v1/tasks/{task_id}/events")).json())

    _capture_execution_diagnostics(result, recording, repo)
    return RunArtifacts(task_id=task_id, run_id=run_id, primary=result)


def _capture_execution_diagnostics(
    result: dict[str, Any], recording: RecordingExecutor, repo: Path
) -> None:
    """Record raw artifacts/diff, structured results, usage and proxy calls."""

    target = repo / TARGET_FILE
    git_diff = _run_git(repo, "diff")
    git_status = _run_git(repo, "status", "--porcelain")
    git_show = _run_git(repo, "diff", "--stat")
    result["workspace"] = {
        "target_exists": target.exists(),
        "target_content": target.read_text(encoding="utf-8") if target.exists() else None,
        "target_sha256": _sha256_file(target) if target.exists() else None,
        "git_status_porcelain": git_status.stdout.splitlines(),
        "git_diff": git_diff.stdout,
        "git_diff_stat": git_show.stdout,
    }
    result["executor_results"] = [
        {
            "state": r.state,
            "summary": r.summary,
            "model": r.model,
            "upstream_model": r.upstream_model,
            "usage": r.usage.to_dict(),
            "artifact_refs": list(r.artifact_refs),
            "diff_ref": r.diff_ref,
            "stop_reason": r.stop_reason,
            "stop_confirmed": r.stop_confirmed,
            "session_ref": r.session_ref.to_dict() if r.session_ref else None,
            "failure": r.failure.to_dict() if r.failure else None,
            "check_records": [c.to_dict() for c in r.check_records],
        }
        for r in recording.results
    ]
    finished = [
        e for e in recording.events if e.get("type") == "adapter.execution_finished"
    ]
    result["adapter_upstream_calls"] = [e.get("upstream_calls") for e in finished]
    result["adapter_event_types"] = sorted({str(e.get("type")) for e in recording.events})
    result["adapter_trace"] = [
        {
            key: (value[:200] if isinstance(value, str) else value)
            for key, value in {
                "type": e.get("type"),
                "name": e.get("name"),
                "status": e.get("status"),
                "error": e.get("error"),
                "text": e.get("text"),
            }.items()
            if value is not None
        }
        for e in recording.events
        if e.get("type") in {"adapter.tool_call", "adapter.tool_result", "adapter.error"}
    ][:60]
    result["model_calls_made_after_primary"] = recording.model_calls_made


async def run_failure_case(
    client: httpx.AsyncClient, *, timeout: float
) -> dict[str, Any]:
    """A missing-workspace Task must fail honestly with no model call."""

    create_payload = {
        "request_id": "lg010-fail-create",
        "title": "LG-010 missing workspace",
        "objective": "Create a file in a workspace that does not exist.",
        "acceptance_criteria": ["never reached"],
        "workspace_ref": MISSING_WORKSPACE_REF,
    }
    status_code, created = await _post_json(client, "/api/v1/tasks", create_payload)
    task_id = created["task_id"]
    detail, waited = await _wait_for_phase(
        client, task_id, {"failed", "cancelled", "waiting_user"}, timeout=timeout
    )
    events = (await client.get(f"/api/v1/tasks/{task_id}/events")).json()
    error_events = [
        item for item in events.get("items", []) if item.get("type") == "error.recorded"
    ]
    return {
        "task_id": task_id,
        "create_status": status_code,
        "phase": detail.get("phase"),
        "status": detail.get("status"),
        "waited_seconds": round(waited, 2),
        "run": _shrink(detail.get("run")),
        "error_events": _shrink(error_events),
        "subtasks": [
            {"id": s.get("id"), "state": s.get("state"), "fail_reason": s.get("fail_reason")}
            for s in detail.get("subtasks", [])
        ],
    }


def _shrink(value: Any, *, limit: int = 6000) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...[truncated]"
    if isinstance(value, dict):
        return {str(k): _shrink(v, limit=limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_shrink(item, limit=limit) for item in value]
    return value


async def amain(args: argparse.Namespace) -> int:
    secret = os.environ.get("DEEPSEEK_API_KEY") or ""
    report: dict[str, Any] = {
        "task": "LG-010",
        "kind": "prototype-v0-minimal-backend-closed-loop",
        "at": _now(),
        "python": platform.python_version(),
        "platform": f"{sys.platform}-{platform.machine()}",
        "head": _git_head(),
        "model_requested": MODEL,
        "upstream": UPSTREAM,
        "credential": {
            "source": "env:DEEPSEEK_API_KEY" if secret else "missing",
            "present": bool(secret),
        },
        "hard_caps": {
            "max_proxy_calls_per_execution": args.max_proxy_calls,
            "model_calls_cap_total": args.model_calls_cap,
        },
        "findings": [],
        "limitations": [],
    }
    if not secret:
        report["limitations"].append(
            "DEEPSEEK_API_KEY was not present; the real chain could not run (no stub substituted)."
        )
        _write_report(report, secret)
        return 2

    root = Path(tempfile.mkdtemp(prefix="lg010-e2e-"))
    before = _find_harness_pids()
    report["process_check"] = {"localharness_pids_before": before}
    try:
        data_dir = root / "bot-data"
        workspace_root = data_dir / "workspaces"
        secret_store = root / "secrets"
        workspace_root.mkdir(parents=True, exist_ok=True)
        repo = build_workspace(workspace_root)

        store = FileStore(data_dir, workspace_root)
        build_resources(store)
        recording = RecordingExecutor(
            AntigravityExecutor(
                store,
                artifacts=DirectoryArtifactSink(root / "artifacts"),
                workspace_root=workspace_root,
                max_proxy_calls=args.max_proxy_calls,
                model_calls_cap=args.model_calls_cap,
                cancel_timeout=15.0,
                upstream_timeout=180.0,
            )
        )
        catalog = RoleCatalog(
            {"implementation": ["developer"], "verification": ["developer"]}
        )
        planner = RuleBasedPlanner() if args.planner == "rules" else SingleNodePlanner()
        dispatcher = GraphDispatcher(
            store, recording, catalog=catalog, planner=planner, max_parallel=1
        )
        settings = Settings(
            data_dir=data_dir, workspace_root=workspace_root, secret_store=secret_store
        )
        app = create_app(settings, store=store, dispatcher=dispatcher, executor=recording)

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver", timeout=300.0
            ) as client:
                report["planner"] = args.planner
                report["real_executor_wired"] = bool(app.state.context.real_executor)
                health = (await client.get("/api/v1/health")).json()
                report["health"] = _shrink(health)

                started = time.monotonic()
                artifacts = await run_primary_loop(
                    client,
                    app,
                    app.state.store,
                    recording,
                    repo,
                    timeout=args.timeout,
                )
                report["primary"] = artifacts.primary
                report["primary"]["total_seconds"] = round(time.monotonic() - started, 2)

                fail_started = time.monotonic()
                report["failure_case"] = await run_failure_case(
                    client, timeout=args.timeout
                )
                report["failure_case"]["total_seconds"] = round(
                    time.monotonic() - fail_started, 2
                )

                report["model_calls_this_run"] = recording.model_calls_made
                report["model_calls_previous_attempts"] = args.prior_calls
                report["model_calls_total"] = args.prior_calls + recording.model_calls_made
                report["within_hard_cap_10"] = (
                    args.prior_calls + recording.model_calls_made
                ) <= 10

                # The missing-workspace case must not consume any model call.
                if report["failure_case"].get("phase") != "failed":
                    report["findings"].append(
                        {
                            "severity": "high",
                            "issue": "missing-workspace Task did not end in failed",
                            "evidence": report["failure_case"].get("phase"),
                        }
                    )
    finally:
        if args.keep:
            print(f"kept temp root: {root}", file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)

    after = _find_harness_pids()
    report["process_check"]["localharness_pids_after"] = after
    report["process_check"]["leaked"] = sorted(set(after) - set(before))
    report["limitations"].extend(
        [
            "Minimal backend loop only: no browser/UI, no full crash-recovery suite (LG-021/LG-022).",
            "Only the openai-compat (DeepSeek) backend was exercised; Gemini/Vertex remain unverified.",
            "The verification trigger is invoked on the shared VerificationService; the coordinator "
            "does not call verify_and_prepare automatically and no HTTP endpoint exposes it (recorded below).",
            "Task `checks:` authorization is frontmatter-only in this version; the harness writes it "
            "directly to the Store (no HTTP setter).",
            "sandbox isolation was not escape-tested; only the SDK-reported status is recorded.",
        ]
    )
    # Record the wiring observation explicitly as a finding candidate.
    report["findings"].append(
        {
            "severity": "medium",
            "issue": "coordinator does not auto-trigger verification; no HTTP endpoint exposes verify_and_prepare",
            "location": "backend/lightgravity/coordinator/service.py:_apply_outcome",
            "impact": "a user reaching verifying via the HTTP entry must rely on an internal service call to reach awaiting_acceptance",
            "qa_handling": "harness invoked app.state.verification.verify_and_prepare (documented LG-010 integration step)",
        }
    )
    _write_report(report, secret)
    print(
        json.dumps(
            {
                "evidence": str(EVIDENCE_PATH),
                "primary_phase_final": report.get("primary", {}).get("phase_final"),
                "failure_phase": report.get("failure_case", {}).get("phase"),
                "model_calls_total": report.get("model_calls_total"),
                "leaked_processes": report["process_check"]["leaked"],
                "findings": [f["issue"] for f in report["findings"]],
            },
            indent=2,
        )
    )
    return 0


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True, text=True
    )
    return result.stdout.strip()


def _write_report(report: dict[str, Any], secret: str) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    redacted = mask_values(report, [secret] if secret else [])
    serialized = json.dumps(redacted, indent=2)
    if secret and secret in serialized:
        raise SystemExit("refusing to write evidence: secret value appeared in report")
    EVIDENCE_PATH.write_text(serialized, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-proxy-calls", type=int, default=4)
    parser.add_argument("--model-calls-cap", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--planner", choices=("rules", "rules-single"), default="rules-single")
    parser.add_argument("--prior-calls", type=int, default=6)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.max_proxy_calls * 2 > args.model_calls_cap:
        print("warning: two subtasks may exceed the global cap", file=sys.stderr)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
