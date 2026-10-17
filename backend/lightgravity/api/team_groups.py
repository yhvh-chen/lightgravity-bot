"""Read-only Team grouping projection (LG-126, docs/08 §19.2 / R2 §19.5).

This router is deliberately **derived**: it reads the persisted Task/Run/
Member/Subtask facts and returns them grouped by Task.  It never writes a file,
opens a Run, recruits a member or calls a model.  Release/History is not stored
here either; the flags are computed from the authoritative stop/cleanup fields
so there is no parallel status source.

The shared integration owner mounts this router in ``api/app.py`` and advertises
``capabilities.team_groups=true`` only after the mount is real.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from ..contracts import AppError, ErrorCode, EventType, TaskPhase
from ..store import EntityNotFound, Store
from ..store.ids import id_matches_kind
from .access import require_access
from .context import ApiContext, get_context

_ALLOWED_VIEWS = frozenset({"all", "active", "history"})
_HISTORY_PHASES = frozenset(
    {
        TaskPhase.AWAITING_ACCEPTANCE.value,
        TaskPhase.COMPLETED.value,
        TaskPhase.FAILED.value,
        TaskPhase.CANCELLED.value,
    }
)
_TERMINAL_MEMBER_STATES = frozenset({"released", "failed"})


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _queue_projection(task: dict[str, Any]) -> dict[str, Any]:
    queue = _mapping(task.get("queue"))
    return {
        "state": str(queue.get("state", "not_queued")),
        "order": queue.get("order"),
        "queued_at": queue.get("queued_at"),
        "owner": queue.get("owner"),
        "waiting_reason": queue.get("waiting_reason"),
    }


def _run_projection(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(run.get("id", "")),
        "state": str(run.get("state", "")),
        "attempt": run.get("attempt"),
        "plan_source": run.get("plan_source"),
        "plan_hash": run.get("plan_hash"),
        "team_refs": _string_list(run.get("team_refs")),
        "subtask_refs": _string_list(run.get("subtask_refs")),
        # Raw stop/cleanup facts for the R2 Released/History mapping.  The
        # frontend derives labels; this endpoint stores nothing new.
        "session_refs": _string_list(run.get("session_refs")),
        "cleanup": _mapping(run.get("cleanup")),
        "reviewer_cleanup": (
            _mapping(run.get("reviewer_cleanup"))
            if isinstance(run.get("reviewer_cleanup"), dict)
            else None
        ),
        "waiting_reason": run.get("waiting_reason"),
        "ended_at": run.get("ended_at"),
        "fail_reason": run.get("fail_reason"),
    }


def _subtask_projection(subtask: dict[str, Any]) -> dict[str, Any]:
    acceptance = _mapping(subtask.get("acceptance"))
    return {
        "id": str(subtask.get("id", "")),
        "key": subtask.get("key"),
        "capability": subtask.get("capability"),
        "state": str(subtask.get("state", "")),
        "depends_on": _string_list(subtask.get("depends_on")),
        "blocked_by": _string_list(subtask.get("blocked_by")),
        "assignee_member_ref": subtask.get("assignee_member_ref"),
        "waiting_reason": subtask.get("waiting_reason"),
        "acceptance": {"status": acceptance.get("status", "pending")},
        "fail_reason": subtask.get("fail_reason"),
    }


def _member_projection(member: dict[str, Any], subtasks: list[dict[str, Any]]) -> dict[str, Any]:
    member_id = str(member.get("id", ""))
    assigned = [
        _subtask_projection(subtask)
        for subtask in subtasks
        if subtask.get("assignee_member_ref") == member_id
    ]
    declared = _string_list(member.get("assigned_subtask_refs"))
    return {
        "id": member_id,
        "run_ref": member.get("run_ref"),
        "role_ref": member.get("role_ref"),
        "role_category": member.get("role_category"),
        "state": str(member.get("state", "")),
        "template_version": member.get("template_version"),
        "connection_ref": member.get("connection_ref"),
        "skill_refs": _string_list(member.get("skill_refs")),
        "capabilities": _string_list(member.get("capabilities")),
        "selection_reason": member.get("selection_reason"),
        "assigned_subtask_refs": (
            declared
            if declared
            else [item["id"] for item in assigned]
        ),
        "assigned_subtasks": assigned,
        "config_hash": member.get("config_hash"),
        "fail_reason": member.get("fail_reason"),
    }


def _run_ids(store: Store, task_id: str, task: dict[str, Any]) -> list[str]:
    """Discover every Run attributed to this Task without trusting directories."""

    ordered: list[str] = []

    def add(run_id: Any) -> None:
        if isinstance(run_id, str) and run_id and run_id not in ordered:
            ordered.append(run_id)

    add(task.get("active_run"))
    add(task.get("last_run"))
    after_seq = 0
    while True:
        events = store.read_events(task_id, after_seq=after_seq, limit=500)
        if not events:
            break
        for record in events:
            event = record.event
            payload = event.get("payload")
            if record.type != EventType.RUN_CREATED or event.get("task_ref") != task_id:
                continue
            run_id = event.get("run_ref")
            if not isinstance(run_id, str) or not run_id:
                continue
            if isinstance(payload, dict) and payload.get("run_id") not in (None, run_id):
                continue
            add(run_id)
        next_seq = events[-1].seq
        if next_seq <= after_seq:
            break
        after_seq = next_seq
    return ordered


def _read_runs(store: Store, task_id: str, task: dict[str, Any]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run_id in _run_ids(store, task_id, task):
        try:
            run = dict(store.read("run", run_id).entity)
        except (EntityNotFound, AppError):
            continue
        if run.get("task_ref") != task_id:
            continue
        run.setdefault("id", run_id)
        runs.append(run)

    def key(item: dict[str, Any]) -> tuple[int, str]:
        attempt = item.get("attempt")
        return (
            attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else 0,
            str(item.get("id", "")),
        )

    return sorted(runs, key=key)


def _current_run(
    task: dict[str, Any], runs: list[dict[str, Any]]
) -> dict[str, Any] | None:
    by_id = {str(run.get("id", "")): run for run in runs}
    for pointer in (task.get("active_run"), task.get("last_run")):
        if isinstance(pointer, str) and pointer in by_id:
            return by_id[pointer]
    return runs[-1] if runs else None


def _members_and_subtasks(
    store: Store, run: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if run is None:
        return [], []
    subtasks: list[dict[str, Any]] = []
    for ref in _string_list(run.get("subtask_refs")):
        try:
            subtask = dict(store.read("subtask", ref).entity)
        except (EntityNotFound, AppError):
            continue
        subtask.setdefault("id", ref)
        subtasks.append(subtask)
    members: list[dict[str, Any]] = []
    for ref in _string_list(run.get("team_refs")):
        try:
            member = dict(store.read("member", ref).entity)
        except (EntityNotFound, AppError):
            continue
        member.setdefault("id", ref)
        members.append(_member_projection(member, subtasks))
    return members, [_subtask_projection(item) for item in subtasks]


def _released(
    task: dict[str, Any],
    run: dict[str, Any] | None,
    members: list[dict[str, Any]],
    *,
    never_started: bool = False,
) -> bool:
    """R2 authoritative release derivation (no member-state-only shortcut)."""

    if run is None:
        queue = _mapping(task.get("queue"))
        # A cancelled, never-started Task has no sessions to close. Do not
        # confuse absence of a resolved Run with proof of no execution history:
        # unresolved pointers/events or an already-started status remain held.
        return bool(
            never_started
            and task.get("phase") == TaskPhase.CANCELLED.value
            and task.get("status") == "todo"
            and not members
            and queue.get("state") == "not_queued"
            and queue.get("owner") is None
        )
    phase = str(task.get("phase", ""))
    if phase == TaskPhase.RECOVERY_REQUIRED.value:
        # Recovery-path cleanup parks/releases the slot; it is not proof that
        # every worker/reviewer session was authoritatively stopped.
        return False
    session_refs = _string_list(run.get("session_refs"))
    cleanup = _mapping(run.get("cleanup"))
    cleanup_status = cleanup.get("status")
    worker_stopped = (
        not session_refs
        or cleanup_status == "done"
        or phase in {TaskPhase.AWAITING_ACCEPTANCE.value, TaskPhase.COMPLETED.value}
    )
    reviewer_cleanup = run.get("reviewer_cleanup")
    reviewer_stopped = (
        not isinstance(reviewer_cleanup, dict)
        or not reviewer_cleanup
        or reviewer_cleanup.get("confirmed") is True
    )
    team_refs = set(_string_list(run.get("team_refs")))
    member_ids = {str(member.get("id", "")) for member in members}
    members_terminal = team_refs.issubset(member_ids) and all(
        str(member.get("state", "")) in _TERMINAL_MEMBER_STATES
        for member in members
    )
    queue = _mapping(task.get("queue"))
    slot_free = str(queue.get("state", "not_queued")) == "not_queued"
    return bool(worker_stopped and reviewer_stopped and members_terminal and slot_free)


def build_team_group(store: Store, task_versioned: Any) -> dict[str, Any]:
    """Pure read-only projection for one Task (also used by tests/diagnostics)."""

    task = dict(task_versioned.entity)
    task_id = str(task_versioned.entity_id)
    runs = _read_runs(store, task_id, task)
    current = _current_run(task, runs)
    active_id = task.get("active_run")
    active_run = None
    for run in runs:
        if str(run.get("id", "")) == active_id:
            active_run = _run_projection(run)
            break
    members, subtasks = _members_and_subtasks(store, current)
    return {
        "task": {
            "id": task_id,
            "title": task.get("title"),
            "status": task.get("status"),
            "phase": task.get("phase"),
            "revision": task_versioned.revision,
            "requirements_revision": task.get("requirements_revision"),
            "deliverable_revision": task.get("deliverable_revision"),
            "archived": bool(task.get("archived", False)),
            "active_run": active_id,
            "last_run": task.get("last_run"),
            "queue": _queue_projection(task),
        },
        "active_run": active_run,
        "runs": [_run_projection(run) for run in runs],
        "members": members,
        "subtasks": subtasks,
        "_released": _released(
            task, current, members,
            never_started=current is None and not _run_ids(store, task_id, task),
        ),
    }


def _is_history(group: dict[str, Any]) -> bool:
    return bool(group["_released"]) and str(group["task"].get("phase", "")) in _HISTORY_PHASES


def _strip_internal(group: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in group.items() if not key.startswith("_")}


def _parse_cursor(cursor: str | None) -> str | None:
    if cursor is None or not cursor.strip():
        return None
    prefix, separator, value = cursor.partition(":")
    if prefix != "v1" or not separator or not id_matches_kind("task", value):
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "invalid team groups cursor",
            details={"cursor": cursor},
        )
    return value


def _validate_view(view: str) -> str:
    normalized = view.strip().lower()
    if normalized not in _ALLOWED_VIEWS:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            f"invalid team groups view {view!r}",
            details={"view": view, "allowed": sorted(_ALLOWED_VIEWS)},
        )
    return normalized


def build_team_groups_router() -> APIRouter:
    router = APIRouter(tags=["team"], dependencies=[Depends(require_access)])

    @router.get("/team/groups")
    def list_team_groups(
        ctx: Annotated[ApiContext, Depends(get_context)],
        view: Annotated[str, Query()] = "all",
        task_ref: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        wanted_view = _validate_view(view)
        after = _parse_cursor(cursor)
        if task_ref is not None:
            if not id_matches_kind("task", task_ref):
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "task not found",
                    details={"task_ref": task_ref},
                )
            try:
                tasks = [ctx.store.read("task", task_ref)]
            except (EntityNotFound, AppError) as exc:
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "task not found",
                    details={"task_ref": task_ref},
                ) from exc
        else:
            tasks = sorted(
                (ctx.store.read("task", summary.id) for summary in ctx.store.list_tasks()),
                key=lambda item: item.entity_id,
            )
        if after is not None:
            tasks = [task for task in tasks if task.entity_id > after]
        matching: list[dict[str, Any]] = []
        for task_versioned in tasks:
            group = build_team_group(ctx.store, task_versioned)
            if wanted_view == "active" and _is_history(group):
                continue
            if wanted_view == "history" and not _is_history(group):
                continue
            matching.append(_strip_internal(group))
        page = matching[:limit]
        # ``next_cursor`` is the last returned persisted Task id, so it is
        # stable even when view filtering skipped earlier Tasks.
        next_cursor = (
            f"v1:{page[-1]['task']['id']}"
            if len(matching) > limit and page
            else None
        )
        return {"items": page, "next_cursor": next_cursor}

    return router


__all__ = ["build_team_group", "build_team_groups_router"]
