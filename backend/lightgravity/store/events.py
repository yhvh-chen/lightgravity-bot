"""Append-only event streams as JSONL (LG-004, docs/08 §5.1).

One stream per ``stream_id`` under ``events/<stream_id>/events.jsonl``.  ``seq``
is assigned under the stream lock so it is gap-free and monotonic across
processes.  An incomplete trailing line is truncated before appending.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lightgravity.contracts import SCHEMA_NAMESPACE

from .atomic import append_jsonl, load_jsonl, recover_jsonl
from .clock import Clock, to_iso, utcnow
from .entities import event_type_supported
from .errors import ConfigInvalid
from .ids import new_id
from .locking import LockManager
from .models import EventRecord

_STREAM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class EventLog:
    def __init__(self, data_dir: Path, locks: LockManager, clock: Clock = utcnow) -> None:
        self._data_dir = data_dir
        self._locks = locks
        self._clock = clock

    def path(self, stream_id: str) -> Path:
        return self._data_dir / "events" / stream_id / "events.jsonl"

    def last_seq(self, stream_id: str) -> int:
        records, _ = load_jsonl(self.path(stream_id))
        last = 0
        for record in records:
            seq = record.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool) and seq > last:
                last = seq
        return last

    def append(self, stream_id: str, event: dict[str, Any]) -> EventRecord:
        if not isinstance(stream_id, str) or not _STREAM_RE.match(stream_id):
            raise ConfigInvalid(
                f"invalid stream_id {stream_id!r}",
                diagnostics=[{"code": "stream_id_invalid", "location": "stream_id"}],
            )
        if not isinstance(event, dict):
            raise ConfigInvalid("event must be a mapping")

        event_type = event.get("type")
        if not event_type_supported(event_type):
            raise ConfigInvalid(
                f"unsupported event type {event_type!r}",
                diagnostics=[
                    {
                        "code": "event_type_unsupported",
                        "message": f"unsupported event type {event_type!r}",
                        "location": "event.type",
                    }
                ],
            )

        with self._locks.acquire(f"events:{stream_id}"):
            path = self.path(stream_id)
            recover_jsonl(path)
            seq = self.last_seq(stream_id) + 1
            record: dict[str, Any] = dict(event)
            record["schema"] = SCHEMA_NAMESPACE
            record["kind"] = "event"
            record["event_id"] = event.get("event_id") or new_id("evt")
            record["stream_id"] = stream_id
            record["seq"] = seq
            record["type"] = event_type
            record["at"] = event.get("at") or to_iso(self._clock())
            record.setdefault("actor", "system")
            record.setdefault("task_ref", None)
            record.setdefault("run_ref", None)
            record.setdefault("payload", {})
            append_jsonl(path, record)

        return EventRecord(
            stream_id=stream_id,
            seq=seq,
            event_id=record["event_id"],
            type=str(event_type),
            at=record["at"],
            event=record,
            path=str(path),
        )

    def read(self, stream_id: str, *, after_seq: int = 0, limit: int = 500) -> list[EventRecord]:
        path = self.path(stream_id)
        if not path.is_file():
            return []
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
            EventRecord(
                stream_id=stream_id,
                seq=record["seq"],
                event_id=str(record.get("event_id", "")),
                type=str(record.get("type", "")),
                at=str(record.get("at", "")),
                event=record,
                path=str(path),
            )
            for record in selected[: max(limit, 0)]
        ]


__all__ = ["EventLog"]
