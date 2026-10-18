"""Bounded, process-local worker for deferred source intake (docs/08 §20).

The worker is deliberately *not* a job framework: it repeatedly reads the
authoritative ``intake_job`` files, claims at most ``max_concurrency`` deferred
jobs, and delegates every actual operation to the existing services
(``ProcessingEngine``, ``LexicalSearchService``, ``VectorSearchService``).  There
is no in-memory authoritative queue and no database.

Durability rules kept here:

* queued jobs survive a restart and are picked up again;
* never auto-replay a job interrupted while running;
* cancellation is confirmed only after the run really stopped;
* a stopped/deadline-expired job becomes ``recovery_required``, never success;
* text, keyword and semantic branches fail independently and the receipt shows
  exactly what happened (no fabricated text, no false success).
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.clock import from_iso, to_iso, utcnow
from lightgravity.store.errors import ConfigInvalid, EntityNotFound, RevisionConflict

from .content import ContentStore
from .models import (
    IntakeJobRecord,
    ReceiptEntry,
    SourceRecord,
    normalize_keyword_branch,
    normalize_semantic_branch,
    normalize_text_branch,
    pending_keyword_branch,
    pending_semantic_branch,
    pending_text_branch,
)
from .service import SourceService, _first_branch_error

_IMAGE_PREFIX = "image/"
_AUDIO_PREFIX = "audio/"
_TERMINAL_JOB_STATUSES = ("succeeded", "partial", "failed", "cancelled")


class IntakeWorker:
    """Run deferred jobs with a bounded number of background threads."""

    def __init__(
        self,
        source_service: SourceService,
        *,
        max_concurrency: int = 2,
        poll_interval: float = 0.05,
        stop_timeout: float = 2.0,
        clock: Callable[[], Any] = utcnow,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._service = source_service
        self._max_concurrency = int(max_concurrency)
        self._poll_interval = max(float(poll_interval), 0.01)
        self._stop_timeout = max(float(stop_timeout), 0.0)
        self._clock = clock
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active: dict[str, threading.Thread] = {}
        self._thread: threading.Thread | None = None
        self._started = False

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Recover persisted state, then start pumping queued deferred jobs."""

        with self._lock:
            if self._started and self._thread is not None and self._thread.is_alive():
                return
            self._started = True
            self._stop.clear()
        self._service.intake.recover()
        thread = threading.Thread(
            target=self._run,
            name="lg-intake-worker",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    async def stop(self) -> None:
        """Stop the pump; in-flight jobs are parked as ``recovery_required``."""

        self._stop.set()
        await asyncio.to_thread(self._stop_sync)

    def _stop_sync(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._stop_timeout)
        with self._lock:
            active = list(self._active)
        for job_id in active:
            # A real stop is not a fabricated success: the job outcome is now
            # unknown, so it must be reviewed instead of replayed.
            self._mark_recovery(
                job_id,
                "worker stopped while job was in flight; outcome unknown and not replayed",
            )
        if self._started:
            for job in self._service.store.list_jobs():
                if job.intake_mode != "deferred" or job.status != "running":
                    continue
                self._mark_recovery(
                    job.job_id,
                    "worker stopped while job was in flight; outcome unknown and not replayed",
                )

    # --------------------------------------------------------------- pumping
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._reap()
                self._pump_once()
            except Exception:  # noqa: BLE001 - a transient scan error must not kill the pump
                pass
            self._stop.wait(self._poll_interval)

    def _reap(self) -> None:
        with self._lock:
            done = [job_id for job_id, thread in self._active.items() if not thread.is_alive()]
        if done:
            with self._lock:
                for job_id in done:
                    self._active.pop(job_id, None)

    def _pump_once(self) -> None:
        with self._lock:
            slots = self._max_concurrency - len(self._active)
        jobs = [
            job
            for job in self._service.store.list_jobs()
            if job.status == "queued" and job.intake_mode == "deferred"
        ]
        jobs.sort(key=lambda job: (str(job.entity.get("created_at") or ""), job.job_id))
        for job in jobs:
            if slots <= 0:
                self._service.intake.mark_waiting(job.job_id, reason="worker_limit")
                continue
            if not self._claim(job.job_id):
                continue
            thread = threading.Thread(
                target=self._run_job,
                args=(job.job_id,),
                name=f"lg-intake-{job.job_id[-8:]}",
                daemon=True,
            )
            with self._lock:
                self._active[job.job_id] = thread
            thread.start()
            slots -= 1

    def _claim(self, job_id: str) -> bool:
        try:
            return self._service.intake.start_job(job_id) is not None
        except (RevisionConflict, ConfigInvalid, EntityNotFound):
            return False
        except AppError:
            return False

    def _run_job(self, job_id: str) -> None:
        try:
            self._process_job(job_id)
        except Exception as exc:  # noqa: BLE001 - unknown side effects are parked
            reason = getattr(exc, "message", None) or type(exc).__name__
            self._mark_recovery(job_id, f"intake worker error: {reason}")
        finally:
            with self._lock:
                self._active.pop(job_id, None)

    # --------------------------------------------------------------- one job
    def _process_job(self, job_id: str) -> None:
        job = self._service.store.read_job(job_id)
        source_id = job.source_ref or ""
        source = self._service.store.read_source(source_id)
        if source.status == "archived":
            branches = {
                "text": pending_text_branch(),
                "keyword": pending_keyword_branch(),
                "semantic": pending_semantic_branch(),
            }
            self._finish_interrupted(
                job_id,
                "revoked",
                source,
                branches["text"],
                branches["keyword"],
                branches["semantic"],
            )
            return
        branches, reuse = self._initial_branches(job, source)
        text = branches["text"]
        keyword = branches["keyword"]
        semantic = branches["semantic"]

        # Text branch -------------------------------------------------------
        allow_deadline = False
        if "text" not in reuse:
            text = self._run_text_branch(job, source)
            self._append_receipt(job, source, text, keyword, semantic, stage="extracting")
            if text.get("_stop_unconfirmed"):
                # The real CPU call may still be running. Keep the receipt
                # non-terminal and park the whole job; never replay.
                self._mark_recovery(
                    job_id,
                    "English ASR stop was not confirmed; outcome unknown and not replayed",
                )
                return
            allow_deadline = bool(
                text.get("_confirmed_stop")
                and text.get("status") == "failed"
                and text.get("reason") == "asr_timeout"
            )
            interrupted = self._interruption_reason(job_id)
            if interrupted is not None and not (
                allow_deadline and interrupted == "deadline"
            ):
                self._finish_interrupted(job_id, interrupted, source, text, keyword, semantic)
                return

        # Keyword branch ----------------------------------------------------
        if "keyword" not in reuse:
            keyword = self._run_keyword_branch(job, source, text)
            self._append_receipt(job, source, text, keyword, semantic, stage="indexing")
            interrupted = self._interruption_reason(job_id)
            if interrupted is not None and not (
                allow_deadline and interrupted == "deadline"
            ):
                self._finish_interrupted(
                    job_id,
                    interrupted,
                    source,
                    text,
                    keyword,
                    semantic,
                    allow_deadline=allow_deadline,
                )
                return

        # Semantic branch ---------------------------------------------------
        semantic_recovery: str | None = None
        if "semantic" not in reuse:
            semantic, semantic_recovery = self._run_semantic_branch(job, source, text)
            self._append_receipt(job, source, text, keyword, semantic, stage="indexing")
            # A timeout has an unknown remote outcome, even if a user also
            # requested cancellation. Do not confirm that request as stopped.
            if semantic_recovery is not None:
                self._mark_recovery(job_id, semantic_recovery)
                return
            interrupted = self._interruption_reason(job_id)
            if interrupted is not None and not (
                allow_deadline and interrupted == "deadline"
            ):
                self._finish_interrupted(
                    job_id,
                    interrupted,
                    source,
                    text,
                    keyword,
                    semantic,
                    allow_deadline=allow_deadline,
                )
                return

        self._finish_job(job_id, source, text, keyword, semantic, allow_deadline=allow_deadline)

    # ---------------------------------------------------------- branch rules
    def _initial_branches(
        self, job: IntakeJobRecord, source: SourceRecord
    ) -> tuple[dict[str, Any], set[str]]:
        """Reuse only what is safe: successes on retry, terminal work on replay."""

        prior = self._latest_branches(source)
        reuse: set[str] = set()
        if prior is None:
            return (
                {
                    "text": pending_text_branch(),
                    "keyword": pending_keyword_branch(),
                    "semantic": pending_semantic_branch(),
                },
                reuse,
            )
        if job.attempt == 1 and not self._has_prior_terminal_job(job, source):
            return (
                {
                    "text": pending_text_branch(),
                    "keyword": pending_keyword_branch(),
                    "semantic": pending_semantic_branch(),
                },
                reuse,
            )
        if job.attempt == 1:
            # A duplicate/replayed upload of already-terminal work must not
            # trigger another unbounded OCR/embedding run.
            return prior, {"text", "keyword", "semantic"}

        text = prior["text"]
        keyword = prior["keyword"]
        semantic = prior["semantic"]
        if text["status"] == "ready":
            reuse.add("text")
        else:
            text = pending_text_branch()
        if text["status"] == "ready" and keyword["status"] == "searchable":
            reuse.add("keyword")
        else:
            keyword = pending_keyword_branch()
        if (
            semantic["status"] == "searchable"
            and not semantic.get("failed_kinds")
        ):
            reuse.add("semantic")
        else:
            semantic = pending_semantic_branch()
        return {"text": text, "keyword": keyword, "semantic": semantic}, reuse

    def _latest_branches(self, source: SourceRecord) -> dict[str, Any] | None:
        entries = self._service.store.read_receipts(source.source_id)
        for entry in reversed(entries):
            if entry.source_version != source.source_version:
                continue
            if entry.content_hash not in (None, source.content_digest):
                continue
            explicit = {
                "text": normalize_text_branch(entry.text),
                "keyword": normalize_keyword_branch(entry.keyword),
                "semantic": normalize_semantic_branch(entry.semantic),
            }
            if any(branch["status"] != "pending" for branch in explicit.values()):
                return explicit
            return self._service._infer_branches(source)  # noqa: SLF001
        return None

    def _has_prior_terminal_job(self, job: IntakeJobRecord, source: SourceRecord) -> bool:
        content_hash = source.content_digest
        for other in self._service.store.list_jobs():
            if other.job_id == job.job_id or other.source_ref != source.source_id:
                continue
            if other.entity.get("content_hash") not in (None, content_hash):
                continue
            if other.status in ("succeeded", "partial", "failed"):
                return True
        return False

    def _run_text_branch(
        self, job: IntakeJobRecord, source: SourceRecord
    ) -> dict[str, Any]:
        original = source.entity.get("original")
        original = original if isinstance(original, dict) else {}
        media_type = str(original.get("media_type") or "").split(";", 1)[0].strip().lower()
        origin = source.origin
        if origin.kind == "link" and not origin.fetched:
            return {
                "status": "unavailable",
                "reason": "link_not_fetched",
                "error_code": None,
            }
        if media_type.startswith(_AUDIO_PREFIX):
            return self._run_audio_asr_branch(job, source, media_type)
        processing = self._service.processing
        if processing is None:
            return {
                "status": "failed",
                "reason": "processing_unavailable",
                "error_code": "capability_unavailable",
            }
        try:
            name, data = self._read_original(source)
        except AppError as exc:
            return {
                "status": "failed",
                "reason": exc.message,
                "error_code": exc.code.value,
            }
        native = processing.is_native_text(media_type)
        if not native and not processing.can_process(media_type, data):
            return {
                "status": "unavailable",
                "reason": "no_text_path",
                "error_code": None,
            }
        self._service.intake.set_stage(
            job.job_id,
            stage="extracting",
            branch="text",
            branch_status="extracting",
        )
        try:
            outcome = processing.process(
                source.source_id,
                job_id=None,
                cancel_check=lambda: self._interruption_reason(job.job_id) is not None,
            )
        except AppError as exc:
            return {
                "status": "failed",
                "reason": exc.message,
                "error_code": exc.code.value,
            }
        except Exception as exc:  # noqa: BLE001 - branch isolation, no fake text
            return {
                "status": "failed",
                "reason": f"extraction_error: {type(exc).__name__}",
                "error_code": "internal_error",
            }
        status = str(getattr(outcome, "status", "failed"))
        # LG-224: PDF receipts expose which extractor actually produced the
        # body (embedded text layer vs OCR fallback).  Non-PDF branches keep
        # their existing frozen shape and only add the key when applicable.
        extractor = getattr(outcome, "extractor", None)
        provenance = (
            {"extractor": extractor}
            if media_type == "application/pdf" and isinstance(extractor, str) and extractor
            else {}
        )
        if status == "succeeded":
            return {"status": "ready", "reason": None, "error_code": None, **provenance}
        if status == "partial":
            return {
                "status": "ready",
                "reason": "partial_pages",
                "error_code": None,
                **provenance,
            }
        if status == "cancelled":
            if getattr(outcome, "succeeded_pages", 0) > 0:
                return {
                    "status": "ready",
                    "reason": "partial_pages",
                    "error_code": None,
                    **provenance,
                }
            return pending_text_branch()
        return {
            "status": "failed",
            "reason": getattr(outcome, "reason", None) or "extraction_failed",
            "error_code": "capability_unavailable",
            **provenance,
        }

    def _run_audio_asr_branch(
        self,
        job: IntakeJobRecord,
        source: SourceRecord,
        media_type: str,
    ) -> dict[str, Any]:
        """Run the optional English ASR branch for shared ``audio/*`` material."""

        asr = self._service.english_asr
        if asr is None:
            return {
                "status": "unavailable",
                "reason": "asr_unavailable",
                "error_code": "capability_unavailable",
            }
        max_calls = job.budget.get("max_asr_calls")
        if max_calls is None or (
            isinstance(max_calls, int) and not isinstance(max_calls, bool) and max_calls <= 0
        ):
            self._set_source_text_projection(source, "unavailable", language=None)
            return {
                "status": "unavailable",
                "reason": "asr_disabled",
                "error_code": None,
            }
        try:
            name, data = self._read_original(source)
        except AppError as exc:
            return {
                "status": "failed",
                "reason": exc.message,
                "error_code": exc.code.value,
            }
        self._service.intake.set_stage(
            job.job_id,
            stage="extracting",
            branch="text",
            branch_status="extracting",
        )
        outcome = asr.transcribe(
            data,
            filename=name,
            cancel_check=lambda: self._interruption_reason(job.job_id) is not None,
        )
        if not bool(getattr(outcome, "stop_confirmed", True)):
            self._set_source_text_projection(source, "extracting", language=None)
            return {
                "status": "extracting",
                "reason": "asr_stop_unconfirmed",
                "error_code": getattr(outcome, "error_code", None)
                or "capability_unavailable",
                "_stop_unconfirmed": True,
            }
        status = str(getattr(outcome, "status", "failed"))
        if status == "ready":
            interrupted = self._interruption_reason(job.job_id)
            if interrupted == "deadline":
                # The real call returned, but the job deadline had already
                # expired: this is a confirmed timeout, not a clean transcript.
                self._set_source_text_projection(source, "failed", language=None)
                return {
                    "status": "failed",
                    "reason": "asr_timeout",
                    "error_code": "capability_unavailable",
                    "_confirmed_stop": True,
                }
            if interrupted is not None:
                return {
                    "status": "unavailable",
                    "reason": "cancelled",
                    "error_code": None,
                }
            try:
                self._persist_transcript(source, outcome)
            except AppError as exc:
                self._set_source_text_projection(source, "failed", language=None)
                return {
                    "status": "failed",
                    "reason": "asr_failed",
                    "error_code": exc.code.value,
                }
            except Exception as exc:  # noqa: BLE001 - never fabricate a ready text branch
                self._set_source_text_projection(source, "failed", language=None)
                return {
                    "status": "failed",
                    "reason": f"transcript_persist_error: {type(exc).__name__}",
                    "error_code": "internal_error",
                }
            return {
                "status": "ready",
                "reason": None,
                "error_code": None,
                "language": "en",
                "machine": getattr(outcome, "machine", None),
                "timestamps": None,
            }
        reason = str(getattr(outcome, "reason", None) or "asr_failed")
        if status == "unavailable":
            self._set_source_text_projection(source, "unavailable", language=None)
        else:
            self._set_source_text_projection(source, "failed", language=None)
        branch: dict[str, Any] = {
            "status": "unavailable" if status == "unavailable" else "failed",
            "reason": reason,
            "error_code": getattr(outcome, "error_code", None),
        }
        if reason == "asr_timeout":
            branch["_confirmed_stop"] = True
        return branch

    def _persist_transcript(self, source: SourceRecord, outcome: Any) -> None:
        """Persist the machine transcript derivative + additive provenance."""

        current = self._service.store.read_source(source.source_id)
        if current.status == "archived":
            raise AppError(ErrorCode.NOT_FOUND, "source was revoked during ASR")
        if (
            current.source_version != source.source_version
            or current.content_digest != source.content_digest
        ):
            raise AppError(
                ErrorCode.SOURCE_STALE,
                "source version changed while ASR was running",
            )
        original = current.entity.get("original")
        original = original if isinstance(original, dict) else {}
        rel = original.get("path") if isinstance(original.get("path"), str) else None
        filename = rel.rsplit("/", 1)[-1] if rel else "original"
        machine = getattr(outcome, "machine", None)
        model_version: str = "eg2-reader-v2"
        if isinstance(machine, dict):
            candidate = machine.get("model_version")
            if isinstance(candidate, str) and candidate:
                model_version = candidate
        content = ContentStore(source_root=self._service.store.source_dir(current.source_id))
        written = content.write_transcript(
            current.source_version,
            str(getattr(outcome, "text", "")),
            filename=filename,
            input_sha256=current.content_digest or "",
            model=model_version,
        )
        entry = {
            "kind": "transcript",
            "path": written["markdown_path"],
            "source_version": current.source_version,
            "content_hash": written["markdown_sha256"],
            "model_version": model_version,
        }
        derivatives = current.entity.get("derivatives")
        kept = [
            item
            for item in (derivatives if isinstance(derivatives, list) else [])
            if not (
                isinstance(item, dict)
                and item.get("kind") == "transcript"
                and item.get("source_version") == current.source_version
            )
        ]
        kept.append(entry)
        last: RevisionConflict | None = None
        for _attempt in range(3):
            fresh = self._service.store.read_source(current.source_id)
            existing = fresh.entity.get("derivatives")
            merged = [
                item
                for item in (existing if isinstance(existing, list) else [])
                if not (
                    isinstance(item, dict)
                    and item.get("kind") == "transcript"
                    and item.get("source_version") == fresh.source_version
                )
            ]
            merged.append(entry)
            try:
                self._service.store.update_source(
                    fresh.source_id,
                    {
                        "derivatives": merged,
                        "language": "en",
                        "text_status": "ready",
                        "updated_at": to_iso(self._clock()),
                    },
                    expected_revision=fresh.revision,
                )
                return
            except RevisionConflict as exc:
                last = exc
        # Do not leave a hidden transcript file that the source record does not
        # own after repeated write conflicts.
        content.machine_markdown_path(current.source_version).unlink(missing_ok=True)
        content.pages_path(current.source_version).unlink(missing_ok=True)
        if last is not None:
            raise last

    def _set_source_text_projection(
        self,
        source: SourceRecord,
        state: str,
        *,
        language: str | None,
    ) -> None:
        try:
            current = self._service.store.read_source(source.source_id)
        except (EntityNotFound, ConfigInvalid):
            return
        if current.status == "archived":
            return
        try:
            self._service.store.update_source(
                current.source_id,
                {
                    "language": language,
                    "text_status": state,
                    "updated_at": to_iso(self._clock()),
                },
                expected_revision=current.revision,
            )
        except (RevisionConflict, EntityNotFound, ConfigInvalid):
            return

    def _run_keyword_branch(
        self,
        job: IntakeJobRecord,
        source: SourceRecord,
        text: dict[str, Any],
    ) -> dict[str, Any]:
        if text["status"] != "ready":
            return {
                "status": "no_text",
                "reason": "no_trusted_body",
                "error_code": None,
            }
        lexical = self._service.lexical
        if lexical is None:
            return {
                "status": "failed",
                "reason": "lexical_index_unavailable",
                "error_code": "index_unavailable",
            }
        self._service.intake.set_stage(
            job.job_id,
            stage="indexing",
            branch="keyword",
            branch_status="indexing",
        )
        try:
            result = lexical.index_source(source.source_id)
        except AppError as exc:
            return {
                "status": "failed",
                "reason": exc.details.get("reason") or exc.message,
                "error_code": exc.code.value,
            }
        except Exception as exc:  # noqa: BLE001 - semantic branch still runs
            return {
                "status": "failed",
                "reason": f"lexical_error: {type(exc).__name__}",
                "error_code": "internal_error",
            }
        if isinstance(result, dict) and result.get("indexed") is True:
            return {"status": "searchable", "reason": None, "error_code": None}
        reason = result.get("reason") if isinstance(result, dict) else None
        if reason in ("no_trusted_body", "archived"):
            return {"status": "no_text", "reason": reason, "error_code": None}
        return {
            "status": "failed",
            "reason": reason or "lexical_index_failed",
            "error_code": "index_unavailable",
        }

    def _run_semantic_branch(
        self,
        job: IntakeJobRecord,
        source: SourceRecord,
        text: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        vector = self._service.vector
        if vector is None or not bool(getattr(vector, "enabled", False)):
            self._set_vector_index_state(source, "disabled")
            return (
                {
                    "status": "disabled",
                    "reason": "vector_backend_unavailable",
                    "error_code": None,
                    "model": None,
                    "kinds": [],
                    "failed_kinds": [],
                },
                None,
            )
        inputs = self._semantic_inputs(source, text)
        if not inputs:
            self._set_vector_index_state(source, "not_indexed")
            return (
                {
                    "status": "unsupported",
                    "reason": "no_embeddable_input",
                    "error_code": None,
                    "model": None,
                    "kinds": [],
                    "failed_kinds": [],
                },
                None,
            )
        backend = getattr(vector, "backend", None)
        model = getattr(backend, "model_id", None)
        incompatible = self._cache_incompatibility(vector, model)
        if incompatible is not None:
            self._set_vector_index_state(source, "failed")
            return (
                {
                    "status": "failed",
                    "reason": incompatible,
                    "error_code": "index_unavailable",
                    "model": model if isinstance(model, str) else None,
                    "kinds": [],
                    "failed_kinds": list(inputs),
                },
                None,
            )
        self._service.intake.set_stage(
            job.job_id,
            stage="indexing",
            branch="semantic",
            branch_status="indexing",
        )
        try:
            result = vector.index_source(
                source.source_id,
                cancel_check=lambda: self._interruption_reason(job.job_id) is not None,
            )
        except AppError as exc:
            self._set_vector_index_state(source, "failed")
            reason = str(exc.details.get("reason") or exc.message)
            recovery = (
                "embedding timeout left the outcome unknown; not auto-replayed"
                if "timeout" in reason.lower() or exc.details.get("outcome") == "unknown"
                else None
            )
            return (
                {
                    "status": "failed",
                    "reason": reason,
                    "error_code": exc.code.value,
                    "model": model if isinstance(model, str) else None,
                    "kinds": [],
                    "failed_kinds": list(inputs),
                },
                recovery,
            )
        except Exception as exc:  # noqa: BLE001 - isolate the semantic branch
            self._set_vector_index_state(source, "failed")
            return (
                {
                    "status": "failed",
                    "reason": f"embedding_error: {type(exc).__name__}",
                    "error_code": "internal_error",
                    "model": model if isinstance(model, str) else None,
                    "kinds": [],
                    "failed_kinds": list(inputs),
                },
                None,
            )
        return self._semantic_result(vector, source, inputs, result, model)

    def _semantic_inputs(
        self, source: SourceRecord, text: dict[str, Any]
    ) -> list[str]:
        inputs: list[str] = []
        if text["status"] == "ready" and self._has_trusted_body(source):
            inputs.append("text")
        original = source.entity.get("original")
        original = original if isinstance(original, dict) else {}
        media_type = str(original.get("media_type") or "")
        rel = original.get("path")
        if isinstance(rel, str) and rel and (
            media_type.startswith(_IMAGE_PREFIX) or media_type.startswith(_AUDIO_PREFIX)
        ):
            name = rel.rsplit("/", 1)[-1]
            path = self._service.store.original_dir(source.source_id) / name
            try:
                size = path.stat().st_size
            except OSError:
                size = -1
            if 0 < size <= 10_000_000:
                inputs.append("image" if media_type.startswith(_IMAGE_PREFIX) else "audio")
        return inputs

    def _has_trusted_body(self, source: SourceRecord) -> bool:
        content = ContentStore(source_root=self._service.store.source_dir(source.source_id))
        formal = content.read_formal()
        if formal is not None and formal.strip():
            return True
        pages = content.read_pages(source.source_version)
        if not isinstance(pages, dict):
            return False
        if str(pages.get("status") or "") not in ("succeeded", "partial"):
            return False
        machine = content.read_machine_markdown(source.source_version)
        return machine is not None and bool(machine.strip())

    def _cache_incompatibility(self, vector: Any, model: Any) -> str | None:
        if hasattr(vector, "cache_compatibility_reason"):
            return vector.cache_compatibility_reason()
        index = getattr(vector, "index", None)
        if index is None or not hasattr(index, "exists"):
            return None
        try:
            if not index.exists():
                return None
            if hasattr(index, "readable") and not index.readable():
                return "vector_cache_corrupt"
            header = index.header() if hasattr(index, "header") else {}
        except Exception:  # noqa: BLE001 - an unreadable cache is reported, not crashed
            return "vector_cache_corrupt"
        if not isinstance(header, dict) or not header:
            return None
        if isinstance(model, str) and header.get("model") != model:
            return "model_mismatch_rebuild_required"
        if header.get("cache_version") not in (None, 1):
            return "vector_cache_incompatible_rebuild_required"
        return None

    def _semantic_result(
        self,
        vector: Any,
        source: SourceRecord,
        inputs: list[str],
        result: Any,
        model: Any,
    ) -> tuple[dict[str, Any], str | None]:
        data = result if isinstance(result, dict) else {}
        kinds = [kind for kind in data.get("kinds", []) if kind in ("text", "image", "audio")] if isinstance(data.get("kinds"), list) else []
        failed_kinds = [kind for kind in data.get("failed_kinds", []) if kind in ("text", "image", "audio")] if isinstance(data.get("failed_kinds"), list) else []
        # LG-143 is expected to return the frozen kinds/failed_kinds fields.  The
        # older implementation only returned ``indexed``/``vector``; tolerate it
        # by reading what was actually written to the cache instead of guessing.
        if not kinds:
            index = getattr(vector, "index", None)
            if index is not None and hasattr(index, "entries_for"):
                try:
                    kinds = sorted(
                        {
                            entry.kind
                            for entry in index.entries_for(source.source_id)
                            if entry.source_version == source.source_version
                        }
                    )
                except Exception:  # noqa: BLE001 - cache is a derived projection
                    kinds = []
        indexed = bool(data.get("indexed")) or data.get("vector") == "indexed" or bool(kinds)
        state = data.get("vector")
        reason = data.get("reason") if isinstance(data.get("reason"), str) else None
        recovery = (
            "embedding timeout left the outcome unknown; not auto-replayed"
            if reason is not None and "timeout" in reason.lower()
            else None
        )
        used_model = data.get("model") or data.get("vector_model") or (
            model if isinstance(model, str) else None
        )
        if indexed:
            if not kinds:
                kinds = list(inputs)
            if not failed_kinds:
                failed_kinds = [kind for kind in inputs if kind not in kinds]
            return (
                {
                    "status": "searchable",
                    "reason": reason if recovery is not None else None,
                    "error_code": None,
                    "model": used_model,
                    "kinds": kinds,
                    "failed_kinds": failed_kinds,
                },
                recovery,
            )
        if state == "disabled" or reason in (
            "vector_backend_unavailable",
            "vector_backend_not_configured",
        ):
            status = "disabled"
            self._set_vector_index_state(source, "disabled")
        elif reason in ("no_embeddable_body", "no_embeddable_input"):
            status = "unsupported"
            self._set_vector_index_state(source, "not_indexed")
        else:
            status = "failed"
            self._set_vector_index_state(source, "failed")
        return (
            {
                "status": status,
                "reason": reason or ("vector_index_failed" if status == "failed" else None),
                "error_code": "index_unavailable" if status == "failed" else None,
                "model": used_model if isinstance(used_model, str) else None,
                "kinds": [],
                "failed_kinds": list(inputs) if status == "failed" else [],
            },
            recovery,
        )

    # -------------------------------------------------------------- finishing
    def _finish_job(
        self,
        job_id: str,
        source: SourceRecord,
        text: dict[str, Any],
        keyword: dict[str, Any],
        semantic: dict[str, Any],
        *,
        allow_deadline: bool = False,
    ) -> None:
        interrupted = self._interruption_reason(job_id)
        if interrupted is not None and not (allow_deadline and interrupted == "deadline"):
            self._finish_interrupted(
                job_id,
                interrupted,
                source,
                text,
                keyword,
                semantic,
                allow_deadline=allow_deadline,
            )
            return
        job_status = _job_status(text, keyword, semantic)
        source_status = _source_status(text, semantic, job_status)
        self._update_source_status(source, source_status)
        self._append_receipt(
            self._service.store.read_job(job_id),
            source,
            text,
            keyword,
            semantic,
            stage="done",
        )
        fail_reason = _first_branch_failure(text, keyword, semantic)
        try:
            self._service.intake.set_stage(
                job_id,
                status=job_status,
                stage="done" if job_status in ("succeeded", "partial") else "extracting",
                fail_reason=fail_reason,
                extra={
                    "finished_at": to_iso(self._clock()),
                    "waiting_reason": None,
                },
                branch="receipt",
                branch_status=job_status,
            )
        except RevisionConflict:
            self._finish_interrupted(
                job_id,
                self._interruption_reason(job_id) or "revision_changed",
                source,
                text,
                keyword,
                semantic,
            )

    def _finish_interrupted(
        self,
        job_id: str,
        reason: str,
        source: SourceRecord,
        text: dict[str, Any],
        keyword: dict[str, Any],
        semantic: dict[str, Any],
        *,
        allow_deadline: bool = False,
    ) -> None:
        try:
            job = self._service.store.read_job(job_id)
        except (EntityNotFound, ConfigInvalid):
            return
        if job.status in _TERMINAL_JOB_STATUSES:
            return
        self._append_receipt(job, source, text, keyword, semantic, stage="extracting")
        if reason == "cancelled":
            self._service.intake.confirm_cancel(job_id, reason="cancelled by user")
            return
        if reason == "deadline" and allow_deadline:
            # A timeout whose real CPU call returned/stopped is terminal for the
            # text branch; no model is left running and nothing is replayed.
            self._finish_job(
                job_id,
                source,
                text,
                keyword,
                semantic,
                allow_deadline=True,
            )
            return
        if reason == "revoked":
            self._service.intake.set_stage(
                job_id,
                status="failed",
                fail_reason="source_revoked_during_intake",
                extra={"finished_at": to_iso(self._clock()), "waiting_reason": None},
                branch="receipt",
                branch_status="failed",
            )
            return
        self._mark_recovery(job_id, _recovery_reason(reason))

    def _mark_recovery(self, job_id: str, reason: str) -> None:
        try:
            job = self._service.store.read_job(job_id)
            if job.status in _TERMINAL_JOB_STATUSES:
                return
            self._service.intake.set_stage(
                job_id,
                status="recovery_required",
                fail_reason=reason,
                extra={"finished_at": to_iso(self._clock()), "waiting_reason": None},
            )
        except (RevisionConflict, EntityNotFound, ConfigInvalid, AppError):
            return

    def _set_vector_index_state(self, source: SourceRecord, state: str) -> None:
        try:
            current = self._service.store.read_source(source.source_id)
        except (EntityNotFound, ConfigInvalid):
            return
        if current.status == "archived":
            return
        index = current.entity.get("index")
        index = dict(index) if isinstance(index, dict) else {}
        index["vector"] = state
        index["vector_model"] = None
        try:
            self._service.store.update_source(
                source.source_id,
                {"index": index, "updated_at": to_iso(self._clock())},
                expected_revision=current.revision,
            )
        except (RevisionConflict, EntityNotFound, ConfigInvalid):
            return

    def _update_source_status(self, source: SourceRecord, status: str) -> None:
        try:
            current = self._service.store.read_source(source.source_id)
        except (EntityNotFound, ConfigInvalid):
            return
        if current.status == "archived":
            return  # a revoked source must never be resurrected by intake
        if current.status == status:
            return
        try:
            self._service.store.update_source(
                source.source_id,
                {"status": status, "updated_at": to_iso(self._clock())},
                expected_revision=current.revision,
            )
        except (RevisionConflict, EntityNotFound, ConfigInvalid):
            return

    def _append_receipt(
        self,
        job: IntakeJobRecord,
        source: SourceRecord,
        text: dict[str, Any],
        keyword: dict[str, Any],
        semantic: dict[str, Any],
        *,
        stage: str,
    ) -> None:
        try:
            current = self._service.store.read_source(source.source_id)
        except (EntityNotFound, ConfigInvalid):
            current = source
        original = current.entity.get("original")
        original = original if isinstance(original, dict) else {}
        rel = original.get("path") if isinstance(original.get("path"), str) else None
        filename = rel.rsplit("/", 1)[-1] if rel else "original"
        branches = {
            "text": normalize_text_branch(text),
            "keyword": normalize_keyword_branch(keyword),
            "semantic": normalize_semantic_branch(semantic),
        }
        entry = ReceiptEntry(
            source_id=current.source_id,
            job_id=job.job_id,
            filename=filename,
            status=current.status,
            stage=stage,
            detail=_branch_detail(branches),
            searchable=branches["keyword"]["status"] == "searchable",
            original_path=rel,
            formal_path=(
                f"derivative/machine.v{current.source_version}.md"
                if branches["text"]["status"] == "ready"
                else None
            ),
            content_hash=current.content_digest,
            source_version=current.source_version,
            at=to_iso(self._clock()),
            error_code=_first_branch_error(branches),
            text=branches["text"],
            keyword=branches["keyword"],
            semantic=branches["semantic"],
        )
        self._service.store.append_receipt(current.source_id, entry)

    # -------------------------------------------------------------- stopping
    def _interruption_reason(self, job_id: str) -> str | None:
        try:
            job = self._service.store.read_job(job_id)
        except (EntityNotFound, ConfigInvalid):
            return "missing"
        if job.status in _TERMINAL_JOB_STATUSES:
            return "cancelled" if job.status == "cancelled" else "terminal"
        if job.cancel.get("requested") or job.cancel.get("confirmed"):
            return "cancelled"
        if self._stop.is_set():
            return "stopping"
        deadline = job.entity.get("deadline_at")
        if isinstance(deadline, str) and deadline:
            try:
                if from_iso(deadline) <= self._clock():
                    return "deadline"
            except ValueError:
                pass
        try:
            source = self._service.store.read_source(job.source_ref or "")
        except (EntityNotFound, ConfigInvalid):
            return "missing"
        if source.status == "archived":
            return "revoked"
        return None

    def _read_original(self, source: SourceRecord) -> tuple[str, bytes]:
        original = source.entity.get("original")
        original = original if isinstance(original, dict) else {}
        rel = original.get("path")
        if not isinstance(rel, str) or not rel:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "source has no persisted original to process",
                details={"source_id": source.source_id},
            )
        name = rel.rsplit("/", 1)[-1]
        path = self._service.store.original_dir(source.source_id) / name
        if not path.is_file():
            raise AppError(
                ErrorCode.NOT_FOUND,
                "source original is missing on disk",
                details={"source_id": source.source_id},
            )
        return name, path.read_bytes()


def _job_status(
    text: dict[str, Any], keyword: dict[str, Any], semantic: dict[str, Any]
) -> str:
    succeeded = (
        text["status"] == "ready"
        or keyword["status"] == "searchable"
        or semantic["status"] == "searchable"
    )
    failed = (
        text["status"] == "failed"
        or keyword["status"] == "failed"
        or semantic["status"] == "failed"
    )
    unsuccessful = (
        text["status"] in ("unavailable", "failed")
        or text.get("reason") == "partial_pages"
        or keyword["status"] == "failed"
        or semantic["status"] in ("unsupported", "failed")
        or bool(semantic.get("failed_kinds"))
    )
    if failed and not succeeded:
        return "failed"
    if failed or (succeeded and unsuccessful):
        return "partial"
    return "succeeded"


def _source_status(
    text: dict[str, Any], semantic: dict[str, Any], job_status: str
) -> str:
    if text["status"] == "ready":
        if text.get("reason") == "partial_pages" or job_status == "partial":
            return "partial"
        return "extracted"
    if semantic["status"] == "searchable":
        # A directly embedded media source keeps its receipt shape "extracted"
        # even when there is no ASR/text; a failed text attempt stays partial.
        return "partial" if text["status"] == "failed" else "extracted"
    if job_status == "failed":
        return "failed"
    return "received"


def _first_branch_failure(
    text: dict[str, Any], keyword: dict[str, Any], semantic: dict[str, Any]
) -> str | None:
    for branch in (text, keyword, semantic):
        if branch["status"] in ("failed", "unavailable", "unsupported"):
            return branch.get("reason") or branch["status"]
    return None


def _branch_detail(branches: dict[str, Any]) -> str | None:
    for name in ("text", "keyword", "semantic"):
        branch = branches[name]
        if branch["status"] in ("failed", "unavailable", "unsupported", "disabled", "no_text"):
            return f"{name}: {branch['status']}" + (
                f" ({branch['reason']})" if branch.get("reason") else ""
            )
    return None


def _recovery_reason(reason: str) -> str:
    if reason == "deadline":
        return "intake job deadline exceeded; outcome unknown and not replayed"
    if reason == "missing":
        return "source or job disappeared while running; outcome unknown and not replayed"
    return "worker stopped while job was in flight; outcome unknown and not replayed"


__all__ = ["IntakeWorker"]
