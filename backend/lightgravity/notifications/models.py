"""Persistent notification records (LG-019; docs/04 §8, docs/08 §4.3/§5.1).

A notification is a *projection* of durable events, not a second source of
truth: :mod:`lightgravity.notifications.projection` derives the set from the
append-only event streams, and this store only persists the **read/delivered**
state plus a stable per-notification id.  It never copies Task/Run phase, which
stays in the authoritative frontmatter (docs/08 §6 preamble).

Layout::

    <data>/notifications/<notification_id>.md   kind: notification

The Markdown file keeps the projection identity (source event, Task/Run/
candidate/requirements revision) so a projection can be re-derived and still
resolve to the same notification and read state after a restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Notification kinds for the phases that must page the user (docs/04 §8).
NOTIFICATION_KINDS: tuple[str, ...] = (
    "task.failed",
    "task.waiting_user",
    "task.awaiting_acceptance",
    "task.recovery_required",
)

#: Event types that are *not* enough on their own; the phase payload decides.
_SEVERITY: dict[str, str] = {
    "task.failed": "error",
    "task.waiting_user": "warning",
    "task.awaiting_acceptance": "success",
    "task.recovery_required": "warning",
}


def severity_for(kind: str) -> str:
    return _SEVERITY.get(kind, "info")


@dataclass(frozen=True, slots=True)
class Notification:
    """One durable notification record with accurate Task/Run/version refs."""

    notification_id: str
    kind: str
    title: str
    body: str
    at: str
    severity: str
    task_ref: str
    run_ref: str | None = None
    event_id: str | None = None
    stream_id: str | None = None
    seq: int | None = None
    candidate_ref: str | None = None
    requirements_revision: int | None = None
    deliverable_revision: int | None = None
    reason: str | None = None
    read: bool = False
    read_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "at": self.at,
            "severity": self.severity,
            "task_ref": self.task_ref,
            "run_ref": self.run_ref,
            "event_id": self.event_id,
            "stream_id": self.stream_id,
            "seq": self.seq,
            "candidate_ref": self.candidate_ref,
            "requirements_revision": self.requirements_revision,
            "deliverable_revision": self.deliverable_revision,
            "reason": self.reason,
            "read": self.read,
            "read_at": self.read_at,
            **({"extra": self.extra} if self.extra else {}),
        }


__all__ = [
    "NOTIFICATION_KINDS",
    "Notification",
    "severity_for",
]
