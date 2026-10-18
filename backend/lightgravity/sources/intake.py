"""Recoverable intake-job orchestration (docs/08 §6.6, docs/09 §4/§6/§8).

Responsibilities kept in this module:

* **Original first**: the incoming bytes are persisted under
  ``sources/<id>/original/`` *before* the source/job records exist, so a crash
  never leaves a derived/formal claim pointing at missing source material.
* **Idempotency by ``request_id``**: replaying the same request returns the
  first result; a different payload under the same key is a ``source_conflict``
  (docs/08 §4.2) — never a silent overwrite.
* **Scope-local dedup**: identical content within one Task/global scope reuses
  the same source record; different scope does **not** merge authorization.
* **Source versioning**: ``source_version`` increments only when the content
  hash changes; a stat-revision-only change does not create a new version.
* **Cancel / retry**: cancel is only committed after the job confirms it
  stopped; an unconfirmed cancel records ``cancel.requested`` and reports
  ``cancellation_unconfirmed``.  A job interrupted with unknown side effects is
  never auto-replayed — it becomes ``recovery_required``.
* **Honest stages**: LG-034 receives and attributes.  It does *not* OCR, does
  *not* build an index and never fabricates extracted text; the job therefore
  ends at ``received``/``extracting`` with the status the processors (LG-035)
  will honestly continue from.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.contracts.enums import EventType
from lightgravity.store.clock import Clock, plus_seconds, to_iso, utcnow
from lightgravity.store.errors import ConfigInvalid, EntityNotFound, RevisionConflict

from .models import (
    INTAKE_MODES,
    IntakeJobRecord,
    Origin,
    ReceiptEntry,
    ReceiveResult,
    Scope,
    SourceRecord,
)
from .store import SourceStore, sanitize_filename

#: Payload hashing canonicalisation marker; bumping it invalidates old hashes.
_PAYLOAD_SCHEMA = "lg034.payload.v1"

#: Stage after which the job has fully persisted the original and its records.
_RECEIVED_STAGE = "received"

#: Deferred-intake budget frozen by docs/08 §20.5; LG-230 sets the model-call,
#: OCR-page and embedding-call keys to ``None`` (no limit).  Sync jobs keep the old
#: three-key budget so their on-disk shape and behaviour are unchanged.
DEFERRED_BUDGET: dict[str, Any] = {
    "max_model_calls": None,
    "timeout_seconds": 900,
    "max_retries": 1,
    "max_original_bytes": 10_000_000,
    "max_native_text_bytes": 2_000_000,
    "max_ocr_pages": None,
    "max_tokens_per_page": 2000,
    "max_embedding_calls": None,
    "max_media_embedding_bytes": 10_000_000,
}


class EventSink(Protocol):
    """Minimal append-only event sink (the LG-004 event log satisfies it)."""

    def append_event(self, stream_id: str, event: dict[str, Any]) -> Any: ...


class PayloadHashMismatch(AppError):
    """Same ``request_id`` replayed with a different payload (docs/08 §4.2)."""

    def __init__(self, request_id: str, *, expected: str, actual: str) -> None:
        super().__init__(
            ErrorCode.SOURCE_CONFLICT,
            "request_id was already used with a different payload",
            details={
                "request_id": request_id,
                "expected_payload_hash": expected,
                "actual_payload_hash": actual,
            },
        )
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True, slots=True)
class ReceiveRequest:
    """Normalized, already path-authorized intake request."""

    request_id: str
    filename: str
    data: bytes
    media_type: str | None = None
    title: str | None = None
    title_origin: str = "user"
    scope_task_ref: str | None = None
    project_ref: str | None = None
    inbox_ref: str | None = None
    origin_kind: str = "upload"
    external_ref: str | None = None
    fetched: bool = False
    #: Hash the client *claims*; when present it must match the computed hash.
    claimed_payload_hash: str | None = None
    #: ``sync`` (old behaviour, the frozen default) or ``deferred`` (docs/08
    #: §20.4).  Only the latter is picked up by the intake worker.
    intake_mode: str = "sync"


def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_payload_hash(request: ReceiveRequest) -> str:
    """Deterministic hash of the request *intent* (not just the bytes).

    It deliberately covers scope and origin so the same bytes attributed to a
    different Task is a distinct request, never a cross-scope merge.
    """

    intent: dict[str, Any] = {
        "schema": _PAYLOAD_SCHEMA,
        "content_hash": compute_content_hash(request.data),
        "filename": request.filename,
        "media_type": request.media_type,
        "title": request.title,
        "title_origin": request.title_origin,
        "scope": {
            "task_ref": request.scope_task_ref,
            "project_ref": request.project_ref,
            "inbox_ref": request.inbox_ref,
        },
        "origin": {
            "kind": request.origin_kind,
            "external_ref": request.external_ref,
            "fetched": request.fetched,
        },
    }
    # Keep the historical hash for ``sync`` requests while making a deferred
    # request under the same request_id a detectable payload conflict.
    if request.intake_mode == "deferred":
        intent["intake_mode"] = "deferred"
    canonical = json.dumps(
        intent,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IntakeService:
    """Program-controlled receive + recoverable job state on the file SoT."""

    def __init__(
        self,
        store: SourceStore,
        *,
        clock: Clock = utcnow,
        events: EventSink | None = None,
        asr_enabled: Callable[[], bool] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._events = events
        # 1.20 additive: only decides the new job's ``max_asr_calls`` budget.
        # It never runs inference and is absent for direct/old intake users.
        self._asr_enabled = asr_enabled

    @property
    def store(self) -> SourceStore:
        return self._store

    # ---------------------------------------------------------------- receive
    def receive(self, request: ReceiveRequest) -> ReceiveResult:
        """Persist an original and register a source + job idempotently."""

        if not isinstance(request.data, bytes):
            raise ConfigInvalid(
                "intake payload must be bytes",
                diagnostics=[{"code": "payload_invalid", "location": "data"}],
            )
        if not _SAFE_REQUEST_ID.match(request.request_id or ""):
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "request_id must be a short filesystem-safe token",
                details={"field": "request_id"},
            )
        if request.intake_mode not in INTAKE_MODES:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "intake_mode must be sync or deferred",
                details={"field": "intake_mode", "value": request.intake_mode},
            )
        filename = sanitize_filename(request.filename)
        content_hash = compute_content_hash(request.data)
        if request.claimed_payload_hash is not None:
            claimed = request.claimed_payload_hash
            if not _SHA256_RE.match(claimed):
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "payload_hash must be a sha256 hex digest",
                    details={"field": "payload_hash"},
                )
        payload_hash = compute_payload_hash(request)

        # 1. Idempotency: an already-seen request_id must be byte-identical.
        existing_job_id = self._store.request_job_id(request.request_id)
        if existing_job_id is not None:
            job = self._store.read_job(existing_job_id)
            if job.payload_hash != payload_hash:
                raise PayloadHashMismatch(
                    request.request_id, expected=job.payload_hash or "", actual=payload_hash
                )
            source = self._store.read_source(job.source_ref or "")
            return ReceiveResult(
                source=source,
                job=job,
                deduplicated=True,
                created=False,
                receipts=self._store.read_receipts(source.source_id),
            )

        # 2. Scope-local dedup: same bytes, same scope reuse one source record.
        existing_source_id = self._store.find_within_scope(request.scope_task_ref, content_hash)
        if existing_source_id is not None:
            deduped: SourceRecord | None
            try:
                deduped = self._store.read_source(existing_source_id)
            except (EntityNotFound, ConfigInvalid):
                deduped = None  # stale dedup entry; fall through and rebuild
            if deduped is not None:
                job = self._create_job(
                    deduped.source_id,
                    request_id=request.request_id,
                    payload_hash=payload_hash,
                    content_hash=content_hash,
                    intake_mode=request.intake_mode,
                )
                self._store.record_request(request.request_id, job.job_id)
                receipt = self._emit_received(deduped, job, filename, content_hash, deduplicated=True)
                self._store.append_receipt(deduped.source_id, receipt)
                self._event(EventType.SOURCE_RECEIVED, deduped.source_id, {"deduplicated": True})
                return ReceiveResult(
                    source=deduped,
                    job=job,
                    deduplicated=True,
                    created=False,
                    receipts=[receipt],
                )

        # 3. New source: original bytes are persisted first, then the records.
        source_id = self._store.new_source_id()
        original_path, digest = self._store.persist_original(source_id, filename, request.data)
        assert digest == content_hash
        source = self._create_source(
            source_id, request, filename=filename, content_hash=content_hash
        )
        job = self._create_job(
            source_id,
            request_id=request.request_id,
            payload_hash=payload_hash,
            content_hash=content_hash,
            intake_mode=request.intake_mode,
        )
        self._store.record_request(request.request_id, job.job_id)
        self._store.record_dedup(request.scope_task_ref, content_hash, source_id)
        receipt = self._emit_received(source, job, filename, content_hash, deduplicated=False)
        self._store.append_receipt(source_id, receipt)
        self._event(EventType.SOURCE_RECEIVED, source_id, {"deduplicated": False})
        return ReceiveResult(
            source=source,
            job=job,
            deduplicated=False,
            created=True,
            receipts=[receipt],
        )

    # --------------------------------------------------------- version update
    def record_version(self, source_id: str, data: bytes, *, filename: str | None = None) -> SourceRecord:
        """Persist a new original only when the content hash actually changed.

        A stat/metadata-only change is *not* a new source version (docs/08
        §6.6).  When the hash changes, ``source_version`` increments, the old
        derived/formal references are marked ``stale`` (LG-035/036 will rebuild
        them) and ``source.version_changed`` is emitted.
        """

        source = self._store.read_source(source_id)
        content_hash = compute_content_hash(data)
        if source.content_digest == content_hash:
            return source
        name = filename or _default_filename(source)
        _, digest = self._store.persist_original(source_id, name, data)
        assert digest == content_hash
        index = source.entity.get("index")
        index = index if isinstance(index, dict) else {}
        new_index = dict(index)
        new_index["lexical"] = "stale"
        new_index["lexical_hash"] = None
        updated = self._store.update_source(
            source_id,
            {
                "content_hash": content_hash,
                "source_version": source.source_version + 1,
                "status": "received",
                "index": new_index,
                "updated_at": to_iso(self._clock()),
            },
            expected_revision=source.revision,
        )
        receipt = ReceiptEntry(
            source_id=source_id,
            filename=name,
            status="received",
            stage=_RECEIVED_STAGE,
            detail="original replaced; new source version",
            searchable=False,
            original_path=_relative_original(updated, name),
            formal_path=None,
            content_hash=content_hash,
            source_version=updated.source_version,
            at=to_iso(self._clock()),
        )
        self._store.append_receipt(source_id, receipt)
        self._event(EventType.SOURCE_VERSION_CHANGED, source_id, {"source_version": updated.source_version})
        return updated

    # ------------------------------------------------------------- job control
    def set_stage(
        self,
        job_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        attempt: int | None = None,
        fail_reason: str | None = None,
        extra: dict[str, Any] | None = None,
        branch: str | None = None,
        branch_status: str | None = None,
    ) -> IntakeJobRecord:
        job = self._store.read_job(job_id)
        updates: dict[str, Any] = {"updated_at": to_iso(self._clock())}
        if status is not None:
            updates["status"] = status
        if stage is not None:
            updates["stage"] = stage
        if attempt is not None:
            updates["attempt"] = attempt
        if fail_reason is not None:
            updates["fail_reason"] = fail_reason
        if extra:
            updates.update(extra)
        updated = self._store.update_job(job_id, updates, expected_revision=job.revision)
        if status is not None or stage is not None:
            payload: dict[str, Any] = {
                "job_ref": job_id,
                "status": updated.status,
                "stage": updated.stage,
            }
            if branch is not None:
                payload["branch"] = branch
            if branch_status is not None:
                payload["branch_status"] = branch_status
            self._event(
                EventType.INTAKE_STAGE_CHANGED,
                updated.source_ref or job_id,
                payload,
            )
        if status == "failed":
            payload = {"job_ref": job_id, "reason": fail_reason}
            if branch is not None:
                payload["branch"] = branch
            self._event(EventType.INTAKE_FAILED, updated.source_ref or job_id, payload)
        return updated

    def start_job(self, job_id: str) -> IntakeJobRecord | None:
        """Atomically claim a queued deferred job for this worker.

        ``None`` means another worker/state already claimed it or the job is not
        a deferred job.  The optimistic revision check is the lease: only one
        updater can move ``queued`` to ``running``.
        """

        job = self._store.read_job(job_id)
        if job.status != "queued" or job.intake_mode != "deferred":
            return None
        now = self._clock()
        timeout = _budget_timeout(job)
        extra: dict[str, Any] = {
            "started_at": to_iso(now),
            "waiting_reason": None,
            "deadline_at": (
                to_iso(plus_seconds(now, int(timeout))) if timeout is not None else None
            ),
        }
        try:
            updated = self.set_stage(
                job_id,
                status="running",
                stage="extracting",
                extra=extra,
            )
        except RevisionConflict:
            return None
        return updated

    def mark_waiting(self, job_id: str, *, reason: str = "worker_limit") -> IntakeJobRecord | None:
        """Record why a queued job has not started yet (worker capacity)."""

        try:
            job = self._store.read_job(job_id)
        except (EntityNotFound, ConfigInvalid):
            return None
        if job.status != "queued" or job.entity.get("waiting_reason") == reason:
            return None
        try:
            return self._store.update_job(
                job_id,
                {"waiting_reason": reason, "updated_at": to_iso(self._clock())},
                expected_revision=job.revision,
            )
        except RevisionConflict:
            return None

    def cancel(self, job_id: str, *, confirmed: bool = False, reason: str | None = None) -> IntakeJobRecord:
        """Request (and optionally confirm) cancellation of one job.

        Only a confirmed stop writes ``cancelled``.  An unconfirmed request
        records ``cancel.requested`` and returns ``cancellation_unconfirmed`` so
        the caller retries instead of believing the job stopped (docs/08 §9).
        For deferred jobs a running job is *never* force-written as cancelled on
        the client's confirmation; the worker confirms after it really stops.
        """

        job = self._store.read_job(job_id)
        if job.status in ("succeeded", "partial", "failed", "cancelled"):
            return job  # terminal: idempotent no-op, no resurrect
        cancel = dict(job.cancel)
        cancel["requested"] = True
        deferred_running = job.intake_mode == "deferred" and job.status in (
            "running",
            "recovery_required",
        )
        if not confirmed or deferred_running:
            extra: dict[str, Any] = {"cancel": cancel}
            if deferred_running:
                extra["waiting_reason"] = "cancelling"
            updated = self._store.update_job(
                job_id,
                {**extra, "updated_at": to_iso(self._clock())},
                expected_revision=job.revision,
            )
            raise AppError(
                ErrorCode.CANCELLATION_UNCONFIRMED,
                "intake job cancellation is requested but not yet confirmed",
                details={
                    "job_ref": job_id,
                    "cancel": updated.cancel,
                    "reason": reason,
                },
            )
        cancel["confirmed"] = True
        extra = {
            "cancel": cancel,
            "status": "cancelled",
            "fail_reason": reason,
            "waiting_reason": None,
            "finished_at": to_iso(self._clock()),
        }
        updated = self._store.update_job(
            job_id,
            {**extra, "updated_at": to_iso(self._clock())},
            expected_revision=job.revision,
        )
        self._event(EventType.INTAKE_CANCELLED, updated.source_ref or job_id, {"job_ref": job_id})
        return updated

    def confirm_cancel(self, job_id: str, *, reason: str | None = None) -> IntakeJobRecord:
        """Worker-only: confirm a stop that has actually happened."""

        job = self._store.read_job(job_id)
        if job.status in ("succeeded", "partial", "failed", "cancelled"):
            return job
        cancel = dict(job.cancel)
        cancel["requested"] = True
        cancel["confirmed"] = True
        updated = self._store.update_job(
            job_id,
            {
                "cancel": cancel,
                "status": "cancelled",
                "fail_reason": reason,
                "waiting_reason": None,
                "finished_at": to_iso(self._clock()),
                "updated_at": to_iso(self._clock()),
            },
            expected_revision=job.revision,
        )
        self._event(EventType.INTAKE_CANCELLED, updated.source_ref or job_id, {"job_ref": job_id})
        return updated

    def retry(self, job_id: str) -> IntakeJobRecord:
        """Re-run a *failed/partial* job; unknown side effects are never replayed.

        A job that was interrupted while running (status ``running`` or
        ``recovery_required``) may have produced unknown side effects, so retry
        refuses it and marks ``recovery_required`` instead of silently
        re-executing (docs/08 §9, docs/09 §8).  Deferred jobs enforce the frozen
        attempt budget (initial attempt 1 + ``max_retries``).
        """

        job = self._store.read_job(job_id)
        if job.status in ("running", "recovery_required"):
            if job.status != "recovery_required":
                job = self.set_stage(
                    job_id,
                    status="recovery_required",
                    fail_reason="interrupted with unknown side effects; not auto-replayed",
                    extra={"finished_at": to_iso(self._clock())},
                )
            raise AppError(
                ErrorCode.ILLEGAL_TRANSITION,
                "job was interrupted with unknown side effects and is not auto-replayed",
                details={"job_ref": job_id, "status": job.status},
            )
        if job.status not in ("failed", "partial"):
            raise AppError(
                ErrorCode.ILLEGAL_TRANSITION,
                f"job status {job.status!r} cannot be retried",
                details={"job_ref": job_id, "status": job.status},
            )
        if job.intake_mode == "deferred":
            max_retries = _budget_int(job, "max_retries", 1)
            next_attempt = job.attempt + 1
            if next_attempt > 1 + max_retries:
                raise AppError(
                    ErrorCode.BUDGET_EXHAUSTED,
                    "intake job retry budget is exhausted",
                    details={
                        "job_ref": job_id,
                        "attempt": job.attempt,
                        "max_attempts": 1 + max_retries,
                    },
                )
            extra: dict[str, Any] = {
                "queued_at": to_iso(self._clock()),
                "started_at": None,
                "finished_at": None,
                "deadline_at": None,
                "waiting_reason": None,
                "cancel": {"requested": False, "confirmed": False},
            }
            refreshed_budget = self._refreshed_audio_asr_budget(job)
            if refreshed_budget is not None:
                # LG-222: an old audio job created while ASR was off persisted
                # max_asr_calls=0.  A manual retry after ASR is enabled gets one
                # new bounded attempt; no product-wide call limit is introduced.
                extra["budget"] = refreshed_budget
                extra["reprocess"] = True
            return self.set_stage(
                job_id,
                status="queued",
                stage=_RECEIVED_STAGE,
                attempt=next_attempt,
                fail_reason=None,
                extra=extra,
            )
        return self.set_stage(
            job_id,
            status="queued",
            stage=_RECEIVED_STAGE,
            attempt=job.entity.get("attempt", 1) if isinstance(job.entity.get("attempt"), int) else 1,
            fail_reason=None,
        )

    def create_reprocess_job(
        self, source_id: str, *, asr_enabled: bool
    ) -> IntakeJobRecord:
        """Create one explicit deferred reprocess attempt for an existing source.

        The new job persists its own ``max_asr_calls`` budget (1 when English
        ASR is currently enabled).  It is not an automatic replay: unknown/
        active jobs for the same source are refused, and the resident worker
        still owns concurrency, timeout, cancellation and stop confirmation.
        """

        source = self._store.read_source(source_id)
        if source.status == "archived":
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"source {source_id!r} is revoked and unavailable",
                details={"source_id": source_id, "status": source.status, "revoked": True},
            )
        for existing in self._store.list_jobs():
            if existing.source_ref != source_id:
                continue
            if existing.status in ("queued", "running", "recovery_required"):
                raise AppError(
                    ErrorCode.ILLEGAL_TRANSITION,
                    "source already has an active or unresolved intake job",
                    details={
                        "source_id": source_id,
                        "job_ref": existing.job_id,
                        "status": existing.status,
                    },
                )
        now = to_iso(self._clock())
        job_id = self._store.new_job_id()
        budget = dict(DEFERRED_BUDGET)
        budget["max_asr_calls"] = 1 if asr_enabled else 0
        content: dict[str, Any] = {
            "source_ref": source_id,
            "status": "queued",
            "request_id": f"reprocess-{job_id}",
            "stage": _RECEIVED_STAGE,
            "attempt": 1,
            "cancel": {"requested": False, "confirmed": False},
            "fail_reason": None,
            "created_at": now,
            "updated_at": now,
            "content_hash": source.content_digest,
            "intake_mode": "deferred",
            "queued_at": now,
            "started_at": None,
            "finished_at": None,
            "deadline_at": None,
            "waiting_reason": None,
            "budget": budget,
            # Internal marker: an explicit reprocess is not a duplicate upload,
            # so the worker must not reuse a previously failed text branch.
            "reprocess": True,
        }
        return self._store.create_job(job_id, content)

    def _refreshed_audio_asr_budget(self, job: IntakeJobRecord) -> dict[str, Any] | None:
        """Return a budget with one ASR attempt for an old audio job, if enabled."""

        if self._asr_enabled is None or job.source_ref is None:
            return None
        try:
            source = self._store.read_source(job.source_ref)
        except (EntityNotFound, ConfigInvalid):
            return None
        original = source.entity.get("original")
        original = original if isinstance(original, dict) else {}
        media_type = str(original.get("media_type") or "").split(";", 1)[0].strip().lower()
        if not media_type.startswith("audio/"):
            return None
        current = job.budget.get("max_asr_calls")
        if isinstance(current, int) and not isinstance(current, bool) and current > 0:
            return None
        try:
            enabled = bool(self._asr_enabled())
        except Exception:  # noqa: BLE001 - an optional config failure means off
            enabled = False
        if not enabled:
            return None
        refreshed = dict(job.budget)
        refreshed["max_asr_calls"] = 1
        return refreshed

    def recover(self) -> list[str]:
        """Restart-time recovery: repair JSONL and mark interrupted jobs.

        Running jobs found after a restart cannot prove their side effects, so
        they are moved to ``recovery_required`` (never replayed) and the repair
        list is returned for the caller/log.
        """

        repaired = self._store.recover()
        for job in self._store.list_jobs():
            if job.status != "running":
                continue
            try:
                extra = (
                    {
                        "finished_at": to_iso(self._clock()),
                        "waiting_reason": None,
                    }
                    if job.intake_mode == "deferred"
                    else None
                )
                self.set_stage(
                    job.job_id,
                    status="recovery_required",
                    fail_reason="process restart during running job; not auto-replayed",
                    extra=extra,
                )
            except AppError:
                continue
        return repaired

    # --------------------------------------------------------------- internals
    def _create_source(
        self,
        source_id: str,
        request: ReceiveRequest,
        *,
        filename: str,
        content_hash: str,
    ) -> SourceRecord:
        now = to_iso(self._clock())
        scope = Scope(
            task_ref=request.scope_task_ref,
            project_ref=request.project_ref,
            inbox_ref=request.inbox_ref,
        )
        origin = Origin(
            kind=request.origin_kind,
            external_ref=request.external_ref,
            fetched=request.fetched,
        )
        title = (request.title or "").strip() or filename
        title_origin = request.title_origin if request.title_origin in ("user", "derived") else "user"
        return self._store.create_source(
            source_id,
            {
                "title": title,
                "title_origin": title_origin,
                "status": "received",
                "scope": scope.to_dict(),
                "origin": origin.to_dict(),
                "content_hash": content_hash,
                "stat_revision": None,
                "source_version": 1,
                "original": {
                    "path": f"original/{filename}",
                    "media_type": request.media_type,
                    "bytes": len(request.data),
                    "archived_at": None,
                },
                "derivatives": [],
                "formal": {"path": None, "revision": None, "edited_by": None},
                "index": {
                    "lexical": "not_indexed",
                    "lexical_hash": None,
                    "vector": "disabled",
                    "vector_model": None,
                },
                "archived": False,
                "receipt_ref": "receipt.jsonl",
                "created_at": now,
                "updated_at": now,
            },
        )

    def _create_job(
        self,
        source_id: str,
        *,
        request_id: str,
        payload_hash: str,
        content_hash: str,
        intake_mode: str = "sync",
    ) -> IntakeJobRecord:
        now = to_iso(self._clock())
        content: dict[str, Any] = {
            "source_ref": source_id,
            "status": "queued",
            "request_id": request_id,
            "payload_hash": payload_hash,
            "stage": _RECEIVED_STAGE,
            "attempt": 1,
            "cancel": {"requested": False, "confirmed": False},
            "fail_reason": None,
            "created_at": now,
            "updated_at": now,
            # Non-authoritative convenience for the receipt projection.
            "content_hash": content_hash,
        }
        if intake_mode == "deferred":
            budget = dict(DEFERRED_BUDGET)
            if self._asr_enabled is not None:
                try:
                    enabled = bool(self._asr_enabled())
                except Exception:  # noqa: BLE001 - optional config failure means off
                    enabled = False
                budget["max_asr_calls"] = 1 if enabled else 0
            content.update(
                {
                    "intake_mode": "deferred",
                    "queued_at": now,
                    "started_at": None,
                    "finished_at": None,
                    "deadline_at": None,
                    "waiting_reason": None,
                    "budget": budget,
                }
            )
        else:
            content["budget"] = {
                "max_model_calls": 0,
                "timeout_seconds": None,
                "max_retries": 1,
            }
        return self._store.create_job(self._store.new_job_id(), content)

    def _emit_received(
        self,
        source: SourceRecord,
        job: IntakeJobRecord,
        filename: str,
        content_hash: str,
        *,
        deduplicated: bool,
    ) -> ReceiptEntry:
        original = source.entity.get("original")
        original = original if isinstance(original, dict) else {}
        return ReceiptEntry(
            source_id=source.source_id,
            job_id=job.job_id,
            filename=filename,
            status="received",
            stage=_RECEIVED_STAGE,
            detail=(
                "original already present in this scope; reused"
                if deduplicated
                else "original persisted; extraction not started (LG-035)"
            ),
            searchable=False,  # no lexical index yet (LG-036); never claim otherwise
            original_path=_opt_str(original.get("path")),
            formal_path=None,
            content_hash=content_hash,
            source_version=source.source_version,
            at=to_iso(self._clock()),
        )

    def _event(self, event_type: EventType, stream_id: str, payload: dict[str, Any]) -> None:
        if self._events is None:
            return
        try:
            self._events.append_event(
                stream_id,
                {"type": event_type.value, "actor": "source-intake", "payload": payload},
            )
        except AppError:
            # Event publication is best-effort; the file entities remain the SoT.
            return


def _relative_original(source: SourceRecord, filename: str) -> str:
    return f"original/{filename}"


def _default_filename(source: SourceRecord) -> str:
    original = source.entity.get("original")
    if isinstance(original, dict):
        path = original.get("path")
        if isinstance(path, str) and path:
            return Path(path).name
    return "original"


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _budget_int(job: IntakeJobRecord, key: str, fallback: int) -> int:
    value = job.budget.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _budget_timeout(job: IntakeJobRecord) -> float | None:
    value = job.budget.get("timeout_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


__all__ = [
    "DEFERRED_BUDGET",
    "IntakeService",
    "ReceiveRequest",
    "PayloadHashMismatch",
    "compute_content_hash",
    "compute_payload_hash",
]
