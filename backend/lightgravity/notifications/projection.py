"""Derive notifications from durable Task event streams (LG-019).

This module is deliberately *read-only*: it scans the append-only ``events/*``
JSONL already written by the coordinator/verifier (event-first, then broadcast;
docs/08 §4.4) and produces the notification set.  It never writes control state
and does not require a shared hook inside ``coordinator/service.py`` or
``verify/**`` — the durable event stream is the integration seam.

Mapping (docs/04 §8: 完成/失败/预算停止/等待用户/待验收 generate a persistent
notification):

* ``task.phase_changed`` → ``to`` in {waiting_user, awaiting_acceptance,
  recovery_required, failed} emits the matching kind.  ``awaiting_acceptance``
  also carries the candidate/version binding from the preceding
  ``decision.requested`` payload when present.
* ``decision.requested`` alone (e.g. a manual verify) emits
  ``task.awaiting_acceptance`` when no phase event already covers it.
* ``error.recorded`` with ``mode=worker``/``verify`` is folded into the failed
  notification for the same Run rather than duplicating it.

The projection is deterministic: the notification id is derived from
``(stream_id, seq)`` so re-deriving after a restart resolves to the same record
and its persisted read state.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Iterable

from ..store.models import EventRecord
from .models import Notification, severity_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..store.protocol import Store

#: Task phases that page the user, mapped to the notification kind.
PHASE_TO_KIND: dict[str, str] = {
    "waiting_user": "task.waiting_user",
    "awaiting_acceptance": "task.awaiting_acceptance",
    "recovery_required": "task.recovery_required",
    "failed": "task.failed",
}

_TITLES: dict[str, str] = {
    "task.failed": "Task failed",
    "task.waiting_user": "Task is waiting for you",
    "task.awaiting_acceptance": "Candidate ready for acceptance",
    "task.recovery_required": "Task needs a recovery decision",
}


def notification_id(stream_id: str, seq: int, kind: str) -> str:
    """Stable id derived from the source event; survives reprojection."""

    digest = hashlib.sha256(f"{stream_id}:{seq}:{kind}".encode("utf-8")).hexdigest()
    return f"notif_{digest[:26].upper()}"


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _payload(record: EventRecord) -> dict[str, Any]:
    payload = record.event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _decision_binding(records: Iterable[EventRecord]) -> dict[str, Any]:
    """Latest ``decision.requested`` payload for the Task, if any."""

    binding: dict[str, Any] = {}
    for record in records:
        if record.type != "decision.requested":
            continue
        payload = _payload(record)
        binding = payload
    return binding


def project_task(
    stream_id: str, records: Iterable[EventRecord]
) -> list[Notification]:
    """Project one Task's ordered event records into notifications."""

    ordered = sorted(records, key=lambda record: record.seq)
    decision = _decision_binding(ordered)
    notifications: list[Notification] = []
    # ``decision.requested`` is emitted just before the phase transition; when
    # the Task does have an ``awaiting_acceptance`` phase event we let that one
    # own the notification (with the same binding) instead of emitting both.
    has_acceptance_phase = any(
        record.type == "task.phase_changed"
        and _payload(record).get("to") == "awaiting_acceptance"
        for record in ordered
    )

    for record in ordered:
        payload = _payload(record)
        if record.type == "task.phase_changed":
            to_phase = payload.get("to")
            kind = PHASE_TO_KIND.get(str(to_phase)) if to_phase is not None else None
            if kind is None:
                continue
            run_ref = record.event.get("run_ref")
            candidate_ref = None
            requirements_revision = None
            deliverable_revision = None
            if kind == "task.awaiting_acceptance":
                candidate_ref = decision.get("candidate_ref")
                requirements_revision = _int(decision.get("requirements_revision"))
                deliverable_revision = _int(decision.get("deliverable_revision"))
            notifications.append(
                _make(
                    record,
                    stream_id,
                    kind,
                    run_ref=run_ref if isinstance(run_ref, str) else None,
                    candidate_ref=candidate_ref if isinstance(candidate_ref, str) else None,
                    requirements_revision=requirements_revision,
                    deliverable_revision=deliverable_revision,
                    reason=payload.get("reason"),
                )
            )
        elif (
            record.type == "decision.requested"
            and not has_acceptance_phase
        ):
            run_ref = record.event.get("run_ref")
            notifications.append(
                _make(
                    record,
                    stream_id,
                    "task.awaiting_acceptance",
                    run_ref=run_ref if isinstance(run_ref, str) else None,
                    candidate_ref=(
                        payload.get("candidate_ref")
                        if isinstance(payload.get("candidate_ref"), str)
                        else None
                    ),
                    requirements_revision=_int(payload.get("requirements_revision")),
                    deliverable_revision=_int(payload.get("deliverable_revision")),
                    reason=payload.get("reason"),
                )
            )
    return notifications


def _make(
    record: EventRecord,
    stream_id: str,
    kind: str,
    *,
    run_ref: str | None,
    candidate_ref: str | None = None,
    requirements_revision: int | None = None,
    deliverable_revision: int | None = None,
    reason: Any = None,
) -> Notification:
    task_ref = record.event.get("task_ref")
    if not isinstance(task_ref, str) or not task_ref:
        task_ref = stream_id
    return Notification(
        notification_id=notification_id(stream_id, record.seq, kind),
        kind=kind,
        title=_TITLES.get(kind, kind),
        body=str(reason) if reason else _TITLES.get(kind, kind),
        at=record.at,
        severity=severity_for(kind),
        task_ref=task_ref,
        run_ref=run_ref,
        event_id=record.event_id,
        stream_id=stream_id,
        seq=record.seq,
        candidate_ref=candidate_ref,
        requirements_revision=requirements_revision,
        deliverable_revision=deliverable_revision,
        reason=str(reason) if reason else None,
    )


def project_store(store: "Store", task_ids: Iterable[str]) -> list[Notification]:
    """Project every given Task stream; unknown/empty streams yield nothing."""

    notifications: list[Notification] = []
    for task_id in task_ids:
        try:
            records = store.read_events(task_id, after_seq=0, limit=2000)
        except Exception:  # noqa: BLE001 - a broken stream must not break listing
            continue
        notifications.extend(project_task(task_id, records))
    notifications.sort(key=lambda item: (item.at, item.notification_id), reverse=True)
    return notifications


__all__ = [
    "PHASE_TO_KIND",
    "notification_id",
    "project_store",
    "project_task",
]
