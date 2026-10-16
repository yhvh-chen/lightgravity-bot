#!/usr/bin/env python3
"""L-R2-ROUTING-QA API route probe (independent, component/API ONLY).

Exercises the **public global messages API** end-to-end through the real
``create_app`` wiring for the exact R2 finding goal:

  POST /api/v1/sources                      (native UTF-8 upload -> machine body)
  POST /api/v1/conversations/global/messages (observed goal + selected source)

The fixture **holds the dispatcher with an in-process component executor**: there
is **no Antigravity SDK, no model, no DeepSeek, no network**. This is
**component/API evidence only** and must not be read as actual SDK delivery.

Asserts:
  1. route is ``task`` / ``create_task`` (not ``decision``/control),
  2. the created Task carries program-derived acceptance criteria AND an
     authorized workspace (so the default rule plan validates),
  3. the selected-source snapshot is handed off on the Task's ``selected_trigger``
     (message-bound, not inherited),
  4. the Run persists a validated program ``plan``/``plan_hash`` (single write
     node), and the exact selected brief body reaches the worker instructions.

No product code, no test code, no deps, no port 8123, no real product calls.
Writes a JSON report to stdout; exits non-zero on any failed assertion.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    adapter_capabilities,
)
from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.coordinator.graph import GraphDispatcher
from lightgravity.coordinator.recruiter import RoleCatalog
from lightgravity.store import FileStore

# The exact observed-file goal from the R2 QA finding (contains "approved").
OBSERVED_GOAL = (
    "Create a Markdown file orion-summary.md using only the selected brief. "
    "Include project name, programme owner, primary launch date, total approved "
    "budget, project ID, and change ticket. Return the file as the deliverable."
)

BRIEF_FILENAME = "orion-brief-alpha.txt"
BRIEF_BODY = (
    "PROJECT ORION-71 \u2014 alpha brief. Project code name ORION-71. "
    "Programme owner Halden Reyes. Primary launch date 2027-03-14. "
    "Total approved budget 418,250 EUR. Change ticket CHG-4471."
)

#: prototype single-worker catalog (implementation + verification capability).
ONE_AGENT = RoleCatalog({"implementation": ["developer"], "verification": ["developer"]})


class ComponentExecutor:
    """In-process component executor double (explicitly NOT real SDK evidence).

    Records every ExecuteRequest and returns a deterministic success. It never
    contacts any SDK/model/network.
    """

    name = "component-double"
    version = "0"
    real_sdk = False

    def __init__(self) -> None:
        self.requests: list[ExecuteRequest] = []

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(self, request: ExecuteRequest, emit: Any) -> ExecutorResult:
        self.requests.append(request)
        return ExecutorResult(
            state="succeeded",
            summary="component-double: succeeded (no SDK)",
            artifact_refs=(f"artifact_{request.subtask_id}",),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        return CancelResult(confirmed=True, state="cancelled")


def _seed_resources(store: FileStore) -> None:
    """Test-fixture resources (agents/skills/tools/connection), not product data."""

    def create(kind: str, eid: str, **fields: Any) -> None:
        fields.setdefault("title", eid)
        fields.setdefault("enabled", True)
        store.create(kind, eid, fields, actor="qa-fixture", request_id=f"qa:{kind}:{eid}", body="# res\n")

    create(
        "connection",
        "primary",
        backend="openai-compat",
        model="deepseek-v4-flash",
        credential_ref="worker-default",
        base_url="http://127.0.0.1:9/v1",
    )
    create("conversation", "task-worker", session_continuation_mode="create_or_resume")
    create("skill", "implementation", description="Implementation", body="# Impl\nDo it.")
    create("tool", "view-file", implementation="view-file")
    create("tool", "edit-file", implementation="edit-file")
    create(
        "agent",
        "developer",
        connection_ref="primary",
        conversation_ref="task-worker",
        skills={"source": "inline", "refs": ["implementation"]},
        tool_refs=["view-file", "edit-file"],
        hook_refs=[],
        mcp_refs=[],
        trigger_refs=[],
        subagents=[],
    )


async def _run(root: Path) -> dict[str, Any]:
    data_dir = root / "data"
    settings = Settings(
        data_dir=data_dir,
        workspace_root=data_dir / "workspaces",
        secret_store=root / "secrets",
    )
    store = FileStore(data_dir, settings.workspace_root)
    _seed_resources(store)
    executor = ComponentExecutor()
    dispatcher = GraphDispatcher(store, executor, catalog=ONE_AGENT)
    app = create_app(
        settings,
        store=store,
        dispatcher=dispatcher,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )

    result: dict[str, Any] = {"evidence_boundary": "component/API ONLY; no actual SDK"}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Native UTF-8 upload via the public source API (no seeded derivative).
            up = await client.post(
                "/api/v1/sources",
                json={
                    "request_id": "qa-l-r2-up-1",
                    "filename": BRIEF_FILENAME,
                    "media_type": "text/plain",
                    "content_base64": base64.b64encode(BRIEF_BODY.encode("utf-8")).decode(),
                },
            )
            result["source_upload_status"] = up.status_code
            up_body = up.json()
            result["source_upload_ok"] = up.status_code in (200, 201)
            src = up_body.get("source", {})
            source_id = src.get("source_id")
            result["source_id"] = source_id
            result["source_status"] = src.get("status")
            result["source_derivatives"] = src.get("derivatives")
            result["source_formal"] = src.get("formal")
            result["source_receipts"] = up_body.get("receipts")

            # 2. Observed goal via the public global messages API with selection.
            post = await client.post(
                "/api/v1/conversations/global/messages",
                json={
                    "message_id": "qa-l-r2-msg-1",
                    "content": OBSERVED_GOAL,
                    "selected_sources": [{"source_id": source_id}],
                },
            )
            result["route_status"] = post.status_code
            routed = post.json()
            result["route_kind"] = routed.get("kind")
            result["route_intent"] = routed.get("data", {}).get("intent")
            result["route_creates_task"] = routed.get("data", {}).get("creates_task")
            task_id = routed.get("task_id")
            result["task_id"] = task_id

            # 3. Inspect the created task entity (acceptance + workspace + trigger).
            if task_id:
                detail = (await client.get(f"/api/v1/tasks/{task_id}")).json()
                result["task_acceptance_criteria"] = detail.get("acceptance_criteria")
                result["task_workspace_ref"] = detail.get("workspace_ref")
                entity = store.read("task", task_id).entity
                trigger = entity.get("selected_trigger")
                result["selected_trigger_message_id"] = (trigger or {}).get("message_id")
                snap = (trigger or {}).get("snapshot") or {}
                refs = snap.get("refs") or []
                result["selected_trigger_source_ids"] = [r.get("source_id") for r in refs]

                # 4. Let the run build+validate the program plan and dispatch.
                for _ in range(200):
                    task = store.read("task", task_id).entity
                    if task.get("phase") in {
                        "executing",
                        "verifying",
                        "waiting_user",
                        "awaiting_acceptance",
                        "failed",
                        "completed",
                    }:
                        break
                    await asyncio.sleep(0.02)
                task = store.read("task", task_id).entity
                result["task_phase"] = task.get("phase")
                run_id = task.get("active_run")
                result["run_id"] = run_id
                if run_id:
                    run = store.read("run", run_id).entity
                    plan = run.get("plan") or {}
                    result["run_plan_source"] = run.get("plan_source")
                    result["run_plan_hash"] = run.get("plan_hash")
                    result["run_plan_subtask_keys"] = [
                        s.get("key") for s in plan.get("subtasks", [])
                    ]
                result["executor_request_count"] = len(executor.requests)
                if executor.requests:
                    req = executor.requests[0]
                    result["worker_has_workspace"] = bool(req.workspace_path)
                    result["worker_has_acceptance"] = bool(req.acceptance_criteria)
                    result["worker_instructions_has_brief"] = BRIEF_BODY in req.instructions
                    result["worker_instructions_has_selected_wrap"] = (
                        "UNTRUSTED" in req.instructions or "untrusted" in req.instructions
                    )

    # Assertions (component/API only).
    checks = {
        "source_extracted": result.get("source_status") == "extracted",
        "source_native_derivative": any(
            (d.get("extractor") or "") == "native-utf8-text"
            for d in (result.get("source_derivatives") or [])
        )
        or any(
            (d.get("model_version") == "none")
            for d in (result.get("source_derivatives") or [])
        ),
        "source_native_receipt": any(
            (r.get("detail") or "").startswith("native UTF-8 text extracted")
            for r in (result.get("source_receipts") or [])
        ),
        "route_kind_task": result.get("route_kind") == "task",
        "route_intent_delivery": result.get("route_intent") == "delivery",
        "route_creates_task": result.get("route_creates_task") is True,
        "task_acceptance_present": bool(result.get("task_acceptance_criteria")),
        "task_workspace_present": bool(result.get("task_workspace_ref")),
        "trigger_message_bound": result.get("selected_trigger_message_id") == "qa-l-r2-msg-1",
        "trigger_source_bound": source_id in (result.get("selected_trigger_source_ids") or []),
        "run_plan_present": bool(result.get("run_plan_hash")) and bool(result.get("run_plan_subtask_keys")),
        "worker_ran": (result.get("executor_request_count") or 0) >= 1,
        "worker_has_workspace": result.get("worker_has_workspace") is True,
        "worker_has_acceptance": result.get("worker_has_acceptance") is True,
        "worker_has_brief": result.get("worker_instructions_has_brief") is True,
    }
    result["checks"] = checks
    result["passed"] = all(checks.values())
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="l-r2-routing-qa-") as tmp:
        report = asyncio.run(_run(Path(tmp)))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
