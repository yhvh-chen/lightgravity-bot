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
from lightgravity.store.clock import to_iso, utcnow
from lightgravity.store.errors import EntityNotFound, RevisionConflict

from .intake import IntakeService, ReceiveRequest
from .models import IntakeJobRecord, ReceiptEntry, ReceiveResult, SourceRecord
from .processing import ProcessingEngine
from .store import SourceStore, new_inbox_id, sanitize_filename


def _now(intake: IntakeService) -> Any:
    """Return the current instant (indirect for testability, unused argument kept)."""

    return utcnow()


def _expected(record: SourceRecord, expected_revision: int | None) -> int:
    """Resolve the optimistic-concurrency revision for an action.

    Callers may pass an explicit ``expected_revision`` (409 on mismatch); when
    omitted the action uses the revision just read, preserving the existing
    last-writer-conflict detection under the store lock.
    """

    return record.revision if expected_revision is None else expected_revision

#: ``source.status`` value written by ``revoke`` (docs/08 §6.6).  This is the
#: revoke marker: a *revoked* source is **unavailable** and must refuse to
#: serve its bytes/derivatives.  It is deliberately distinct from the additive
#: reversible ``archived`` boolean flag, which keeps the source openable and
#: searchable (``archive``/``unarchive`` never touch ``status``).
REVOKED_STATUS = "archived"


def _ensure_available(record: SourceRecord) -> None:
    """Fail closed when a source has been revoked (docs/08 §6.6).

    ``revoke`` preserves the original bytes on disk (unlike ``delete``) but the
    material must be **unavailable**: no preview/download of any content kind,
    and no reprocess/formal write that could resurrect its availability.  The
    record is not disclosed as existing, so the refusal is the same
    ``not_found`` a client already handles after ``delete`` (docs/08 §4.2);
    ``details.revoked`` lets diagnostics distinguish the two without leaking
    content.  Reads never stream a single byte of a revoked source.
    """

    if record.status == REVOKED_STATUS:
        raise AppError(
            ErrorCode.NOT_FOUND,
            f"source {record.source_id!r} is revoked and unavailable",
            details={
                "source_id": record.source_id,
                "status": record.status,
                "revoked": True,
            },
        )


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
        processing: ProcessingEngine | None = None,
        lexical: Any | None = None,
        events: Any | None = None,
    ) -> None:
        self._store = store
        self._tasks = task_store
        self._resolve_path = resolve_path
        self._projects = project_resolver
        self._intake = intake or IntakeService(store)
        self._processing = processing
        self._lexical = lexical
        self._events = events

    @property
    def intake(self) -> IntakeService:
        return self._intake

    @property
    def processing(self) -> ProcessingEngine | None:
        return self._processing

    @property
    def lexical(self) -> Any | None:
        """The optional LG-036 lexical index/search service (None when unwired)."""

        return self._lexical

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

    # ------------------------------------------------------------- processing
    def process_source(
        self,
        source_id: str,
        *,
        job_id: str | None = None,
        force: bool = False,
        cancel_check: Any | None = None,
    ) -> dict[str, Any]:
        """Run OCR extraction into a machine derivative (never the formal one)."""

        if self._processing is None:
            from .ocr import UnavailableOcrBackend
            from .processing import ProcessingEngine

            self._processing = ProcessingEngine(
                self._store,
                backend=UnavailableOcrBackend("no OCR backend configured for this service"),
                intake=self._intake,
            )
        outcome = self._processing.process(
            source_id, job_id=job_id, force=force, cancel_check=cancel_check
        )
        return outcome.to_dict()

    def _content_store(self, source_id: str) -> Any:
        from .content import ContentStore

        return ContentStore(source_root=self._store.source_dir(source_id))

    def content_view(self, source_id: str, *, kind: str = "auto") -> dict[str, Any]:
        """Preview the formal version if present, else the machine derivative.

        Reading never mutates state and never executes content (docs/08 §4.3).
        """

        record = self._store.read_source(source_id)
        _ensure_available(record)
        content = self._content_store(source_id)
        formal = content.read_formal()
        machine = content.read_machine_markdown(record.source_version)
        wanted = kind
        if wanted == "auto":
            wanted = "formal" if formal is not None else "machine"
        if wanted == "formal":
            body = formal
            path = content.formal_relative_path() if body is not None else None
        elif wanted == "machine":
            body = machine
            path = (
                f"derivative/machine.v{record.source_version}.md" if body is not None else None
            )
        else:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "kind must be one of: auto, formal, machine",
                details={"kind": kind},
            )
        if body is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"no {wanted} content exists for source {source_id!r}",
                details={"source_id": source_id, "kind": wanted},
            )
        return {
            "source_id": source_id,
            "kind": wanted,
            "path": path,
            "media_type": "text/markdown; charset=utf-8",
            "content": body,
            "formal_present": formal is not None,
        }

    def download_view(self, source_id: str, *, kind: str = "original") -> dict[str, Any]:
        """Return the original bytes plus a **stat**-type revision (not a hash)."""

        record = self._store.read_source(source_id)
        _ensure_available(record)
        if kind == "original":
            original = record.entity.get("original")
            original = original if isinstance(original, dict) else {}
            rel = original.get("path")
            if not isinstance(rel, str) or not rel:
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "source has no persisted original",
                    details={"source_id": source_id},
                )
            name = rel.rsplit("/", 1)[-1]
            path = self._store.original_dir(source_id) / name
            if not path.is_file():
                raise AppError(
                    ErrorCode.NOT_FOUND,
                    "original bytes are missing on disk",
                    details={"source_id": source_id},
                )
            stat = path.stat()
            return {
                "source_id": source_id,
                "kind": "original",
                "filename": name,
                "media_type": original.get("media_type") or "application/octet-stream",
                "bytes": path.read_bytes(),
                "stat_revision": f"{stat.st_size}-{stat.st_mtime_ns}",
                "content_hash": record.content_digest,
            }
        # Formal/machine download is served as text content, not raw bytes.
        view = self.content_view(source_id, kind=kind)
        return {
            "source_id": source_id,
            "kind": view["kind"],
            "filename": view["path"].rsplit("/", 1)[-1] if view["path"] else "content.md",
            "media_type": view["media_type"],
            "bytes": view["content"].encode("utf-8"),
            "stat_revision": f"{record.revision}",
            "content_hash": None,
        }

    # ----------------------------------------------------------- formal edits
    def edit_formal(
        self,
        source_id: str,
        *,
        content: str,
        edited_by: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Create/update the human formal version and record it on the source.

        The **machine derivative is untouched**: this is the separation that
        makes reprocessing non-destructive (docs/08 §6.6).
        """

        record = self._store.read_source(source_id)
        _ensure_available(record)
        content_store = self._content_store(source_id)
        formal = record.entity.get("formal")
        formal = formal if isinstance(formal, dict) else {}
        current_revision = formal.get("revision")
        current_revision = (
            current_revision
            if isinstance(current_revision, int) and not isinstance(current_revision, bool)
            else 0
        )
        if expected_revision is not None and expected_revision != current_revision:
            raise AppError(
                ErrorCode.REVISION_CONFLICT,
                "formal version revision does not match",
                details={
                    "expected": expected_revision,
                    "actual": current_revision,
                    "source_id": source_id,
                },
            )
        if not content_store.has_formal():
            # Seed once from the current machine derivative, then apply the edit.
            content_store.initialize_formal_from_machine(record.source_version, edited_by=edited_by)
        new_revision = current_revision + 1
        content_store.write_formal(content, edited_by=edited_by, expected_revision=current_revision)
        updated = self._store.update_source(
            source_id,
            {
                "formal": {
                    "path": content_store.formal_relative_path(),
                    "revision": new_revision,
                    "edited_by": edited_by,
                },
                "title_origin": record.entity.get("title_origin", "user"),
                "updated_at": to_iso(_now(self._intake)),
            },
            expected_revision=record.revision,
        )
        self._reindex(source_id)
        return {
            "source_id": source_id,
            "formal": updated.entity.get("formal"),
            "revision": updated.revision,
        }

    def source_actions(
        self,
        source_id: str,
        *,
        action: str,
        confirmed: bool = False,
        job_id: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Control actions: ``reprocess``/``cancel``/``archive``/``unarchive``/``revoke``/``delete``.

        ``reprocess`` re-runs OCR into a new machine derivative and never
        overwrites the formal version.  ``delete``/``revoke`` make the source
        unavailable (``status=archived`` + cache/hit invalidation); the original
        is preserved for ``revoke`` and removed only for an explicit ``delete``.

        ``archive``/``unarchive`` are the **reversible整理** actions: they only
        toggle the additive ``archived`` flag and never touch ``status``, the
        index, retrieval or opening.  A reversible archive must **not** be
        conflated with ``revoke``:撤销 makes the source unavailable, while
        archiving merely tidies it away from default listings.
        """

        record = self._store.read_source(source_id)
        if action == "reprocess":
            # A revoked source must not be resurrected by reprocessing: the
            # processing path rewrites ``status`` (and can re-index), which
            # would undo the revocation.  Fail closed instead.
            _ensure_available(record)
            return self.process_source(source_id, job_id=job_id, force=True)
        if action == "cancel":
            if job_id is None:
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "cancel requires the intake job_id being cancelled",
                    details={"source_id": source_id},
                )
            job = self._intake.cancel(job_id, confirmed=confirmed, reason="source cancel")
            return {"source_id": source_id, "job_id": job_id, "status": job.status, "confirmed": True}
        if action == "archive":
            # Reversible organizational archive: keeps status/index/retrieval
            # intact; only sets the additive flag.  Never invalidates hits.
            updated = self._store.update_source(
                source_id,
                {"archived": True, "updated_at": to_iso(_now(self._intake))},
                expected_revision=_expected(record, expected_revision),
            )
            return {"source_id": source_id, "status": updated.status, "archived": True}
        if action == "unarchive":
            updated = self._store.update_source(
                source_id,
                {"archived": False, "updated_at": to_iso(_now(self._intake))},
                expected_revision=_expected(record, expected_revision),
            )
            return {"source_id": source_id, "status": updated.status, "archived": False}
        if action == "revoke":
            updated = self._store.update_source(
                source_id,
                {
                    "status": "archived",
                    "index": {
                        "lexical": "not_indexed",
                        "lexical_hash": None,
                        "vector": "disabled",
                        "vector_model": None,
                    },
                    "updated_at": to_iso(_now(self._intake)),
                },
                expected_revision=record.revision,
            )
            # Invalidate old hits: the archived source must not return results.
            self._invalidate_index(source_id, reason="revoked")
            return {"source_id": source_id, "status": updated.status, "revoked": True}
        if action == "delete":
            if not confirmed:
                raise AppError(
                    ErrorCode.CANCELLATION_UNCONFIRMED,
                    "delete must be confirmed",
                    details={"source_id": source_id},
                )
            self._invalidate_index(source_id, reason="deleted")
            self._delete_source(source_id)
            return {"source_id": source_id, "deleted": True}
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            f"unsupported action {action!r}; supported: reprocess, cancel, archive, unarchive, revoke, delete",
            details={"action": action},
        )

    # ---------------------------------------------------- lexical index hooks
    def _reindex(self, source_id: str) -> None:
        """Best-effort re-index hook after a human formal edit (LG-036).

        The file SoT is authoritative; a missing/corrupt cache never blocks the
        formal write, it only means search reports ``index_unavailable``.
        """

        if self._lexical is None:
            return
        try:
            self._lexical.index_source(source_id)
        except (AppError, RevisionConflict):
            # The cache is a派生; a failed/busy index never blocks the file write
            # (search then honestly reports index_unavailable/not_indexed).
            return

    def _invalidate_index(self, source_id: str, *, reason: str) -> None:
        """Drop a source from the lexical cache so old hits cannot be returned."""

        if self._lexical is None:
            return
        try:
            self._lexical.remove(source_id, reason=reason)
        except (AppError, RevisionConflict):
            return

    def search(self, request: Any) -> dict[str, Any]:
        """Run a lexical search (delegates to the LG-036 service when wired)."""

        if self._lexical is None:
            from .lexical import LexicalSearchService

            self._lexical = LexicalSearchService(
                self._store, task_store=self._tasks, events=self._events
            )
        return self._lexical.search(request)

    def _delete_source(self, source_id: str) -> None:
        import shutil

        self._store._validate_source_id(source_id)  # noqa: SLF001 - same package
        root = self._store.source_dir(source_id)
        if not root.is_dir():
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} not found",
                details={"source_id": source_id},
            )
        shutil.rmtree(root)

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
            "archived": record.archived,
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
    ocr_backend: Any | None = None,
) -> SourceService:
    """Construct a service bound to one data root (single-app wiring helper)."""

    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    store = SourceStore(data_dir, **kwargs)
    from .lexical import LexicalSearchService

    lexical = LexicalSearchService(
        store,
        task_store=task_store,
        events=events,
    )
    intake_kwargs: dict[str, Any] = {}
    if clock is not None:
        intake_kwargs["clock"] = clock
    if events is not None:
        intake_kwargs["events"] = events
    intake = IntakeService(store, **intake_kwargs)
    processing_kwargs: dict[str, Any] = {}
    if clock is not None:
        processing_kwargs["clock"] = clock
    if events is not None:
        processing_kwargs["events"] = events
    if ocr_backend is None:
        from .ocr import backend_from_env

        ocr_backend = backend_from_env()
    from .processing import ProcessingConfig

    # Compose the optional render scale from the environment into the *actual*
    # product processing path so an explicit ``LIGHTGRAVITY_OCR_SCALE`` reaches
    # the real ``PdfiumRasterizer`` (not just a standalone backend test).
    # Absent/empty keeps the default 2.0; an invalid value raises an explicit
    # diagnostic here instead of silently falling back.
    processing = ProcessingEngine(
        store,
        backend=ocr_backend,
        intake=intake,
        config=ProcessingConfig.from_env(),
        **processing_kwargs,
    )
    return SourceService(
        store,
        task_store=task_store,
        resolve_path=resolve_path,
        project_resolver=project_resolver,
        intake=intake,
        processing=processing,
        lexical=lexical,
        events=events,
    )


__all__ = ["SourceService", "ProjectResolver", "TaskReader", "build_source_service", "MAX_INLINE_BYTES"]
