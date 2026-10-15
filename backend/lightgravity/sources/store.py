"""Filesystem source of truth for ``source`` / ``intake_job`` (docs/08 §6.6).

Layout (source-store internal; callers use the service, not paths)::

    <data>/sources/<source_id>/SOURCE.md        # source frontmatter + body
    <data>/sources/<source_id>/original/<name>  # persisted original bytes
    <data>/sources/<source_id>/receipt.jsonl    # per-file receipt (append-only)
    <data>/intake/<job_id>/JOB.md               # intake job frontmatter
    <data>/intake/by-request/<sha>.json         # request_id -> job idempotency map
    <data>/inbox/<inbox_id>/messages.jsonl      # controlled inbox (no Task)
    <data>/inbox/<inbox_id>/attachments/<name>  # controlled inbox originals
    <data>/sources-hash/<scope>/<hash>.json     # scope-local dedup map

Every write reuses LG-004's primitives (``atomic_write_text`` for Markdown,
``append_jsonl`` for logs, ``LockManager`` flock around read-modify-write) so
this is the same durability/locking discipline the rest of the project uses,
not a second authoritative database.  All state is rebuildable from these
files; the dedup/idempotency maps are derived caches that can be deleted and
recomputed by scanning ``<data>/sources`` and ``<data>/intake``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from lightgravity.contracts import AppError, ErrorCode, SCHEMA_NAMESPACE
from lightgravity.store import ConfigInvalid, EntityNotFound, RevisionConflict
from lightgravity.store.atomic import append_jsonl, atomic_write_text, load_jsonl, recover_jsonl
from lightgravity.store.clock import Clock, to_iso, utcnow
from lightgravity.store.frontmatter import merge_maps, parse_document, plain, render_document
from lightgravity.store.ids import new_ulid
from lightgravity.store.locking import LockManager
from lightgravity.store.paths import resolve_workspace_path

from .models import (
    JOB_STAGES,
    JOB_STATUSES,
    LEXICAL_STATES,
    ORIGIN_KINDS,
    SOURCE_STATUSES,
    TITLE_ORIGINS,
    VECTOR_STATES,
    IntakeJobRecord,
    ReceiptEntry,
    SourceRecord,
)

from ruamel.yaml.comments import CommentedMap

#: Only these characters may appear in an original filename we persist.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,199}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
#: Request ids are opaque but must be filesystem-safe for the idempotency map.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")

SOURCE_KIND = "source"
JOB_KIND = "intake_job"


class SourceStore:
    """Authoritative Markdown/JSONL storage for the source-intake entities."""

    def __init__(self, data_dir: Path | str, *, clock: Clock = utcnow) -> None:
        self._data_dir = Path(data_dir)
        self._clock = clock
        self._locks = LockManager(self._data_dir / "locks", default_timeout=10.0)

    # ------------------------------------------------------------------ paths
    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def sources_dir(self) -> Path:
        return self._data_dir / "sources"

    def source_dir(self, source_id: str) -> Path:
        return self.sources_dir() / source_id

    def source_path(self, source_id: str) -> Path:
        return self.source_dir(source_id) / "SOURCE.md"

    def original_dir(self, source_id: str) -> Path:
        return self.source_dir(source_id) / "original"

    def receipt_path(self, source_id: str) -> Path:
        return self.source_dir(source_id) / "receipt.jsonl"

    def intake_dir(self) -> Path:
        return self._data_dir / "intake"

    def job_path(self, job_id: str) -> Path:
        return self.intake_dir() / job_id / "JOB.md"

    def inbox_messages_path(self, inbox_id: str) -> Path:
        return self._data_dir / "inbox" / inbox_id / "messages.jsonl"

    def inbox_attachments_dir(self, inbox_id: str) -> Path:
        return self._data_dir / "inbox" / inbox_id / "attachments"

    # -------------------------------------------------------------- id checks
    @staticmethod
    def _validate_source_id(source_id: str) -> None:
        if not _is_source_id(source_id):
            raise EntityNotFound(SOURCE_KIND, source_id)

    @staticmethod
    def _validate_job_id(job_id: str) -> None:
        if not _is_job_id(job_id):
            raise EntityNotFound(JOB_KIND, job_id)

    @staticmethod
    def new_source_id() -> str:
        # ``source``/``intake`` prefixes are frozen in docs/08 §3.1 but are not
        # runtime kinds the LG-004 store accepts, so the ULID is generated with
        # the same shared helper and prefixed here.
        return f"source_{new_ulid()}"

    @staticmethod
    def new_job_id() -> str:
        return f"intake_{new_ulid()}"

    # ------------------------------------------------------------------- read
    def read_source(self, source_id: str) -> SourceRecord:
        self._validate_source_id(source_id)
        path = self.source_path(source_id)
        if not path.is_file():
            raise EntityNotFound(SOURCE_KIND, source_id, path=str(path))
        text = path.read_text("utf-8")
        raw, body = parse_document(text, source=str(path))
        data = plain(raw)
        diagnostics = validate_source(data, source=str(path))
        if data.get("id") != source_id:
            diagnostics.append(
                _diag("id_path_mismatch", f"id {data.get('id')!r} != {source_id!r}", str(path))
            )
        if diagnostics:
            raise ConfigInvalid(
                f"source {source_id!r} failed validation",
                diagnostics=[d.to_dict() for d in diagnostics],
                location=str(path),
            )
        return SourceRecord(
            source_id=source_id,
            revision=_revision_of(data),
            entity=data,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            body=body,
            path=str(path),
        )

    def read_job(self, job_id: str) -> IntakeJobRecord:
        self._validate_job_id(job_id)
        path = self.job_path(job_id)
        if not path.is_file():
            raise EntityNotFound(JOB_KIND, job_id, path=str(path))
        text = path.read_text("utf-8")
        raw, body = parse_document(text, source=str(path))
        data = plain(raw)
        diagnostics = validate_job(data, source=str(path))
        if data.get("id") != job_id:
            diagnostics.append(
                _diag("id_path_mismatch", f"id {data.get('id')!r} != {job_id!r}", str(path))
            )
        if diagnostics:
            raise ConfigInvalid(
                f"intake_job {job_id!r} failed validation",
                diagnostics=[d.to_dict() for d in diagnostics],
                location=str(path),
            )
        return IntakeJobRecord(
            job_id=job_id,
            revision=_revision_of(data),
            entity=data,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            body=body,
            path=str(path),
        )

    def list_sources(self) -> list[SourceRecord]:
        """Scan the authoritative files; unreadable entries are skipped honestly."""

        root = self.sources_dir()
        if not root.is_dir():
            return []
        records: list[SourceRecord] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not _is_source_id(child.name):
                continue
            try:
                records.append(self.read_source(child.name))
            except (ConfigInvalid, EntityNotFound, AppError):
                continue
        return records

    def list_jobs(self) -> list[IntakeJobRecord]:
        root = self.intake_dir()
        if not root.is_dir():
            return []
        records: list[IntakeJobRecord] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not _is_job_id(child.name):
                continue
            try:
                records.append(self.read_job(child.name))
            except (ConfigInvalid, EntityNotFound, AppError):
                continue
        return records

    # ----------------------------------------------------------------- create
    def create_source(self, source_id: str, content: dict[str, Any], *, body: str = "") -> SourceRecord:
        self._validate_source_id(source_id)
        path = self.source_path(source_id)
        with self._locks.acquire(f"source:{source_id}"):
            if path.exists():
                raise ConfigInvalid(
                    f"source {source_id!r} already exists",
                    diagnostics=[{"code": "duplicate_id", "location": str(path)}],
                    location=str(path),
                )
            raw: Any = CommentedMap()
            merge_maps(raw, dict(content))
            raw["schema"] = SCHEMA_NAMESPACE
            raw["kind"] = SOURCE_KIND
            raw["id"] = source_id
            raw["revision"] = 0
            data = plain(raw)
            _raise_on_errors(SOURCE_KIND, source_id, validate_source(data, source=str(path)), path)
            atomic_write_text(path, render_document(raw, body))
        return self.read_source(source_id)

    def create_job(self, job_id: str, content: dict[str, Any], *, body: str = "") -> IntakeJobRecord:
        self._validate_job_id(job_id)
        path = self.job_path(job_id)
        with self._locks.acquire(f"intake:{job_id}"):
            if path.exists():
                raise ConfigInvalid(
                    f"intake_job {job_id!r} already exists",
                    diagnostics=[{"code": "duplicate_id", "location": str(path)}],
                    location=str(path),
                )
            raw: Any = CommentedMap()
            merge_maps(raw, dict(content))
            raw["schema"] = SCHEMA_NAMESPACE
            raw["kind"] = JOB_KIND
            raw["id"] = job_id
            raw["revision"] = 0
            data = plain(raw)
            _raise_on_errors(JOB_KIND, job_id, validate_job(data, source=str(path)), path)
            atomic_write_text(path, render_document(raw, body))
        return self.read_job(job_id)

    # ------------------------------------------------------------------ write
    def update_source(
        self, source_id: str, updates: dict[str, Any], *, expected_revision: int
    ) -> SourceRecord:
        return self._update(
            kind=SOURCE_KIND,
            entity_id=source_id,
            path=self.source_path(source_id),
            read=self.read_source,
            validate=validate_source,
            updates=updates,
            expected_revision=expected_revision,
        )

    def update_job(
        self, job_id: str, updates: dict[str, Any], *, expected_revision: int
    ) -> IntakeJobRecord:
        return self._update(
            kind=JOB_KIND,
            entity_id=job_id,
            path=self.job_path(job_id),
            read=self.read_job,
            validate=validate_job,
            updates=updates,
            expected_revision=expected_revision,
        )

    def _update(
        self,
        *,
        kind: str,
        entity_id: str,
        path: Path,
        read: Any,
        validate: Any,
        updates: dict[str, Any],
        expected_revision: int,
    ) -> Any:
        lock_key = f"{kind}:{entity_id}"
        with self._locks.acquire(lock_key):
            if not path.is_file():
                raise EntityNotFound(kind, entity_id, path=str(path))
            text = path.read_text("utf-8")
            raw, body = parse_document(text, source=str(path))
            data = plain(raw)
            current = _revision_of(data)
            if current != expected_revision:
                raise RevisionConflict(kind, entity_id, expected=expected_revision, actual=current)
            merge_maps(raw, dict(updates))
            raw["schema"] = SCHEMA_NAMESPACE
            raw["kind"] = kind
            raw["id"] = entity_id
            raw["revision"] = current + 1
            new_data = plain(raw)
            _raise_on_errors(
                kind,
                entity_id,
                validate(new_data, source=str(path)),
                path,
            )
            atomic_write_text(path, render_document(raw, body))
        return read(entity_id)

    # ------------------------------------------------------------- originals
    def persist_original(self, source_id: str, filename: str, data: bytes) -> tuple[Path, str]:
        """Write the original bytes **before** any processing; return (path, sha256).

        This is the "original first, then extract" ordering (docs/09 §4): the
        caller persists, then creates the source/job records.  The write is
        atomic and locked per source.
        """

        self._validate_source_id(source_id)
        safe = sanitize_filename(filename)
        target = self.original_dir(source_id) / safe
        with self._locks.acquire(f"source-original:{source_id}"):
            _atomic_write_bytes(target, data)
        return target, hashlib.sha256(data).hexdigest()

    # -------------------------------------------------------------- receipts
    def append_receipt(self, source_id: str, entry: ReceiptEntry) -> None:
        self._validate_source_id(source_id)
        path = self.receipt_path(source_id)
        with self._locks.acquire(f"source-receipt:{source_id}"):
            recover_jsonl(path)
            append_jsonl(path, entry.to_dict())

    def read_receipts(self, source_id: str) -> list[ReceiptEntry]:
        self._validate_source_id(source_id)
        records, _ = load_jsonl(self.receipt_path(source_id))
        entries: list[ReceiptEntry] = []
        for record in records:
            try:
                entries.append(
                    ReceiptEntry(
                        source_id=str(record.get("source_id", source_id)),
                        filename=str(record.get("filename", "")),
                        status=str(record.get("status", "")),
                        stage=str(record.get("stage", "")),
                        detail=record.get("detail") if isinstance(record.get("detail"), str) else None,
                        searchable=bool(record.get("searchable", False)),
                        original_path=_opt_str(record.get("original_path")),
                        formal_path=_opt_str(record.get("formal_path")),
                        content_hash=_opt_str(record.get("content_hash")),
                        source_version=int(record.get("source_version", 1) or 1),
                        at=str(record.get("at", "")),
                        error_code=_opt_str(record.get("error_code")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return entries

    # ------------------------------------------------------- idempotency map
    def request_job_id(self, request_id: str) -> str | None:
        path = self._request_map_path(request_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = data.get("job_id") if isinstance(data, dict) else None
        return value if isinstance(value, str) and _is_job_id(value) else None

    def record_request(self, request_id: str, job_id: str) -> None:
        path = self._request_map_path(request_id)
        with self._locks.acquire(f"request-map:{_sanitize(request_id)}"):
            if path.exists():
                return
            atomic_write_text(path, json.dumps({"request_id": request_id, "job_id": job_id}))

    def _request_map_path(self, request_id: str) -> Path:
        if not _SAFE_REQUEST_ID.match(request_id or ""):
            raise ConfigInvalid(
                "request_id must be a short filesystem-safe token",
                diagnostics=[{"code": "request_id_invalid", "location": "request_id"}],
            )
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:32]
        return self.data_dir / "intake" / "by-request" / f"{digest}.json"

    # ----------------------------------------------------------------- dedup
    def find_within_scope(self, task_ref: str | None, content_hash: str) -> str | None:
        """Return an existing source id with the same hash inside one scope.

        Dedup is **scope-local** by construction: the map key includes the Task
        ref, so identical bytes arriving under a different Task/source never
        merge, never share authorization (docs/08 §6.6).
        """

        path = self._dedup_path(task_ref, content_hash)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = data.get("source_id") if isinstance(data, dict) else None
        return value if isinstance(value, str) and _is_source_id(value) else None

    def record_dedup(self, task_ref: str | None, content_hash: str, source_id: str) -> None:
        path = self._dedup_path(task_ref, content_hash)
        with self._locks.acquire(f"dedup:{_sanitize(str(task_ref))}:{content_hash[:16]}"):
            if path.exists():
                return
            atomic_write_text(
                path,
                json.dumps(
                    {"task_ref": task_ref, "content_hash": content_hash, "source_id": source_id}
                ),
            )

    def _dedup_path(self, task_ref: str | None, content_hash: str) -> Path:
        if not _SHA256_RE.match(content_hash or ""):
            raise ConfigInvalid("invalid content hash", diagnostics=[{"code": "content_hash_invalid"}])
        scope = task_ref if isinstance(task_ref, str) and task_ref else "global"
        return self.data_dir / "sources-hash" / _sanitize(scope) / f"{content_hash}.json"

    # ----------------------------------------------------------------- inbox
    def resolve_inbox_path(self, inbox_id: str, relative: str, *, write: bool) -> Path:
        """Resolve a path inside one controlled inbox root (no Task implied)."""

        if not _is_inbox_id(inbox_id):
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"inbox {inbox_id!r} does not exist",
                details={"inbox_ref": inbox_id},
            )
        root = self.data_dir / "inbox" / inbox_id
        return resolve_workspace_path(root, relative, write=write)

    def append_inbox_message(self, inbox_id: str, message: dict[str, Any]) -> dict[str, Any]:
        if not _is_inbox_id(inbox_id):
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"inbox {inbox_id!r} does not exist",
                details={"inbox_ref": inbox_id},
            )
        path = self.inbox_messages_path(inbox_id)
        message_id = message.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise ConfigInvalid(
                "message_id is required for idempotent inbox append",
                diagnostics=[{"code": "message_id_missing"}],
            )
        with self._locks.acquire(f"inbox:{inbox_id}"):
            recover_jsonl(path)
            records, _ = load_jsonl(path)
            for record in records:
                if record.get("message_id") == message_id:
                    return record
            last = 0
            for record in records:
                seq = record.get("seq")
                if isinstance(seq, int) and not isinstance(seq, bool) and seq > last:
                    last = seq
            stored = dict(message)
            stored["schema"] = SCHEMA_NAMESPACE
            stored["kind"] = "message"
            stored["inbox_ref"] = inbox_id
            stored.setdefault("at", to_iso(self._clock()))
            stored["seq"] = last + 1
            append_jsonl(path, stored)
        return stored

    def read_inbox_messages(self, inbox_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not _is_inbox_id(inbox_id):
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"inbox {inbox_id!r} does not exist",
                details={"inbox_ref": inbox_id},
            )
        records, _ = load_jsonl(self.inbox_messages_path(inbox_id))
        records.sort(key=lambda record: record.get("seq", 0))
        return records[: max(limit, 0)]

    def persist_inbox_attachment(self, inbox_id: str, filename: str, data: bytes) -> tuple[Path, str]:
        if not _is_inbox_id(inbox_id):
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"inbox {inbox_id!r} does not exist",
                details={"inbox_ref": inbox_id},
            )
        safe = sanitize_filename(filename)
        target = self.inbox_attachments_dir(inbox_id) / safe
        with self._locks.acquire(f"inbox-attachments:{inbox_id}"):
            _atomic_write_bytes(target, data)
        return target, hashlib.sha256(data).hexdigest()

    # -------------------------------------------------------------- recovery
    def recover(self) -> list[str]:
        """Truncate partial JSONL tails; report what was repaired.

        Called at service construction so a crash mid-append cannot make the
        receipt/inbox history unreadable on restart (docs/08 §7, docs/09 §8).
        """

        repaired: list[str] = []
        for path in self._jsonl_files():
            if recover_jsonl(path):
                repaired.append(str(path))
        return repaired

    def _jsonl_files(self) -> Iterable[Path]:
        root = self._data_dir
        if not root.is_dir():
            return []
        return sorted(root.rglob("*.jsonl"))


# --------------------------------------------------------------- validation
def validate_source(data: dict[str, Any], *, source: str) -> list[Any]:
    diagnostics: list[Any] = []
    if data.get("kind") != SOURCE_KIND:
        diagnostics.append(_diag("kind_mismatch", "kind must be 'source'", f"{source}.kind"))
    _check_schema(data, source, diagnostics)
    _check_id(data, source, diagnostics, _is_source_id, "source")
    _check_revision(data, source, diagnostics)
    _check_enum(data, "status", SOURCE_STATUSES, source, diagnostics, default="received")
    _check_enum(data, "title_origin", TITLE_ORIGINS, source, diagnostics, default="user")

    scope = data.get("scope")
    if not isinstance(scope, dict):
        diagnostics.append(_diag("scope_invalid", "scope must be a mapping", f"{source}.scope"))
    else:
        set_targets = [
            key
            for key in ("task_ref", "project_ref", "inbox_ref")
            if isinstance(scope.get(key), str) and scope.get(key)
        ]
        if len(set_targets) > 1:
            diagnostics.append(
                _diag(
                    "scope_conflict",
                    "scope may set at most one of task_ref/project_ref/inbox_ref",
                    f"{source}.scope",
                    targets=set_targets,
                )
            )
        for key in ("task_ref", "project_ref", "inbox_ref"):
            value = scope.get(key)
            if value is not None and not (isinstance(value, str) and value.strip()):
                diagnostics.append(_diag("scope_ref_invalid", f"{key} must be a non-empty string", f"{source}.scope.{key}"))

    origin = data.get("origin")
    if not isinstance(origin, dict):
        diagnostics.append(_diag("origin_invalid", "origin must be a mapping", f"{source}.origin"))
    else:
        _check_enum(origin, "kind", ORIGIN_KINDS, f"{source}.origin", diagnostics, field_key="kind")

    _check_optional_digest(data, "content_hash", source, diagnostics)
    version = data.get("source_version")
    if version is None or isinstance(version, bool) or not isinstance(version, int) or version < 1:
        diagnostics.append(_diag("source_version_invalid", "source_version must be an int >= 1", f"{source}.source_version"))

    index = data.get("index")
    if index is None or not isinstance(index, dict):
        diagnostics.append(_diag("index_invalid", "index must be a mapping", f"{source}.index"))
    else:
        _check_enum(index, "lexical", LEXICAL_STATES, f"{source}.index", diagnostics, required=True)
        _check_enum(index, "vector", VECTOR_STATES, f"{source}.index", diagnostics, required=True)
    return diagnostics


def validate_job(data: dict[str, Any], *, source: str) -> list[Any]:
    diagnostics: list[Any] = []
    if data.get("kind") != JOB_KIND:
        diagnostics.append(_diag("kind_mismatch", "kind must be 'intake_job'", f"{source}.kind"))
    _check_schema(data, source, diagnostics)
    _check_id(data, source, diagnostics, _is_job_id, "intake")
    _check_revision(data, source, diagnostics)
    _check_enum(data, "status", JOB_STATUSES, source, diagnostics, default="queued")
    _check_enum(data, "stage", JOB_STAGES, source, diagnostics, default="received")

    source_ref = data.get("source_ref")
    if not (isinstance(source_ref, str) and _is_source_id(source_ref)):
        diagnostics.append(_diag("source_ref_invalid", "source_ref must be a source id", f"{source}.source_ref"))
    request_id = data.get("request_id")
    if not (isinstance(request_id, str) and _SAFE_REQUEST_ID.match(request_id)):
        diagnostics.append(_diag("request_id_invalid", "request_id is required", f"{source}.request_id"))
    _check_optional_digest(data, "payload_hash", source, diagnostics)

    cancel = data.get("cancel")
    if not isinstance(cancel, dict):
        diagnostics.append(_diag("cancel_invalid", "cancel must be a mapping", f"{source}.cancel"))
    else:
        for key in ("requested", "confirmed"):
            if not isinstance(cancel.get(key, False), bool):
                diagnostics.append(_diag("cancel_flag_invalid", f"cancel.{key} must be a boolean", f"{source}.cancel.{key}"))
    if data.get("status") == "cancelled" and isinstance(cancel, dict) and not cancel.get("confirmed", False):
        diagnostics.append(
            _diag(
                "cancel_unconfirmed",
                "a job may only be cancelled after cancel.confirmed",
                f"{source}.status",
            )
        )
    return diagnostics


# ------------------------------------------------------------------ helpers
def sanitize_filename(filename: str) -> str:
    """Return a safe single-component filename or raise ``validation_failed``."""

    candidate = (filename or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if not candidate or candidate in (".", "..") or not _SAFE_FILENAME.match(candidate):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            "filename is not a safe single path component",
            details={"filename": filename},
        )
    return candidate


def _diag(code: str, message: str, location: str, **detail: Any) -> Any:
    from lightgravity.store.models import Diagnostic

    return Diagnostic(code=code, message=message, location=location, detail=detail)


def _raise_on_errors(kind: str, entity_id: str, diagnostics: list[Any], path: Path) -> None:
    errors = [d for d in diagnostics if getattr(d, "level", "error") == "error"]
    if errors:
        raise ConfigInvalid(
            f"{kind} {entity_id!r} failed validation",
            diagnostics=[d.to_dict() for d in errors],
            location=str(path),
        )


def _check_schema(data: dict[str, Any], source: str, diagnostics: list[Any]) -> None:
    if data.get("schema") != SCHEMA_NAMESPACE:
        diagnostics.append(_diag("schema_unsupported", f"schema must be {SCHEMA_NAMESPACE!r}", f"{source}.schema"))


def _check_id(data: dict[str, Any], source: str, diagnostics: list[Any], predicate: Any, prefix: str) -> None:
    value = data.get("id")
    if not (isinstance(value, str) and predicate(value)):
        diagnostics.append(_diag("id_invalid", f"id must be {prefix}_<ULID>", f"{source}.id"))


def _check_revision(data: dict[str, Any], source: str, diagnostics: list[Any]) -> None:
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        diagnostics.append(_diag("revision_invalid", "revision must be an int >= 0", f"{source}.revision"))


def _check_enum(
    data: dict[str, Any],
    field: str,
    allowed: tuple[str, ...],
    source: str,
    diagnostics: list[Any],
    *,
    default: str | None = None,
    required: bool = False,
    field_key: str | None = None,
) -> None:
    key = field_key or field
    value = data.get(field)
    if value is None and default is not None:
        value = default
    if value is None:
        if required:
            diagnostics.append(_diag(f"{key}_missing", f"{key} is required", f"{source}.{key}"))
        return
    if value not in allowed:
        diagnostics.append(_diag(f"{key}_invalid", f"{key}={value!r} is not supported", f"{source}.{key}"))


def _check_optional_digest(data: dict[str, Any], field: str, source: str, diagnostics: list[Any]) -> None:
    value = data.get(field)
    if value is None:
        return
    if not (isinstance(value, str) and _SHA256_RE.match(value)):
        diagnostics.append(_diag(f"{field}_invalid", f"{field} must be a sha256 hex digest", f"{source}.{field}"))


def _revision_of(data: dict[str, Any]) -> int:
    value = data.get("revision")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _sanitize(key: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)[:180] or "default"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    import os
    import tempfile

    from lightgravity.store.atomic import TEMP_PREFIX

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=TEMP_PREFIX)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _is_source_id(value: object) -> bool:
    return isinstance(value, str) and bool(_SOURCE_ID_RE.match(value))


def _is_job_id(value: object) -> bool:
    return isinstance(value, str) and bool(_JOB_ID_RE.match(value))


def _is_inbox_id(value: object) -> bool:
    return isinstance(value, str) and bool(_INBOX_ID_RE.match(value))


_ULID = r"[0-9A-HJKMNP-TV-Z]{26}"
_SOURCE_ID_RE = re.compile(rf"^source_{_ULID}$")
_JOB_ID_RE = re.compile(rf"^intake_{_ULID}$")
_INBOX_ID_RE = re.compile(rf"^inbox_{_ULID}$")


def new_inbox_id() -> str:
    return f"inbox_{new_ulid()}"


__all__ = [
    "SourceStore",
    "SOURCE_KIND",
    "JOB_KIND",
    "validate_source",
    "validate_job",
    "sanitize_filename",
    "new_inbox_id",
]
