"""LG-126 read-only GET /team/groups projection (actual HTTP, no mutation)."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX
from lightgravity.store import FileStore, new_id


@pytest.fixture
def groups_app(settings: Settings) -> FastAPI:
    # ``create_app`` mounts the projection in api/app.py; the test must not
    # mount it a second time by hand.
    return create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )


@pytest.fixture
async def groups_client(groups_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with groups_app.router.lifespan_context(groups_app):
        transport = httpx.ASGITransport(app=groups_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


def _task(
    app: FastAPI,
    request_id: str,
    *,
    phase: str = "queued",
    status: str = "todo",
) -> str:
    store = app.state.store
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": f"Task {request_id}",
            "objective": "do the thing",
            "acceptance_criteria": ["it works"],
            "status": status,
            "phase": phase,
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
        request_id=f"task:{request_id}",
        body="# Task\n",
    )
    return task_id


def _run(
    app: FastAPI,
    task_id: str,
    *,
    state: str,
    cleanup: str,
    session_refs: list[str],
    reviewer_cleanup: dict[str, Any] | None,
    member_id: str,
    subtask_id: str,
) -> str:
    store = app.state.store
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": state,
            "plan_ref": "PLAN.md",
            "plan_source": "rules",
            "plan_hash": "abc",
            "team_refs": [member_id],
            "subtask_refs": [subtask_id],
            "session_refs": session_refs,
            "cleanup": {"status": cleanup},
            "reviewer_cleanup": reviewer_cleanup,
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"run:{run_id}",
        body=f"# Run {run_id}\n",
    )
    task = store.read("task", task_id)
    store.write(
        "task",
        task_id,
        {"active_run": run_id, "last_run": run_id},
        expected_revision=task.revision,
        actor="test",
    )
    return run_id


def _member_and_subtask(
    app: FastAPI,
    task_id: str,
    run_id: str,
    *,
    member_state: str,
    role_ref: str = "frontend-developer",
) -> tuple[str, str]:
    store = app.state.store
    member_id = new_id("member")
    subtask_id = new_id("subtask")
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
            "role_ref": role_ref,
            "role_category": "engineering",
            "state": member_state,
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
        body=f"# Member {role_ref}\n",
    )
    return member_id, subtask_id


def _tree_digest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


async def test_groups_are_paginated_filtered_and_release_guarded_without_writes(
    groups_client: httpx.AsyncClient, groups_app: FastAPI
) -> None:
    # History: clean worker + reviewer cleanup and released member.
    history_task = _task(groups_app, "history", phase="awaiting_acceptance", status="in-progress")
    history_member, history_subtask = _member_and_subtask(
        groups_app, history_task, "placeholder", member_state="released"
    )
    history_run = _run(
        groups_app,
        history_task,
        state="awaiting_acceptance",
        cleanup="done",
        session_refs=[],
        reviewer_cleanup={"status": "done", "confirmed": True},
        member_id=history_member,
        subtask_id=history_subtask,
    )
    # Re-point the run/member/subtask at the real Run id where relevant.
    store = groups_app.state.store
    for kind, item_id, field in (
        ("subtask", history_subtask, "run_ref"),
        ("member", history_member, "run_ref"),
    ):
        current = store.read(kind, item_id)
        store.write(
            kind,
            item_id,
            {field: history_run},
            expected_revision=current.revision,
            actor="test",
        )

    # Failed member alone is not stop proof: live session + pending cleanup.
    guarded_task = _task(groups_app, "guarded", phase="failed", status="in-progress")
    guarded_member, guarded_subtask = _member_and_subtask(
        groups_app, guarded_task, "placeholder", member_state="failed"
    )
    guarded_run = _run(
        groups_app,
        guarded_task,
        state="failed",
        cleanup="pending",
        session_refs=["native-session-live"],
        reviewer_cleanup=None,
        member_id=guarded_member,
        subtask_id=guarded_subtask,
    )
    for kind, item_id in (("subtask", guarded_subtask), ("member", guarded_member)):
        current = store.read(kind, item_id)
        store.write(
            kind,
            item_id,
            {"run_ref": guarded_run},
            expected_revision=current.revision,
            actor="test",
        )

    intake_task = _task(groups_app, "intake", phase="intake", status="todo")

    before = _tree_digest(groups_app.state.settings.data_dir)
    first = await groups_client.get("/api/v1/team/groups", params={"limit": 2})
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 2
    assert isinstance(page["next_cursor"], str)
    second = await groups_client.get(
        "/api/v1/team/groups", params={"limit": 2, "cursor": page["next_cursor"]}
    )
    second_page = second.json()
    all_items = page["items"] + second_page["items"]
    assert {item["task"]["id"] for item in all_items} == {
        history_task,
        guarded_task,
        intake_task,
    }
    assert second_page["next_cursor"] is None

    history = await groups_client.get(
        "/api/v1/team/groups", params={"view": "history"}
    )
    assert [item["task"]["id"] for item in history.json()["items"]] == [history_task]
    history_item = history.json()["items"][0]
    assert history_item["runs"][0]["cleanup"]["status"] == "done"
    assert history_item["runs"][0]["reviewer_cleanup"]["confirmed"] is True
    assert history_item["task"]["queue"]["state"] == "not_queued"
    assert history_item["active_run"]["id"] == history_run
    assert history_item["members"][0]["assigned_subtasks"][0]["state"] == "passed"
    assert history_item["subtasks"][0]["acceptance"]["status"] == "passed"

    active = await groups_client.get(
        "/api/v1/team/groups", params={"view": "active"}
    )
    active_ids = {item["task"]["id"] for item in active.json()["items"]}
    assert active_ids == {guarded_task, intake_task}
    guarded_item = next(
        item for item in active.json()["items"] if item["task"]["id"] == guarded_task
    )
    # A failed member does not prove cleanup; the raw live session is exposed.
    assert guarded_item["runs"][0]["session_refs"] == ["native-session-live"]
    assert guarded_item["runs"][0]["cleanup"]["status"] == "pending"
    assert guarded_item["members"][0]["state"] == "failed"

    filtered = await groups_client.get(
        "/api/v1/team/groups", params={"task_ref": history_task}
    )
    assert [item["task"]["id"] for item in filtered.json()["items"]] == [history_task]

    assert (
        await groups_client.get("/api/v1/team/groups", params={"view": "bogus"})
    ).status_code == 400
    assert (
        await groups_client.get("/api/v1/team/groups", params={"cursor": "bad"})
    ).status_code == 400
    assert (
        await groups_client.get("/api/v1/team/groups", params={"task_ref": "task_missing"})
    ).status_code == 404

    after = _tree_digest(groups_app.state.settings.data_dir)
    assert after == before, "read-only projection must not write any file"


async def test_team_mode_anonymous_groups_is_unauthorized(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "team-data",
        workspace_root=tmp_path / "team-data" / "workspaces",
        secret_store=tmp_path / "team-secrets",
        team_mode=True,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/api/v1/team/groups")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_cancelled_never_started_task_repairs_stale_queue_via_normal_action(
    groups_client: httpx.AsyncClient, groups_app: FastAPI,
) -> None:
    task_id = _task(groups_app, 'old-queued-cancel', phase='cancelled', status='todo')
    store = groups_app.state.store
    task = store.read('task', task_id)
    store.write('task', task_id, {'queue': {
        'state': 'queued', 'order': 5, 'queued_at': '2026-10-17T22:28:44.905Z',
        'waiting_reason': 'active_task_limit',
    }}, expected_revision=task.revision, actor='test')
    # Reading the old bad record must not act as a migration or claim it free.
    before = _tree_digest(groups_app.state.settings.data_dir)
    old = await groups_client.get('/api/v1/team/groups', params={'view': 'active', 'task_ref': task_id})
    assert [item['task']['id'] for item in old.json()['items']] == [task_id]
    assert _tree_digest(groups_app.state.settings.data_dir) == before
    result = await groups_client.post(f'/api/v1/tasks/{task_id}/actions', json={
        'action': 'cancel', 'request_id': 'fresh-cancel-old-queued-task',
    })
    assert result.status_code == 200, result.text
    assert result.json()['confirmed'] is True and result.json()['run_id'] is None
    after_cancel = _tree_digest(groups_app.state.settings.data_dir)
    active = await groups_client.get('/api/v1/team/groups', params={'view': 'active', 'task_ref': task_id})
    history = await groups_client.get('/api/v1/team/groups', params={'view': 'history', 'task_ref': task_id})
    assert active.json()['items'] == []
    item = history.json()['items'][0]
    assert item['task']['phase'] == 'cancelled' and item['task']['status'] == 'todo'
    assert item['task']['queue'] == {
        'state': 'not_queued', 'order': 5, 'queued_at': '2026-10-17T22:28:44.905Z',
        'owner': None, 'waiting_reason': None,
    }
    assert item['runs'] == [] and item['members'] == [] and item['subtasks'] == []
    assert item['active_run'] is None
    assert _tree_digest(groups_app.state.settings.data_dir) == after_cancel


async def test_cancelled_actual_run_with_unknown_sessions_stays_active(
    groups_client: httpx.AsyncClient, groups_app: FastAPI,
) -> None:
    task_id = _task(groups_app, 'cancelled-unknown-stop', phase='cancelled', status='in-progress')
    member_id, subtask_id = _member_and_subtask(groups_app, task_id, 'placeholder', member_state='released')
    run_id = _run(groups_app, task_id, state='cancelled', cleanup='pending',
                  session_refs=['actual-session-with-unknown-stop'], reviewer_cleanup=None,
                  member_id=member_id, subtask_id=subtask_id)
    store = groups_app.state.store
    for kind, entity_id in [('member', member_id), ('subtask', subtask_id)]:
        current = store.read(kind, entity_id)
        store.write(kind, entity_id, {'run_ref': run_id}, expected_revision=current.revision, actor='test')
    history = await groups_client.get('/api/v1/team/groups', params={'view': 'history', 'task_ref': task_id})
    active = await groups_client.get('/api/v1/team/groups', params={'view': 'active', 'task_ref': task_id})
    assert history.json()['items'] == []
    item = active.json()['items'][0]
    assert item['task']['queue']['state'] == 'not_queued'
    assert item['active_run']['session_refs'] == ['actual-session-with-unknown-stop']
    assert item['active_run']['cleanup'] == {'status': 'pending'}
