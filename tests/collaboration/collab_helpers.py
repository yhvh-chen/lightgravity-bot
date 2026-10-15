"""Shared entity builders and a deterministic clock for LG-029 tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from lightgravity.store import FileStore, new_id


class FakeClock:
    """Deterministic UTC clock for lease-expiry tests (no sleeps)."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def create_task(
    store: FileStore,
    *,
    task_id: str | None = None,
    budget: dict[str, int] | None = None,
    **overrides: Any,
) -> str:
    entity_id = task_id or new_id("task")
    content: dict[str, Any] = {
        "title": "collab task",
        "status": "in-progress",
        "phase": "executing",
        "requirements_revision": 1,
        "project_ref": None,
        "repository_ref": None,
        "workspace_ref": "ws",
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
        "budget": budget or {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
        "archived": False,
    }
    content.update(overrides)
    store.create(
        "task",
        entity_id,
        content,
        actor="test",
        request_id=f"req_{entity_id}",
        body="# Task\n",
    )
    return entity_id


def create_run(store: FileStore, task_id: str, *, run_id: str | None = None, **overrides: Any) -> str:
    entity_id = run_id or new_id("run")
    content: dict[str, Any] = {
        "task_ref": task_id,
        "attempt": 1,
        "state": "executing",
        "plan_ref": "PLAN.md",
        "plan_source": "rules",
        "team_refs": [],
        "subtask_refs": [],
        "session_refs": [],
        "cleanup": {"status": "pending"},
        "ended_at": None,
        "fail_reason": None,
    }
    content.update(overrides)
    store.create(
        "run",
        entity_id,
        content,
        actor="test",
        request_id=f"req_{entity_id}",
        body=f"# Run {entity_id}\n",
    )
    return entity_id


def create_subtask(
    store: FileStore,
    run_id: str,
    *,
    subtask_id: str | None = None,
    state: str = "pending",
    capability: str = "implementation",
    write: bool = False,
    depends_on: list[str] | None = None,
    key: str | None = None,
    owner: str | None = None,
    lease_expires_at: str | None = None,
    fence: int | None = None,
    **overrides: Any,
) -> str:
    entity_id = subtask_id or new_id("subtask")
    content: dict[str, Any] = {
        "run_ref": run_id,
        "state": state,
        "depends_on": list(depends_on or []),
        "assignee_member_ref": None,
        "upstream_artifact_refs": [],
        "objective": f"objective for {key or entity_id}",
        "capability": capability,
        "key": key or entity_id,
        "write": write,
        "config_hash": "hash-" + (key or entity_id),
        "owner": owner,
        "lease_expires_at": lease_expires_at,
        "fail_reason": None,
        "blocked_by": [],
        "acceptance": {"status": "pending", "criteria": [], "evidence_refs": []},
    }
    if fence is not None:
        content["fence"] = fence
    content.update(overrides)
    store.create(
        "subtask",
        entity_id,
        content,
        actor="test",
        request_id=f"req_{entity_id}",
        body=f"# Subtask {key or entity_id}\n",
    )
    return entity_id


def link_subtasks(store: FileStore, run_id: str, subtask_ids: list[str]) -> None:
    """Record the authoritative ``run.subtask_refs`` list (what discovery reads)."""

    current = store.read("run", run_id)
    store.write(
        "run",
        run_id,
        {"subtask_refs": list(subtask_ids)},
        expected_revision=current.revision,
        actor="test",
    )


def set_switches(
    store: FileStore,
    *,
    enabled: bool,
    lease_seconds: int = 300,
    collab_enabled: bool = False,
) -> None:
    """Write the collaboration switches into ``settings/SETTINGS.md`` (read-only use)."""

    try:
        current = store.read("settings", "settings")
    except Exception:  # noqa: BLE001 - create when missing
        store.create(
            "settings",
            "settings",
            {
                "title": "Global settings",
                "enabled": True,
                "default_coordinator_connection_ref": None,
                "default_worker_connection_ref": None,
                "decentralized_claim_enabled": enabled,
                "collab_requests_enabled": collab_enabled,
                "claim_lease_seconds": lease_seconds,
            },
            actor="test",
            request_id="req_settings",
            body="# Settings\n",
        )
        return
    store.write(
        "settings",
        "settings",
        {
            "decentralized_claim_enabled": enabled,
            "collab_requests_enabled": collab_enabled,
            "claim_lease_seconds": lease_seconds,
        },
        expected_revision=current.revision,
        actor="test",
    )
