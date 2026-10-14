"""Shared helpers for LG-004 store tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from lightgravity.store import FileStore, new_id


def task_content(**overrides: Any) -> dict[str, Any]:
    content: dict[str, Any] = {
        "title": "Test task",
        "status": "todo",
        "phase": "intake",
        "revision": 0,
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
    return content


def create_task(store: FileStore, *, task_id: str | None = None, body: str = "\n# Task\n", **overrides: Any) -> str:
    entity_id = task_id or new_id("task")
    store.create(
        "task",
        entity_id,
        task_content(**overrides),
        actor="test",
        request_id=f"req_{entity_id}",
        body=body,
    )
    return entity_id


class FakeClock:
    """Deterministic UTC clock for lease-expiry tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)
