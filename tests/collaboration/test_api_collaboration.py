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
from lightgravity.collaboration import ExecutionGrantRegistry
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
def registry() -> ExecutionGrantRegistry:
    """A fresh program-side grant registry (stands in for the graph dispatcher)."""

    return ExecutionGrantRegistry()


@pytest.fixture
def app(settings: Settings, registry: ExecutionGrantRegistry) -> Iterator[FastAPI]:
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
        # Program-authenticated worker identity seam (LG-030/LG-031).  This test
        # stands in for the coordinator injection: the authenticated member ref
        # comes from a *header*, never from the request body, so a body-supplied
        # `from_member_ref` cannot authenticate itself.
        worker_identity=lambda request: request.headers.get("X-Test-Worker"),
        # LG-029 F2 program-frozen grant seam: discovery/claim/renew/release
        # derive identity + scope + fence from the minted grant, resolved from
        # the execution-grant header only (never from the request body).
        worker_grant=lambda request: registry.resolve(
            request.headers.get("X-LG-Execution-Grant")
        ),
    )
    application = FastAPI()
    application.state.context = context
    application.state.grant_registry = registry
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


def _mint(
    app: FastAPI,
    *,
    run_id: str,
    subtask_id: str,
    member_ref: str = "w1",
    fence: int = 0,
    authorized_node_refs: set[str] | None = None,
    lease_owner: str | None = None,
    kind: str = "pool",
) -> str:
    """Mint a program-frozen grant, exactly as the graph dispatcher would."""

    registry: ExecutionGrantRegistry = app.state.grant_registry
    token, _grant = registry.mint(
        task_id="task_test",
        run_id=run_id,
        subtask_id=subtask_id,
        member_ref=member_ref,
        fence=fence,
        authorized_node_refs=authorized_node_refs or {subtask_id},
        ttl_seconds=600,
        kind=kind,
        lease_owner=lease_owner,
    )
    return token


def _grant_headers(token: str) -> dict[str, str]:
    return {"X-LG-Execution-Grant": token}


async def test_discoverable_endpoint_returns_projection(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    _, run_id, sub = seeded
    token = _mint(app, run_id=run_id, subtask_id=sub)
    response = await client.get(
        f"/api/v1/runs/{run_id}/discoverable",
        params={"owner": "w1"},
        headers=_grant_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert [item["subtask_ref"] for item in body["items"]] == [sub]


async def test_discoverable_requires_program_grant(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    """No grant -> default-deny; the body/query owner can never authenticate."""

    _, run_id, _sub = seeded
    response = await client.get(
        f"/api/v1/runs/{run_id}/discoverable", params={"owner": "w1"}
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "claim_refused"
    assert body["details"]["reason"] == "unauthenticated"


async def test_discoverable_cross_run_scope_is_refused(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    """A grant for Run A cannot read Run B's projection (scope is program-bound)."""

    store: FileStore = app.state.context.store
    _, run_a, sub_a = seeded
    task_b = create_task(store)
    run_b = create_run(store, task_b)
    sub_b = create_subtask(store, run_b, key="b")
    link_subtasks(store, run_b, [sub_b])
    token = _mint(app, run_id=run_a, subtask_id=sub_a)
    response = await client.get(
        f"/api/v1/runs/{run_b}/discoverable", headers=_grant_headers(token)
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "identity_mismatch"


async def test_discoverable_projection_limited_to_grant_scope(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """A grant sees only the nodes the program authorized, not the whole Run."""

    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub_a = create_subtask(store, run_id, key="a")
    sub_b = create_subtask(store, run_id, key="b")
    link_subtasks(store, run_id, [sub_a, sub_b])
    set_switches(store, enabled=True, lease_seconds=60)
    token = _mint(
        app,
        run_id=run_id,
        subtask_id=sub_a,
        authorized_node_refs={sub_a},
    )
    response = await client.get(
        f"/api/v1/runs/{run_id}/discoverable", headers=_grant_headers(token)
    )
    items = [item["subtask_ref"] for item in response.json()["items"]]
    assert items == [sub_a]


async def test_discoverable_default_off_when_no_switch(app: FastAPI) -> None:
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    # No SETTINGS.md switch -> closed.
    token = _mint(app, run_id=run_id, subtask_id=sub)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.get(
            f"/api/v1/runs/{run_id}/discoverable",
            params={"owner": "w1"},
            headers=_grant_headers(token),
        )
    body = response.json()
    assert body["enabled"] is False
    assert body["items"] == []


async def test_claim_requests_endpoint_grants_once(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    _, run_id, sub = seeded
    token = _mint(app, run_id=run_id, subtask_id=sub)
    headers = _grant_headers(token)
    payload = {"owner": "w1", "request_id": "r1", "subtask_ref": sub}
    first = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests", json=payload, headers=headers
    )
    assert first.status_code == 200
    body = first.json()
    assert body["granted"] is True
    assert first.headers["ETag"] == '"1"'

    replay = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests", json=payload, headers=headers
    )
    assert replay.json()["granted"] is True
    assert replay.json()["idempotent_replay"] is True

    # A different authenticated principal cannot steal the held node.
    other_token = _mint(app, run_id=run_id, subtask_id=sub, member_ref="w2")
    other = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w2", "request_id": "r2", "subtask_ref": sub},
        headers=_grant_headers(other_token),
    )
    assert other.json()["granted"] is False
    # A different owner cannot even discover the node once another holds it, so
    # the refusal is the stricter ``not_discoverable`` rather than a leak of the
    # holder's identity.
    assert other.json()["reason"] == "not_discoverable"


async def test_claim_without_grant_default_denies_and_writes_nothing(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    store: FileStore = app.state.context.store
    _, run_id, sub = seeded
    response = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "unauthenticated"
    # No business state was written: the Subtask is still unowned and pending.
    entity = store.read("subtask", sub).entity
    assert entity["owner"] is None
    assert entity["state"] == "pending"


async def test_claim_body_owner_cannot_impersonate(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    """Authenticated A naming B in the body is refused and persists nothing."""

    store: FileStore = app.state.context.store
    _, run_id, sub = seeded
    token = _mint(app, run_id=run_id, subtask_id=sub, member_ref="member-a")
    response = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "member-b", "request_id": "r1", "subtask_ref": sub},
        headers=_grant_headers(token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "identity_mismatch"
    assert store.read("subtask", sub).entity["owner"] is None


async def test_claim_body_cannot_cross_run_scope(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    store: FileStore = app.state.context.store
    _, run_a, sub_a = seeded
    task_b = create_task(store)
    run_b = create_run(store, task_b)
    sub_b = create_subtask(store, run_b, key="b")
    link_subtasks(store, run_b, [sub_b])
    token = _mint(app, run_id=run_a, subtask_id=sub_a)
    response = await client.post(
        f"/api/v1/runs/{run_b}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub_b},
        headers=_grant_headers(token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "identity_mismatch"
    assert store.read("subtask", sub_b).entity["owner"] is None


async def test_claim_cannot_take_node_outside_grant_scope(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """A grant authorized for node A cannot claim node B in the same Run."""

    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub_a = create_subtask(store, run_id, key="a")
    sub_b = create_subtask(store, run_id, key="b")
    link_subtasks(store, run_id, [sub_a, sub_b])
    set_switches(store, enabled=True, lease_seconds=60)
    token = _mint(app, run_id=run_id, subtask_id=sub_a, authorized_node_refs={sub_a})
    response = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub_b},
        headers=_grant_headers(token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "not_discoverable"
    assert store.read("subtask", sub_b).entity["owner"] is None


async def test_claim_refused_when_feature_disabled(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """An authenticated worker still gets the frozen ``feature_disabled`` when off."""

    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    # No SETTINGS.md switch -> the policy is closed.
    token = _mint(app, run_id=run_id, subtask_id=sub)
    response = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
        headers=_grant_headers(token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "claim_refused"
    assert response.json()["error"]["details"]["reason"] == "feature_disabled"


async def test_claim_refused_is_frozen_error_code(app: FastAPI) -> None:
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            f"/api/v1/runs/{run_id}/claim_requests",
            json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "claim_refused"
    assert response.json()["error"]["details"]["reason"] == "unauthenticated"


async def test_renew_and_release_endpoints(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    _, run_id, sub = seeded
    token = _mint(app, run_id=run_id, subtask_id=sub)
    headers = _grant_headers(token)
    granted = await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
        headers=headers,
    )
    fence = granted.json()["fence"]
    # The grant minted before the claim has fence 0; re-mint it at the claimed
    # fence exactly as the dispatcher does when it upgrades a pool grant.
    token = _mint(app, run_id=run_id, subtask_id=sub, fence=fence, kind="node")
    headers = _grant_headers(token)

    renewed = await client.post(
        f"/api/v1/subtasks/{sub}/lease/renew",
        json={"owner": "w1", "fence": fence, "lease_seconds": 60},
        headers=headers,
    )
    assert renewed.status_code == 200
    assert renewed.json()["renewed"] is True

    stale = await client.post(
        f"/api/v1/subtasks/{sub}/lease/renew",
        json={"owner": "w1", "fence": fence + 9, "lease_seconds": 60},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_lease"

    released = await client.post(
        f"/api/v1/subtasks/{sub}/lease/release",
        json={"owner": "w1", "fence": fence},
        headers=headers,
    )
    assert released.status_code == 200
    assert released.json()["released"] is True


async def test_renew_requires_grant_and_writes_nothing(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    store: FileStore = app.state.context.store
    _, run_id, sub = seeded
    token = _mint(app, run_id=run_id, subtask_id=sub)
    await client.post(
        f"/api/v1/runs/{run_id}/claim_requests",
        json={"owner": "w1", "request_id": "r1", "subtask_ref": sub},
        headers=_grant_headers(token),
    )
    before = store.read("subtask", sub).entity
    # No grant header -> default-deny, no lease change.
    denied = await client.post(
        f"/api/v1/subtasks/{sub}/lease/renew",
        json={"owner": "w1", "lease_seconds": 60},
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["details"]["reason"] == "unauthenticated"
    after = store.read("subtask", sub).entity
    assert after["lease_expires_at"] == before["lease_expires_at"]


async def test_renew_cannot_steal_peer_lease(
    client: httpx.AsyncClient, app: FastAPI, seeded: tuple[str, str, str]
) -> None:
    """A grant scoped to node A cannot renew a peer's node B lease."""

    store: FileStore = app.state.context.store
    _, run_id, sub_a = seeded
    sub_b = create_subtask(store, run_id, key="b", state="pending")
    link_subtasks(store, run_id, [sub_a, sub_b])
    # Peer B holds a lease on node B via the program path.
    from lightgravity.collaboration import ClaimPolicy, ClaimRequest, CollaborationService

    service = CollaborationService(store, policy=ClaimPolicy(enabled=True, lease_seconds=60))
    decision = service.request_claim(
        run_id,
        ClaimRequest(subtask_id=sub_b, owner="peer", request_id="peer-1", lease_seconds=60),
    )
    assert decision.granted is True
    before = store.read("subtask", sub_b).entity
    token = _mint(app, run_id=run_id, subtask_id=sub_a, authorized_node_refs={sub_a})
    response = await client.post(
        f"/api/v1/subtasks/{sub_b}/lease/renew",
        json={"owner": "peer", "lease_seconds": 60},
        headers=_grant_headers(token),
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["reason"] == "not_discoverable"
    after = store.read("subtask", sub_b).entity
    assert after["owner"] == "peer"
    assert after["lease_expires_at"] == before["lease_expires_at"]


# ---------------------------------------------------------------------------
# LG-030 peer collaboration endpoints
def _seed_peer(app: FastAPI, *, collab_enabled: bool = True) -> tuple[str, str, str]:
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_id = create_run(store, task_id, team_refs=["member-a", "member-b"])
    sub = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub])
    set_switches(store, enabled=True, lease_seconds=60, collab_enabled=collab_enabled)
    return task_id, run_id, sub


def _peer_payload(node: str, **overrides):  # type: ignore[no-untyped-def]
    payload = {
        "request_id": "creq-1",
        "from_member_ref": "member-a",
        "to_member_ref": "member-b",
        "node_ref": node,
        "mode": "review",
        "summary": "please review node a",
        "message_id": "msg_01J00000000000000000000AA",
        "correlation_id": "corr_01J00000000000000000000AA",
    }
    payload.update(overrides)
    return payload


async def test_collab_request_endpoint_accepts_and_lists(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    _, run_id, sub = _seed_peer(app)
    headers = {"X-Test-Worker": "member-a"}
    response = await client.post(
        f"/api/v1/runs/{run_id}/collab_requests",
        json=_peer_payload(sub),
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "collab_request"
    assert body["state"] == "requested"
    assert body["reason"] == "accepted"
    assert body["summary"]["instruction_like"] is False

    replay = await client.post(
        f"/api/v1/runs/{run_id}/collab_requests",
        json=_peer_payload(sub),
        headers=headers,
    )
    assert replay.json()["idempotent_replay"] is True

    listed = await client.get(f"/api/v1/runs/{run_id}/collab_requests")
    assert listed.status_code == 200
    listing = listed.json()
    assert listing["enabled"] is True
    assert [item["request_id"] for item in listing["items"]] == ["creq-1"]


async def test_collab_request_without_program_identity_default_denies(app: FastAPI) -> None:
    """A body-supplied member ref is not authentication: no seam identity -> deny."""

    _, run_id, sub = _seed_peer(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            f"/api/v1/runs/{run_id}/collab_requests", json=_peer_payload(sub)
        )
        body = response.json()
        assert body["state"] == "rejected"
        assert body["reason"] == "unauthenticated"
        # Nothing was persisted for the unauthenticated attempt.
        listed = await http.get(f"/api/v1/runs/{run_id}/collab_requests")
        assert listed.json()["items"] == []


async def test_collab_request_identity_mismatch_is_refused(app: FastAPI) -> None:
    """An authenticated worker cannot act as a different run member."""

    _, run_id, sub = _seed_peer(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            f"/api/v1/runs/{run_id}/collab_requests",
            json=_peer_payload(sub),
            headers={"X-Test-Worker": "member-b"},
        )
    body = response.json()
    assert body["state"] == "rejected"
    assert body["reason"] == "identity_mismatch"


async def test_collab_request_disabled_returns_definite_rejection(app: FastAPI) -> None:
    _, run_id, sub = _seed_peer(app, collab_enabled=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            f"/api/v1/runs/{run_id}/collab_requests",
            json=_peer_payload(sub),
            headers={"X-Test-Worker": "member-a"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "rejected"
    assert body["reason"] == "feature_disabled"


async def test_collab_cross_task_node_is_refused_over_http(app: FastAPI) -> None:
    store: FileStore = app.state.context.store
    _, run_a, _ = _seed_peer(app)
    task_b = create_task(store)
    run_b = create_run(store, task_b, team_refs=["member-a", "member-b"])
    sub_b = create_subtask(store, run_b, key="b")
    link_subtasks(store, run_b, [sub_b])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.post(
            f"/api/v1/runs/{run_a}/collab_requests",
            json=_peer_payload(sub_b),
            headers={"X-Test-Worker": "member-a"},
        )
    body = response.json()
    assert body["state"] == "rejected"
    assert body["reason"] == "unknown_node"
