"""Persistent notifications projected from durable events (LG-019).

The tests drive the real ``create_app`` wiring: they append durable events the
way the coordinator/verifier do (``append_event``), then assert the frozen
``GET/POST /api/v1/notifications`` surface projects them, persists read state
independently of the projection, and keeps accurate Task/Run/version targeting.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI

from api_helpers import create_bare_task


def _emit_phase(
    app: FastAPI,
    task_id: str,
    to_phase: str,
    *,
    run_ref: str | None = None,
    reason: str | None = None,
) -> int:
    payload: dict[str, Any] = {"from": "executing", "to": to_phase}
    if reason:
        payload["reason"] = reason
    record = app.state.store.append_event(
        task_id,
        {
            "type": "task.phase_changed",
            "actor": "coordinator",
            "task_ref": task_id,
            "run_ref": run_ref,
            "payload": payload,
        },
    )
    return record.seq


async def test_empty_when_no_events(app: FastAPI, api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/notifications")
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "next_cursor": None, "unread": 0}


async def test_projects_failed_waiting_and_acceptance_with_targets(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    task_id = create_bare_task(app)
    run_id = "run_01J0000000000000000000001"
    # awaiting_acceptance carries a preceding decision binding.
    app.state.store.append_event(
        task_id,
        {
            "type": "decision.requested",
            "actor": "verify",
            "task_ref": task_id,
            "run_ref": run_id,
            "payload": {
                "candidate_ref": run_id,
                "requirements_revision": 3,
                "deliverable_revision": 2,
            },
        },
    )
    _emit_phase(app, task_id, "waiting_user", run_ref=run_id, reason="need a decision")
    _emit_phase(app, task_id, "awaiting_acceptance", run_ref=run_id)
    _emit_phase(app, task_id, "failed", run_ref=run_id, reason="budget exhausted")

    body = (await api.get("/api/v1/notifications")).json()
    kinds = {item["kind"] for item in body["items"]}
    assert kinds == {
        "task.waiting_user",
        "task.awaiting_acceptance",
        "task.failed",
    }
    assert body["unread"] == 3

    acceptance = next(
        item for item in body["items"] if item["kind"] == "task.awaiting_acceptance"
    )
    assert acceptance["task_ref"] == task_id
    assert acceptance["run_ref"] == run_id
    assert acceptance["candidate_ref"] == run_id
    assert acceptance["requirements_revision"] == 3
    assert acceptance["deliverable_revision"] == 2
    assert acceptance["severity"] == "success"
    assert acceptance["read"] is False

    failed = next(item for item in body["items"] if item["kind"] == "task.failed")
    assert failed["reason"] == "budget exhausted"
    assert failed["severity"] == "error"


async def test_read_state_is_durable_and_independent(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    task_id = create_bare_task(app)
    _emit_phase(app, task_id, "failed", reason="boom")

    first = (await api.get("/api/v1/notifications")).json()["items"][0]
    notification_id = first["notification_id"]
    assert first["read"] is False

    marked = (
        await api.post(
            "/api/v1/notifications",
            json={"notification_ids": [notification_id], "request_id": "req-read-1"},
        )
    ).json()
    assert marked["marked_read"] == [notification_id]
    assert marked["unread"] == 0

    # A fresh list still shows the notification, now read (projection intact).
    again = (await api.get("/api/v1/notifications")).json()
    assert again["unread"] == 0
    assert again["items"][0]["notification_id"] == notification_id
    assert again["items"][0]["read"] is True
    assert again["items"][0]["read_at"]

    only_unread = (await api.get("/api/v1/notifications?unread_only=true")).json()
    assert only_unread["items"] == []

    # Idempotent repeat does not fail or duplicate.
    repeat = (
        await api.post(
            "/api/v1/notifications",
            json={"notification_ids": [notification_id]},
        )
    ).json()
    assert repeat["unread"] == 0

    # An unknown id is reported, never fabricated.
    unknown = (
        await api.post(
            "/api/v1/notifications",
            json={"notification_ids": ["notif_DOESNOTEXIST"]},
        )
    ).json()
    assert unknown["unknown"] == ["notif_DOESNOTEXIST"]


async def test_task_filter(app: FastAPI, api: httpx.AsyncClient) -> None:
    first_task = create_bare_task(app)
    second_task = create_bare_task(app)
    _emit_phase(app, first_task, "failed")
    _emit_phase(app, second_task, "failed")

    filtered = (
        await api.get("/api/v1/notifications", params={"task_ref": first_task})
    ).json()
    assert len(filtered["items"]) == 1
    assert filtered["items"][0]["task_ref"] == first_task


async def test_notification_id_is_stable_across_reprojection(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    task_id = create_bare_task(app)
    _emit_phase(app, task_id, "failed")

    first = (await api.get("/api/v1/notifications")).json()["items"][0]
    second = (await api.get("/api/v1/notifications")).json()["items"][0]
    assert first["notification_id"] == second["notification_id"]
    assert first["notification_id"].startswith("notif_")
    assert first["seq"] == second["seq"]
