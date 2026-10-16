"""Idempotent Task conversation log as JSONL (LG-004, docs/08 §5.2).

Messages are history, not current state.  ``message_id`` is the idempotency
key: appending an existing id returns the stored record without writing again.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lightgravity.contracts import SCHEMA_NAMESPACE

from .atomic import append_jsonl, load_jsonl, recover_jsonl
from .clock import Clock, to_iso, utcnow
from .errors import ConfigInvalid, EntityNotFound
from .ids import id_matches_kind
from .locking import LockManager
from .models import MessageRecord

_ALLOWED_ROLES = frozenset({"user", "assistant", "system", "tool"})


def parse_cursor(cursor: str | None) -> int:
    """Parse an opaque message cursor ``v1:<task_id>:<seq>`` into a seq."""

    if not cursor:
        return 0
    parts = cursor.split(":")
    if len(parts) != 3 or parts[0] != "v1":
        raise ConfigInvalid(
            f"invalid message cursor {cursor!r}",
            diagnostics=[{"code": "cursor_invalid", "location": "after", "cursor": cursor}],
        )
    try:
        return int(parts[2])
    except ValueError as exc:
        raise ConfigInvalid(
            f"invalid message cursor {cursor!r}",
            diagnostics=[{"code": "cursor_invalid", "location": "after"}],
        ) from exc


class MessageLog:
    def __init__(self, data_dir: Path, locks: LockManager, clock: Clock = utcnow) -> None:
        self._data_dir = data_dir
        self._locks = locks
        self._clock = clock

    def path(self, task_id: str) -> Path:
        return self._data_dir / "tasks" / task_id / "conversation.jsonl"

    def _require_task(self, task_id: str) -> Path:
        if not id_matches_kind("task", task_id):
            raise ConfigInvalid(
                f"invalid task id {task_id!r}",
                diagnostics=[{"code": "id_invalid", "location": "task_id"}],
            )
        task_file = self._data_dir / "tasks" / task_id / "TASK.md"
        if not task_file.is_file():
            raise EntityNotFound("task", task_id, path=str(task_file))
        return task_file

    def append(self, task_id: str, message: dict[str, Any]) -> MessageRecord:
        self._require_task(task_id)
        if not isinstance(message, dict):
            raise ConfigInvalid("message must be a mapping")
        message_id = message.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise ConfigInvalid(
                "message_id is required for idempotent append",
                diagnostics=[{"code": "message_id_missing", "location": "message.message_id"}],
            )
        role = message.get("role")
        if role is not None and role not in _ALLOWED_ROLES:
            raise ConfigInvalid(
                f"unsupported message role {role!r}",
                diagnostics=[{"code": "role_invalid", "location": "message.role"}],
            )

        with self._locks.acquire(f"messages:{task_id}"):
            path = self.path(task_id)
            recover_jsonl(path)
            records, _ = load_jsonl(path)
            for record in records:
                if record.get("message_id") == message_id:
                    seq = record.get("seq")
                    return MessageRecord(
                        task_id=task_id,
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
            seq = last + 1
            stored: dict[str, Any] = dict(message)
            stored["schema"] = SCHEMA_NAMESPACE
            stored["kind"] = "message"
            stored.setdefault("task_ref", task_id)
            stored.setdefault("at", to_iso(self._clock()))
            stored["seq"] = seq
            append_jsonl(path, stored)

        return MessageRecord(
            task_id=task_id,
            message_id=message_id,
            seq=seq,
            message=stored,
            path=str(path),
        )

    def read(self, task_id: str, *, after: str | None = None, limit: int = 200) -> list[MessageRecord]:
        self._require_task(task_id)
        after_seq = parse_cursor(after)
        path = self.path(task_id)
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
            MessageRecord(
                task_id=task_id,
                message_id=str(record.get("message_id", "")),
                seq=record["seq"],
                message=record,
                path=str(path),
            )
            for record in selected[: max(limit, 0)]
        ]


__all__ = ["MessageLog", "parse_cursor"]
