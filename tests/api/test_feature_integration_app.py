"""LG-124 integration checks on the *actual* assembled application.

These tests intentionally do **not** mount any feature router by hand.  They
exercise ``create_app`` exactly as the resident process does, so a missing
shared-file wiring line (``api/app.py``/``api/health.py``) fails here even when
the package-level tests still pass.

Scope: route presence/capability advertisement, settings/embedding mount,
private-attachment mount plus owner permission, and the Personal responder
context seam.  Package-level semantic coverage stays in the feature test files;
no product model/embedding/OCR call is made.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX, CONTRACT_VERSION
from lightgravity.store import new_id
from lightgravity.team import TeamAccounts

PRIVATE = f"{API_PREFIX}/attachments/private"
PERSONAL = f"{API_PREFIX}/conversations/personal/messages"


def _settings(tmp_path: Path, *, team_mode: bool = False) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
        team_mode=team_mode,
    )


def _single_app(settings: Settings, responder=None) -> FastAPI:
    return create_app(
        settings,
        responder=responder,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )


async def _client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


def _upload(
    client: httpx.AsyncClient,
    attachment_id: str,
    data: bytes,
    *,
    filename: str = "notes.txt",
    media_type: str = "text/plain",
) -> httpx.Response:
    return client.post(
        PRIVATE,
        params={
            "attachment_id": attachment_id,
            "filename": filename,
            "media_type": media_type,
        },
        content=data,
    )


async def test_actual_app_advertises_and_serves_mounted_routes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = _single_app(settings)
    # The real governor uses the validated Settings values (2/3/1/2 defaults).
    snapshot = app.state.coordinator.capacity_snapshot()
    assert snapshot["config"] == {
        "max_active_tasks": 2,
        "max_global_sessions": 3,
        "max_reviewer_sessions": 1,
        "max_parallel_nodes_per_task": 2,
    }
    paths = {getattr(route, "path", "") for route in app.routes}
    # The complete LG-119 factory is mounted by api/app.py, not only by tests.
    assert PRIVATE in paths
    assert f"{PRIVATE}/{{attachment_id}}" in paths
    assert f"{PRIVATE}/{{attachment_id}}/content" in paths
    assert f"{PRIVATE}/{{attachment_id}}/download" in paths
    # LG-117 routes live in the already-mounted settings router.
    assert f"{API_PREFIX}/settings" in paths
    assert f"{API_PREFIX}/settings/embedding" in paths
    assert f"{API_PREFIX}/settings/embedding/test-draft" in paths
    # LG-126 projection is mounted by the same real factory.
    assert f"{API_PREFIX}/team/groups" in paths

    async for client in _client(app):
        health = await client.get(f"{API_PREFIX}/health")
        assert health.status_code == 200
        assert health.json()["contract_version"] == CONTRACT_VERSION
        capabilities = health.json()["capabilities"]
        assert capabilities["embedding_settings"] is True
        assert capabilities["private_attachments"] is True
        # LG-126 surfaces are wired by the real factory in this candidate.
        assert capabilities["team_groups"] is True
        assert capabilities["capacity_v2"] is True

        # The projection route is served by the actual app and is read-only.
        groups = await client.get(f"{API_PREFIX}/team/groups")
        assert groups.status_code == 200, groups.text
        assert groups.json() == {"items": [], "next_cursor": None}

        view = await client.get(f"{API_PREFIX}/settings")
        assert view.status_code == 200
        assert "embedding" in view.json()

        draft = await client.post(
            f"{API_PREFIX}/settings/embedding/test-draft",
            json={
                "base_url": "https://embed.invalid/v1",
                "model": "embedding-test-model",
                "allow_network": False,
            },
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["draft"] is True
        assert draft.json()["overall"] in {"failed", "not_run"}

        attachment_id = new_id("att")
        sentinel = b"actual-mounted-app-private-sentinel"
        uploaded = await _upload(client, attachment_id, sentinel)
        assert uploaded.status_code == 201, uploaded.text
        content = await client.get(f"{PRIVATE}/{attachment_id}/content")
        assert content.status_code == 200
        assert content.json()["content"] == sentinel.decode()


def _seed_group(app: FastAPI) -> str:
    """Persist one Task/Run/Member/Subtask group directly through the store."""

    store = app.state.store
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "Actual app grouped task",
            "objective": "deliver a page",
            "acceptance_criteria": ["it works"],
            "status": "todo",
            "phase": "queued",
            "requirements_revision": 1,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": None,
            "agent_ref": "coordinator",
            "depends_on": [],
            "active_run": None,
            "deliverable_revision": 0,
            "queue": {
                "state": "not_queued",
                "order": None,
                "queued_at": None,
                "owner": None,
                "lease_expires_at": None,
                "waiting_reason": None,
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
        },
        actor="test",
        request_id="task:actual-integration",
        body="# Task\n",
    )
    run_id = new_id("run")
    member_id = new_id("member")
    subtask_id = new_id("subtask")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "executing",
            "plan_ref": "PLAN.md",
            "plan_source": "rules",
            "plan_hash": "abc",
            "team_refs": [member_id],
            "subtask_refs": [subtask_id],
            "session_refs": ["session-live"],
            "cleanup": {"status": "pending"},
            "reviewer_cleanup": None,
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"run:{run_id}",
        body=f"# Run {run_id}\n",
    )
    store.create(
        "subtask",
        subtask_id,
        {
            "run_ref": run_id,
            "state": "passed",
            "depends_on": [],
            "blocked_by": [],
            "assignee_member_ref": member_id,
            "upstream_artifact_refs": [],
            "objective": "build the page",
            "capability": "implementation",
            "key": "deliver",
            "write": True,
            "waiting_reason": None,
            "fail_reason": None,
            "acceptance": {
                "status": "passed",
                "criteria": ["it works"],
                "evidence_refs": ["index.html"],
            },
        },
        actor="test",
        request_id=f"subtask:{subtask_id}",
        body="# Subtask\n",
    )
    store.create(
        "member",
        member_id,
        {
            "run_ref": run_id,
            "role_ref": "frontend-developer",
            "role_category": "engineering",
            "state": "running",
            "template_version": "3",
            "connection_ref": None,
            "skill_refs": ["implementation"],
            "capabilities": ["implementation"],
            "selection_reason": "goal-fit metadata match",
            "assigned_subtask_refs": [subtask_id],
            "config_hash": "hash-1",
            "fail_reason": None,
        },
        actor="test",
        request_id=f"member:{member_id}",
        body="# Member\n",
    )
    task = store.read("task", task_id)
    store.write(
        "task",
        task_id,
        {"active_run": run_id, "last_run": run_id},
        expected_revision=task.revision,
        actor="test",
    )
    return task_id


async def test_actual_app_team_groups_projects_real_fields(
    tmp_path: Path,
) -> None:
    app = _single_app(_settings(tmp_path))
    task_id = _seed_group(app)
    async for client in _client(app):
        response = await client.get(
            f"{API_PREFIX}/team/groups", params={"task_ref": task_id}
        )
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["task"]["id"] == task_id
        run = item["runs"][0]
        assert run["session_refs"] == ["session-live"]
        assert run["subtask_refs"]
        assert run["cleanup"] == {"status": "pending"}
        member = item["members"][0]
        assert member["role_category"] == "engineering"
        assert member["selection_reason"] == "goal-fit metadata match"
        assert item["subtasks"][0]["acceptance"]["status"] == "passed"
        history = await client.get(
            f"{API_PREFIX}/team/groups", params={"view": "history"}
        )
        assert history.json()["items"] == []


async def test_actual_app_personal_responder_receives_bounded_context(
    tmp_path: Path,
) -> None:
    contexts: list[str | None] = []

    def responder(
        content: str,
        _classification: object,
        attachment_context: str | None = None,
    ) -> str:
        contexts.append(attachment_context)
        return "answer recorded without persisting the file body"

    app = _single_app(_settings(tmp_path), responder=responder)
    attachment_id = new_id("att")
    sentinel = "ACTUAL-APP-PRIVATE-CONTEXT-SENTINEL"
    async for client in _client(app):
        assert (await _upload(client, attachment_id, sentinel.encode())).status_code == 201
        posted = await client.post(
            PERSONAL,
            json={
                "message_id": "msg_actual_integration",
                "content": "summarize the attachment",
                "attachments": [{"attachment_id": attachment_id}],
            },
        )
        assert posted.status_code == 200, posted.text
        assert contexts and contexts[-1] is not None
        assert sentinel in contexts[-1]
        history = (await client.get(PERSONAL)).json()["items"]
        message = next(
            item for item in history if item["message_id"] == "msg_actual_integration"
        )
        # The bounded context is a separate responder argument, never persisted
        # as user content.
        assert sentinel not in message["message"]["content"]
        assert message["message"]["attachments"][0]["attachment_id"] == attachment_id


async def test_actual_team_app_keeps_private_attachment_owner_isolation(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, team_mode=True)
    accounts = TeamAccounts(settings.team_accounts_path)
    accounts.add("alice", "temporary-test-password", "member")
    accounts.add("bob", "temporary-test-password", "member")
    accounts.add("admin", "temporary-test-password", "admin")
    app = create_app(settings)
    attachment_id = new_id("att")
    sentinel = b"team-private-sentinel-must-not-leak"
    async for alice, bob, admin in _team_clients(app):
        for client, username in (
            (alice, "alice"),
            (bob, "bob"),
            (admin, "admin"),
        ):
            login = await client.post(
                f"{API_PREFIX}/auth/login",
                json={"username": username, "password": "temporary-test-password"},
            )
            assert login.status_code == 200
        assert (await _upload(alice, attachment_id, sentinel)).status_code == 201
        for viewer in (bob, admin):
            denied = await viewer.get(f"{PRIVATE}/{attachment_id}/content")
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "not_found"
            assert "sentinel" not in denied.text


async def _team_clients(
    app: FastAPI,
) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient, httpx.AsyncClient]]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as alice,
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as bob,
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as admin,
        ):
            yield alice, bob, admin
