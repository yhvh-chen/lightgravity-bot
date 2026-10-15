"""Shared helpers for LG-008 planner/recruiter/scheduler/graph tests.

All data lives under pytest ``tmp_path``; no test touches ``bot-data``, the
network or a real model.  The fake executor is unit evidence only - the real
SDK/DeepSeek end-to-end path is LG-010.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    SessionRef,
    adapter_capabilities,
)
from lightgravity.coordinator import DispatchContext, RunController
from lightgravity.coordinator.planning import PlanningRequest
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore, new_id

Responder = Callable[[ExecuteRequest], ExecutorResult]


def create_resource(store: FileStore, kind: str, entity_id: str, **fields: Any) -> None:
    fields.setdefault("title", entity_id)
    fields.setdefault("enabled", True)
    store.create(
        kind,
        entity_id,
        fields,
        actor="test",
        request_id=f"req-{kind}-{entity_id}",
        body=fields.pop("body", ""),
    )


def build_environment(
    store: FileStore,
    *,
    tool_refs: tuple[str, ...] = ("view-file", "edit-file"),
) -> None:
    """Create a verified openai-compat connection, skills, tools and agents."""

    create_resource(
        store,
        "connection",
        "primary",
        backend="openai-compat",
        model="deepseek-v4-flash",
        credential_ref="worker-default",
        base_url="http://127.0.0.1:9/v1",
    )
    create_resource(store, "conversation", "task-worker", session_continuation_mode="create_or_resume")
    create_resource(store, "skill", "implementation", description="Implementation", body="# Impl\nDo it.")
    create_resource(store, "skill", "verification", description="Verification", body="# Verify\nCheck it.")
    create_resource(store, "tool", "view-file", implementation="view-file")
    create_resource(store, "tool", "edit-file", implementation="edit-file")
    create_resource(store, "tool", "run-command", implementation="run-command")
    create_agent(store, "developer", skill_refs=["implementation"], tool_refs=tool_refs)
    create_agent(
        store,
        "verifier",
        skill_refs=["verification"],
        tool_refs=("view-file", "run-command"),
    )


def create_agent(
    store: FileStore,
    agent_id: str,
    *,
    skill_refs: list[str],
    tool_refs: tuple[str, ...],
    body: str = "# Agent\n",
    extra: Mapping[str, Any] | None = None,
) -> None:
    fields: dict[str, Any] = {
        "connection_ref": "primary",
        "conversation_ref": "task-worker",
        "skills": {"source": "inline", "refs": list(skill_refs)},
        "tool_refs": list(tool_refs),
        "hook_refs": [],
        "mcp_refs": [],
        "trigger_refs": [],
        "subagents": [],
    }
    if extra:
        fields.update(extra)
    create_resource(store, "agent", agent_id, body=body, **fields)


def make_dispatch_setup(
    store: FileStore,
    *,
    objective: str = "implement the feature",
    acceptance: tuple[str, ...] = ("the feature works",),
    workspace_ref: str = "task-ws",
    agent_ref: str | None = "developer",
    allowed_tools: tuple[str, ...] | None = None,
    budget: Mapping[str, int] | None = None,
    planning_request: PlanningRequest | None = None,
) -> tuple[str, str, RunController, DispatchContext]:
    """Create a Task+Run already in the ``planning`` phase and a RunController."""

    workspace = store.resolve_path(workspace_ref, write=True)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "graph task",
            "objective": objective,
            "acceptance_criteria": list(acceptance),
            "status": "in-progress",
            "phase": "planning",
            "requirements_revision": 1,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": workspace_ref,
            "agent_ref": agent_ref,
            "depends_on": [],
            "active_run": None,
            "deliverable_revision": 0,
            "queue": {
                "state": "not_queued",
                "order": None,
                "queued_at": None,
                "owner": None,
                "lease_expires_at": None,
            },
            "acceptance": {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": [],
                "decided_at": None,
                "decision_ref": None,
            },
            "budget": dict(budget or {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1}),
            "archived": False,
        },
        actor="test",
        request_id=f"req-{task_id}",
        body="# Task\n",
    )
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "planning",
            "plan_ref": "PLAN.md",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"req-{run_id}",
        body=f"# Run {run_id}\n",
    )
    writer = StateWriter(store, actor="test")
    writer.write_task(task_id, {"active_run": run_id})
    controller = RunController(writer, task_id, run_id)
    context = DispatchContext(
        task_id=task_id,
        run_id=run_id,
        attempt=1,
        objective=objective,
        acceptance_criteria=acceptance,
        instructions="# Task\n",
        workspace_path=str(workspace),
        allowed_tools=allowed_tools,
        agent_ref=agent_ref,
        budget=dict(budget or {}),
        planning_request=planning_request,
    )
    return task_id, run_id, controller, context


class FakeGraphExecutor:
    """Deterministic in-process executor; unit evidence only (not real SDK)."""

    name = "fake-graph"
    version = "0"

    def __init__(
        self,
        responder: Responder | None = None,
        *,
        gate: asyncio.Event | None = None,
        cancel_confirms: bool = True,
        delay: float = 0.0,
    ) -> None:
        self.requests: list[ExecuteRequest] = []
        self.cancel_calls = 0
        self.cancel_confirms = cancel_confirms
        self._gate = gate
        self._delay = delay
        self._responder = responder or self._default_responder
        self.active = 0
        self.peak_concurrent = 0
        self.started = asyncio.Event()

    @staticmethod
    def _default_responder(request: ExecuteRequest) -> ExecutorResult:
        return ExecutorResult(
            state="succeeded",
            summary=f"ok:{request.subtask_id}",
            artifact_refs=(f"artifact_{request.subtask_id}",),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(self, request: ExecuteRequest, emit: Any) -> ExecutorResult:
        self.active += 1
        self.peak_concurrent = max(self.peak_concurrent, self.active)
        self.requests.append(request)
        self.started.set()
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            if self._gate is not None:
                await self._gate.wait()
            return self._responder(request)
        finally:
            self.active -= 1

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        self.cancel_calls += 1
        return CancelResult(
            confirmed=self.cancel_confirms,
            state="cancelled" if self.cancel_confirms else "unconfirmed",
        )

    async def close(self, session_ref: SessionRef) -> None:
        return None


def task_phase(store: FileStore, task_id: str) -> str:
    return str(store.read("task", task_id).entity.get("phase"))


def run_state(store: FileStore, run_id: str) -> str:
    return str(store.read("run", run_id).entity.get("state"))


def subtask_states(store: FileStore) -> list[dict[str, Any]]:
    base = store.data_dir / "subtasks"
    if not base.is_dir():
        return []
    return [
        dict(store.read("subtask", child.name).entity)
        for child in sorted(base.iterdir())
        if child.is_dir()
    ]


__all__ = [
    "FakeGraphExecutor",
    "Responder",
    "build_environment",
    "create_agent",
    "create_resource",
    "make_dispatch_setup",
    "run_state",
    "subtask_states",
    "task_phase",
]
