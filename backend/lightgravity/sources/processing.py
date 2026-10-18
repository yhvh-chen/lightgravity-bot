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
    PDF_TEXT_LAYER_EXTRACTOR,
    PDF_TEXT_LAYER_OCR_EXTRACTOR,
)
from .intake import IntakeService
from .models import SourceRecord
from .ocr import (
    OCR_PROMPT,
    OCR_TABLE_PROMPT,
    OcrBackend,
    OcrRequest,
    OcrTimeout,
    OcrUnavailable,
    OcrTableModeInvalid,
    PdfRasterizer,
    PdfiumRasterizer,
    UnavailableOcrBackend,
    classify_image_bytes,
    is_pdf_bytes,
    parse_scale_env,
    parse_table_mode_env,
)
from .ocr.text import (
    MIN_TEXT_LAYER_CHARS,
    PDF_TEXT_LAYER_EXTRACTOR as TEXT_LAYER_EXTRACTOR,
    PDF_TEXT_LAYER_MODEL,
    PdfTextLayerExtractor,
    PdfiumTextLayerExtractor,
    is_sparse_text_layer,
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

#: Media types handled by the **native, model-free** UTF-8 text path.
#: These are read directly as UTF-8 (no OCR, no model, no network) and written
#: as a machine derivative.  Everything else still goes through OCR/unsupported.
NATIVE_TEXT_MEDIA_TYPES = (
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/x-log",
    "application/x-ndjson",
)

#: Bound on the native-text body accepted for extraction (bytes).  A larger
#: original is refused honestly (never truncated silently into a fake body).
NATIVE_TEXT_MAX_BYTES = 2_000_000

#: Extractor/model provenance recorded for a native text derivative.
NATIVE_TEXT_EXTRACTOR = "native-utf8-text"
NATIVE_TEXT_MODEL = "none"


@dataclass(frozen=True, slots=True)
class ProcessingConfig:
    """Bounded work limits for one extraction run (never unbounded).

    ``scale`` is the PDF page-render scale passed to the product rasteriser.
    The PDF user unit is 1/72 inch, so the default ``2.0`` renders at ~144 DPI
    (the historical value, documented as "~150 DPI").  It can be overridden
    additively via the optional ``LIGHTGRAVITY_OCR_SCALE`` env var through
    :meth:`from_env`; absent/empty keeps the default unchanged and any invalid
    value is rejected with an explicit diagnostic (never silently clamped).
    """

    max_pages: int | None = None
    max_tokens_per_page: int = 2000
    scale: float = 2.0
    #: PDF pages with fewer visible characters than this use OCR fallback.
    #: Electronic pages with a real text layer never call OCR (LG-224).
    min_text_layer_chars: int = MIN_TEXT_LAYER_CHARS
    #: Optional, **default OFF** table-aware OCR mode.  When False (the
    #: default) every page uses the unchanged default prompt, so ordinary pages
    #: and existing behaviour are byte-for-byte unchanged.  When True, a page is
    #: first passed through the program-side, model-free layout classifier and the
    #: explicit-grid table prompt is used **only** for pages confidently
    #: identified as an actual ruled table; ordinary pages still use the default
    #: prompt (R5 showed a global prompt swap regresses ordinary pages).
    table_mode: bool = False

    @classmethod
    def from_env(cls, env: Any = None) -> "ProcessingConfig":
        """Build the config from the environment, keeping default behaviour.

        Reads the optional render ``scale`` and the optional ``table_mode`` flag.
        Page/token bounds stay code defaults; this does **not** widen any work
        limit.  An invalid ``table_mode`` value is rejected with an explicit
        diagnostic instead of being silently ignored.
        """

        import os

        source = os.environ if env is None else env
        scale = parse_scale_env(source, default=ProcessingConfig().scale)
        table_mode = parse_table_mode_env(source, default=ProcessingConfig().table_mode)
        return ProcessingConfig(scale=scale, table_mode=table_mode)


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
    #: Honest extraction provenance: ``pdfium-text-layer``, ``lg035-ocr``,
    #: ``pdfium-text-layer+ocr``, ``native-utf8-text`` or ``None``.
    extractor: str | None = None
    #: LG-222 additive: this failed attempt did **not** overwrite a previously
    #: usable machine body.  The old body/index remain in place.
    preserved_existing_body: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "status": self.status,
            "total_pages": self.total_pages,
            "succeeded_pages": self.succeeded_pages,
            "failed_pages": self.failed_pages,
            "model": self.model,
            "extractor": self.extractor,
            "derivative_path": self.derivative_path,
            "reason": self.reason,
            "preserved_existing_body": self.preserved_existing_body,
        }


class ProcessingEngine:
    """Program-controlled OCR job over the file SoT."""

    def __init__(
        self,
        store: SourceStore,
        *,
        backend: OcrBackend | None = None,
        rasterizer: PdfRasterizer | None = None,
        text_extractor: PdfTextLayerExtractor | None = None,
        config: ProcessingConfig | None = None,
        clock: Clock = utcnow,
        events: Any | None = None,
        intake: IntakeService | None = None,
    ) -> None:
        self._store = store
        self._backend = backend or UnavailableOcrBackend()
        self._rasterizer = rasterizer or PdfiumRasterizer()
        self._text_extractor = text_extractor or PdfiumTextLayerExtractor()
        self._config = config or ProcessingConfig()
        self._clock = clock
        self._events = events
        self._intake = intake or IntakeService(store, clock=clock, events=events)

    @property
    def backend_model(self) -> str:
        return self._backend.model_id

    @property
    def ocr_configured(self) -> bool:
        """Whether a real OCR backend is configured (not the honest stub)."""

        return self._backend.model_id != "unavailable"

    def can_process(self, media_type: str | None, data: bytes) -> bool:
        if is_pdf_bytes(data):
            return True
        normalized = _normalize_media_type(media_type)
        return normalized in IMAGE_MEDIA_TYPES or normalized in NATIVE_TEXT_MEDIA_TYPES

    def is_native_text(self, media_type: str | None) -> bool:
        """Whether this source is handled by the model-free UTF-8 text path."""

        return _normalize_media_type(media_type) in NATIVE_TEXT_MEDIA_TYPES

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

        if self.is_native_text(media_type):
            return self._process_native_text(
                source, job_id, original_name, original_bytes, media_type, content
            )

        if is_pdf_bytes(original_bytes):
            return self._process_pdf(
                source,
                job_id,
                original_name,
                original_bytes,
                media_type,
                content,
                cancel_check=cancel_check,
            )

        return self._process_raster_pages(
            source,
            job_id,
            original_name,
            original_bytes,
            media_type,
            content,
            cancel_check=cancel_check,
        )

    def _process_raster_pages(
        self,
        source: SourceRecord,
        job_id: str | None,
        original_name: str,
        original_bytes: bytes,
        media_type: str | None,
        content: ContentStore,
        *,
        cancel_check: Any | None,
    ) -> ProcessingOutcome:
        """Rasterise and OCR every page (images and sparse/scanned PDFs)."""

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
        return self._commit(source, job_id, draft, content, cancelled=cancelled)

    def _process_pdf(
        self,
        source: SourceRecord,
        job_id: str | None,
        original_name: str,
        original_bytes: bytes,
        media_type: str | None,
        content: ContentStore,
        *,
        cancel_check: Any | None,
    ) -> ProcessingOutcome:
        """Extract a PDF text-layer-first; OCR only empty/very sparse pages.

        A page with a real embedded text layer is used directly (no rasterise,
        no OCR call).  Empty/scanned pages fall back to the unchanged OCR path.
        If the text-layer reader cannot open the PDF we retain the historical
        behaviour and let the rasteriser/OCR path report the real failure.
        """

        import hashlib

        try:
            text_pages = self._text_extractor.extract(
                original_bytes, max_pages=self._config.max_pages
            )
        except AppError:
            text_pages = []
        if not text_pages:
            return self._process_raster_pages(
                source,
                job_id,
                original_name,
                original_bytes,
                media_type,
                content,
                cancel_check=cancel_check,
            )

        min_chars = self._config.min_text_layer_chars
        sparse = [
            page for page in text_pages if is_sparse_text_layer(page.text, min_chars=min_chars)
        ]
        rendered: dict[int, bytes] = {}
        if sparse:
            rendered_pages = self._rasterize(original_bytes, media_type)
            rendered = {
                page_number: page_bytes
                for page_number, page_bytes in rendered_pages
                if page_number is not None
            }

        total_pages = len(text_pages)
        input_hash = hashlib.sha256(original_bytes).hexdigest()
        results: list[PageText] = []
        cancelled = False
        for text_page in text_pages:
            if cancel_check is not None and cancel_check():
                cancelled = True
                break
            if job_id is not None:
                self._intake.set_stage(job_id, stage="extracting")
            if not is_sparse_text_layer(text_page.text, min_chars=min_chars):
                results.append(
                    PageText(
                        page=text_page.page,
                        text=text_page.text,
                        input_sha256=input_hash,
                        model=PDF_TEXT_LAYER_MODEL,
                        status="succeeded",
                        extractor=TEXT_LAYER_EXTRACTOR,
                    )
                )
                continue
            fallback_bytes = rendered.get(text_page.page)
            if fallback_bytes is None:
                results.append(
                    PageText(
                        page=text_page.page,
                        text="",
                        input_sha256=input_hash,
                        model=self._backend.model_id,
                        status="failed",
                        error="sparse text layer and page could not be rendered for OCR fallback",
                        extractor="lg035-ocr",
                    )
                )
                continue
            results.append(
                self._ocr_page(
                    content=content,
                    source=source,
                    original_name=original_name,
                    page_number=text_page.page,
                    page_bytes=fallback_bytes,
                    media_type=media_type,
                )
            )

        draft = self._finalize(
            source=source,
            original_name=original_name,
            results=results,
            total_pages=total_pages,
            cancelled=cancelled,
        )
        return self._commit(source, job_id, draft, content, cancelled=cancelled)

    def _commit(
        self,
        source: SourceRecord,
        job_id: str | None,
        draft: MachineDraft,
        content: ContentStore,
        *,
        cancelled: bool,
    ) -> ProcessingOutcome:
        """Persist one finished draft and return the honest outcome.

        LG-222: a failed attempt with no successful page must not replace an
        already usable machine body for the same source version.  In that case
        no failure derivative is written; the old body and its index remain.
        """

        preserve_existing = (
            (draft.status == "failed" or (cancelled and not draft.succeeded_pages))
            and self._has_trusted_machine(content, draft.source_version)
        )
        written: dict[str, Any] | None = None
        if not preserve_existing:
            written = content.write_machine(draft)
            if draft.status in ("succeeded", "partial"):
                self._record_derivatives(source, draft, written)
        status = draft.status
        if cancelled:
            status = "cancelled"
        self._record_outcome(
            source, job_id, draft, status, preserved_existing_body=preserve_existing
        )
        return ProcessingOutcome(
            source_id=source.source_id,
            source_version=draft.source_version,
            status=status,
            total_pages=draft.total_pages or 0,
            succeeded_pages=len(draft.succeeded_pages),
            failed_pages=len(draft.failed_pages),
            model=draft.model,
            derivative_path=written["markdown_path"] if written is not None else None,
            reason=draft.fail_reason,
            extractor=draft.extractor,
            preserved_existing_body=preserve_existing,
        )

    def _process_native_text(
        self,
        source: SourceRecord,
        job_id: str | None,
        original_name: str,
        original_bytes: bytes,
        media_type: str | None,
        content: ContentStore,
    ) -> ProcessingOutcome:
        """Extract a native UTF-8 text original into a machine derivative.

        This is the **model-free** path: the original bytes are decoded as UTF-8
        under a bounded size limit and written verbatim as one machine page.
        No OCR backend, no model call, no network and no new inference path is
        entered.  A non-UTF-8 or oversized original fails honestly (never a
        fabricated or silently truncated body).
        """

        import hashlib

        if len(original_bytes) > NATIVE_TEXT_MAX_BYTES:
            return self._finish_text_failure(
                source,
                job_id,
                reason=(
                    "native text original exceeds the extraction size limit "
                    f"({NATIVE_TEXT_MAX_BYTES} bytes)"
                ),
            )
        try:
            text = original_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return self._finish_text_failure(
                source, job_id, reason="native text original is not valid UTF-8"
            )

        # Keep a bounded, deterministic page model so the derivative shape is
        # identical to the OCR path (frontmatter + one locatable page block).
        draft = MachineDraft(
            source_version=source.source_version,
            filename=original_name,
            model=NATIVE_TEXT_MODEL,
            pages=[
                PageText(
                    page=1,
                    text=text,
                    input_sha256=hashlib.sha256(original_bytes).hexdigest(),
                    model=NATIVE_TEXT_MODEL,
                    status="succeeded",
                    extractor=NATIVE_TEXT_EXTRACTOR,
                )
            ],
            extractor=NATIVE_TEXT_EXTRACTOR,
            status="succeeded",
            total_pages=1,
        )
        written = content.write_machine(draft)
        self._record_derivatives(source, draft, written)
        self._record_outcome(source, job_id, draft, "succeeded")
        return ProcessingOutcome(
            source_id=source.source_id,
            source_version=draft.source_version,
            status="succeeded",
            total_pages=1,
            succeeded_pages=1,
            failed_pages=0,
            model=draft.model,
            derivative_path=written["markdown_path"],
            reason=None,
            extractor=draft.extractor,
        )

    def _finish_text_failure(
        self, source: SourceRecord, job_id: str | None, *, reason: str
    ) -> ProcessingOutcome:
        """Honest failure for an unusable native text original (no fake body)."""

        current = self._store.read_source(source.source_id)
        preserved = self._has_usable_body(current.source_id, current.source_version)
        self._store.update_source(
            source.source_id,
            {"status": "partial" if preserved else "failed", "updated_at": to_iso(self._clock())},
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
            model=NATIVE_TEXT_MODEL,
            derivative_path=None,
            reason=reason,
            extractor=NATIVE_TEXT_EXTRACTOR,
        )

    # -------------------------------------------------------------- internals
    def _has_trusted_machine(self, content: ContentStore, source_version: int) -> bool:
        """Whether a usable machine derivative already exists for this version."""

        pages = content.read_pages(source_version)
        if not isinstance(pages, dict):
            return False
        if str(pages.get("status") or "") not in ("succeeded", "partial"):
            return False
        markdown = content.read_machine_markdown(source_version)
        return markdown is not None and bool(markdown.strip())

    def _has_usable_body(self, source_id: str, source_version: int) -> bool:
        """A formal body or trusted machine body is already readable."""

        content = ContentStore(source_root=self._store.source_dir(source_id))
        formal = content.read_formal()
        if formal is not None and bool(formal.strip()):
            return True
        return self._has_trusted_machine(content, source_version)

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

        request_media_type = (
            "image/png"
            if is_pdf_bytes(page_bytes) or page_number is not None
            else _normalize_media_type(media_type) or "image/png"
        )
        # Optional, default-OFF table-aware branch: classify the page with the
        # bounded, model-free layout analyser and override the prompt **only**
        # when it is confidently a real ruled table.  Ordinary pages fall through
        # to the unchanged default prompt, so the default request is unchanged.
        prompt = OCR_PROMPT
        table_decision = None
        if self._config.table_mode:
            try:
                decision = classify_image_bytes(page_bytes)
            except Exception:  # noqa: BLE001 - classification must never break OCR
                decision = None
            if decision is not None:
                table_decision = decision
                if decision.is_table:
                    prompt = OCR_TABLE_PROMPT
        request = OcrRequest(
            data=page_bytes,
            media_type=request_media_type,
            page=page_number,
            max_tokens=self._config.max_tokens_per_page,
            prompt=prompt if prompt is not OCR_PROMPT else None,
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
                extractor="lg035-ocr",
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
                extractor="lg035-ocr",
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
                extractor="lg035-ocr",
            )
        detail: dict[str, Any] = {
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "latency_seconds": round(time.monotonic() - started, 3),
            "finish_reason": result.finish_reason,
            "raw_response_sha256": hashlib.sha256(result.raw_response.encode("utf-8")).hexdigest(),
        }
        if self._config.table_mode:
            detail["prompt_kind"] = "table" if prompt is OCR_TABLE_PROMPT else "default"
            detail["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            if table_decision is not None:
                detail["table_classification"] = table_decision.to_dict()
        self._evidence(
            content,
            source,
            original_name,
            page_number,
            page_bytes,
            "succeeded",
            detail,
        )
        return PageText(
            page=page_number,
            text=result.text,
            input_sha256=result.input_sha256,
            model=result.model,
            status="succeeded",
            extractor="lg035-ocr",
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
        used_extractors = {page.extractor for page in results if page.extractor}
        if used_extractors == {TEXT_LAYER_EXTRACTOR}:
            extractor = PDF_TEXT_LAYER_EXTRACTOR
            model = PDF_TEXT_LAYER_MODEL
        elif TEXT_LAYER_EXTRACTOR in used_extractors:
            extractor = PDF_TEXT_LAYER_OCR_EXTRACTOR
            model = self._backend.model_id
        else:
            extractor = "lg035-ocr"
            model = self._backend.model_id
        return MachineDraft(
            source_version=source.source_version,
            filename=original_name,
            model=model,
            pages=results,
            extractor=extractor,
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
        self,
        source: SourceRecord,
        job_id: str | None,
        draft: MachineDraft,
        status: str,
        *,
        preserved_existing_body: bool = False,
    ) -> None:
        # Re-read: _record_derivatives may have bumped the revision.
        current = self._store.read_source(source.source_id)
        new_status = {
            "succeeded": "extracted",
            "partial": "partial",
            "failed": "failed",
            "cancelled": "partial" if draft.succeeded_pages else "failed",
        }.get(status, "failed")
        if new_status == "failed" and (
            preserved_existing_body
            or self._has_usable_body(current.source_id, current.source_version)
        ):
            # A failed new attempt did not destroy an already usable formal or
            # machine body: report a mixed state instead of "failed".
            new_status = "partial"
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
        preserved = self._has_usable_body(current.source_id, current.source_version)
        self._store.update_source(
            source.source_id,
            {"status": "partial" if preserved else "failed", "updated_at": to_iso(self._clock())},
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
            extractor=None,
        )

    def _fail(self, source: SourceRecord, job_id: str | None, reason: str) -> ProcessingOutcome:
        current = self._store.read_source(source.source_id)
        preserved = self._has_usable_body(current.source_id, current.source_version)
        self._store.update_source(
            source.source_id,
            {"status": "partial" if preserved else "failed", "updated_at": to_iso(self._clock())},
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
            extractor=None,
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
                    "actor": (
                        "source-pdf-text-layer"
                        if draft is not None
                        and draft.extractor
                        in (PDF_TEXT_LAYER_EXTRACTOR, PDF_TEXT_LAYER_OCR_EXTRACTOR)
                        else "source-ocr"
                    ),
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
    "NATIVE_TEXT_EXTRACTOR",
    "NATIVE_TEXT_MAX_BYTES",
    "NATIVE_TEXT_MEDIA_TYPES",
    "NATIVE_TEXT_MODEL",
    "ProcessingConfig",
    "ProcessingEngine",
    "ProcessingOutcome",
    "encode_data_url",
]
