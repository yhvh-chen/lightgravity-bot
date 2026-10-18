"""Team role/access matrix and anti-bypass constraints (LG-050 docs/08 §4)."""

from __future__ import annotations

import httpx

from lightgravity.api.app import create_app
from lightgravity.config import Settings

from team_helpers import (
    error_code,
    login_admin,
    login_member,
    seeded_accounts,
    team_app,
    team_client,
    team_settings,
)


async def test_anonymous_business_gets_and_sse_are_401(
    team_client: httpx.AsyncClient,
) -> None:
    assert (await team_client.get("/api/v1/files")).status_code == 401
    assert (await team_client.get("/api/v1/sources")).status_code == 401
    stream = await team_client.get("/api/v1/events/stream")
    assert stream.status_code == 401
    assert error_code(stream) == "unauthorized"


async def test_health_and_version_are_public(team_client: httpx.AsyncClient) -> None:
    assert (await team_client.get("/api/v1/health")).status_code == 200
    assert (await team_client.get("/api/v1/version")).status_code == 200


async def test_member_can_read_and_write_business_endpoints(
    team_client: httpx.AsyncClient,
) -> None:
    assert (await login_member(team_client)).status_code == 200
    assert (await team_client.get("/api/v1/team/available")).status_code == 200
    recorded = await team_client.post(
        "/api/v1/conversations/global/messages",
        json={"message_id": "msg_member_business", "content": "hello team"},
    )
    assert recorded.status_code == 200
    assert recorded.json()["kind"] == "recorded"


async def test_member_cannot_read_or_write_settings(
    team_client: httpx.AsyncClient,
) -> None:
    assert (await login_member(team_client)).status_code == 200
    read = await team_client.get("/api/v1/settings")
    assert read.status_code == 403
    assert error_code(read) == "forbidden"
    write = await team_client.patch("/api/v1/settings", json={})
    assert write.status_code == 403
    assert error_code(write) == "forbidden"


async def test_admin_can_read_settings(team_client: httpx.AsyncClient) -> None:
    assert (await login_admin(team_client)).status_code == 200
    assert (await team_client.get("/api/v1/settings")).status_code == 200


async def test_member_cannot_patch_resources(team_client: httpx.AsyncClient) -> None:
    assert (await login_member(team_client)).status_code == 200
    response = await team_client.patch(
        "/api/v1/resources/agent/example",
        json={"expected_revision": 0, "patch": {}},
    )
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


async def test_member_can_upload_files_but_not_settings(
    team_client: httpx.AsyncClient, team_settings: Settings
) -> None:
    team_settings.workspace_root.mkdir(parents=True, exist_ok=True)
    assert (await login_member(team_client)).status_code == 200
    upload = await team_client.post(
        "/api/v1/files/upload",
        params={"path": "note.txt", "expected_revision": None},
        content=b"hello",
    )
    assert upload.status_code in (200, 201), upload.text
    assert (await team_client.get("/api/v1/settings")).status_code == 403


async def test_token_header_never_grants_team_access(
    team_client: httpx.AsyncClient,
) -> None:
    # Anonymous + arbitrary token is still anonymous.
    anonymous = await team_client.get(
        "/api/v1/files", headers={"X-LG-Token": "let-me-in"}
    )
    assert anonymous.status_code == 401
    # Member + token stays a member (no admin elevation).
    assert (await login_member(team_client)).status_code == 200
    elevated = await team_client.get(
        "/api/v1/settings", headers={"X-LG-Token": "let-me-in"}
    )
    assert elevated.status_code == 403
    assert error_code(elevated) == "forbidden"
    # And the token cannot impersonate a user on an otherwise anonymous endpoint.
    me = await team_client.get(
        "/api/v1/auth/me", headers={"X-LG-Token": "let-me-in"}
    )
    assert me.json()["username"] == "alice"


async def test_client_supplied_author_is_rejected(
    team_client: httpx.AsyncClient,
) -> None:
    assert (await login_member(team_client)).status_code == 200
    response = await team_client.post(
        "/api/v1/conversations/global/messages",
        json={
            "message_id": "msg_forged_author",
            "content": "hi",
            "author": {"kind": "user", "username": "admin", "role": "admin"},
        },
    )
    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


async def test_member_cannot_use_task_resource_proposal(
    team_client: httpx.AsyncClient,
) -> None:
    assert (await login_member(team_client)).status_code == 200
    response = await team_client.post(
        "/api/v1/tasks/task_whatever/messages",
        json={
            "message_id": "msg_proposal_bypass",
            "content": "update the agent",
            "resource_proposal": {
                "kind": "agent",
                "id": "example",
                "expected_revision": 0,
                "patch": {},
            },
        },
    )
    # Refused by the admin-only control-change gate before any resource write.
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


async def test_files_cannot_read_team_accounts_even_inside_workspace(
    team_settings: Settings,
    seeded_accounts: object,
) -> None:
    import dataclasses

    # Worst case: the workspace root is configured to contain the team dir.
    misconfigured = dataclasses.replace(
        team_settings, workspace_root=team_settings.data_dir
    )
    app = create_app(misconfigured)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            assert (await login_member(client)).status_code == 200
            response = await client.get(
                "/api/v1/files/content", params={"path": "team/accounts.json"}
            )
            assert response.status_code == 403
            assert error_code(response) == "path_outside_workspace"


async def test_vector_rebuild_is_admin_only(
    team_client: httpx.AsyncClient,
) -> None:
    """LG-144: a full rebuild is the one protected global vector operation."""

    assert (await login_member(team_client)).status_code == 200
    denied = await team_client.post("/api/v1/vector/rebuild", json={})
    assert denied.status_code == 403, denied.text
    assert error_code(denied) == "forbidden"

    # A fresh client keeps the member cookie from leaking into the admin login.
    await team_client.post("/api/v1/auth/logout")
    assert (await login_admin(team_client)).status_code == 200
    allowed = await team_client.post("/api/v1/vector/rebuild", json={})
    assert allowed.status_code == 200, allowed.text
    # The test app has no configured embedding backend, so the rebuild is an
    # honest no-op; the authorization boundary is what this test proves.
    assert isinstance(allowed.json()["rebuilt"], bool)
