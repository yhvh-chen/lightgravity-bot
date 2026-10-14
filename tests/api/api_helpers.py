"""Shared doubles for LG-012 API tests.

``FakeExecutor`` is an in-process adapter double (unit evidence only; real
SDK/DeepSeek end-to-end is LG-010).  ``StubDispatcher`` is a deterministic
implementation of the LG-007 ``Dispatcher`` seam used to exercise control
confirmation without depending on the queue's timing.

``AsgiEventStream`` is a tiny in-loop ASGI client: httpx's ``ASGITransport``
buffers responses, so real SSE replay/disconnect is asserted by driving the
ASGI app directly with ``receive``/``send`` in the same event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import FastAPI

from lightgravity.adapter import (
    AdapterCapabilities,
    CancelResult,
    ExecuteRequest,
    ExecutionRef,
    ExecutorResult,
    SessionRef,
    adapter_capabilities,
)
from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.coordinator.dispatcher import DispatchContext, DispatchOutcome
from lightgravity.coordinator.state import RunController

_TERMINAL_PHASES = {"failed", "cancelled", "completed"}


class FakeExecutor:
    name = "fake"
    version = "0"

    def __init__(self, *, cancel_confirms: bool = True) -> None:
        self.cancel_confirms = cancel_confirms
        self.gate: asyncio.Event | None = None
        self.started = asyncio.Event()
        self.cancel_calls = 0
        self.requests: list[ExecuteRequest] = []

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(
        self, request: ExecuteRequest, emit: Any
    ) -> ExecutorResult:
        self.requests.append(request)
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        return ExecutorResult(
            state="succeeded",
            summary="fake: succeeded",
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.run_id}",
                task_id=request.task_id,
                run_id=request.run_id,
            ),
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        self.cancel_calls += 1
        if self.gate is not None:
            self.gate.set()
        return CancelResult(
            confirmed=self.cancel_confirms,
            state="cancelled" if self.cancel_confirms else "unconfirmed",
            reason="fake cancel",
        )

    async def close(self, session_ref: SessionRef) -> None:
        return None


class StubDispatcher:
    """Dispatcher seam double that stays in ``executing`` until cancelled."""

    name = "stub"

    def __init__(self, *, cancel_confirmed: bool = True) -> None:
        self.cancel_confirmed = cancel_confirmed
        self.cancel_calls = 0
        self.started = asyncio.Event()

    async def dispatch(
        self,
        context: DispatchContext,
        controller: RunController,
        emit: Any,
    ) -> DispatchOutcome:
        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        self.started.set()
        await asyncio.Event().wait()  # blocks until the worker task is cancelled
        return DispatchOutcome(state="succeeded", summary="stub")

    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        self.cancel_calls += 1
        return CancelResult(
            confirmed=self.cancel_confirmed,
            state="cancelled" if self.cancel_confirmed else "unconfirmed",
            reason="stub cancel",
        )


def _parse_sse_block(raw: str) -> dict[str, str] | None:
    event: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        event[field] = value[1:] if value.startswith(" ") else value
    return event or None


class AsgiEventStream:
    """Drive one SSE request against an ASGI app inside the running loop."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self._messages: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        self._buffer = ""
        self._disconnect = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.status: int | None = None
        self.headers: dict[str, str] = {}

    async def start(self, path: str, *, query: str = "", headers: dict[str, str] | None = None) -> None:
        started = asyncio.Event()
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [
                (key.lower().encode(), value.encode())
                for key, value in (headers or {}).items()
            ],
            "client": ("127.0.0.1", 51234),
            "server": ("testserver", 80),
        }

        async def receive() -> dict[str, Any]:
            await self._disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                self.status = int(message["status"])
                self.headers = {
                    key.decode(): value.decode()
                    for key, value in message.get("headers", [])
                }
                started.set()
                return
            if message["type"] != "http.response.body":
                return
            body = message.get("body", b"")
            if body:
                self._buffer += body.decode("utf-8", "replace")
                while "\n\n" in self._buffer:
                    raw, self._buffer = self._buffer.split("\n\n", 1)
                    event = _parse_sse_block(raw)
                    if event is not None:
                        await self._messages.put(event)
            if not message.get("more_body", False):
                await self._messages.put(None)

        self._task = asyncio.create_task(self._app(scope, receive, send))
        await asyncio.wait_for(started.wait(), timeout=5)

    async def events(self, count: int, *, timeout: float = 5.0) -> list[dict[str, str]]:
        collected: list[dict[str, str]] = []
        for _ in range(count):
            item = await asyncio.wait_for(self._messages.get(), timeout=timeout)
            if item is None:
                break
            collected.append(item)
        return collected

    async def close(self) -> None:
        self._disconnect.set()
        task = self._task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
                task.cancel()


__all__ = [
    "AsgiEventStream",
    "FakeExecutor",
    "StubDispatcher",
    "create_task",
    "make_stub_app",
    "settle_task",
    "wait_for_phase",
]


async def create_task(client: httpx.AsyncClient, **overrides: object) -> str:
    payload: dict[str, object] = {
        "request_id": f"req-{asyncio.get_running_loop().time():.9f}",
        "title": "Test task",
        "objective": "do the thing",
        "acceptance_criteria": ["it works"],
    }
    payload.update(overrides)
    response = await client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 200, response.text
    return str(response.json()["task_id"])


async def wait_for_phase(
    client: httpx.AsyncClient, task_id: str, phases: set[str], *, timeout: float = 5.0
) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    detail: dict[str, object] = {}
    while loop.time() < deadline:
        response = await client.get(f"/api/v1/tasks/{task_id}")
        detail = response.json()
        if detail.get("phase") in phases:
            return detail
        await asyncio.sleep(0.01)
    raise AssertionError(f"task {task_id} did not reach {phases}; last={detail}")


async def settle_task(
    client: httpx.AsyncClient, task_id: str, *, timeout: float = 5.0
) -> dict[str, object]:
    """Wait until the worker has released the Task lease (revision is stable)."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    detail: dict[str, object] = {}
    while loop.time() < deadline:
        detail = (await client.get(f"/api/v1/tasks/{task_id}")).json()
        queue = detail.get("queue") or {}
        if (
            detail.get("phase") in _TERMINAL_PHASES
            and queue.get("state") == "not_queued"
            and queue.get("owner") is None
        ):
            return detail
        await asyncio.sleep(0.01)
    raise AssertionError(f"task {task_id} did not settle; last={detail}")


def make_stub_app(settings: Settings, **dispatcher_kwargs: object) -> FastAPI:
    dispatcher = StubDispatcher(**dispatcher_kwargs)  # type: ignore[arg-type]
    return create_app(
        settings,
        dispatcher=dispatcher,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
