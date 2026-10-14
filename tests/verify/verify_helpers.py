"""Shared helpers for the LG-009 verify tests.

These build authoritative Task/Run/Subtask/Member frontmatter directly through
the Store (no graph execution), so the verification service is tested against
real files/versions and real optimistic-concurrency writes.  Unit evidence only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore, new_id
from lightgravity.verify.candidate import Candidate

PENDING_ACCEPTANCE: dict[str, Any] = {
    "status": "pending",
    "requirements_revision": None,
    "deliverable_revision": None,
    "evidence_refs": [],
    "decided_at": None,
    "decision_ref": None,
}


def create_task(
    store: FileStore,
    *,
    phase: str = "verifying",
    status: str = "in-progress",
    checks: tuple[str, ...] | None = ("evidence-present",),
    workspace_ref: str | None = "ws",
    requirements_revision: int = 1,
    deliverable_revision: int = 0,
    acceptance: dict[str, Any] | None = None,
    queue_state: str = "not_queued",
    queue_owner: str | None = None,
    active_run: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    task_id = new_id("task")
    content: dict[str, Any] = {
        "title": "verify task",
        "objective": "deliver something",
        "acceptance_criteria": ["it works"],
        "status": status,
        "phase": phase,
        "requirements_revision": requirements_revision,
        "project_ref": None,
        "repository_ref": None,
        "workspace_ref": workspace_ref,
        "agent_ref": "developer",
        "depends_on": [],
        "active_run": active_run,
        "deliverable_revision": deliverable_revision,
        "queue": {
            "state": queue_state,
            "order": None,
            "queued_at": None,
            "owner": queue_owner,
            "lease_expires_at": None,
        },
        "acceptance": dict(acceptance or PENDING_ACCEPTANCE),
        "budget": {"max_workers": 3, "max_parallel": 2, "max_repair_rounds": 1},
        "archived": False,
    }
    if checks is not None:
        content["checks"] = list(checks)
    if extra:
        content.update(extra)
    store.create(
        "task",
        task_id,
        content,
        actor="test",
        request_id=f"req-{task_id}",
        body="# Task\n\nbody text preserved\n",
    )
    return task_id


def create_run(
    store: FileStore,
    task_id: str,
    *,
    state: str = "verifying",
    session_refs: tuple[str, ...] = (),
    cleanup: str = "pending",
    plan_hash: str | None = "a" * 64,
) -> str:
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": state,
            "plan_ref": "PLAN.md",
            "plan": None,
            "plan_hash": plan_hash,
            "plan_source": "rules",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": list(session_refs),
            "cleanup": {"status": cleanup},
            "ended_at": None,
            "fail_reason": None,
        },
        actor="test",
        request_id=f"req-{run_id}",
        body=f"# Run {run_id}\n",
    )
    return run_id


def create_member(
    store: FileStore,
    run_id: str,
    *,
    state: str = "released",
    role_ref: str = "developer",
) -> str:
    member_id = new_id("member")
    store.create(
        "member",
        member_id,
        {
            "run_ref": run_id,
            "role_ref": role_ref,
            "state": state,
            "template_version": "1",
            "connection_ref": "primary",
            "skill_refs": [],
            "session_ref": None,
            "tool_policy": {},
            "workspace_ref": "ws",
            "assigned_subtask_refs": [],
            "budget": {},
        },
        actor="test",
        request_id=f"req-{member_id}",
        body=f"# Member {role_ref}\n",
    )
    return member_id


def create_subtask(
    store: FileStore,
    run_id: str,
    *,
    state: str = "passed",
    evidence: tuple[str, ...] = ("out/result.txt",),
    acceptance_status: str = "passed",
) -> str:
    subtask_id = new_id("subtask")
    store.create(
        "subtask",
        subtask_id,
        {
            "run_ref": run_id,
            "state": state,
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
                "status": acceptance_status,
                "criteria": ["it works"],
                "evidence_refs": list(evidence),
            },
        },
        actor="test",
        request_id=f"req-{subtask_id}",
        body="# Subtask deliver\n",
    )
    return subtask_id


def make_verifying_task(
    store: FileStore,
    *,
    checks: tuple[str, ...] | None = ("evidence-present",),
    evidence: tuple[str, ...] = ("out/result.txt",),
    member_state: str | None = "released",
    run_state: str = "verifying",
    session_refs: tuple[str, ...] = (),
    cleanup: str = "pending",
    queue_state: str = "not_queued",
    queue_owner: str | None = None,
    requirements_revision: int = 1,
    deliverable_revision: int = 0,
    acceptance: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str, list[str], list[str]]:
    task_id = create_task(
        store,
        checks=checks,
        queue_state=queue_state,
        queue_owner=queue_owner,
        requirements_revision=requirements_revision,
        deliverable_revision=deliverable_revision,
        acceptance=acceptance,
        extra=extra,
    )
    run_id = create_run(
        store, task_id, state=run_state, session_refs=session_refs, cleanup=cleanup
    )
    members: list[str] = []
    if member_state is not None:
        members.append(create_member(store, run_id, state=member_state))
    subtasks: list[str] = []
    if evidence is not None:
        subtasks.append(create_subtask(store, run_id, evidence=evidence))
    writer = StateWriter(store, actor="test")
    writer.write_run(run_id, {"team_refs": members, "subtask_refs": subtasks})
    writer.set_active_run(task_id, run_id)
    return task_id, run_id, members, subtasks


def set_requirements_revision(store: FileStore, task_id: str, value: int) -> None:
    StateWriter(store, actor="test").write_task(task_id, {"requirements_revision": value})


def write_workspace_file(store: FileStore, relative: str, content: str = "ok\n") -> Path:
    target = store.resolve_path(relative, write=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def make_candidate(**overrides: Any) -> Candidate:
    values: dict[str, Any] = {
        "task_id": "task_x",
        "run_id": "run_x",
        "run_state": "verifying",
        "attempt": 1,
        "plan_hash": "hash",
        "requirements_revision": 1,
        "deliverable_revision": 0,
        "workspace_ref": "ws",
        "workspace_path": None,
        "member_refs": (),
        "subtask_refs": (),
        "artifact_refs": (),
        "diff_ref": None,
        "session_refs": (),
        "check_records": (),
    }
    values.update(overrides)
    return Candidate(**values)


__all__ = [
    "PENDING_ACCEPTANCE",
    "create_member",
    "create_run",
    "create_subtask",
    "create_task",
    "make_candidate",
    "make_verifying_task",
    "set_requirements_revision",
    "write_workspace_file",
]
