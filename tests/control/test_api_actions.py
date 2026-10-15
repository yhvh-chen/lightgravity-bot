"""LG-016 control actions through the frozen HTTP endpoint.

Exercises the real ``POST /tasks/{id}/actions`` path with a controllable
dispatcher so pause/resume/cancel flow through the API and the
cancellation-confirmation error code is the documented one.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from api_helpers import create_task
from lightgravity.adapter import CancelResult
from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.coordinator.dispatcher import DispatchContext, DispatchOutcome


class ControllableDispatcher:
    name = "controllable"

    def __init__(self, *, cancel_confirmed: bool = True) -> None:
        self.cancel_confirmed = cancel_confirmed
        self.started = asyncio.Event()
        self._blocker = asyncio.Event()

    async def dispatch(
        self, context: DispatchContext, controller: Any, emit: Any
    ) -> DispatchOutcome:
        controller.set_task_phase("recruiting")
        controller.set_run_state("recruiting")
        controller.set_task_phase("executing")
        controller.set_run_state("executing")
        self.started.set()
        await self._blocker.wait()
        return DispatchOutcome(state="succeeded", summary="controllable")

    async def cancel(self, task_id: str, run_id: str) -> CancelResult:
        if self.cancel_confirmed:
            self._blocker.set()
        return CancelResult(
            confirmed=self.cancel_confirmed,
            state="cancelled" if self.cancel_confirmed else "unconfirmed",
            reason="stub cancel",
        )


@asynccontextmanager
async def _client(settings: Settings, dispatcher: ControllableDispatcher):
    application = create_app(
        settings,
        dispatcher=dispatcher,  # type: ignore[arg-type]
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_cancel_unconfirmed_returns_documented_error(settings: Settings) -> None:
    dispatcher = ControllableDispatcher(cancel_confirmed=False)
    async with _client(settings, dispatcher) as client:
        task_id = await create_task(client)
        await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
        response = await client.post(
            f"/api/v1/tasks/{task_id}/actions",
            json={"action": "cancel", "request_id": "req-unc"},
        )
        assert response.status_code == 409
        body = response.json()["error"]
        assert body["code"] == "cancellation_unconfirmed"
        assert body["retryable"] is True
        detail = (await client.get(f"/api/v1/tasks/{task_id}")).json()
        assert detail["phase"] == "cancelling"


async def test_pause_and_resume_via_api(settings: Settings) -> None:
    dispatcher = ControllableDispatcher()
    async with _client(settings, dispatcher) as client:
        task_id = await create_task(client)
        await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
        paused = await client.post(
            f"/api/v1/tasks/{task_id}/actions",
            json={"action": "pause", "request_id": "req-p"},
        )
        assert paused.status_code == 200, paused.text
        assert paused.json()["confirmed"] is True
        assert paused.json()["phase"] == "paused"
        resumed = await client.post(
            f"/api/v1/tasks/{task_id}/actions",
            json={"action": "resume", "request_id": "req-r"},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["confirmed"] is True
