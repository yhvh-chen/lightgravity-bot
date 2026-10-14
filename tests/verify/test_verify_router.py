"""Router tests for the LG-009 verify router factory.

The throwaway app mounts the factory under ``/api/v1`` exactly as LG-012 /
the integration owner would; ``lightgravity/api/app.py`` is not modified.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.store import FileStore
from lightgravity.verify import VerificationService, build_router

from verify_helpers import make_verifying_task, set_requirements_revision


@pytest.fixture
async def api(store: FileStore) -> AsyncIterator[tuple[httpx.AsyncClient, FileStore]]:
    service = VerificationService(store)
    app = FastAPI()
    app.include_router(build_router(service), prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, store


async def test_acceptance_endpoint_exposes_candidate(api) -> None:
    client, store = api
    task_id, run_id, _members, _subtasks = make_verifying_task(store)
    # Verification is triggered by the service/coordinator (not a frozen HTTP
    # endpoint); the router guarantees the read + accept/reject surface.
    VerificationService(store).verify_and_prepare(task_id, request_id="prep")

    response = await client.get(f"/api/v1/tasks/{task_id}/acceptance")
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "awaiting_acceptance"
    assert body["candidate"]["run_id"] == run_id
    assert body["acceptance"]["status"] == "awaiting"


async def test_action_accept_is_idempotent(api) -> None:
    client, store = api
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)
    VerificationService(store).verify_and_prepare(task_id, request_id="prep")

    payload = {"action": "accept", "request_id": "api-accept"}
    first = await client.post(f"/api/v1/tasks/{task_id}/actions", json=payload)
    second = await client.post(f"/api/v1/tasks/{task_id}/actions", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["confirmed"] is True
    assert first.json() == second.json()


async def test_action_rejects_unsupported_action(api) -> None:
    client, store = api
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)

    response = await client.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={"action": "pause", "request_id": "p"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


async def test_action_stale_decision_returns_409(api) -> None:
    client, store = api
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)
    VerificationService(store).verify_and_prepare(task_id, request_id="prep")
    set_requirements_revision(store, task_id, 2)

    response = await client.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={"action": "accept", "request_id": "stale"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "acceptance_stale"
