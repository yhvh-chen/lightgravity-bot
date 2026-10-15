"""Entity kinds, static validation and Task state-machine rules (LG-004).

Validation is deliberately data-driven and side-effect free so the same rules
are used by ``read``, ``write`` and ``rebuild_index``.  Unknown frontmatter
fields are preserved by the write path but are never interpreted here.
"""

from __future__ import annotations

from typing import Any

from lightgravity.contracts import (
    SCHEMA_NAMESPACE,
    AcceptanceStatus,
    MemberState,
    QueueState,
    RunCleanupStatus,
    RunState,
    SubtaskAcceptanceStatus,
    SubtaskState,
    TaskPhase,
    TaskStatus,
)
from lightgravity.contracts.enums import EventType

from .models import Diagnostic

#: Runtime/state kinds and resource kinds supported by the v1 store.
STATE_KINDS = ("task", "run", "subtask", "member")
RESOURCE_KINDS = (
    "agent",
    "connection",
    "conversation",
    "hook",
    "mcp",
    "tool",
    "trigger",
    "skill",
    "settings",
)
ALL_KINDS = STATE_KINDS + RESOURCE_KINDS

#: Directory name (under ``resources/``) for each resource kind.
RESOURCE_DIRS: dict[str, str] = {
    "agent": "agents",
    "connection": "connections",
    "conversation": "conversations",
    "hook": "hooks",
    "mcp": "mcp",
    "tool": "tools",
    "trigger": "triggers",
    "skill": "skills",
}

STATE_FIELD: dict[str, str | None] = {
    "task": "phase",
    "run": "state",
    "subtask": "state",
    "member": "state",
    "agent": None,
    "connection": None,
    "conversation": None,
    "hook": None,
    "mcp": None,
    "tool": None,
    "trigger": None,
    "skill": None,
    "settings": None,
}

#: Legal ``status + phase`` combinations (docs/08 §6.1).
TASK_STATUS_PHASES: dict[TaskStatus, frozenset[TaskPhase]] = {
    TaskStatus.TODO: frozenset(
        {TaskPhase.INTAKE, TaskPhase.QUEUED, TaskPhase.WAITING_DEPENDENCIES, TaskPhase.CANCELLED}
    ),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskPhase.PLANNING,
            TaskPhase.RECRUITING,
            TaskPhase.EXECUTING,
            TaskPhase.VERIFYING,
            TaskPhase.REPAIRING,
            TaskPhase.WAITING_USER,
            TaskPhase.PAUSING,
            TaskPhase.PAUSED,
            TaskPhase.CANCELLING,
            TaskPhase.AWAITING_ACCEPTANCE,
            TaskPhase.RECOVERY_REQUIRED,
            TaskPhase.FAILED,
            TaskPhase.CANCELLED,
        }
    ),
    TaskStatus.DONE: frozenset({TaskPhase.COMPLETED}),
}

#: Allowed Task phase transitions (docs/08 §6.1).
TASK_PHASE_TRANSITIONS: dict[TaskPhase, frozenset[TaskPhase]] = {
    TaskPhase.INTAKE: frozenset(
        {TaskPhase.QUEUED, TaskPhase.WAITING_DEPENDENCIES, TaskPhase.CANCELLED}
    ),
    TaskPhase.QUEUED: frozenset(
        {TaskPhase.PLANNING, TaskPhase.WAITING_DEPENDENCIES, TaskPhase.CANCELLED}
    ),
    TaskPhase.WAITING_DEPENDENCIES: frozenset({TaskPhase.QUEUED, TaskPhase.CANCELLED}),
    TaskPhase.PLANNING: frozenset(
        {TaskPhase.RECRUITING, TaskPhase.WAITING_USER, TaskPhase.FAILED, TaskPhase.CANCELLING}
    ),
    TaskPhase.RECRUITING: frozenset(
        {TaskPhase.EXECUTING, TaskPhase.WAITING_USER, TaskPhase.FAILED, TaskPhase.CANCELLING}
    ),
    TaskPhase.EXECUTING: frozenset(
        {
            TaskPhase.VERIFYING,
            TaskPhase.WAITING_USER,
            TaskPhase.PAUSING,
            TaskPhase.CANCELLING,
            TaskPhase.FAILED,
            TaskPhase.RECOVERY_REQUIRED,
        }
    ),
    TaskPhase.VERIFYING: frozenset(
        {
            TaskPhase.REPAIRING,
            TaskPhase.AWAITING_ACCEPTANCE,
            TaskPhase.WAITING_USER,
            TaskPhase.FAILED,
            TaskPhase.CANCELLING,
            # LG-022 R1 (contract 1.8.0): a restart during the independent
            # review has unknown side effects and must be able to park for a
            # human decision rather than stay artificially ``verifying``.
            TaskPhase.RECOVERY_REQUIRED,
        }
    ),
    TaskPhase.REPAIRING: frozenset(
        {
            TaskPhase.EXECUTING,
            TaskPhase.WAITING_USER,
            TaskPhase.FAILED,
            TaskPhase.CANCELLING,
            # LG-022 R1 (contract 1.8.0): same restart-safety reason as above.
            TaskPhase.RECOVERY_REQUIRED,
        }
    ),
    TaskPhase.WAITING_USER: frozenset(
        {
            TaskPhase.QUEUED,
            TaskPhase.PLANNING,
            TaskPhase.PAUSED,
            TaskPhase.CANCELLING,
            TaskPhase.FAILED,
        }
    ),
    TaskPhase.PAUSING: frozenset(
        {TaskPhase.PAUSED, TaskPhase.CANCELLING, TaskPhase.FAILED}
    ),
    TaskPhase.PAUSED: frozenset(
        {TaskPhase.QUEUED, TaskPhase.PLANNING, TaskPhase.CANCELLING}
    ),
    TaskPhase.CANCELLING: frozenset({TaskPhase.CANCELLED}),
    TaskPhase.AWAITING_ACCEPTANCE: frozenset(
        {TaskPhase.COMPLETED, TaskPhase.REPAIRING, TaskPhase.CANCELLED}
    ),
    TaskPhase.RECOVERY_REQUIRED: frozenset(
        {TaskPhase.PLANNING, TaskPhase.FAILED, TaskPhase.CANCELLED}
    ),
    TaskPhase.FAILED: frozenset({TaskPhase.QUEUED, TaskPhase.CANCELLED}),
    TaskPhase.CANCELLED: frozenset({TaskPhase.QUEUED}),
    TaskPhase.COMPLETED: frozenset({TaskPhase.QUEUED, TaskPhase.PLANNING}),
}


def _diag(code: str, message: str, location: str, level: str = "error", **detail: Any) -> Diagnostic:
    return Diagnostic(code=code, message=message, level=level, location=location, detail=detail)


def _coerce_enum(enum_type: type[Any], value: Any) -> Any | None:
    try:
        return enum_type(value)
    except ValueError:
        return None


def _validate_enum_field(
    data: dict[str, Any], field: str, enum_type: type[Any], kind: str, diagnostics: list[Diagnostic]
) -> Any | None:
    if field not in data:
        diagnostics.append(_diag(f"{field}_missing", f"missing {field}", f"{kind}.{field}"))
        return None
    coerced = _coerce_enum(enum_type, data[field])
    if coerced is None:
        diagnostics.append(
            _diag(
                f"{field}_invalid",
                f"{field}={data[field]!r} is not a supported {kind} {field}",
                f"{kind}.{field}",
            )
        )
    return coerced


def _validate_revision(data: dict[str, Any], kind: str, diagnostics: list[Diagnostic]) -> None:
    revision = data.get("revision")
    if revision is None:
        diagnostics.append(_diag("revision_missing", "missing revision", f"{kind}.revision"))
    elif isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        diagnostics.append(
            _diag("revision_invalid", f"revision={revision!r} must be an int >= 0", f"{kind}.revision")
        )


def _validate_int(
    data: dict[str, Any], field: str, kind: str, diagnostics: list[Diagnostic], *, minimum: int = 0
) -> None:
    value = data.get(field)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        diagnostics.append(
            _diag(
                f"{field}_invalid",
                f"{field}={value!r} must be an int >= {minimum}",
                f"{kind}.{field}",
            )
        )


def validate_task_static(data: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    status = _validate_enum_field(data, "status", TaskStatus, "task", diagnostics)
    phase = _validate_enum_field(data, "phase", TaskPhase, "task", diagnostics)
    if status is not None and phase is not None:
        allowed = TASK_STATUS_PHASES.get(status, frozenset())
        if phase not in allowed:
            diagnostics.append(
                _diag(
                    "illegal_status_phase",
                    f"status={status.value} cannot combine with phase={phase.value}",
                    "task.status+phase",
                    status=status.value,
                    phase=phase.value,
                )
            )
    if "queue" in data:
        queue = data["queue"]
        if not isinstance(queue, dict):
            diagnostics.append(_diag("queue_invalid", "queue must be a mapping", "task.queue"))
        else:
            _validate_enum_field(queue, "state", QueueState, "task.queue", diagnostics)
            _validate_int(queue, "order", "task.queue", diagnostics)
    else:
        diagnostics.append(_diag("queue_missing", "missing queue mapping", "task.queue"))

    if "acceptance" in data:
        acceptance = data["acceptance"]
        if not isinstance(acceptance, dict):
            diagnostics.append(
                _diag("acceptance_invalid", "acceptance must be a mapping", "task.acceptance")
            )
        else:
            _validate_enum_field(
                acceptance, "status", AcceptanceStatus, "task.acceptance", diagnostics
            )
    else:
        diagnostics.append(
            _diag("acceptance_missing", "missing acceptance mapping", "task.acceptance")
        )

    _validate_int(data, "requirements_revision", "task", diagnostics, minimum=0)
    _validate_int(data, "deliverable_revision", "task", diagnostics, minimum=0)
    if "archived" in data and not isinstance(data["archived"], bool):
        diagnostics.append(
            _diag("archived_invalid", "archived must be a boolean", "task.archived")
        )
    return diagnostics


def validate_run_static(data: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    _validate_enum_field(data, "state", RunState, "run", diagnostics)
    if "cleanup" in data:
        cleanup = data["cleanup"]
        if not isinstance(cleanup, dict):
            diagnostics.append(_diag("cleanup_invalid", "cleanup must be a mapping", "run.cleanup"))
        else:
            _validate_enum_field(cleanup, "status", RunCleanupStatus, "run.cleanup", diagnostics)
    return diagnostics


def validate_subtask_static(data: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    _validate_enum_field(data, "state", SubtaskState, "subtask", diagnostics)
    if "acceptance" in data:
        acceptance = data["acceptance"]
        if not isinstance(acceptance, dict):
            diagnostics.append(
                _diag("acceptance_invalid", "acceptance must be a mapping", "subtask.acceptance")
            )
        else:
            _validate_enum_field(
                acceptance, "status", SubtaskAcceptanceStatus, "subtask.acceptance", diagnostics
            )
    return diagnostics


def validate_member_static(data: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    _validate_enum_field(data, "state", MemberState, "member", diagnostics)
    return diagnostics


def validate_resource_static(data: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if "enabled" in data and not isinstance(data["enabled"], bool):
        diagnostics.append(
            _diag("enabled_invalid", "enabled must be a boolean", "resource.enabled")
        )
    return diagnostics


def validate_entity(kind: str, data: Any, *, source: str = "<memory>") -> list[Diagnostic]:
    """Validate a parsed frontmatter mapping for ``kind``."""

    if not isinstance(data, dict):
        return [_diag("frontmatter_not_mapping", "frontmatter must be a mapping", source)]

    diagnostics: list[Diagnostic] = []
    location = f"{source}::{kind}"

    if data.get("schema") != SCHEMA_NAMESPACE:
        diagnostics.append(
            _diag(
                "schema_unsupported",
                f"schema must be {SCHEMA_NAMESPACE!r}",
                f"{location}.schema",
                actual=data.get("schema"),
            )
        )
    if kind not in ALL_KINDS:
        diagnostics.append(_diag("kind_unsupported", f"unsupported kind {kind!r}", f"{location}.kind"))
        return diagnostics
    if data.get("kind") != kind:
        diagnostics.append(
            _diag(
                "kind_mismatch",
                f"kind field must match storage kind {kind!r}",
                f"{location}.kind",
                actual=data.get("kind"),
            )
        )

    entity_id = data.get("id")
    if entity_id is None:
        diagnostics.append(_diag("id_missing", "missing id", f"{location}.id"))
    else:
        from .ids import id_matches_kind

        if not id_matches_kind(kind, entity_id):
            diagnostics.append(
                _diag("id_invalid", f"id {entity_id!r} does not match {kind} id rules", f"{location}.id")
            )

    _validate_revision(data, kind, diagnostics)

    if kind == "task":
        diagnostics.extend(validate_task_static(data))
    elif kind == "run":
        diagnostics.extend(validate_run_static(data))
    elif kind == "subtask":
        diagnostics.extend(validate_subtask_static(data))
    elif kind == "member":
        diagnostics.extend(validate_member_static(data))
    else:
        diagnostics.extend(validate_resource_static(data))
    return [d for d in diagnostics]


def validate_transition(kind: str, old: dict[str, Any], new: dict[str, Any]) -> list[Diagnostic]:
    """Validate state-change rules between two already-static-valid entities."""

    if kind != "task":
        return []
    diagnostics: list[Diagnostic] = []
    old_phase = _coerce_enum(TaskPhase, old.get("phase"))
    new_phase = _coerce_enum(TaskPhase, new.get("phase"))
    if old_phase is None or new_phase is None or old_phase == new_phase:
        return diagnostics
    allowed = TASK_PHASE_TRANSITIONS.get(old_phase, frozenset())
    if new_phase not in allowed:
        diagnostics.append(
            _diag(
                "illegal_transition",
                f"task phase {old_phase.value} -> {new_phase.value} is not allowed",
                "task.phase",
                level="error",
                **{"from": old_phase.value, "to": new_phase.value},
            )
        )
    return diagnostics


def event_type_supported(value: Any) -> bool:
    return _coerce_enum(EventType, value) is not None


__all__ = [
    "STATE_KINDS",
    "RESOURCE_KINDS",
    "ALL_KINDS",
    "RESOURCE_DIRS",
    "STATE_FIELD",
    "TASK_STATUS_PHASES",
    "TASK_PHASE_TRANSITIONS",
    "validate_entity",
    "validate_transition",
    "event_type_supported",
]
