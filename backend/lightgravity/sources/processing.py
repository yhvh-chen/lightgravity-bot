"""OCR processing orchestration for a source (LG-035).

This is the program-controlled job that turns a persisted original into a
machine, traceable Markdown derivative:

1. read the authoritative source record + original bytes (no path escapes);
2. rasterise a PDF into per-page PNGs (or use the image bytes directly);
3. call the configured OCR backend **once per page**, bounded and without
   automatic retry;
4. write ``derivative/machine.v<source_version>.md`` with per-page locators and
   the redacted per-page evidence;
5. update ``source.derivatives``/``status`` from what actually happened.

Honest-failure rules (docs/08 §6.6, docs/09 §6):

* a failed page is recorded as a failure, never as body text;
* a job with some good pages is ``partial``; with none, ``failed``;
* cancellation is only committed after it is confirmed, and the derivative is
  written for the pages that did complete;
* a timeout has an **unknown** outcome and is never automatically replayed;
* the human formal version is never read from or written to here.

Embedding is out of scope: OCR does not use the embedding route and never
pretends vectors are text (docs/09 §7).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.contracts.enums import EventType
from lightgravity.store.clock import Clock, to_iso, utcnow

from .content import (
    ContentStore,
    MachineDraft,
    PageText,
    DERIVATIVE_MACHINE,
    DERIVATIVE_PAGES,
)
from .intake import IntakeService
from .models import SourceRecord
from .ocr import (
    OcrBackend,
    OcrRequest,
    OcrTimeout,
    OcrUnavailable,
    PdfRasterizer,
    PdfiumRasterizer,
    UnavailableOcrBackend,
    is_pdf_bytes,
)
from .store import SourceStore

#: Media types handled by the OCR path.
IMAGE_MEDIA_TYPES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
)


@dataclass(frozen=True, slots=True)
class ProcessingConfig:
    """Bounded work limits for one extraction run (never unbounded)."""

    max_pages: int = 100
    max_tokens_per_page: int = 2000
    scale: float = 2.0


@dataclass(frozen=True, slots=True)
class ProcessingOutcome:
    """What actually happened, for the receipt and the source update."""

    source_id: str
    source_version: int
    status: str  # succeeded | partial | failed | cancelled
    total_pages: int
    succeeded_pages: int
    failed_pages: int
    model: str
    derivative_path: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "status": self.status,
            "total_pages": self.total_pages,
            "succeeded_pages": self.succeeded_pages,
            "failed_pages": self.failed_pages,
            "model": self.model,
            "derivative_path": self.derivative_path,
            "reason": self.reason,
        }


class ProcessingEngine:
    """Program-controlled OCR job over the file SoT."""

    def __init__(
        self,
        store: SourceStore,
        *,
        backend: OcrBackend | None = None,
        rasterizer: PdfRasterizer | None = None,
        config: ProcessingConfig | None = None,
        clock: Clock = utcnow,
        events: Any | None = None,
        intake: IntakeService | None = None,
    ) -> None:
        self._store = store
        self._backend = backend or UnavailableOcrBackend()
        self._rasterizer = rasterizer or PdfiumRasterizer()
        self._config = config or ProcessingConfig()
        self._clock = clock
        self._events = events
        self._intake = intake or IntakeService(store, clock=clock, events=events)

    @property
    def backend_model(self) -> str:
        return self._backend.model_id

    def can_process(self, media_type: str | None, data: bytes) -> bool:
        if is_pdf_bytes(data):
            return True
        return _normalize_media_type(media_type) in IMAGE_MEDIA_TYPES

    # ------------------------------------------------------------------ run
    def process(
        self,
        source_id: str,
        *,
        job_id: str | None = None,
        force: bool = False,
        cancel_check: Any | None = None,
    ) -> ProcessingOutcome:
        """Extract a source into a machine derivative.

        ``job_id`` links the extraction to an intake job so its stage/status are
        updated honestly.  ``cancel_check`` is an optional zero-arg callable the
        caller can use to stop between pages; a confirmed cancel ends the run
        early with the pages that already succeeded.
        """

        source = self._store.read_source(source_id)
        if job_id is not None:
            self._intake.set_stage(job_id, status="running", stage="extracting")

        original_name, original_bytes = self._read_original(source)
        media_type = _original_media_type(source)
        content = ContentStore(source_root=self._store.source_dir(source_id))

        if not self.can_process(media_type, original_bytes):
            return self._finish_unprocessable(
                source, job_id, media_type, reason="unsupported media type for OCR"
            )

        pages = self._rasterize(original_bytes, media_type)
        if not pages:
            return self._fail(source, job_id, "no pages could be rendered")

        total_pages = len(pages)
        results: list[PageText] = []
        cancelled = False
        for page_number, page_bytes in pages:
            if cancel_check is not None and cancel_check():
                cancelled = True
                break
            if job_id is not None:
                self._intake.set_stage(job_id, stage="extracting")
            got = self._ocr_page(
                content=content,
                source=source,
                original_name=original_name,
                page_number=page_number,
                page_bytes=page_bytes,
                media_type=media_type,
            )
            results.append(got)

        draft = self._finalize(
            source=source,
            original_name=original_name,
            results=results,
            total_pages=total_pages,
            cancelled=cancelled,
        )
        written = content.write_machine(draft)
        status = draft.status
        if status in ("succeeded", "partial"):
            self._record_derivatives(source, draft, written)
        if cancelled:
            status = "cancelled"
        self._record_outcome(source, job_id, draft, status)
        return ProcessingOutcome(
            source_id=source.source_id,
            source_version=draft.source_version,
            status=status,
            total_pages=total_pages,
            succeeded_pages=len(draft.succeeded_pages),
            failed_pages=len(draft.failed_pages),
            model=draft.model,
            derivative_path=written["markdown_path"],
            reason=draft.fail_reason,
        )

    # -------------------------------------------------------------- internals
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
        path = self._store.original_dir(source.source_id) / name
        if not path.is_file():
            raise AppError(
                ErrorCode.NOT_FOUND,
                "source original is missing on disk",
                details={"source_id": source.source_id, "original": rel},
            )
        return name, path.read_bytes()

    def _rasterize(self, data: bytes, media_type: str | None) -> list[tuple[int | None, bytes]]:
        if is_pdf_bytes(data):
            rendered = self._rasterizer.render(
                data, scale=self._config.scale, max_pages=self._config.max_pages
            )
            return [(page.page, page.png) for page in rendered]
        # A single image is a single "page"; keep page=None to distinguish it.
        return [(None, data)]

    def _ocr_page(
        self,
        *,
        content: ContentStore,
        source: SourceRecord,
        original_name: str,
        page_number: int | None,
        page_bytes: bytes,
        media_type: str | None,
    ) -> PageText:
        import hashlib
        import time

        request = OcrRequest(
            data=page_bytes,
            media_type="image/png" if is_pdf_bytes(page_bytes) or page_number is not None else _normalize_media_type(media_type) or "image/png",
            page=page_number,
            max_tokens=self._config.max_tokens_per_page,
        )
        started = time.monotonic()
        try:
            result = self._backend.transcribe(request)
        except OcrTimeout as exc:
            self._evidence(
                content, source, original_name, page_number, page_bytes, "timeout", exc.details
            )
            return PageText(
                page=page_number,
                text="",
                input_sha256=hashlib.sha256(page_bytes).hexdigest(),
                model=self._backend.model_id,
                status="timeout",
                error="timeout (outcome unknown; not replayed)",
            )
        except OcrUnavailable as exc:
            self._evidence(
                content, source, original_name, page_number, page_bytes, "unavailable", {"reason": exc.detail}
            )
            return PageText(
                page=page_number,
                text="",
                input_sha256=hashlib.sha256(page_bytes).hexdigest(),
                model=self._backend.model_id,
                status="failed",
                error=f"OCR backend unavailable: {exc.detail}",
            )
        except AppError as exc:
            self._evidence(
                content, source, original_name, page_number, page_bytes, "error", exc.details
            )
            return PageText(
                page=page_number,
                text="",
                input_sha256=hashlib.sha256(page_bytes).hexdigest(),
                model=self._backend.model_id,
                status="failed",
                error=f"{exc.code.value}: {exc.message}",
            )
        self._evidence(
            content,
            source,
            original_name,
            page_number,
            page_bytes,
            "succeeded",
            {
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_seconds": round(time.monotonic() - started, 3),
                "finish_reason": result.finish_reason,
                "raw_response_sha256": hashlib.sha256(result.raw_response.encode("utf-8")).hexdigest(),
            },
        )
        return PageText(
            page=page_number,
            text=result.text,
            input_sha256=result.input_sha256,
            model=result.model,
            status="succeeded",
        )

    def _evidence(
        self,
        content: ContentStore,
        source: SourceRecord,
        original_name: str,
        page_number: int | None,
        page_bytes: bytes,
        outcome: str,
        detail: dict[str, Any] | None,
    ) -> None:
        import hashlib

        content.append_evidence(
            {
                "source_id": source.source_id,
                "source_version": source.source_version,
                "original": original_name,
                "page": page_number,
                "input_sha256": hashlib.sha256(page_bytes).hexdigest(),
                "outcome": outcome,
                "detail": _redact(detail or {}),
                "at": to_iso(self._clock()),
            }
        )

    def _finalize(
        self,
        *,
        source: SourceRecord,
        original_name: str,
        results: list[PageText],
        total_pages: int,
        cancelled: bool,
    ) -> MachineDraft:
        succeeded = [p for p in results if p.status == "succeeded"]
        if cancelled and results:
            status = "partial"
        elif not results:
            status = "failed"
        elif len(succeeded) == total_pages:
            status = "succeeded"
        elif succeeded:
            status = "partial"
        else:
            status = "failed"
        reason: str | None = None
        if status == "failed" and results:
            reason = "all pages failed"
        elif status == "failed":
            reason = "no pages processed"
        elif status == "partial":
            reason = f"{len(results) - len(succeeded)} of {total_pages} pages failed" + (
                "; cancelled" if cancelled else ""
            )
        return MachineDraft(
            source_version=source.source_version,
            filename=original_name,
            model=self._backend.model_id,
            pages=results,
            extractor="lg035-ocr",
            status=status,
            fail_reason=reason,
            total_pages=total_pages,
            cancelled=cancelled,
        )

    def _record_derivatives(
        self, source: SourceRecord, draft: MachineDraft, written: dict[str, Any]
    ) -> None:
        import hashlib

        existing = source.entity.get("derivatives")
        existing = existing if isinstance(existing, list) else []
        # Replace only this source_version's machine derivatives; keep others.
        kept = [
            entry
            for entry in existing
            if not (
                isinstance(entry, dict)
                and entry.get("source_version") == draft.source_version
                and entry.get("kind") in (DERIVATIVE_MACHINE, DERIVATIVE_PAGES)
            )
        ]
        pages_json = self._store.source_dir(source.source_id) / written["pages_path"]
        pages_hash = hashlib.sha256(pages_json.read_bytes()).hexdigest() if pages_json.is_file() else None
        kept.append(
            {
                "kind": DERIVATIVE_MACHINE,
                "path": written["markdown_path"],
                "source_version": draft.source_version,
                "content_hash": written["markdown_sha256"],
                "model_version": draft.model,
            }
        )
        kept.append(
            {
                "kind": DERIVATIVE_PAGES,
                "path": written["pages_path"],
                "source_version": draft.source_version,
                "content_hash": pages_hash,
                "model_version": draft.model,
            }
        )
        index = source.entity.get("index")
        index = dict(index) if isinstance(index, dict) else {}
        index.setdefault("lexical", "not_indexed")
        index.setdefault("lexical_hash", None)
        index.setdefault("vector", "disabled")
        index.setdefault("vector_model", None)
        self._store.update_source(
            source.source_id,
            {
                "derivatives": kept,
                "index": index,
                "updated_at": to_iso(self._clock()),
            },
            expected_revision=source.revision,
        )

    def _record_outcome(
        self, source: SourceRecord, job_id: str | None, draft: MachineDraft, status: str
    ) -> None:
        # Re-read: _record_derivatives may have bumped the revision.
        current = self._store.read_source(source.source_id)
        new_status = {
            "succeeded": "extracted",
            "partial": "partial",
            "failed": "failed",
            "cancelled": "partial" if draft.succeeded_pages else "failed",
        }.get(status, "failed")
        index = current.entity.get("index")
        index = dict(index) if isinstance(index, dict) else {}
        index.setdefault("lexical", "not_indexed")
        index.setdefault("lexical_hash", None)
        index.setdefault("vector", "disabled")
        index.setdefault("vector_model", None)
        self._store.update_source(
            source.source_id,
            {"status": new_status, "index": index, "updated_at": to_iso(self._clock())},
            expected_revision=current.revision,
        )
        if job_id is not None:
            job_status = {
                "succeeded": "succeeded",
                "partial": "partial",
                "failed": "failed",
                "cancelled": "cancelled",
            }.get(status, "failed")
            self._intake.set_stage(
                job_id,
                status=job_status,
                stage="done" if job_status == "succeeded" else "extracting",
                fail_reason=draft.fail_reason,
            )
        self._event(source, status, draft)

    def _finish_unprocessable(
        self, source: SourceRecord, job_id: str | None, media_type: str | None, *, reason: str
    ) -> ProcessingOutcome:
        # Keep the original, record an explicit failure; never fake a body.
        current = self._store.read_source(source.source_id)
        self._store.update_source(
            source.source_id,
            {"status": "failed", "updated_at": to_iso(self._clock())},
            expected_revision=current.revision,
        )
        if job_id is not None:
            self._intake.set_stage(job_id, status="failed", fail_reason=f"{reason}: {media_type}")
        self._event(source, "failed", None)
        return ProcessingOutcome(
            source_id=source.source_id,
            source_version=source.source_version,
            status="failed",
            total_pages=0,
            succeeded_pages=0,
            failed_pages=0,
            model=self._backend.model_id,
            derivative_path=None,
            reason=f"{reason}: {media_type}",
        )

    def _fail(self, source: SourceRecord, job_id: str | None, reason: str) -> ProcessingOutcome:
        current = self._store.read_source(source.source_id)
        self._store.update_source(
            source.source_id,
            {"status": "failed", "updated_at": to_iso(self._clock())},
            expected_revision=current.revision,
        )
        if job_id is not None:
            self._intake.set_stage(job_id, status="failed", fail_reason=reason)
        self._event(source, "failed", None)
        return ProcessingOutcome(
            source_id=source.source_id,
            source_version=source.source_version,
            status="failed",
            total_pages=0,
            succeeded_pages=0,
            failed_pages=0,
            model=self._backend.model_id,
            derivative_path=None,
            reason=reason,
        )

    def _event(self, source: SourceRecord, status: str, draft: MachineDraft | None) -> None:
        if self._events is None:
            return
        from lightgravity.contracts import AppError as _AppError

        try:
            self._events.append_event(
                source.source_id,
                {
                    "type": EventType.SOURCE_ATTRIBUTED.value
                    if status in ("succeeded", "partial")
                    else EventType.INTAKE_FAILED.value,
                    "actor": "source-ocr",
                    "payload": {
                        "source_version": source.source_version,
                        "status": status,
                        "model": self._backend.model_id,
                        "pages": len(draft.pages) if draft else 0,
                    },
                },
            )
        except _AppError:
            return


def _normalize_media_type(media_type: str | None) -> str | None:
    if not media_type:
        return None
    return media_type.split(";", 1)[0].strip().lower() or None


def _original_media_type(source: SourceRecord) -> str | None:
    original = source.entity.get("original")
    if isinstance(original, dict):
        value = original.get("media_type")
        if isinstance(value, str):
            return value
    return None


def _redact(detail: dict[str, Any]) -> dict[str, Any]:
    """Drop anything that could carry credentials or huge image payloads."""

    blocked = {"authorization", "api_key", "token", "bearer", "base64", "image", "data_url"}
    clean: dict[str, Any] = {}
    for key, value in detail.items():
        if key.lower() in blocked:
            clean[key] = "[redacted]"
        elif isinstance(value, str) and len(value) > 2000:
            clean[key] = value[:2000] + "…[truncated]"
        else:
            clean[key] = value
    return clean


def encode_data_url(data: bytes, media_type: str) -> str:
    """Expose the exact data-URL form for tests without importing private helpers."""

    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


__all__ = [
    "IMAGE_MEDIA_TYPES",
    "ProcessingConfig",
    "ProcessingEngine",
    "ProcessingOutcome",
    "encode_data_url",
]
