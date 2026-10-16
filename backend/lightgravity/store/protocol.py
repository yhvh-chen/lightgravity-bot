"""Structural ``Store`` protocol frozen by docs/08 §7 (LG-004).

``FileStore`` is the concrete implementation.  Keeping the protocol explicit
lets adapter/coordinator tasks type against the boundary without importing the
filesystem implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import (
    ClaimResult,
    EventRecord,
    IndexReport,
    MessageRecord,
    TaskSummary,
    Versioned,
)


@runtime_checkable
class Store(Protocol):
    def read(self, kind: str, entity_id: str) -> Versioned: ...

    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
    ) -> Versioned: ...

    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
    ) -> Versioned: ...

    def append_event(self, stream_id: str, event: dict[str, Any]) -> EventRecord: ...

    def read_events(
        self, stream_id: str, *, after_seq: int = 0, limit: int = 500
    ) -> list[EventRecord]: ...

    def append_message(self, task_id: str, message: dict[str, Any]) -> MessageRecord: ...

    def read_messages(
        self, task_id: str, *, after: str | None = None, limit: int = 200
    ) -> list[MessageRecord]: ...

    def claim(self, task_id: str, owner: str, *, lease_seconds: int) -> ClaimResult: ...

    def renew(self, task_id: str, owner: str, *, lease_seconds: int) -> bool: ...

    def release(self, task_id: str, owner: str) -> None: ...

    def list_tasks(self) -> list[TaskSummary]: ...

    def rebuild_index(self) -> IndexReport: ...

    def resolve_path(self, relative: str, *, write: bool) -> Path: ...


__all__ = ["Store"]
