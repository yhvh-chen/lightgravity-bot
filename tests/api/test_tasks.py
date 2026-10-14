"""Frozen Task read/patch/event/action endpoints (LG-012)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.config import Settings

from api_helpers import create_task, make_stub_app, settle_task, wait_for_phase


async def test_task_list_detail_and_pagination(api: httpx.AsyncClient) -> None:
    first = await create_task(api, title="Alpha")
    await settle_task(api, first)
    await create_task(api, title="Bravo")
    await create_task(api, title="Charlie")

    listed = await api.get("/api/v1/tasks", params={"limit": 2})
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    assert body["items"][0]["id"] < body["items"][1]["id"]

    second = await api.get("/api/v1/tasks", params={"limit": 2, "cursor": body["next_cursor"]})
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1

    detail = await api.get(f"/api/v1/tasks/{first}")
    assert detail.status_code == 200
    assert detail.headers["etag"] == f'"{detail.json()["revision"]}"'
    payload = detail.json()
    assert payload["task_id"] == first
    assert payload["queue"]["state"] in {"not_queued", "queued", "claimed"}
    assert payload["acceptance"]["status"] == "pending"
    assert "run" in payload
    assert "members" in payload


async def test_task_detail_embeds_active_run(
    run_api: httpx.AsyncClient, fake_executor: object
) -> None:
    import asyncio

    executor = fake_executor
    executor.gate = asyncio.Event()  # type: ignore[attr-defined]
    task_id = await create_task(run_api)
    await wait_for_phase(run_api, task_id, {"executing"})
    payload = (await run_api.get(f"/api/v1/tasks/{task_id}")).json()
    assert payload["run"] is not None
    assert payload["run"]["state"] == "executing"
    assert payload["members"] == []
    assert payload["subtasks"] == []
    executor.gate.set()  # type: ignore[attr-defined]


async def test_task_list_filters_invalid_values(api: httpx.AsyncClient) -> None:
    await create_task(api)
    ok = await api.get("/api/v1/tasks", params={"phase": "queued"})
    assert ok.status_code == 200
    bad = await api.get("/api/v1/tasks", params={"phase": "not-a-phase"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_request"


async def test_task_patch_title_conflict_and_validation(api: httpx.AsyncClient) -> None:
    task_id = await create_task(api)
    await settle_task(api, task_id)
    detail = (await api.get(f"/api/v1/tasks/{task_id}")).json()
    revision = detail["revision"]

    patched = await api.patch(
        f"/api/v1/tasks/{task_id}",
        json={"expected_revision": revision, "title": "Renamed"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Renamed"
    assert patched.json()["revision"] == revision + 1

    conflict = await api.patch(
        f"/api/v1/tasks/{task_id}",
        json={"expected_revision": revision, "title": "Stale"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "revision_conflict"
    assert conflict.json()["error"]["details"]["actual_revision"] == revision + 1
    assert conflict.headers["etag"] == f'"{revision + 1}"'

    invalid = await api.patch(f"/api/v1/tasks/{task_id}", json={"title": "No revision"})
    assert invalid.status_code == 422


async def test_task_patch_requirements_bumps_revision(api: httpx.AsyncClient) -> None:
    task_id = await create_task(api)
    await settle_task(api, task_id)
    detail = (await api.get(f"/api/v1/tasks/{task_id}")).json()
    patched = await api.patch(
        f"/api/v1/tasks/{task_id}",
        json={
            "expected_revision": detail["revision"],
            "acceptance_criteria": ["new criterion"],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["requirements_revision"] == 2
    assert patched.json()["acceptance"]["status"] == "pending"
    assert "new criterion" in patched.json()["body"]


async def test_task_events_read_and_cursor(api: httpx.AsyncClient) -> None:
    task_id = await create_task(api)
    events = await api.get(f"/api/v1/tasks/{task_id}/events")
    assert events.status_code == 200
    types = [item["type"] for item in events.json()["items"]]
    assert "task.created" in types

    after = await api.get(f"/api/v1/tasks/{task_id}/events", params={"after_seq": 1})
    assert after.status_code == 200
    assert all(item["seq"] > 1 for item in after.json()["items"])

    mismatch = await api.get(
        f"/api/v1/tasks/{task_id}/events", params={"cursor": "v1:task_OTHER:3"}
    )
    assert mismatch.status_code == 400

    invalid = await api.get(f"/api/v1/tasks/{task_id}/events", params={"cursor": "bogus"})
    assert invalid.status_code == 422


async def test_unknown_task_is_not_found(api: httpx.AsyncClient) -> None:
    from lightgravity.store import new_id

    response = await api.get(f"/api/v1/tasks/{new_id('task')}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_coordinator_message_routes_are_mounted(api: httpx.AsyncClient) -> None:
    task_id = await create_task(api)
    appended = await api.post(
        f"/api/v1/tasks/{task_id}/messages",
        json={"message_id": "msg-lg012-1", "content": "补充", "role": "user"},
    )
    assert appended.status_code == 200, appended.text
    listed = await api.get(f"/api/v1/tasks/{task_id}/messages")
    assert listed.status_code == 200
    body = listed.json()
    assert [item["message_id"] for item in body["items"]] == ["msg-lg012-1"]
    assert body["next_cursor"]


async def test_action_cancel_confirmed(settings: Settings) -> None:
    app = make_stub_app(settings, cancel_confirmed=True)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            task_id = await create_task(client)
            dispatcher = app.state.coordinator.dispatcher
            await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
            await wait_for_phase(client, task_id, {"executing"})
            response = await client.post(
                f"/api/v1/tasks/{task_id}/actions",
                json={"action": "cancel", "request_id": "req-cancel-1"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["confirmed"] is True
            assert response.json()["state"] == "confirmed"
            detail = (await client.get(f"/api/v1/tasks/{task_id}")).json()
            assert detail["phase"] == "cancelled"


async def test_action_cancel_unconfirmed(settings: Settings) -> None:
    app = make_stub_app(settings, cancel_confirmed=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            task_id = await create_task(client)
            dispatcher = app.state.coordinator.dispatcher
            await asyncio.wait_for(dispatcher.started.wait(), timeout=5)
            await wait_for_phase(client, task_id, {"executing"})
            response = await client.post(
                f"/api/v1/tasks/{task_id}/actions",
                json={"action": "cancel", "request_id": "req-cancel-2"},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "cancellation_unconfirmed"
            detail = (await client.get(f"/api/v1/tasks/{task_id}")).json()
            assert detail["phase"] == "cancelling"


async def test_action_not_ready_and_unknown(api: httpx.AsyncClient) -> None:
    task_id = await create_task(api)
    accept = await api.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={"action": "accept", "request_id": "req-accept"},
    )
    assert accept.status_code == 409
    assert accept.json()["error"]["code"] == "not_ready"
    assert accept.json()["error"]["details"]["owner"] == "LG-009"

    unknown = await api.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={"action": "explode", "request_id": "req-x"},
    )
    assert unknown.status_code == 400


async def test_action_expected_revision_conflict(api: httpx.AsyncClient) -> None:
    task_id = await create_task(api)
    await settle_task(api, task_id)
    detail = (await api.get(f"/api/v1/tasks/{task_id}")).json()
    response = await api.post(
        f"/api/v1/tasks/{task_id}/actions",
        json={
            "action": "cancel",
            "request_id": "req-conflict",
            "expected_revision": detail["revision"] - 1,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "revision_conflict"
