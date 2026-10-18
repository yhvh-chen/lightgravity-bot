"""Filesystem Store: Markdown entities, JSONL logs, leases and recovery.

Implements the ``Store`` protocol frozen in docs/08 §7 (LG-004).  The single
writer rule is enforced with per-entity ``flock`` locks around every
read-modify-write, and writes are committed with an atomic replace.

Layout (store-internal; callers use the Store API, not paths)::

    <data>/tasks/<task_id>/TASK.md
    <data>/tasks/<task_id>/conversation.jsonl
    <data>/runs/<run_id>/RUN.md
    <data>/subtasks/<subtask_id>/SUBTASK.md
    <data>/members/<member_id>.md
    <data>/resources/<dir>/<id>.md            (skills: <id>/SKILL.md)
    <data>/settings/SETTINGS.md
    <data>/events/<stream_id>/events.jsonl

The flat per-kind containers keep ``read(kind, id)`` resolvable from the id
alone, as required by the protocol, while every ref field still records the
owning Task/Run.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightgravity.contracts import SCHEMA_NAMESPACE
from ruamel.yaml.comments import CommentedMap

from .atomic import TEMP_PREFIX, atomic_write_text, recover_jsonl, sha256_text
from .clock import Clock, from_iso, plus_seconds, to_iso, utcnow
from .entities import ALL_KINDS, RESOURCE_DIRS, validate_entity, validate_transition
from .errors import (
    ConfigInvalid,
    EntityNotFound,
    IllegalTransition,
    LockConflict,
    RevisionConflict,
)
from .events import EventLog
from .frontmatter import as_mapping, merge_maps, parse_document, plain, render_document
from .ids import id_matches_kind
from .index import build_index, task_summary
from .locking import LockManager
from .messages import MessageLog
from .models import (
    ClaimResult,
    Diagnostic,
    EventRecord,
    IndexReport,
    MessageRecord,
    RecoveryReport,
    TaskSummary,
    Versioned,
)

_STORE_TEMP_GLOB = f"{TEMP_PREFIX}*"

#: A file-version signature.  ``st_dev``/``st_ino`` catch atomic replacement
#: (the Store's own write path), while the timestamps and size catch external
#: in-place edits.  Nothing in this signature survives the process.
_FileSignature = tuple[int, int, int, int, int]


def _stat_signature(stat: os.stat_result) -> _FileSignature:
    return (
        stat.st_dev,
        stat.st_ino,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
        stat.st_size,
    )


@dataclass(frozen=True, slots=True)
class _CachedDocument:
    """Parsed/validated result for one exact file version (never authoritative)."""

    signature: _FileSignature
    versioned: Versioned

    def snapshot(self) -> Versioned:
        """Return a caller-owned copy so cached mutable data cannot leak."""

        return Versioned(
            kind=self.versioned.kind,
            entity_id=self.versioned.entity_id,
            entity=deepcopy(self.versioned.entity),
            revision=self.versioned.revision,
            content_hash=self.versioned.content_hash,
            body=self.versioned.body,
            path=self.versioned.path,
        )


class FileStore:
    """Markdown filesystem source of truth."""

    def __init__(
        self,
        data_dir: Path | str,
        workspace_root: Path | str,
        *,
        lock_timeout: float = 10.0,
        clock: Clock = utcnow,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._workspace_root = Path(workspace_root)
        self._clock = clock
        self._locks = LockManager(self._data_dir / "locks", default_timeout=lock_timeout)
        self._events = EventLog(self._data_dir, self._locks, clock)
        self._messages = MessageLog(self._data_dir, self._locks, clock)
        self._entries: dict[tuple[str, str], Any] | None = None
        self._index_diagnostics: list[Diagnostic] = []
        # Path -> last successfully parsed/validated file version.  This is a
        # disposable in-process cache only: Markdown files remain the single
        # source of truth and every hit is gated by the current file signature.
        self._read_cache: dict[Path, _CachedDocument] = {}

    # ------------------------------------------------------------------ paths
    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def entity_path(self, kind: str, entity_id: str) -> Path:
        if kind == "task":
            return self._data_dir / "tasks" / entity_id / "TASK.md"
        if kind == "run":
            return self._data_dir / "runs" / entity_id / "RUN.md"
        if kind == "subtask":
            return self._data_dir / "subtasks" / entity_id / "SUBTASK.md"
        if kind == "member":
            return self._data_dir / "members" / f"{entity_id}.md"
        if kind == "settings":
            return self._data_dir / "settings" / "SETTINGS.md"
        if kind in RESOURCE_DIRS:
            directory = RESOURCE_DIRS[kind]
            if kind == "skill":
                return self._data_dir / "resources" / directory / entity_id / "SKILL.md"
            return self._data_dir / "resources" / directory / f"{entity_id}.md"
        raise ConfigInvalid(
            f"unsupported kind {kind!r}",
            diagnostics=[{"code": "kind_unsupported", "location": "kind", "kind": kind}],
        )

    def _validate_kind_id(self, kind: str, entity_id: str) -> None:
        if kind not in ALL_KINDS:
            raise ConfigInvalid(
                f"unsupported kind {kind!r}",
                diagnostics=[{"code": "kind_unsupported", "location": "kind", "kind": kind}],
            )
        if kind == "settings":
            if entity_id != "settings":
                raise ConfigInvalid(
                    "settings entity id must be 'settings'",
                    diagnostics=[{"code": "id_invalid", "location": "id", "id": entity_id}],
                )
            return
        if not id_matches_kind(kind, entity_id):
            raise ConfigInvalid(
                f"invalid {kind} id {entity_id!r}",
                diagnostics=[{"code": "id_invalid", "location": "id", "id": entity_id}],
            )

    def _lock_key(self, kind: str, entity_id: str) -> str:
        return f"entity:{kind}:{entity_id}"

    @staticmethod
    def _file_signature(path: Path) -> _FileSignature | None:
        try:
            return _stat_signature(path.stat())
        except OSError:
            return None

    def _invalidate_read_cache(self, path: Path) -> None:
        # Unified Store writes invalidate immediately; the signature check also
        # handles external writers that never go through this Store instance.
        self._read_cache.pop(path, None)

    # ------------------------------------------------------------------- read
    def read(self, kind: str, entity_id: str) -> Versioned:
        self._validate_kind_id(kind, entity_id)
        path = self.entity_path(kind, entity_id)
        if not path.is_file():
            self._invalidate_read_cache(path)
            raise EntityNotFound(kind, entity_id, path=str(path))
        signature = self._file_signature(path)
        if signature is None:
            self._invalidate_read_cache(path)
            raise EntityNotFound(kind, entity_id, path=str(path))
        cached = self._read_cache.get(path)
        if cached is not None and cached.signature == signature:
            return cached.snapshot()

        text = path.read_text("utf-8")
        raw, body = parse_document(text, source=str(path))
        data = plain(raw)
        diagnostics = [d for d in validate_entity(kind, data, source=str(path)) if d.level == "error"]
        if data.get("id") != entity_id:
            diagnostics.append(
                Diagnostic(
                    code="id_path_mismatch",
                    message=f"id {data.get('id')!r} does not match requested id {entity_id!r}",
                    location=str(path),
                )
            )
        if diagnostics:
            # Never cache a failed validation: repeating the read must repeat
            # the same authoritative check until the file itself is fixed.
            self._invalidate_read_cache(path)
            raise ConfigInvalid(
                f"{kind} {entity_id!r} failed validation",
                diagnostics=[d.to_dict() for d in diagnostics],
                location=str(path),
            )
        revision = data["revision"]
        versioned = Versioned(
            kind=kind,
            entity_id=entity_id,
            entity=data,
            revision=revision,
            content_hash=sha256_text(text),
            body=body,
            path=str(path),
        )
        # Cache only a snapshot that still corresponds to the signature that
        # was observed before reading.  A concurrent replacement makes the
        # check fail and the next read simply parses the newer file.
        if self._file_signature(path) == signature:
            cached = _CachedDocument(signature=signature, versioned=versioned)
            self._read_cache[path] = cached
            # The cold read must already be caller-owned: otherwise mutating it
            # would mutate the object now held by the cache.
            return cached.snapshot()
        return versioned

    # ----------------------------------------------------------------- create
    def create(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        actor: str,
        request_id: str,
        body: str | None = None,
    ) -> Versioned:
        self._validate_kind_id(kind, entity_id)
        if not isinstance(content, dict):
            raise ConfigInvalid("content must be a mapping")
        with self._locks.acquire(self._lock_key(kind, entity_id)):
            path = self.entity_path(kind, entity_id)
            if path.exists():
                raise ConfigInvalid(
                    f"{kind} {entity_id!r} already exists",
                    diagnostics=[
                        {"code": "duplicate_id", "location": str(path), "id": entity_id}
                    ],
                    location=str(path),
                )
            raw: Any = CommentedMap()
            merge_maps(raw, dict(content))
            raw["schema"] = SCHEMA_NAMESPACE
            raw["kind"] = kind
            raw["id"] = entity_id
            raw["revision"] = 0
            data = plain(raw)
            diagnostics = validate_entity(kind, data, source=str(path))
            errors = [d for d in diagnostics if d.level == "error"]
            if errors:
                raise ConfigInvalid(
                    f"{kind} {entity_id!r} failed validation",
                    diagnostics=[d.to_dict() for d in errors],
                    location=str(path),
                )
            text = render_document(raw, body or "")
            atomic_write_text(path, text)
            self._invalidate_read_cache(path)
            self._touch_index(kind, entity_id, data, 0, str(path))
            return Versioned(
                kind=kind,
                entity_id=entity_id,
                entity=data,
                revision=0,
                content_hash=sha256_text(text),
                body=body or "",
                path=str(path),
            )

    # ------------------------------------------------------------------ write
    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
        body: str | None = None,
    ) -> Versioned:
        self._validate_kind_id(kind, entity_id)
        if expected_revision is None:
            raise ConfigInvalid(
                "expected_revision is required for write; use create() for new entities",
                diagnostics=[{"code": "expected_revision_missing", "location": "expected_revision"}],
            )
        if not isinstance(content, dict):
            raise ConfigInvalid("content must be a mapping")
        with self._locks.acquire(self._lock_key(kind, entity_id)):
            path = self.entity_path(kind, entity_id)
            if not path.is_file():
                raise EntityNotFound(kind, entity_id, path=str(path))
            text = path.read_text("utf-8")
            raw, old_body = parse_document(text, source=str(path))
            old_data = plain(raw)
            current = old_data.get("revision")
            if isinstance(current, bool) or not isinstance(current, int):
                raise ConfigInvalid(
                    f"{kind} {entity_id!r} has invalid revision",
                    diagnostics=[{"code": "revision_invalid", "location": str(path)}],
                )
            if current != expected_revision:
                raise RevisionConflict(kind, entity_id, expected=expected_revision, actual=current)
            return self._commit_locked(
                kind,
                entity_id,
                path,
                raw,
                old_body,
                old_data,
                current,
                content,
                body,
            )

    def delete(
        self,
        kind: str,
        entity_id: str,
        *,
        expected_revision: int,
        actor: str,
        guard: Callable[[], None] | None = None,
    ) -> Versioned:
        """Delete an entity under the same per-entity lock as writes.

        The revision is re-checked while the lock is held; an optional ``guard``
        runs at that point so cross-file reference checks and the unlink share a
        single controlled boundary.  The caller owns any compensation policy.
        """

        self._validate_kind_id(kind, entity_id)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ConfigInvalid(
                "expected_revision is required for delete",
                diagnostics=[
                    {"code": "expected_revision_missing", "location": "expected_revision"}
                ],
            )
        with self._locks.acquire(self._lock_key(kind, entity_id)):
            path = self.entity_path(kind, entity_id)
            if not path.is_file():
                raise EntityNotFound(kind, entity_id, path=str(path))
            text = path.read_text("utf-8")
            raw, body = parse_document(text, source=str(path))
            data = plain(raw)
            current = data.get("revision")
            if isinstance(current, bool) or not isinstance(current, int):
                raise ConfigInvalid(
                    f"{kind} {entity_id!r} has invalid revision",
                    diagnostics=[{"code": "revision_invalid", "location": str(path)}],
                )
            if current != expected_revision:
                raise RevisionConflict(
                    kind, entity_id, expected=expected_revision, actual=current
                )
            if guard is not None:
                guard()
            path.unlink()
            self._invalidate_read_cache(path)
            if self._entries is not None:
                self._entries.pop((kind, entity_id), None)
            return Versioned(
                kind=kind,
                entity_id=entity_id,
                entity=data,
                revision=current,
                content_hash=sha256_text(text),
                body=body,
                path=str(path),
            )

    def _commit_locked(
        self,
        kind: str,
        entity_id: str,
        path: Path,
        raw: Any,
        old_body: str,
        old_data: dict[str, Any],
        current: int,
        updates: dict[str, Any],
        body: str | None,
    ) -> Versioned:
        merge_maps(raw, updates)
        raw["schema"] = SCHEMA_NAMESPACE
        raw["kind"] = kind
        raw["id"] = entity_id
        raw["revision"] = current + 1
        new_data = plain(raw)
        static = [d for d in validate_entity(kind, new_data, source=str(path)) if d.level == "error"]
        if static:
            raise ConfigInvalid(
                f"{kind} {entity_id!r} update failed validation",
                diagnostics=[d.to_dict() for d in static],
                location=str(path),
            )
        transitions = validate_transition(kind, old_data, new_data)
        if transitions:
            raise IllegalTransition(
                f"{kind} {entity_id!r} transition rejected",
                diagnostics=[d.to_dict() for d in transitions],
            )
        new_body = old_body if body is None else body
        text = render_document(raw, new_body)
        atomic_write_text(path, text)
        self._invalidate_read_cache(path)
        self._touch_index(kind, entity_id, new_data, current + 1, str(path))
        return Versioned(
            kind=kind,
            entity_id=entity_id,
            entity=new_data,
            revision=current + 1,
            content_hash=sha256_text(text),
            body=new_body,
            path=str(path),
        )

    # ----------------------------------------------------------------- events
    def append_event(self, stream_id: str, event: dict[str, Any]) -> EventRecord:
        return self._events.append(stream_id, event)

    def read_events(
        self, stream_id: str, *, after_seq: int = 0, limit: int = 500
    ) -> list[EventRecord]:
        return self._events.read(stream_id, after_seq=after_seq, limit=limit)

    # --------------------------------------------------------------- messages
    def append_message(self, task_id: str, message: dict[str, Any]) -> MessageRecord:
        return self._messages.append(task_id, message)

    def read_messages(
        self, task_id: str, *, after: str | None = None, limit: int = 200
    ) -> list[MessageRecord]:
        return self._messages.read(task_id, after=after, limit=limit)

    # ------------------------------------------------------- lease/claim (task)
    def _task_raw(self, task_id: str) -> tuple[Path, Any, str, dict[str, Any]]:
        self._validate_kind_id("task", task_id)
        path = self.entity_path("task", task_id)
        if not path.is_file():
            raise EntityNotFound("task", task_id, path=str(path))
        raw, body = parse_document(path.read_text("utf-8"), source=str(path))
        data = plain(raw)
        errors = [d for d in validate_entity("task", data, source=str(path)) if d.level == "error"]
        if errors:
            raise ConfigInvalid(
                f"task {task_id!r} failed validation",
                diagnostics=[d.to_dict() for d in errors],
                location=str(path),
            )
        return path, raw, body, data

    def claim(self, task_id: str, owner: str, *, lease_seconds: int) -> ClaimResult:
        if lease_seconds <= 0:
            raise ConfigInvalid("lease_seconds must be > 0")
        with self._locks.acquire(self._lock_key("task", task_id)):
            path, raw, body, data = self._task_raw(task_id)
            queue = as_mapping(data.get("queue"))
            state = queue.get("state")
            current_owner = queue.get("owner")
            expires = queue.get("lease_expires_at")
            now = self._clock()
            if state == "claimed" and current_owner and current_owner != owner:
                if isinstance(expires, str):
                    try:
                        active = from_iso(expires) > now
                    except ValueError:
                        active = False
                else:
                    active = False
                if active:
                    raise LockConflict(f"task:{task_id}", owner=str(current_owner))
            expiry = to_iso(plus_seconds(now, lease_seconds))
            revision = data["revision"]
            updates = {
                "queue": {
                    "state": "claimed",
                    "owner": owner,
                    "lease_expires_at": expiry,
                }
            }
            versioned = self._commit_locked(
                "task", task_id, path, raw, body, data, revision, updates, None
            )
            return ClaimResult(
                task_id=task_id,
                claimed=True,
                owner=owner,
                lease_expires_at=expiry,
                revision=versioned.revision,
                entity=versioned.entity,
            )

    def renew(self, task_id: str, owner: str, *, lease_seconds: int) -> bool:
        if lease_seconds <= 0:
            raise ConfigInvalid("lease_seconds must be > 0")
        with self._locks.acquire(self._lock_key("task", task_id)):
            path, raw, body, data = self._task_raw(task_id)
            queue = as_mapping(data.get("queue"))
            if queue.get("state") != "claimed" or queue.get("owner") != owner:
                return False
            expires = queue.get("lease_expires_at")
            now = self._clock()
            if isinstance(expires, str):
                try:
                    if from_iso(expires) <= now:
                        return False
                except ValueError:
                    return False
            else:
                return False
            expiry = to_iso(plus_seconds(now, lease_seconds))
            revision = data["revision"]
            self._commit_locked(
                "task",
                task_id,
                path,
                raw,
                body,
                data,
                revision,
                {"queue": {"state": "claimed", "owner": owner, "lease_expires_at": expiry}},
                None,
            )
            return True

    def release(self, task_id: str, owner: str) -> None:
        with self._locks.acquire(self._lock_key("task", task_id)):
            path, raw, body, data = self._task_raw(task_id)
            queue = as_mapping(data.get("queue"))
            if queue.get("state") == "claimed" and queue.get("owner") not in (None, owner):
                raise LockConflict(f"task:{task_id}", owner=str(queue.get("owner")))
            if queue.get("state") == "not_queued" and queue.get("owner") is None:
                return
            revision = data["revision"]
            self._commit_locked(
                "task",
                task_id,
                path,
                raw,
                body,
                data,
                revision,
                {"queue": {"state": "not_queued", "owner": None, "lease_expires_at": None}},
                None,
            )

    # ------------------------------------------------------------------ index
    def _ensure_index(self) -> dict[tuple[str, str], Any]:
        if self._entries is None:
            result = build_index(self._data_dir)
            self._entries = result.entries
            self._index_diagnostics = result.diagnostics
        return self._entries

    def _touch_index(
        self, kind: str, entity_id: str, data: dict[str, Any], revision: int, path: str
    ) -> None:
        if self._entries is None:
            return
        from .index import IndexEntry

        self._entries[(kind, entity_id)] = IndexEntry(
            kind=kind, entity_id=entity_id, data=data, revision=revision, path=path
        )

    def list_tasks(self) -> list[TaskSummary]:
        entries = self._ensure_index()
        summaries = [task_summary(entry) for (kind, _), entry in entries.items() if kind == "task"]
        summaries.sort(key=lambda summary: summary.id)
        return summaries

    def rebuild_index(self) -> IndexReport:
        started = time.monotonic()
        result = build_index(self._data_dir)
        self._entries = result.entries
        self._index_diagnostics = result.diagnostics
        duration_ms = (time.monotonic() - started) * 1000.0
        tasks = sum(1 for kind, _ in result.entries if kind == "task")
        return IndexReport(
            scanned=result.scanned,
            indexed=len(result.entries),
            tasks=tasks,
            diagnostics=result.diagnostics,
            duration_ms=duration_ms,
        )

    def index_diagnostics(self) -> list[Diagnostic]:
        self._ensure_index()
        return list(self._index_diagnostics)

    # ------------------------------------------------------------------ paths
    def resolve_path(self, relative: str, *, write: bool = False) -> Path:
        from .paths import resolve_workspace_path

        return resolve_workspace_path(self._workspace_root, relative, write=write)

    # ---------------------------------------------------------------- recovery
    def recover(self) -> RecoveryReport:
        removed: list[str] = []
        truncated: list[str] = []
        diagnostics: list[Diagnostic] = []
        recorded = 0

        if self._data_dir.is_dir():
            for temp in sorted(self._data_dir.rglob(_STORE_TEMP_GLOB)):
                if temp.is_file():
                    temp.unlink(missing_ok=True)
                    removed.append(str(temp))

        if self._data_dir.is_dir():
            for path in sorted(self._data_dir.rglob("*.jsonl")):
                if any(part.startswith(TEMP_PREFIX) for part in path.parts):
                    continue
                try:
                    if recover_jsonl(path):
                        truncated.append(str(path))
                        stream_id = self._stream_for_path(path)
                        self._events.append(
                            stream_id,
                            {
                                "type": "error.recorded",
                                "actor": "store",
                                "payload": {
                                    "path": str(path),
                                    "action": "truncated_partial_record",
                                },
                            },
                        )
                        recorded += 1
                except Exception as exc:  # noqa: BLE001 - recovery must not abort
                    diagnostics.append(
                        Diagnostic(
                            code="recovery_failed",
                            message=str(exc),
                            location=str(path),
                        )
                    )

        return RecoveryReport(
            removed_temp_files=removed,
            truncated_jsonl=truncated,
            recorded_events=recorded,
            diagnostics=diagnostics,
        )

    def _stream_for_path(self, path: Path) -> str:
        try:
            relative = path.relative_to(self._data_dir)
        except ValueError:
            return "system"
        parts = relative.parts
        if len(parts) == 3 and parts[0] == "events" and parts[2] == "events.jsonl":
            return parts[1]
        if len(parts) == 3 and parts[0] == "tasks" and parts[2] == "conversation.jsonl":
            return f"task_{parts[1]}"
        return "system"

__all__ = ["FileStore"]
