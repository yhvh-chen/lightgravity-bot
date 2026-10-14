"""LG-015 controlled resource-change proposals through the Task conversation.

These tests exercise the real ``create_app`` + Coordinator wiring: a structured
``resource_proposal`` attached to a Task message is program-validated and applied
through ``ResourceService.update``; the *actual* result (applied/conflict/
rejected) is recorded back into the conversation.  No code Run is created and a
non-user message cannot write control state.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.store import new_id

from conftest import create_resource


def _create_task(app: FastAPI, task_id: str | None = None, **overrides) -> str:
    task_id = task_id or new_id("task")
    content = {
        "title": "Resource task",
        "status": "todo",
        "phase": "intake",
        "requirements_revision": 1,
        "deliverable_revision": 0,
        "active_run": None,
        "agent_ref": "coordinator",
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
    app.state.store.create(
        "task", task_id, content, actor="test", request_id=f"req-{task_id}"
    )
    return task_id


async def _post_proposal(
    api: httpx.AsyncClient,
    task_id: str,
    proposal: dict,
    *,
    message_id: str = "msg_proposal_1",
    role: str = "user",
    content: str = "please change this resource template",
) -> httpx.Response:
    return await api.post(
        f"/api/v1/tasks/{task_id}/messages",
        json={
            "message_id": message_id,
            "content": content,
            "role": role,
            "resource_proposal": proposal,
        },
    )


def _agent_proposal(**overrides) -> dict:
    proposal = {
        "kind": "agent",
        "id": "developer",
        "expected_revision": 0,
        "patch": {"title": "Developer v2"},
    }
    proposal.update(overrides)
    return proposal


async def test_proposal_applies_through_service_and_records_result(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = _create_task(app)

    response = await _post_proposal(api, task_id, _agent_proposal())
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "resource_change"
    assert payload["data"]["status"] == "applied"
    assert payload["data"]["revision"] == 1
    assert payload["data"]["recorded_in_conversation"] is True

    # The authoritative Markdown file changed exactly once.
    stored = app.state.store.read("agent", "developer")
    assert stored.entity["title"] == "Developer v2"
    assert stored.revision == 1

    # No Run was created and the Task scope is preserved.
    assert app.state.store.read("task", task_id).entity.get("active_run") is None

    # The actual result is recorded in the same Task conversation.
    messages = await api.get(f"/api/v1/tasks/{task_id}/messages")
    recorded = [item["message"] for item in messages.json()["items"]]
    assert any(msg["role"] == "user" and "resource_proposal" in msg for msg in recorded)
    replies = [msg for msg in recorded if msg["role"] == "assistant"]
    assert replies and "revision -> 1" in replies[-1]["content"]
    assert replies[-1]["resource_result"]["status"] == "applied"


async def test_proposal_is_idempotent_on_message_id(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = _create_task(app)

    first = await _post_proposal(api, task_id, _agent_proposal(), message_id="msg_once")
    second = await _post_proposal(api, task_id, _agent_proposal(), message_id="msg_once")
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]

    stored = app.state.store.read("agent", "developer")
    assert stored.revision == 1  # the second identical message did not re-apply

    messages = await api.get(f"/api/v1/tasks/{task_id}/messages")
    replies = [item for item in messages.json()["items"] if item["message"]["role"] == "assistant"]
    assert len(replies) == 1


async def test_proposal_reports_revision_conflict_without_overwrite(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = _create_task(app)

    response = await _post_proposal(
        api, task_id, _agent_proposal(expected_revision=99)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "conflict"
    assert data["error_code"] == "revision_conflict"
    assert data["actual_revision"] == 0
    assert app.state.store.read("agent", "developer").revision == 0

    messages = await api.get(f"/api/v1/tasks/{task_id}/messages")
    reply = [m for m in messages.json()["items"] if m["message"]["role"] == "assistant"][-1]
    assert reply["message"]["resource_result"]["status"] == "conflict"


async def test_proposal_rejects_unresolved_references(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = _create_task(app)

    response = await _post_proposal(
        api, task_id, _agent_proposal(patch={"connection_ref": "ghost"})
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "rejected"
    assert response.json()["data"]["error_code"] == "reference_invalid"
    assert app.state.store.read("agent", "developer").revision == 0


async def test_non_user_message_cannot_change_control_resources(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = _create_task(app)

    response = await _post_proposal(
        api, task_id, _agent_proposal(), role="assistant", message_id="msg_model"
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "unauthorized_source"
    assert app.state.store.read("agent", "developer").revision == 0


async def test_connection_proposal_is_sent_to_settings(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(
        app,
        "connection",
        "deepseek",
        {
            "title": "DeepSeek",
            "enabled": True,
            "backend": "openai-compat",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com/v1",
            "credential_ref": "deepseek-key",
        },
    )
    task_id = _create_task(app)

    response = await _post_proposal(
        api,
        task_id,
        {
            "kind": "connection",
            "id": "deepseek",
            "expected_revision": 0,
            "patch": {"title": "Elsewhere"},
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "rejected"
    assert app.state.store.read("connection", "deepseek").revision == 0


async def test_malformed_proposal_is_rejected_not_500(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    task_id = _create_task(app)

    response = await _post_proposal(api, task_id, {"kind": "agent", "id": "developer"})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "invalid_proposal"
    assert app.state.store.read("agent", "developer").revision == 0


async def test_active_member_keeps_pinned_config_after_template_change(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    create_resource(app, "agent", "developer", {"title": "Developer", "enabled": True})
    run_id = new_id("run")
    member_id = new_id("member")
    app.state.store.create(
        "member",
        member_id,
        {
            "run_ref": run_id,
            "role_ref": "developer",
            "state": "running",
            "template_version": "1",
            "config_hash": "hash-pinned",
            "skill_refs": [],
            "assigned_subtask_refs": [],
        },
        actor="test",
        request_id="req-member",
    )
    task_id = _create_task(app)

    response = await _post_proposal(api, task_id, _agent_proposal())
    assert response.json()["data"]["status"] == "applied"

    member = app.state.store.read("member", member_id)
    assert member.entity["config_hash"] == "hash-pinned"  # no hot-swap
    assert member.entity["state"] == "running"
    assert member.revision == 0


async def test_proposal_without_task_is_404(api: httpx.AsyncClient) -> None:
    missing = new_id("task")
    response = await _post_proposal(api, missing, _agent_proposal())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_resource_proposal_requires_the_runtime_token(settings) -> None:
    app = create_app(settings, access_policy=LocalAccessPolicy())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as api:
            create_resource(
                app, "agent", "developer", {"title": "Developer", "enabled": True}
            )
            task_id = _create_task(app)
            denied = await _post_proposal(api, task_id, _agent_proposal())
            assert denied.status_code == 401
            assert denied.json()["error"]["code"] == "unauthorized"
            assert app.state.store.read("agent", "developer").revision == 0
