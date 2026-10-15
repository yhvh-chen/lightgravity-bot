"""Frozen Task/Run/Member read endpoints and control actions (LG-012).

Covers the docs/08 §4.3 endpoints owned by this task:

* ``GET   /tasks``                 list (``phase``/``status``/``archived``)
* ``GET   /tasks/{task_id}``       detail incl. active Run/Subtask/Member
* ``PATCH /tasks/{task_id}``       title/scope/acceptance (optimistic revision)
* ``GET   /tasks/{task_id}/events`` persisted event read (``after_seq``/cursor)
* ``POST  /tasks/{task_id}/actions`` control envelope

Task creation and message routes are owned by LG-007 and mounted from its router
factory; this module does not duplicate them.  Full pause/cancel/accept
semantics are owned by LG-016/LG-009: unsupported actions return an honest
``not_ready`` with the owning task instead of faking a state transition.
"""

from __future__ import annotations

from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict

from ..contracts import ActionName, AppError, ErrorCode, TaskPhase, TaskStatus
from ..store import EntityNotFound, RevisionConflict, Versioned
from ..store.models import TaskSummary
from .context import ApiContext, get_context
from .eventbus import event_cursor, parse_stream_cursor


class _BodyStore(Protocol):
    """The concrete store accepts a Markdown ``body``; docs/08 §7 does not model it."""

    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
        body: str | None = None,
    ) -> Versioned: ...


class TaskUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    title: str | None = None
    objective: str | None = None
    scope: str | None = None
    acceptance_criteria: list[str] | None = None
    archived: bool | None = None


class TaskActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    request_id: str
    expected_revision: int | None = None
    target_run_id: str | None = None
    decision: str | None = None
    note: str | None = None
    # Additive accept/reject binding fields (docs/08 §4.3, §6.1).
    expected_requirements_revision: int | None = None
    expected_deliverable_revision: int | None = None


#: Actions not implemented here; the honest response names the owning task.
_ACTION_OWNER: dict[str, str] = {
    ActionName.RETRY.value: "LG-016",
    ActionName.ACCEPT.value: "LG-009",
    ActionName.REJECT.value: "LG-009",
}


def _summary(summary: TaskSummary) -> dict[str, Any]:
    return {
        "id": summary.id,
        "task_id": summary.id,
        "title": summary.title,
        "status": summary.status,
        "phase": summary.phase,
        "revision": summary.revision,
        "etag": f'"{summary.revision}"',
        "requirements_revision": summary.requirements_revision,
        "queue": {
            "state": summary.queue_state,
            "owner": summary.owner,
            "lease_expires_at": summary.lease_expires_at,
        },
        "archived": summary.archived,
    }


def _embedded(versioned: Versioned) -> dict[str, Any]:
    payload = dict(versioned.entity)
    payload["revision"] = versioned.revision
    payload["etag"] = versioned.etag
    payload["body"] = versioned.body
    return payload


def _safe_read(ctx: ApiContext, kind: str, entity_id: str) -> dict[str, Any] | None:
    try:
        return _embedded(ctx.store.read(kind, entity_id))
    except (EntityNotFound, AppError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


def _task_detail(ctx: ApiContext, task_id: str) -> dict[str, Any]:
    versioned = ctx.store.read("task", task_id)
    detail: dict[str, Any] = _embedded(versioned)
    detail["task_id"] = versioned.entity_id

    run: dict[str, Any] | None = None
    members: list[dict[str, Any]] = []
    subtasks: list[dict[str, Any]] = []
    active = versioned.entity.get("active_run")
    if isinstance(active, str) and active:
        run_versioned = _safe_read_versioned(ctx, "run", active)
        if run_versioned is None:
            run = {"id": active, "state": "missing"}
        else:
            run = _embedded(run_versioned)
            for ref in _string_list(run_versioned.entity.get("team_refs")):
                member = _safe_read(ctx, "member", ref)
                if member is not None:
                    members.append(member)
            for ref in _string_list(run_versioned.entity.get("subtask_refs")):
                subtask = _safe_read(ctx, "subtask", ref)
                if subtask is not None:
                    subtasks.append(subtask)
    detail["run"] = run
    detail["members"] = members
    detail["subtasks"] = subtasks
    return detail


def _safe_read_versioned(ctx: ApiContext, kind: str, entity_id: str) -> Versioned | None:
    try:
        return ctx.store.read(kind, entity_id)
    except (EntityNotFound, AppError):
        return None


def _coerce_phase(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return TaskPhase(value).value
    except ValueError as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            f"unknown task phase {value!r}",
            details={"phase": value},
        ) from exc


def _coerce_status(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return TaskStatus(value).value
    except ValueError as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            f"unknown task status {value!r}",
            details={"status": value},
        ) from exc


def _coerce_action(value: str) -> ActionName:
    try:
        return ActionName(value)
    except ValueError as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            f"unknown control action {value!r}",
            details={"action": value, "allowed": [item.value for item in ActionName]},
        ) from exc


def _render_task_body(
    objective: str, scope: str | None, acceptance: tuple[str, ...]
) -> str:
    lines = ["# Task", "", "## 目标", "", objective.strip(), ""]
    if scope and scope.strip():
        lines += ["## 范围", "", scope.strip(), ""]
    if acceptance:
        lines += ["## 验收条件", ""]
        lines += [f"- {item}" for item in acceptance]
        lines += [""]
    return "\n".join(lines)


def _parse_task_body(body: str) -> dict[str, Any]:
    objective_lines: list[str] = []
    scope_lines: list[str] = []
    acceptance: list[str] = []
    current: str | None = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        if current == "目标":
            objective_lines.append(line)
        elif current == "范围":
            scope_lines.append(line)
        elif current == "验收条件":
            stripped = line.strip()
            if stripped.startswith("- "):
                acceptance.append(stripped[2:].strip())
    scope_text = "\n".join(scope_lines).strip()
    return {
        "objective": "\n".join(objective_lines).strip(),
        "scope": scope_text or None,
        "acceptance": acceptance,
    }


def _spawn_rework_after_reject(
    ctx: ApiContext,
    task_id: str,
    payload: TaskActionRequest,
    decision: Any,
) -> dict[str, Any] | None:
    """Queue a fresh rework Run after a human reject (LG-017).

    The rejected candidate + evidence are kept (the prior Run stays on disk and
    ``last_run``); the Task keeps its id.  A new Run re-recruits and re-verifies.
    Returns the spawn outcome for the response, or ``None`` when the runtime has
    no rework spawner (the reject still stands; the Task stays ``repairing``).
    """

    coordinator = ctx.coordinator
    spawn_fn = getattr(coordinator, "spawn_repair_run", None)
    if not callable(spawn_fn):
        return None
    candidate_ref = getattr(decision, "candidate_ref", None)
    note = (payload.note or "").strip()
    findings = (
        (
            {
                "finding_id": "human-reject",
                "severity": "blocking",
                "summary": note or "user rejected the candidate",
                "evidence_ref": "",
                "rework_target": "deliverable",
                "candidate_ref": candidate_ref or "",
                "detail": "human acceptance decision",
            },
        )
        if note
        else ()
    )
    outcome = spawn_fn(
        task_id,
        prior_run_id=candidate_ref or "",
        findings=findings,
        request_id=payload.request_id,
    )
    return outcome.to_dict() if hasattr(outcome, "to_dict") else None


def build_task_router() -> APIRouter:
    router = APIRouter(tags=["tasks"])

    @router.get("/tasks")
    def list_tasks(
        ctx: Annotated[ApiContext, Depends(get_context)],
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        cursor: Annotated[str | None, Query()] = None,
        phase: Annotated[str | None, Query()] = None,
        status: Annotated[str | None, Query()] = None,
        archived: Annotated[bool | None, Query()] = None,
    ) -> dict[str, Any]:
        wanted_phase = _coerce_phase(phase)
        wanted_status = _coerce_status(status)
        summaries = sorted(ctx.store.list_tasks(), key=lambda item: item.id)
        if wanted_phase is not None:
            summaries = [item for item in summaries if item.phase == wanted_phase]
        if wanted_status is not None:
            summaries = [item for item in summaries if item.status == wanted_status]
        if archived is not None:
            summaries = [item for item in summaries if item.archived is archived]
        if cursor:
            summaries = [item for item in summaries if item.id > cursor]
        page = summaries[:limit]
        next_cursor = page[-1].id if len(summaries) > limit and page else None
        return {"items": [_summary(item) for item in page], "next_cursor": next_cursor}

    @router.get("/tasks/{task_id}")
    def get_task(
        task_id: str,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        detail = _task_detail(ctx, task_id)
        response.headers["ETag"] = str(detail["etag"])
        return detail

    @router.patch("/tasks/{task_id}")
    def update_task(
        task_id: str,
        payload: TaskUpdateRequest,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        current = ctx.store.read("task", task_id)
        if payload.expected_revision != current.revision:
            raise RevisionConflict(
                "task",
                task_id,
                expected=payload.expected_revision,
                actual=current.revision,
            )
        updates: dict[str, Any] = {}
        if payload.title is not None:
            updates["title"] = payload.title
        if payload.archived is not None:
            updates["archived"] = payload.archived

        requirements_changed = (
            payload.objective is not None
            or payload.scope is not None
            or payload.acceptance_criteria is not None
        )
        body: str | None = None
        if requirements_changed:
            parsed = _parse_task_body(current.body)
            objective = (
                payload.objective
                if payload.objective is not None
                else str(parsed["objective"])
            )
            scope = payload.scope if payload.scope is not None else parsed["scope"]
            acceptance = (
                tuple(payload.acceptance_criteria)
                if payload.acceptance_criteria is not None
                else tuple(str(item) for item in parsed["acceptance"])
            )
            body = _render_task_body(objective, scope, acceptance)
            acceptance_map = current.entity.get("acceptance")
            evidence_refs: Any = []
            if isinstance(acceptance_map, dict):
                evidence_refs = acceptance_map.get("evidence_refs", [])
            updates["requirements_revision"] = (
                int(current.entity.get("requirements_revision", 0)) + 1
            )
            updates["acceptance"] = {
                "status": "pending",
                "requirements_revision": None,
                "deliverable_revision": None,
                "evidence_refs": evidence_refs,
                "decided_at": None,
                "decision_ref": None,
                # Additive candidate binding is invalidated on a requirements change.
                "candidate_ref": None,
                "candidate_plan_hash": None,
                "check_records": [],
                "note": None,
            }
        if not updates:
            detail = _task_detail(ctx, task_id)
        else:
            cast(_BodyStore, ctx.store).write(
                "task",
                task_id,
                updates,
                expected_revision=payload.expected_revision,
                actor="api",
                body=body,
            )
            detail = _task_detail(ctx, task_id)
        response.headers["ETag"] = str(detail["etag"])
        return detail

    @router.get("/tasks/{task_id}/events")
    def read_task_events(
        task_id: str,
        ctx: Annotated[ApiContext, Depends(get_context)],
        after_seq: Annotated[int, Query(ge=0)] = 0,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    ) -> dict[str, Any]:
        ctx.store.read("task", task_id)  # 404 when the Task does not exist
        parsed = parse_stream_cursor(cursor)
        if parsed is not None:
            stream_id, seq = parsed
            if stream_id != task_id:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    "cursor stream does not match the requested Task",
                    details={"cursor_stream": stream_id, "task_id": task_id},
                )
            after_seq = seq
        records = ctx.store.read_events(task_id, after_seq=after_seq, limit=limit)
        items = [record.event for record in records]
        next_cursor = event_cursor(records[-1]) if len(records) == limit and records else None
        return {"items": items, "next_cursor": next_cursor}

    @router.post("/tasks/{task_id}/actions")
    async def task_action(
        task_id: str,
        payload: TaskActionRequest,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        action = _coerce_action(payload.action)
        current = ctx.store.read("task", task_id)
        # Idempotent replay is checked before the revision/target guards so a
        # duplicate accept/reject acknowledgement returns the first full result
        # even though acceptance cleared ``active_run`` and bumped the revision.
        # ``replay_decision`` only matches the same Task, same action and the
        # originally bound candidate, so a new request or a different target
        # still falls through to the strict guards below.
        verification = ctx.verification
        if verification is not None and action in {ActionName.ACCEPT, ActionName.REJECT}:
            replayed = verification.replay_decision(
                task_id,
                action.value,
                payload.request_id,
                target_run_id=payload.target_run_id,
            )
            if replayed is not None:
                response.headers["ETag"] = f'"{ctx.store.read("task", task_id).revision}"'
                replayed_payload = replayed.to_dict()
                if action is ActionName.REJECT:
                    # A duplicate reject must be byte-for-byte idempotent with the
                    # first response, including the LG-017 rework outcome.  The
                    # spawner collapses a duplicate request, so re-deriving the
                    # outcome here is safe and writes no second Run.
                    spawn = _spawn_rework_after_reject(ctx, task_id, payload, replayed)
                    if spawn is not None:
                        replayed_payload["rework"] = spawn
                return replayed_payload
        if (
            payload.expected_revision is not None
            and payload.expected_revision != current.revision
        ):
            raise RevisionConflict(
                "task",
                task_id,
                expected=payload.expected_revision,
                actual=current.revision,
            )
        if payload.target_run_id is not None:
            active = current.entity.get("active_run")
            if active != payload.target_run_id:
                raise AppError(
                    ErrorCode.ILLEGAL_TRANSITION,
                    "target_run_id does not match the Task's active Run",
                    details={"active_run": active, "target_run_id": payload.target_run_id},
                )
        if action in {
            ActionName.PAUSE,
            ActionName.CANCEL,
            ActionName.RESUME,
            ActionName.RETRY,
            ActionName.REOPEN,
            ActionName.ENQUEUE,
        }:
            result = await ctx.coordinator.request_control(
                task_id, action.value, request_id=payload.request_id
            )
            state = result.data.get("state")
            confirmed = bool(result.data.get("confirmed", False))
            if confirmed:
                response.headers["ETag"] = f'"{ctx.store.read("task", task_id).revision}"'
                return {
                    "action": action.value,
                    "state": "confirmed",
                    "confirmed": True,
                    "task_id": task_id,
                    "request_id": payload.request_id,
                    "phase": result.data.get("phase"),
                    "run_id": result.data.get("run_id"),
                }
            if state == "unconfirmed":
                raise AppError(
                    ErrorCode.CANCELLATION_UNCONFIRMED,
                    f"Task {task_id} {action.value} was not confirmed stopped",
                    details={
                        "action": action.value,
                        "state": state,
                        "confirmed": False,
                        "task_id": task_id,
                        "request_id": payload.request_id,
                        "phase": result.data.get("phase"),
                        "reason": result.data.get("reason"),
                    },
                )
            raise AppError(
                ErrorCode.NOT_READY,
                f"Task {task_id} cannot {action.value} in its current phase",
                details={
                    "action": action.value,
                    "state": state,
                    "phase": result.data.get("phase"),
                    "reason": result.data.get("reason"),
                    "task_id": task_id,
                    "request_id": payload.request_id,
                },
            )
        if action in {ActionName.ACCEPT, ActionName.REJECT}:
            if verification is None:
                raise AppError(
                    ErrorCode.NOT_READY,
                    f"verification service is not wired for {action.value!r}",
                    details={
                        "action": action.value,
                        "owner": "LG-009",
                        "request_id": payload.request_id,
                    },
                )
            decision = verification.decide(
                task_id,
                action.value,
                request_id=payload.request_id,
                expected_revision=payload.expected_revision,
                expected_requirements_revision=payload.expected_requirements_revision,
                expected_deliverable_revision=payload.expected_deliverable_revision,
                target_run_id=payload.target_run_id,
                note=payload.note,
            )
            rework_spawn: dict[str, Any] | None = None
            if action is ActionName.REJECT:
                # A human reject must open a fresh rework Run that re-recruits
                # and re-verifies, while keeping the original Task ID and the
                # rejected candidate/evidence (docs/08 §6.1; LG-017).  The
                # decision already moved the Task to ``repairing`` with
                # ``active_run=None``; the spawner queues the new Run.
                rework_spawn = _spawn_rework_after_reject(ctx, task_id, payload, decision)
            response.headers["ETag"] = f'"{ctx.store.read("task", task_id).revision}"'
            decision_payload = decision.to_dict()
            if rework_spawn is not None:
                decision_payload["rework"] = rework_spawn
            return decision_payload
        owner = _ACTION_OWNER.get(action.value, "LG-016")
        raise AppError(
            ErrorCode.NOT_READY,
            f"control action {action.value!r} is not implemented in this version",
            details={"action": action.value, "owner": owner, "request_id": payload.request_id},
        )

    return router


__all__ = ["build_task_router", "TaskUpdateRequest", "TaskActionRequest"]
