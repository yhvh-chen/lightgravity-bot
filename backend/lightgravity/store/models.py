"""Typed records returned by the store (LG-004).

These are internal plain dataclasses, not wire DTOs.  ``Versioned`` mirrors the
fields required by docs/08 §7 (``entity``, ``revision``, ``content_hash``) and
adds ``body``/``path`` so callers do not re-read the file to preserve prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A structured, serializable validation finding.

    ``level`` is ``error`` for blocking problems and ``warning`` for findings
    that are preserved but do not make the entity unusable.  ``code`` is a
    stable machine token such as ``duplicate_key`` or ``illegal_status_phase``.
    """

    code: str
    message: str
    level: str = "error"
    location: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "level": self.level,
            "location": self.location,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Versioned:
    """One authoritative entity read from or written to disk."""

    kind: str
    entity_id: str
    entity: dict[str, Any]
    revision: int
    content_hash: str
    body: str
    path: str

    @property
    def etag(self) -> str:
        return f'"{self.revision}"'


@dataclass(frozen=True, slots=True)
class EventRecord:
    stream_id: str
    seq: int
    event_id: str
    type: str
    at: str
    event: dict[str, Any]
    path: str


@dataclass(frozen=True, slots=True)
class MessageRecord:
    task_id: str
    message_id: str
    seq: int
    message: dict[str, Any]
    path: str

    @property
    def cursor(self) -> str:
        return f"v1:{self.task_id}:{self.seq}"


@dataclass(frozen=True, slots=True)
class ClaimResult:
    task_id: str
    claimed: bool
    owner: str
    lease_expires_at: str
    revision: int
    entity: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TaskSummary:
    id: str
    title: str
    status: str
    phase: str
    revision: int
    requirements_revision: int
    queue_state: str
    owner: str | None
    lease_expires_at: str | None
    archived: bool
    path: str


@dataclass(frozen=True, slots=True)
class IndexReport:
    scanned: int
    indexed: int
    tasks: int
    diagnostics: list[Diagnostic]
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "indexed": self.indexed,
            "tasks": self.tasks,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    removed_temp_files: list[str]
    truncated_jsonl: list[str]
    recorded_events: int
    diagnostics: list[Diagnostic]

    def to_dict(self) -> dict[str, Any]:
        return {
            "removed_temp_files": list(self.removed_temp_files),
            "truncated_jsonl": list(self.truncated_jsonl),
            "recorded_events": self.recorded_events,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


__all__ = [
    "Diagnostic",
    "Versioned",
    "EventRecord",
    "MessageRecord",
    "ClaimResult",
    "TaskSummary",
    "IndexReport",
    "RecoveryReport",
]
