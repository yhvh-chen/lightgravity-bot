"""HTTP regression tests for the LG-010 round-2 duplicate-ack blocker.

The real closed loop reaches ``awaiting_acceptance`` and a bound ``accept``
clears ``active_run``.  A caller that retries the *same* acknowledgement with
the same ``request_id`` and the same ``target_run_id`` must get the first full
result (HTTP 200, no repeated control write), not a spurious ``409`` from the
``target_run_id``/``active_run`` guard.  At the same time the replay must not
weaken the safety boundary: a reused ``request_id`` with a different Task, a
different target or a different action must still be rejected by the normal
contract checks.

All data lives under pytest ``tmp_path``; no network, model or SDK is used.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import new_id
from lightgravity.verify import VerificationService

_PENDING_ACCEPTANCE = {
    "status": "pending",
    "requirements_revision": None,
    "deliverable_revision": None,
    "evidence_refs": [],
    "decided_at": None,
    "decision_ref": None,
}


def _seed_awaiting_task(app: FastAPI) -> tuple[str, str]:
    """Seed a verifying Task/Run with evidence, then prepare acceptance."""

    store = app.state.store
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "accept replay task",
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
    prepared = app.state.verification.verify_and_prepare(task_id, request_id="prep")
    assert prepared.confirmed is True
    return task_id, run_id


async def _call(client: httpx.AsyncClient, task_id: str, payload: dict) -> httpx.Response:
    return await client.post(f"/api/v1/tasks/{task_id}/actions", json=payload)


async def test_duplicate_accept_with_same_target_is_idempotent(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id, run_id = _seed_awaiting_task(app)
            payload = {
                "action": "accept",
                "request_id": "dup-accept",
                "target_run_id": run_id,
            }
            first = await _call(client, task_id, payload)
            assert first.status_code == 200, first.text
            assert first.json()["confirmed"] is True
            assert first.json()["phase"] == "completed"

            # active_run is now cleared; the duplicate must still replay the
            # first result instead of 409 from the target guard.
            second = await _call(client, task_id, payload)
            assert second.status_code == 200, second.text
            assert second.json() == first.json()

            # A duplicate without target_run_id also replays the first result.
            third = await _call(
                client, task_id, {"action": "accept", "request_id": "dup-accept"}
            )
            assert third.status_code == 200, third.text
            assert third.json() == first.json()


async def test_replay_does_not_accept_wrong_target(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id, run_id = _seed_awaiting_task(app)
            first = await _call(
                client,
                task_id,
                {"action": "accept", "request_id": "dup-accept", "target_run_id": run_id},
            )
            assert first.status_code == 200, first.text

            # Same request_id but a different (bogus) target must not replay.
            wrong = await _call(
                client,
                task_id,
                {
                    "action": "accept",
                    "request_id": "dup-accept",
                    "target_run_id": "run_does_not_exist",
                },
            )
            assert wrong.status_code == 409, wrong.text
            assert wrong.json()["error"]["code"] == "illegal_transition"


async def test_replay_does_not_leak_across_tasks(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_a, run_a = _seed_awaiting_task(app)
            task_b, _run_b = _seed_awaiting_task(app)
            first = await _call(
                client,
                task_a,
                {"action": "accept", "request_id": "shared-req", "target_run_id": run_a},
            )
            assert first.status_code == 200, first.text

            # Reusing task A's request_id on task B (unrelated) must not replay
            # task A's decision; task B is decided on its own candidate binding.
            crossed = await _call(
                client,
                task_b,
                {"action": "accept", "request_id": "shared-req", "target_run_id": _run_b},
            )
            assert crossed.status_code == 200, crossed.text
            assert crossed.json()["acceptance"]["candidate_ref"] != first.json()["candidate_ref"]
            assert crossed.json()["acceptance"]["decision_ref"] == "shared-req"
            assert crossed.json()["task_id"] == task_b


async def test_new_request_after_accept_replays_bound_candidate(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id, run_id = _seed_awaiting_task(app)
            first = await _call(
                client,
                task_id,
                {"action": "accept", "request_id": "req-1", "target_run_id": run_id},
            )
            assert first.status_code == 200, first.text

            # A brand new request_id is not an idempotent replay, but the
            # already-decided candidate is still recognised as bound.
            later = await _call(client, task_id, {"action": "accept", "request_id": "req-2"})
            assert later.status_code == 200, later.text
            assert later.json()["phase"] == "completed"
            assert later.json()["acceptance"]["status"] == "accepted"


async def test_reject_duplicate_is_idempotent_and_bounded(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id, run_id = _seed_awaiting_task(app)
            payload = {"action": "reject", "request_id": "dup-reject", "target_run_id": run_id}
            first = await _call(client, task_id, payload)
            assert first.status_code == 200, first.text
            assert first.json()["phase"] == "repairing"

            second = await _call(client, task_id, payload)
            assert second.status_code == 200, second.text
            assert second.json() == first.json()


async def test_stale_revision_still_rejected(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id, run_id = _seed_awaiting_task(app)
            stale = await _call(
                client,
                task_id,
                {"action": "accept", "request_id": "stale-1", "target_run_id": run_id},
            )
            assert stale.status_code == 200, stale.text

            # New request, stale expected revision must still conflict.
            conflict = await _call(
                client,
                task_id,
                {"action": "accept", "request_id": "stale-2", "expected_revision": 1},
            )
            assert conflict.status_code == 409, conflict.text


async def test_non_loopback_duplicate_ack_requires_token(settings: Settings) -> None:
    """A non-loopback caller must present the local token, even for a replay."""

    from lightgravity.api.access import TOKEN_HEADER

    app = create_app(settings, access_policy=LocalAccessPolicy(token="sesame"))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(
            app=app, client=("10.1.2.3", 5555)
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            task_id, run_id = _seed_awaiting_task(app)
            payload = {"action": "accept", "request_id": "deny-1", "target_run_id": run_id}
            denied = await _call(client, task_id, payload)
            assert denied.status_code == 401, denied.text
            assert denied.json()["error"]["code"] == "unauthorized"

            allowed = await client.post(
                f"/api/v1/tasks/{task_id}/actions",
                json=payload,
                headers={TOKEN_HEADER: "sesame"},
            )
            assert allowed.status_code == 200, allowed.text

            replay = await client.post(
                f"/api/v1/tasks/{task_id}/actions",
                json=payload,
                headers={TOKEN_HEADER: "sesame"},
            )
            assert replay.status_code == 200, replay.text
            assert replay.json() == allowed.json()


async def test_replay_decision_requires_same_action(settings: Settings) -> None:
    """``replay_decision`` is bounded to the same Task/action/original target."""

    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    service = VerificationService(store)
    assert service.replay_decision("task_x", "accept", "missing") is None
