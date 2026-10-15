"""API-facing source service: authorization, attribution and read views.

The intake engine (:mod:`lightgravity.sources.intake`) owns persistence; this
facade is where **program-side permission checks** happen before any write:

* a ``task_ref`` must resolve to an existing Task in the authoritative store —
  the browser cannot attribute material to an arbitrary/foreign Task;
* a ``project_ref`` currently has no project registry, so it is refused with an
  honest ``reference_invalid`` rather than silently accepted (recorded as a
  limitation, not a capability);
* a workspace ``path`` is authorized through the injected ``Store.resolve_path``
  so ``..``/absolute/symlink escapes raise ``path_outside_workspace``;
* an ``inbox_ref`` must name a controlled inbox the caller created; global
  material goes there and **never** forces a Task.

Nothing here writes Task/Run/Member control state, starts a delivery Run, or
grants execution semantics to uploaded content (docs/08 §6.6).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.errors import EntityNotFound

from .intake import IntakeService, ReceiveRequest
from .models import IntakeJobRecord, ReceiptEntry, ReceiveResult, SourceRecord
from .store import SourceStore, new_inbox_id, sanitize_filename

#: Max bytes for an inline base64 body accepted via ``POST /sources``.
MAX_INLINE_BYTES = 10_000_000
#: Max bytes for one inbox attachment (mirrors the LG-014 upload bound).
MAX_ATTACHMENT_BYTES = 10_000_000


class TaskReader(Protocol):
    """The subset of the LG-004 Store used to authorize Task attribution."""

    def read(self, kind: str, entity_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class ProjectResolver(Protocol):
    """Resolve a ``project_ref``; no implementation ships in LG-034."""

    def resolve(self, project_ref: str) -> bool: ...


class SourceService:
    """Program-controlled attribution + read projections for the API layer."""

    def __init__(
        self,
        store: SourceStore,
        *,
        task_store: TaskReader | None = None,
        resolve_path: Callable[[str, bool], Path] | None = None,
        project_resolver: ProjectResolver | None = None,
        intake: IntakeService | None = None,
    ) -> None:
        self._store = store
        self._tasks = task_store
        self._resolve_path = resolve_path
        self._projects = project_resolver
        self._intake = intake or IntakeService(store)

    @property
    def intake(self) -> IntakeService:
        return self._intake

    @property
    def store(self) -> SourceStore:
        return self._store

    # ------------------------------------------------------------- attribution
    def authorize_scope(
        self, *, task_ref: str | None, project_ref: str | None, inbox_ref: str | None
    ) -> None:
        """Validate attribution refs; raise a frozen error when unauthorized."""

        provided = [ref for ref in (task_ref, project_ref, inbox_ref) if ref]
        if len(provided) > 1:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "at most one of task_ref/project_ref/inbox_ref may be set",
                details={"task_ref": task_ref, "project_ref": project_ref, "inbox_ref": inbox_ref},
            )
        if task_ref is not None:
            self._require_task(task_ref)
        if project_ref is not None:
            if self._projects is None or not self._projects.resolve(project_ref):
                # No project registry exists yet; do not pretend it resolves.
                raise AppError(
                    ErrorCode.REFERENCE_INVALID,
                    "project_ref cannot be resolved; no project registry is configured",
                    details={"field": "project_ref", "project_ref": project_ref},
                )
        if inbox_ref is not None:
            self._require_inbox(inbox_ref)

    def _require_task(self, task_ref: str) -> None:
        if self._tasks is None:
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                "task attribution requires an authoritative Task store",
                details={"field": "task_ref", "task_ref": task_ref},
            )
        try:
            self._tasks.read("task", task_ref)
        except EntityNotFound as exc:
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                f"task_ref {task_ref!r} does not resolve to a known Task",
                details={"field": "task_ref", "task_ref": task_ref},
            ) from exc

    def _require_inbox(self, inbox_ref: str) -> None:
        # An inbox is implicitly created by the first message; a ref that does
        # not exist yet is refused so callers cannot invent arbitrary refs.
        from .store import _is_inbox_id  # local import: private helper, same package

        if not _is_inbox_id(inbox_ref):
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                f"inbox_ref {inbox_ref!r} is malformed",
                details={"field": "inbox_ref"},
            )
        path = self._store.inbox_messages_path(inbox_ref)
        if not path.is_file() and not self._store.inbox_attachments_dir(inbox_ref).is_dir():
            raise AppError(
                ErrorCode.REFERENCE_INVALID,
                f"inbox_ref {inbox_ref!r} does not resolve to a controlled inbox",
                details={"field": "inbox_ref", "inbox_ref": inbox_ref},
            )

    # --------------------------------------------------------------- receiving
    def receive_from_path(
        self,
        *,
        request_id: str,
        path: str,
        filename: str | None = None,
        task_ref: str | None = None,
        project_ref: str | None = None,
        inbox_ref: str | None = None,
        title: str | None = None,
        title_origin: str = "user",
        media_type: str | None = None,
        origin_kind: str = "upload",
        external_ref: str | None = None,
        fetched: bool = False,
        payload_hash: str | None = None,
    ) -> ReceiveResult:
        """Read an authorized workspace file and register it as a source."""

        self.authorize_scope(task_ref=task_ref, project_ref=project_ref, inbox_ref=inbox_ref)
        if self._resolve_path is None:
            raise AppError(
                ErrorCode.PATH_OUTSIDE_WORKSPACE,
                "no authorized workspace resolver is configured",
                details={"path": path},
            )
        target = self._resolve_path(path, False)
        if not target.is_file():
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"file {path!r} does not exist",
                details={"path": path},
            )
        data = target.read_bytes()
        if len(data) > MAX_INLINE_BYTES:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "source file exceeds the intake size limit",
                details={"path": path, "max_bytes": MAX_INLINE_BYTES},
            )
        return self._intake.receive(
            ReceiveRequest(
                request_id=request_id,
                filename=filename or target.name,
                data=data,
                media_type=media_type,
                title=title,
                title_origin=title_origin,
                scope_task_ref=task_ref,
                project_ref=project_ref,
                inbox_ref=inbox_ref,
                origin_kind=origin_kind,
                external_ref=external_ref,
                fetched=fetched,
                claimed_payload_hash=payload_hash,
            )
        )

    def receive_inline(
        self,
        *,
        request_id: str,
        filename: str,
        content_base64: str,
        task_ref: str | None = None,
        project_ref: str | None = None,
        inbox_ref: str | None = None,
        title: str | None = None,
        title_origin: str = "user",
        media_type: str | None = None,
        origin_kind: str = "upload",
        external_ref: str | None = None,
        fetched: bool = False,
        payload_hash: str | None = None,
    ) -> ReceiveResult:
        """Register an inline body (bounded, decoded defensively)."""

        self.authorize_scope(task_ref=task_ref, project_ref=project_ref, inbox_ref=inbox_ref)
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "content_base64 is not valid base64",
                details={"field": "content_base64"},
            ) from exc
        if len(data) > MAX_INLINE_BYTES:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "inline source exceeds the intake size limit",
                details={"max_bytes": MAX_INLINE_BYTES},
            )
        return self._intake.receive(
            ReceiveRequest(
                request_id=request_id,
                filename=filename,
                data=data,
                media_type=media_type,
                title=title,
                title_origin=title_origin,
                scope_task_ref=task_ref,
                project_ref=project_ref,
                inbox_ref=inbox_ref,
                origin_kind=origin_kind,
                external_ref=external_ref,
                fetched=fetched,
                claimed_payload_hash=payload_hash,
            )
        )

    # ------------------------------------------------------------------- inbox
    def create_inbox(self) -> str:
        """Create a new controlled inbox id (no Task is created)."""

        inbox_id = new_inbox_id()
        # Materialize the directory so the ref resolves immediately.
        self._store.inbox_attachments_dir(inbox_id).mkdir(parents=True, exist_ok=True)
        return inbox_id

    def append_inbox_message(
        self,
        *,
        inbox_id: str,
        message_id: str,
        content: str,
        attachment_base64: str | None = None,
        attachment_filename: str | None = None,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        """Store one inbox message + optional attachment; never creates a Task."""

        if attachment_base64 is not None:
            data = base64.b64decode(attachment_base64, validate=True)
            if len(data) > MAX_ATTACHMENT_BYTES:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "inbox attachment exceeds the size limit",
                    details={"max_bytes": MAX_ATTACHMENT_BYTES},
                )
            name = sanitize_filename(attachment_filename or "attachment.bin")
            path, digest = self._store.persist_inbox_attachment(inbox_id, name, data)
            attachment = {
                "path": f"attachments/{name}",
                "media_type": media_type,
                "content_hash": digest,
                "bytes": len(data),
            }
        else:
            attachment = None
        return self._store.append_inbox_message(
            inbox_id,
            {
                "message_id": message_id,
                "role": "user",
                "content": content,
                "inbox_ref": inbox_id,
                "attachments": [attachment] if attachment else [],
            },
        )

    def read_inbox(self, inbox_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._store.read_inbox_messages(inbox_id, limit=limit)

    # ---------------------------------------------------------------- read views
    def get_source(self, source_id: str) -> dict[str, Any]:
        record = self._store.read_source(source_id)
        return self._source_view(record)

    def list_sources(
        self,
        *,
        task_ref: str | None = None,
        project_ref: str | None = None,
        inbox_ref: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        records = self._store.list_sources()
        if task_ref is not None:
            records = [r for r in records if r.scope.task_ref == task_ref]
        if project_ref is not None:
            records = [r for r in records if r.scope.project_ref == project_ref]
        if inbox_ref is not None:
            records = [r for r in records if r.scope.inbox_ref == inbox_ref]
        records.sort(key=lambda r: r.source_id)
        if cursor:
            records = [r for r in records if r.source_id > cursor]
        page = records[: max(limit, 0)]
        next_cursor = page[-1].source_id if len(records) > len(page) and page else None
        return {
            "items": [self._source_view(record) for record in page],
            "next_cursor": next_cursor,
        }

    def receipt(self, source_id: str) -> dict[str, Any]:
        record = self._store.read_source(source_id)
        entries: list[ReceiptEntry] = self._store.read_receipts(source_id)
        latest = entries[-1] if entries else None
        return {
            "source_id": source_id,
            "revision": record.revision,
            "status": record.status,
            "source_version": record.source_version,
            "items": [entry.to_dict() for entry in entries],
            "latest": latest.to_dict() if latest else None,
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self._store.read_job(job_id)
        return self._job_view(job)

    # ---------------------------------------------------------------- internals
    def _source_view(self, record: SourceRecord) -> dict[str, Any]:
        entity = record.entity
        scope = record.scope
        return {
            "id": record.source_id,
            "source_id": record.source_id,
            "title": record.title,
            "title_origin": entity.get("title_origin"),
            "status": record.status,
            "revision": record.revision,
            "etag": record.etag,
            "scope": scope.to_dict(),
            "origin": record.origin.to_dict(),
            "content_hash": entity.get("content_hash"),
            "stat_revision": entity.get("stat_revision"),
            "source_version": record.source_version,
            "original": entity.get("original"),
            "derivatives": entity.get("derivatives") or [],
            "formal": entity.get("formal"),
            "index": entity.get("index"),
            "receipt_ref": entity.get("receipt_ref"),
            "created_at": entity.get("created_at"),
            "updated_at": entity.get("updated_at"),
            # Never echo a raw absolute path: expose the source-root-relative one.
            "path": f"sources/{record.source_id}/SOURCE.md",
        }

    def _job_view(self, job: IntakeJobRecord) -> dict[str, Any]:
        entity = job.entity
        return {
            "id": job.job_id,
            "job_id": job.job_id,
            "source_ref": job.source_ref,
            "status": job.status,
            "revision": job.revision,
            "etag": job.etag,
            "request_id": job.request_id,
            "payload_hash": job.payload_hash,
            "stage": job.stage,
            "attempt": entity.get("attempt"),
            "budget": entity.get("budget"),
            "cancel": job.cancel,
            "fail_reason": entity.get("fail_reason"),
            "created_at": entity.get("created_at"),
            "updated_at": entity.get("updated_at"),
        }


def build_source_service(
    *,
    data_dir: Path | str,
    task_store: TaskReader | None = None,
    resolve_path: Callable[[str, bool], Path] | None = None,
    project_resolver: ProjectResolver | None = None,
    clock: Any | None = None,
    events: Any | None = None,
) -> SourceService:
    """Construct a service bound to one data root (single-app wiring helper)."""

    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    store = SourceStore(data_dir, **kwargs)
    intake_kwargs: dict[str, Any] = {}
    if clock is not None:
        intake_kwargs["clock"] = clock
    if events is not None:
        intake_kwargs["events"] = events
    intake = IntakeService(store, **intake_kwargs)
    return SourceService(
        store,
        task_store=task_store,
        resolve_path=resolve_path,
        project_resolver=project_resolver,
        intake=intake,
    )


__all__ = ["SourceService", "ProjectResolver", "TaskReader", "build_source_service", "MAX_INLINE_BYTES"]
