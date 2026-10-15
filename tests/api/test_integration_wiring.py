"""Integration wiring for LG-009 verification + LG-012 global conversation.

These tests exercise the *integrated* app factory rather than the standalone
router factories: the verification service is built by ``create_app`` and shared
by the read-only ``GET /tasks/{id}/acceptance`` route and the accept/reject
branch of ``POST /tasks/{id}/actions``; the singleton global conversation is
reachable over HTTP.  All data lives under pytest ``tmp_path`` via the
``settings`` fixture; no network or real model is used.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from lightgravity.api.conversations import GLOBAL_CONVERSATION_ID
from lightgravity.config import Settings
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import new_id
from lightgravity.verify import StopReport

_PENDING_ACCEPTANCE = {
    "status": "pending",
    "requirements_revision": None,
    "deliverable_revision": None,
    "evidence_refs": [],
    "decided_at": None,
    "decision_ref": None,
}


def _seed_verifying_task(app: FastAPI) -> str:
    """Seed an authoritative verifying Task/Run/Subtask directly through Store."""

    store = app.state.store
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "integration acceptance",
            "objective": "deliver something",
            "acceptance_criteria": ["it works"],
            "status": "in-progress",
            "phase": "verifying",
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
            },
            "checks": ["evidence-present"],
            "acceptance": dict(_PENDING_ACCEPTANCE),
            "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
            "archived": False,
        },
        actor="test",
        request_id=f"req-{task_id}",
        body="# Task\n\nbody text preserved\n",
    )
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "verifying",
            "plan_ref": "PLAN.md",
            "plan": None,
            "plan_hash": "a" * 64,
            "plan_source": "rules",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "pending"},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"req-{run_id}",
        body=f"# Run {run_id}\n",
    )
    subtask_id = new_id("subtask")
    store.create(
        "subtask",
        subtask_id,
        {
            "run_ref": run_id,
            "state": "passed",
            "depends_on": [],
            "assignee_member_ref": None,
            "upstream_artifact_refs": [],
            "objective": "deliver",
            "capability": "implementation",
            "key": "deliver",
            "write": True,
            "config_hash": None,
            "fail_reason": None,
            "blocked_by": [],
            "acceptance": {
                "status": "passed",
                "criteria": ["it works"],
                "evidence_refs": ["out/result.txt"],
            },
        },
        actor="test",
        request_id=f"req-{subtask_id}",
        body="# Subtask deliver\n",
    )
    writer = StateWriter(store, actor="test")
    writer.write_run(run_id, {"subtask_refs": [subtask_id]})
    writer.set_active_run(task_id, run_id)
    return task_id


async def test_verification_is_injected_and_wired(app: FastAPI) -> None:
    assert app.state.verification is not None
    assert app.state.context.verification is app.state.verification


async def test_injected_coordinator_auto_verifies(settings: Settings) -> None:
    """An explicitly injected coordinator shares the app verification service.

    Regression for the LG-010 blocker: the normal ``POST /tasks`` delivery must
    reach ``awaiting_acceptance`` automatically, including the create_app branch
    that receives a caller-built coordinator/dispatcher/executor.
    """

    from lightgravity.api.access import LocalAccessPolicy
    from lightgravity.api.app import create_app
    from lightgravity.coordinator import Coordinator, SingleSlotDispatcher
    from lightgravity.store import FileStore

    from api_helpers import (
        FakeExecutor,
        create_task,
        wait_for_phase,
        wire_program_reviewer,
    )

    base = FileStore(settings.data_dir, settings.workspace_root)
    fake = FakeExecutor()
    coordinator = Coordinator(base, dispatcher=SingleSlotDispatcher(fake))
    app = create_app(
        settings,
        store=base,
        coordinator=coordinator,
        executor=fake,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    # This test targets the auto-verify/acceptance wiring; opt in to the
    # deterministic machine-gate reviewer explicitly (the honest default is an
    # unavailable independent reviewer, which would park at waiting_user).
    wire_program_reviewer(app)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id = await create_task(client)
            detail = await wait_for_phase(client, task_id, {"awaiting_acceptance"})
            assert detail["phase"] == "awaiting_acceptance"
            assert detail["acceptance"]["status"] == "awaiting"
            snapshot = await client.get(f"/api/v1/tasks/{task_id}/acceptance")
            assert snapshot.status_code == 200
            assert snapshot.json()["candidate"]["run_id"] == detail["run"]["id"]


class _RefusingStopper:
    """ResourceStopper double that never confirms a stop."""

    def stop(self, task_id: str, run_id: str) -> StopReport:
        return StopReport(
            confirmed=False,
            run_stopped=False,
            sessions_stopped=False,
            slot_released=False,
            problems=("injected refusal",),
        )


async def test_resource_stopper_injection_is_used(settings: Settings) -> None:
    from lightgravity.api.access import LocalAccessPolicy
    from lightgravity.api.app import create_app

    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
        resource_stopper=_RefusingStopper(),
    )
    task_id = _seed_verifying_task(app)
    result = app.state.verification.verify_and_prepare(task_id, request_id="prep")
    assert result.confirmed is False
    assert result.state == "unconfirmed"


async def test_acceptance_read_and_decide_via_actions(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id = _seed_verifying_task(app)
            prepared = app.state.verification.verify_and_prepare(
                task_id, request_id="prep"
            )
            assert prepared.confirmed is True

            snapshot = await client.get(f"/api/v1/tasks/{task_id}/acceptance")
            assert snapshot.status_code == 200
            body = snapshot.json()
            assert body["phase"] == "awaiting_acceptance"
            assert body["acceptance"]["status"] == "awaiting"
            assert body["acceptance"]["candidate_ref"] == prepared.candidate_ref
            assert body["candidate"]["run_id"] == prepared.candidate_ref

            payload = {
                "action": "accept",
                "request_id": "accept-1",
                "expected_requirements_revision": 1,
                "expected_deliverable_revision": 1,
            }
            first = await client.post(
                f"/api/v1/tasks/{task_id}/actions", json=payload
            )
            assert first.status_code == 200, first.text
            assert first.json()["confirmed"] is True
            assert first.json()["phase"] == "completed"

            # Same request_id replays the first result without a second write.
            second = await client.post(
                f"/api/v1/tasks/{task_id}/actions", json=payload
            )
            assert second.status_code == 200
            assert second.json() == first.json()


async def test_global_conversation_roundtrip_and_source_limits(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            posted = await client.post(
                "/api/v1/conversations/global/messages",
                json={"message_id": "msg-global-1", "content": "你好"},
            )
            assert posted.status_code == 200, posted.text
            assert posted.json()["conversation_id"] == GLOBAL_CONVERSATION_ID

            listed = await client.get("/api/v1/conversations/global/messages")
            assert listed.status_code == 200
            assert [item["message_id"] for item in listed.json()["items"]] == [
                "msg-global-1"
            ]
            assert listed.json()["next_cursor"]

            replay = await client.post(
                "/api/v1/conversations/global/messages",
                json={"message_id": "msg-global-1", "content": "你好"},
            )
            assert replay.status_code == 200
            again = await client.get("/api/v1/conversations/global/messages")
            assert len(again.json()["items"]) == 1

            escaped = await client.post(
                "/api/v1/conversations/global/messages",
                json={
                    "message_id": "msg-global-2",
                    "content": "hi",
                    "workspace_ref": "../escape",
                },
            )
            assert escaped.status_code == 403
            assert escaped.json()["error"]["code"] == "path_outside_workspace"

            unknown_agent = await client.post(
                "/api/v1/conversations/global/messages",
                json={
                    "message_id": "msg-global-3",
                    "content": "hi",
                    "agent_ref": "does-not-exist",
                },
            )
            assert unknown_agent.status_code == 422
            assert unknown_agent.json()["error"]["code"] == "reference_invalid"
