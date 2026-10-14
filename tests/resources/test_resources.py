"""LG-015 Resource catalogue, diagnostics, controlled writes and Team reads.

These tests use the real ``create_app`` wiring and a ``tmp_path`` data root; the
access policy allows sensitive writes without a token so the controlled write
path can be exercised, and a second app with the default-deny policy proves the
path is protected.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.store import new_id

from conftest import create_resource


def _deepseek_connection() -> dict:
    return {
        "title": "DeepSeek",
        "enabled": True,
        "backend": "openai-compat",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com/v1",
        "credential_ref": "deepseek-key",
    }


async def test_catalog_separates_declared_parsed_and_runtime(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "connection", "deepseek", _deepseek_connection())
    create_resource(app, "skill", "implementation", {"title": "Implementation"}, body="# Steps")
    create_resource(
        app, "tool", "view-file", {"title": "View file", "implementation": "view-file"}
    )
    create_resource(
        app,
        "agent",
        "developer",
        {
            "title": "Developer",
            "enabled": True,
            "connection_ref": "deepseek",
            "skills": {"source": "paths", "refs": ["implementation"]},
            "tool_refs": ["view-file"],
        },
        body="Implement the change.",
    )
    create_resource(
        app,
        "tool",
        "unknown-tool",
        {"title": "Unknown tool", "implementation": "not-registered"},
    )
    create_resource(app, "trigger", "nightly", {"title": "Nightly", "type": "schedule"})
    create_resource(
        app,
        "hook",
        "task-policy",
        {"title": "Task policy", "enabled": False, "handler": "not-registered"},
    )

    agents = await api.get("/api/v1/resources/agent")
    assert agents.status_code == 200
    developer = agents.json()["items"][0]
    assert developer["id"] == "developer"
    assert developer["availability"]["state"] == "unknown"
    assert developer["revision"] == 0
    assert developer["etag"] == '"0"'

    detail = await api.get("/api/v1/resources/agent/developer")
    assert detail.status_code == 200
    payload = detail.json()
    assert detail.headers["etag"] == '"0"'
    assert payload["declared"]["enabled"] is True
    assert payload["parsed"]["valid"] is True
    assert payload["availability"]["state"] == "unknown"
    resolved = {(ref["kind"], ref["ref"]): ref["state"] for ref in payload["references"]}
    assert resolved[("connection", "deepseek")] == "resolved"
    assert resolved[("skill", "implementation")] == "resolved"
    assert resolved[("tool", "view-file")] == "resolved"

    # An unregistered implementation is "unsupported", never a fake success.
    unknown = await api.get("/api/v1/resources/tool/unknown-tool")
    assert unknown.json()["availability"]["state"] == "unsupported"

    # MCP/Triggers are described but not started in this version.
    trigger = await api.get("/api/v1/resources/trigger/nightly")
    assert trigger.json()["availability"]["state"] == "unsupported"

    # A declared disabled resource reports "disabled" before anything else.
    hook = await api.get("/api/v1/resources/hook/task-policy")
    assert hook.json()["availability"]["state"] == "disabled"


async def test_agent_availability_missing_dependency(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "connection", "deepseek", _deepseek_connection())
    create_resource(
        app,
        "agent",
        "broken",
        {
            "title": "Broken",
            "enabled": True,
            "connection_ref": "deepseek",
            "tool_refs": ["ghost"],
        },
    )
    available = await api.get("/api/v1/team/available")
    assert available.status_code == 200
    broken = next(item for item in available.json()["items"] if item["id"] == "broken")
    assert broken["availability"]["state"] == "missing_dependency"
    assert broken["executable"] is False

    detail = await api.get("/api/v1/resources/agent/broken")
    assert detail.status_code == 200
    missing = [ref for ref in detail.json()["references"] if ref["state"] == "missing"]
    assert missing and missing[0]["ref"] == "ghost"


async def test_inbound_references_link_templates(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "connection", "deepseek", _deepseek_connection())
    create_resource(app, "skill", "implementation", {"title": "Implementation"})
    create_resource(
        app,
        "agent",
        "developer",
        {
            "title": "Developer",
            "enabled": True,
            "connection_ref": "deepseek",
            "skills": {"source": "paths", "refs": ["implementation"]},
        },
    )
    connection = await api.get("/api/v1/resources/connection/deepseek")
    inbound = connection.json()["inbound_refs"]
    assert {"from_kind": "agent", "from_id": "developer", "field": "connection_ref"} in inbound

    skill = await api.get("/api/v1/resources/skill/implementation")
    assert any(ref["from_id"] == "developer" for ref in skill.json()["inbound_refs"])


async def test_controlled_update_is_validated_and_versioned(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(
        app, "conversation", "task-worker", {"title": "Task worker", "enabled": True}
    )
    updated = await api.patch(
        "/api/v1/resources/conversation/task-worker",
        json={
            "expected_revision": 0,
            "patch": {"title": "Worker profile", "enabled": False},
            "body": "# Session configuration\n\n- continuation: resume",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["title"] == "Worker profile"
    assert payload["revision"] == 1
    assert payload["etag"] == '"1"'
    assert "continuation: resume" in payload["body"]

    # A field outside the allow-list is rejected, not silently stored.
    rejected = await api.patch(
        "/api/v1/resources/conversation/task-worker",
        json={"expected_revision": 1, "patch": {"backend": "openai-compat"}},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "invalid_request"

    # A stale revision must conflict, never last-write-wins.
    stale = await api.patch(
        "/api/v1/resources/conversation/task-worker",
        json={"expected_revision": 0, "patch": {"title": "Stale"}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"

    # An empty change is not a write.
    empty = await api.patch(
        "/api/v1/resources/conversation/task-worker",
        json={"expected_revision": 1, "patch": {}},
    )
    assert empty.status_code == 400


async def test_controlled_update_validates_references(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "connection", "deepseek", _deepseek_connection())
    create_resource(
        app,
        "agent",
        "developer",
        {"title": "Developer", "enabled": True, "connection_ref": "deepseek"},
    )
    broken = await api.patch(
        "/api/v1/resources/agent/developer",
        json={"expected_revision": 0, "patch": {"tool_refs": ["ghost"]}},
    )
    assert broken.status_code == 422
    assert broken.json()["error"]["code"] == "reference_invalid"
    # The rejected proposal did not change the stored revision.
    current = await api.get("/api/v1/resources/agent/developer")
    assert current.json()["revision"] == 0


async def test_connections_are_sent_to_settings(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "connection", "deepseek", _deepseek_connection())
    blocked = await api.patch(
        "/api/v1/resources/connection/deepseek",
        json={"expected_revision": 0, "patch": {"title": "Elsewhere"}},
    )
    assert blocked.status_code == 400
    assert blocked.json()["error"]["details"]["use"] == "/api/v1/settings/connections/deepseek"


async def test_controlled_update_requires_the_runtime_token(settings) -> None:
    from lightgravity.config import Settings

    assert isinstance(settings, Settings)
    app = create_app(settings, access_policy=LocalAccessPolicy())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as api:
            create_resource(
                app, "conversation", "task-worker", {"title": "Task worker"}
            )
            # Reads stay available on loopback; the write default-denies.
            assert (await api.get("/api/v1/resources/conversation")).status_code == 200
            denied = await api.patch(
                "/api/v1/resources/conversation/task-worker",
                json={"expected_revision": 0, "patch": {"title": "Nope"}},
            )
            assert denied.status_code == 401
            assert denied.json()["error"]["code"] == "unauthorized"


async def test_team_members_split_current_and_released(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = new_id("task")
    run_id = new_id("run")
    app.state.store.create(
        "task",
        task_id,
        {
            "title": "Task",
            "status": "in-progress",
            "phase": "executing",
            "queue": {"state": "not_queued"},
            "acceptance": {"status": "pending"},
        },
        actor="test",
        request_id="req-task",
    )
    app.state.store.create(
        "run",
        run_id,
        {"task_ref": task_id, "attempt": 1, "state": "executing"},
        actor="test",
        request_id="req-run",
    )
    current_id = new_id("member")
    released_id = new_id("member")
    app.state.store.create(
        "member",
        current_id,
        {
            "run_ref": run_id,
            "role_ref": "developer",
            "state": "running",
            "template_version": "1",
            "skill_refs": ["implementation"],
            "assigned_subtask_refs": [],
        },
        actor="test",
        request_id="req-current",
    )
    app.state.store.create(
        "member",
        released_id,
        {
            "run_ref": run_id,
            "role_ref": "reviewer",
            "state": "released",
            "template_version": "1",
        },
        actor="test",
        request_id="req-released",
    )

    current = await api.get("/api/v1/team/members", params={"task_ref": task_id, "include_released": False})
    assert current.status_code == 200
    current_ids = [item["id"] for item in current.json()["items"]]
    assert current_ids == [current_id]

    history = await api.get(
        "/api/v1/team/members", params={"task_ref": task_id, "include_released": True}
    )
    states = {item["id"]: item["released"] for item in history.json()["items"]}
    assert states[current_id] is False
    assert states[released_id] is True

    # Another Task's members are not mixed in.
    other = await api.get("/api/v1/team/members", params={"task_ref": "task_other"})
    assert other.json()["items"] == []


async def test_unknown_kind_is_rejected(api: httpx.AsyncClient) -> None:
    unknown = await api.get("/api/v1/resources/wizard")
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "invalid_request"
