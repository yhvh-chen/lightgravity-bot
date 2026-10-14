"""Frozen enums for the v1 contract (docs/08-interface-contract.md §4-§6).

Values are the wire representation: lower snake_case strings, with the
documented exception of ``TaskStatus`` which uses the ``todo`` / ``in-progress``
/ ``done`` spelling fixed by docs/02 and §6.1.
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in-progress"
    DONE = "done"


class TaskPhase(StrEnum):
    INTAKE = "intake"
    QUEUED = "queued"
    WAITING_DEPENDENCIES = "waiting_dependencies"
    PLANNING = "planning"
    RECRUITING = "recruiting"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    WAITING_USER = "waiting_user"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class QueueState(StrEnum):
    NOT_QUEUED = "not_queued"
    QUEUED = "queued"
    CLAIMED = "claimed"


class AcceptanceStatus(StrEnum):
    PENDING = "pending"
    AWAITING = "awaiting"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RunState(StrEnum):
    PLANNING = "planning"
    RECRUITING = "recruiting"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    COMPLETED = "completed"
    WAITING_USER = "waiting_user"
    PAUSING = "pausing"
    PAUSED = "paused"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class RunCleanupStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class SubtaskState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    PASSED = "passed"
    REPAIRING = "repairing"
    WAITING_USER = "waiting_user"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubtaskAcceptanceStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class MemberState(StrEnum):
    RECRUITING = "recruiting"
    READY = "ready"
    RUNNING = "running"
    RELEASED = "released"
    WAITING_USER = "waiting_user"
    FAILED = "failed"


class ActionName(StrEnum):
    ENQUEUE = "enqueue"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"
    ACCEPT = "accept"
    REJECT = "reject"
    REOPEN = "reopen"


class ActionState(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    PATH_OUTSIDE_WORKSPACE = "path_outside_workspace"
    NOT_FOUND = "not_found"
    REVISION_CONFLICT = "revision_conflict"
    LOCK_CONFLICT = "lock_conflict"
    NOT_READY = "not_ready"
    ILLEGAL_TRANSITION = "illegal_transition"
    CANCELLATION_UNCONFIRMED = "cancellation_unconfirmed"
    ACCEPTANCE_STALE = "acceptance_stale"
    CONFIG_INVALID = "config_invalid"
    REFERENCE_INVALID = "reference_invalid"
    VALIDATION_FAILED = "validation_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    INTERNAL_ERROR = "internal_error"


class EventType(StrEnum):
    """Minimal frozen event set (docs/08 §5.1)."""

    TASK_CREATED = "task.created"
    TASK_PHASE_CHANGED = "task.phase_changed"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_REQUIREMENTS_CHANGED = "task.requirements_changed"
    QUEUE_ENQUEUED = "queue.enqueued"
    QUEUE_CLAIMED = "queue.claimed"
    QUEUE_RELEASED = "queue.released"
    RUN_CREATED = "run.created"
    RUN_STATE_CHANGED = "run.state_changed"
    SUBTASK_STATE_CHANGED = "subtask.state_changed"
    MEMBER_RECRUITED = "member.recruited"
    MEMBER_STATE_CHANGED = "member.state_changed"
    MEMBER_RELEASED = "member.released"
    MESSAGE_APPENDED = "message.appended"
    DECISION_REQUESTED = "decision.requested"
    DECISION_RESOLVED = "decision.resolved"
    ARTIFACT_PRODUCED = "artifact.produced"
    CLEANUP_UPDATED = "cleanup.updated"
    NOTIFICATION_CREATED = "notification.created"
    ERROR_RECORDED = "error.recorded"


__all__ = [
    "TaskStatus",
    "TaskPhase",
    "QueueState",
    "AcceptanceStatus",
    "RunState",
    "RunCleanupStatus",
    "SubtaskState",
    "SubtaskAcceptanceStatus",
    "MemberState",
    "ActionName",
    "ActionState",
    "ErrorCode",
    "EventType",
]
