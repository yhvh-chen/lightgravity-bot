"""Coordinator-owned persistence: global conversations and request idempotency.

The store protocol (docs/08 §7) owns Task conversation messages, but the global
conversation (docs/04 §4) and the ``request_id`` idempotency record live outside
it.  Both are append-only JSONL under ``<data>/`` and use the same durable
append helpers and file locks as the store (read-only reuse; the store package
is not modified).

These are *derived/navigational* records: they never become a second
authoritative Task state.  A Task's state is only in its TASK.md.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Callable

from lightgravity.store.atomic import append_jsonl, load_jsonl, recover_jsonl
from lightgravity.store.ids import id_matches_kind
from lightgravity.store.locking import LockManager

from .classification import MessageIntent  # noqa: F401  (documented seam)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


@dataclasses.dataclass(frozen=True, slots=True)
class ConversationRecord:
    """One persisted global-conversation message."""

    conversation_id: str
    message_id: str
    seq: int
    message: dict[str, Any]
    path: str

    @property
    def cursor(self) -> str:
        return f"v1:{self.conversation_id}:{self.seq}"


class GlobalConversationLog:
    """Idempotent JSONL log for the global conversation (docs/04 §4).

    Layout: ``<data>/conversations/<conversation-id>/messages.jsonl``.  The
    ``message_id`` is the idempotency key; re-appending the same id returns the
    stored record without writing again.
    """

    def __init__(self, data_dir: Path, locks: LockManager) -> None:
        self._data_dir = Path(data_dir)
        self._locks = locks

    def path(self, conversation_id: str) -> Path:
        return self._data_dir / "conversations" / conversation_id / "messages.jsonl"

    def _validate(self, conversation_id: str) -> None:
        if not id_matches_kind("conv", conversation_id):
            from lightgravity.contracts import AppError, ErrorCode

            raise AppError(
                ErrorCode.CONFIG_INVALID,
                f"invalid conversation id {conversation_id!r}",
                details={"kind": "conv", "id": conversation_id},
            )

    def append(self, conversation_id: str, message: dict[str, Any]) -> ConversationRecord:
        self._validate(conversation_id)
        if not isinstance(message, dict):
            from lightgravity.contracts import AppError, ErrorCode

            raise AppError(ErrorCode.INVALID_REQUEST, "message must be a mapping")
        message_id = message.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            from lightgravity.contracts import AppError, ErrorCode

            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "message_id is required for idempotent append",
                details={"field": "message_id"},
            )
        with self._locks.acquire(f"global-messages:{conversation_id}"):
            path = self.path(conversation_id)
            recover_jsonl(path)
            records, _ = load_jsonl(path)
            for record in records:
                if record.get("message_id") == message_id:
                    seq = record.get("seq")
                    return ConversationRecord(
                        conversation_id=conversation_id,
                        message_id=message_id,
                        seq=seq if isinstance(seq, int) and not isinstance(seq, bool) else 0,
                        message=record,
                        path=str(path),
                    )
            last = 0
            for record in records:
                seq = record.get("seq")
                if isinstance(seq, int) and not isinstance(seq, bool) and seq > last:
                    last = seq
            stored = dict(message)
            stored["schema"] = "lightgravity.bot/v1"
            stored["kind"] = "message"
            stored["conversation_ref"] = conversation_id
            stored.setdefault("at", _now_iso())
            stored["seq"] = last + 1
            append_jsonl(path, stored)
            return ConversationRecord(
                conversation_id=conversation_id,
                message_id=message_id,
                seq=stored["seq"],
                message=stored,
                path=str(path),
            )

    def read(
        self, conversation_id: str, *, after: str | None = None, limit: int = 200
    ) -> list[ConversationRecord]:
        self._validate(conversation_id)
        after_seq = 0
        if after:
            parts = after.split(":")
            if len(parts) != 3 or parts[0] != "v1":
                from lightgravity.contracts import AppError, ErrorCode

                raise AppError(
                    ErrorCode.CONFIG_INVALID,
                    f"invalid cursor {after!r}",
                    details={"cursor": after},
                )
            after_seq = int(parts[2])
        path = self.path(conversation_id)
        records, _ = load_jsonl(path)
        selected = [
            record
            for record in records
            if isinstance(record.get("seq"), int)
            and not isinstance(record.get("seq"), bool)
            and record["seq"] > after_seq
        ]
        selected.sort(key=lambda record: record["seq"])
        return [
            ConversationRecord(
                conversation_id=conversation_id,
                message_id=str(record.get("message_id", "")),
                seq=record["seq"],
                message=record,
                path=str(path),
            )
            for record in selected[: max(limit, 0)]
        ]


class IdempotencyLog:
    """Persistent ``request_id`` → first-result map for control operations.

    ``execute`` serializes concurrent callers with the same request id so a
    retried create/enqueue/action is not applied twice within a process and is
    remembered across restarts.
    """

    def __init__(self, data_dir: Path, locks: LockManager) -> None:
        self._data_dir = Path(data_dir)
        self._locks = locks

    @property
    def path(self) -> Path:
        return self._data_dir / "coordinator" / "requests.jsonl"

    def lookup(self, request_id: str) -> dict[str, Any] | None:
        recover_jsonl(self.path)
        records, _ = load_jsonl(self.path)
        found: dict[str, Any] | None = None
        for record in records:
            if record.get("request_id") == request_id:
                result = record.get("result")
                found = result if isinstance(result, dict) else None
        return found

    def execute(self, request_id: str, producer: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if not isinstance(request_id, str) or not request_id:
            from lightgravity.contracts import AppError, ErrorCode

            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "request_id is required",
                details={"field": "request_id"},
            )
        with self._locks.acquire(f"request:{request_id}"):
            existing = self.lookup(request_id)
            if existing is not None:
                return existing
            result = producer()
            append_jsonl(self.path, {"request_id": request_id, "at": _now_iso(), "result": result})
            return result

    def record(self, request_id: str, result: dict[str, Any]) -> None:
        """Record a result for an idempotency key without a producer.

        Used by async callers (control actions) that cannot run inside the
        synchronous :meth:`execute` producer.  ``request_id`` must be unique per
        logical operation.
        """

        if not isinstance(request_id, str) or not request_id:
            from lightgravity.contracts import AppError, ErrorCode

            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "request_id is required",
                details={"field": "request_id"},
            )
        append_jsonl(self.path, {"request_id": request_id, "at": _now_iso(), "result": result})


__all__ = ["ConversationRecord", "GlobalConversationLog", "IdempotencyLog"]
