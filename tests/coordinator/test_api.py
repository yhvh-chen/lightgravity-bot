"""Coordinator router factory (LG-007).

The router is mounted here on a throwaway app; LG-012 mounts the same factory
under ``/api/v1``.  ``lightgravity/api/app.py`` is intentionally not modified.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.coordinator import build_router
from lightgravity.store import FileStore

from coordinator_helpers import make_coordinator


@pytest.fixture
async def api(store: FileStore) -> AsyncIterator[tuple[httpx.AsyncClient, object]]:
    coordinator = make_coordinator(store)
    app = FastAPI()
    app.include_router(build_router(coordinator), prefix="/api/v1")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, coordinator


async def test_create_task_endpoint_is_idempotent(api) -> None:
    client, _ = api
    payload = {"request_id": "req-1", "title": "T", "objective": "do"}
    first = await client.post("/api/v1/tasks", json=payload)
    second = await client.post("/api/v1/tasks", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["task_id"] == second.json()["task_id"]


async def test_append_and_read_messages(api) -> None:
    client, _ = api
    created = await client.post(
        "/api/v1/tasks", json={"request_id": "req-2", "title": "T", "objective": "do"}
    )
    task_id = created.json()["task_id"]
    append = await client.post(
        f"/api/v1/tasks/{task_id}/messages",
        json={"message_id": "msg-1", "content": "补充", "role": "user"},
    )
    assert append.status_code == 200
    listed = await client.get(f"/api/v1/tasks/{task_id}/messages")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["message_id"] == "msg-1"
    assert body["next_cursor"]


async def test_invalid_message_is_rejected(api) -> None:
    client, _ = api
    created = await client.post(
        "/api/v1/tasks", json={"request_id": "req-3", "title": "T", "objective": "do"}
    )
    task_id = created.json()["task_id"]
    response = await client.post(
        f"/api/v1/tasks/{task_id}/messages",
        json={"content": "no message id"},
    )
    assert response.status_code == 422
