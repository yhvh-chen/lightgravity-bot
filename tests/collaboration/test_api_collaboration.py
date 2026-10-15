"""API-level checks for the LG-029 collaboration endpoints (docs/08 §4.3).

The router is exercised through a real FastAPI app with a real ``FileStore`` and
a real ``ApiContext``.  The router is *not yet mounted* in ``api/app.py`` (that
is the integration owner's serial wiring, see ``probes/lg029/INTEGRATION.md``),
so this test mounts it exactly the way integration will.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.collaboration import build_collaboration_router
from lightgravity.api.context import ApiContext
from lightgravity.api.eventbus import EventBroker
from lightgravity.config import Settings
from lightgravity.contracts import AppError
from lightgravity.coordinator import Coordinator
from lightgravity.coordinator.dispatcher import SingleSlotDispatcher, UnavailableExecutor
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore

from collab_helpers import create_run, create_subtask, create_task, link_subtasks, set_switches


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    settings.ensure_data_dir()
    store = FileStore(settings.data_dir, settings.workspace_root)
    secret_store = FileSecretStore(settings.secret_store)
    connections = ConnectionService(store, secret_store=secret_store)
    coordinator = Coordinator(store, dispatcher=SingleSlotDispatcher(UnavailableExecutor()))
    context = ApiContext(
        settings=settings,
        store=store,
        coordinator=coordinator,
        connections=connections,
        secret_store=secret_store,
        broker=EventBroker(),
        access=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    application = FastAPI()
    application.state.context = context
    # Mirror the frozen AppError handler from api/app.py so the API test asserts
    # the real error envelope rather than a bare traceback.  Integration mounts
    # this router into create_app, which already registers the handler.
    @application.exception_handler(AppError)
    async def _handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope(request_id=None).model_dump(mode="json"),
        )

    application.include_router(build_collaboration_router(), prefix="/api/v1")
    yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest.fixture
def seeded(app: FastAPI) -> tuple[str, str, str]:
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    set_switches(store, enabled=True, lease_seconds=60)
    return task_id, run_id, sub


async def test_discoverable_endpoint_returns_projection(
    client: httpx.AsyncClient, seeded: tuple[str, str, str]
) -> None:
    _, run_id, sub = seeded
    response = await client.get(f"/api/v1/runs/{run_id}/discoverable", params={"owner": "w1"})
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert [item["subtask_ref"] for item in body["items"]] == [sub]


async def test_discoverable_default_off_when_no_switch(app: FastAPI) -> None:
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    # No SETTINGS.md switch -> closed.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.get(f"/api/v1/runs/{run_id}/discoverable", params={"owner": "w1"})
    body = response.json()
    assert body["enabled"] is False
    assert body["items"] == []


async def test_claim_requests_endpoint_grants_once(
    client: httpx.AsyncClient, seeded: tuple[str, str, str]
) -> None:
    _, run_id, sub = seeded
    payload = {"owner": "w1", "request_id": "r1", "subtask_ref": sub}
    first = await client.post(f"/api/v1/runs/{run_id}/claim_requests", json=payload)
    assert first.status_code == 200
    body = first.json()
    assert body["granted"] is True
    assert first.headers["ETag"] == '"1"'

    replay = await client.post(f"/api/v1/runs/{run_id}/claim_requests", json=payload)
    assert replay.json()["granted"] is True
    assert replay.json()["idempotent_replay"] is True

    other = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w2", "request_id": "r2", "subtask_ref": sub},
    )
    assert other.json()["granted"] is False
    # A different owner cannot even discover the node once another holds it, so
    # the refusal is the stricter ``not_discoverable`` rather than a leak of the
    # holder's identity.
    assert other.json()["reason"] == "not_discoverable"


async def test_claim_refused_is_frozen_error_code(app: FastAPI) -> None:
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    # Delegated feature is off.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            f"/api/v1/runs/{run_id}/claim_requests",
            json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "claim_refused"
    assert response.json()["error"]["details"]["reason"] == "feature_disabled"


async def test_renew_and_release_endpoints(
    client: httpx.AsyncClient, seeded: tuple[str, str, str]
) -> None:
    _, run_id, sub = seeded
    granted = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
    )
    fence = granted.json()["fence"]

    renewed = await client.post(
        f"/api/v1/subtasks/{sub}/lease/renew",
        json={"owner": "w1", "fence": fence, "lease_seconds": 60},
    )
    assert renewed.status_code == 200
    assert renewed.json()["renewed"] is True

    stale = await client.post(
        f"/api/v1/subtasks/{sub}/lease/renew",
        json={"owner": "w1", "fence": fence + 9, "lease_seconds": 60},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_lease"

    released = await client.post(
        f"/api/v1/subtasks/{sub}/lease/release",
        json={"owner": "w1", "fence": fence},
    )
    assert released.status_code == 200
    assert released.json()["released"] is True
