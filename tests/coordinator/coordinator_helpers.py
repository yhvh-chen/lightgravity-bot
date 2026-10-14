"""Shared helpers for LG-007 coordinator tests."""

from __future__ import annotations

import asyncio
from typing import Any

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    FailureInfo,
    SessionRef,
    adapter_capabilities,
)
from lightgravity.coordinator import Coordinator, SingleSlotDispatcher
from lightgravity.store import FileStore, new_id

CONV = new_id("conv")


def task_content(**overrides: Any) -> dict[str, Any]:
    content: dict[str, Any] = {
        "title": "Test task",
        "objective": "do the thing",
        "acceptance_criteria": ["it works"],
        "status": "todo",
        "phase": "intake",
        "requirements_revision": 1,
        "project_ref": None,
        "repository_ref": None,
        "workspace_ref": None,
        "agent_ref": "coordinator",
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
        "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
        "archived": False,
    }
    content.update(overrides)
    return content


def raw_task(store: FileStore, **overrides: Any) -> str:
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        task_content(**overrides),
        actor="test",
        request_id=f"req:{task_id}",
        body="# Task\n",
    )
    return task_id


def message(content: str, *, message_id: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message_id": message_id or new_id("msg"),
        "role": "user",
        "content": content,
    }
    payload.update(extra)
    return payload


class FakeExecutor:
    """Deterministic in-process executor used only as unit evidence.

    This is explicitly **not** real SDK/mode evidence; LG-010 runs the real
    backend.  It can block on a gate so tests can observe the single execution
    slot and control responsiveness.
    """

    name = "fake"
    version = "0"

    def __init__(
        self,
        state: str = "succeeded",
        *,
        gate: asyncio.Event | None = None,
        cancel_confirms: bool = True,
    ) -> None:
        self.state = state
        self.gate = gate
        self.cancel_confirms = cancel_confirms
        self.requests: list[ExecuteRequest] = []
        self.started = asyncio.Event()
        self.cancel_calls = 0

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(self, request: ExecuteRequest, emit: Any) -> ExecutorResult:
        self.requests.append(request)
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        failure = (
            FailureInfo("boom", "boom") if self.state in {"failed", "blocked"} else None
        )
        return ExecutorResult(
            state=self.state,
            summary=f"fake:{self.state}",
            failure=failure,
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.run_id}",
                task_id=request.task_id,
                run_id=request.run_id,
            ),
            stop_confirmed=True if self.state == "cancelled" else None,
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        self.cancel_calls += 1
        if self.gate is not None:
            self.gate.set()
        return CancelResult(
            confirmed=self.cancel_confirms,
            state="cancelled" if self.cancel_confirms else "unconfirmed",
        )

    async def close(self, session_ref: SessionRef) -> None:
        return None


def make_coordinator(store: FileStore, executor: FakeExecutor | None = None, **kwargs: Any) -> Coordinator:
    return Coordinator(store, dispatcher=SingleSlotDispatcher(executor or FakeExecutor()), **kwargs)


async def wait_for_phase(
    coordinator: Coordinator, task_id: str, phases: set[str], *, timeout: float = 5.0
) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        phase = str(coordinator.status(task_id)["phase"])
        if phase in phases:
            return phase
        await asyncio.sleep(0.01)
    return str(coordinator.status(task_id)["phase"])
