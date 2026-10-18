"""LG-224: PDF text-layer-first extraction with OCR only as sparse fallback.

The fixtures build real, byte-valid PDFs at runtime.  The electronic sample has
an actual embedded Helvetica text object, so ``pypdfium2`` reads the text
layer exactly like a product PDF.  The scanned sample has blank pages and no
text object, so only the OCR fallback can produce a body.

No model/OCR service is contacted: empty/sparse pages use an in-process
scripted backend, and the electronic path must succeed even with the
*unconfigured* backend.  This is local developer evidence, not independent QA.
"""

from __future__ import annotations

import hashlib

import pytest

from lightgravity.sources import build_source_service
from lightgravity.sources.content import (
    ContentStore,
    PDF_TEXT_LAYER_EXTRACTOR,
    PDF_TEXT_LAYER_OCR_EXTRACTOR,
)
from lightgravity.sources.intake import IntakeService, ReceiveRequest
from lightgravity.sources.ocr import (
    OcrPageResult,
    PdfiumRasterizer,
    UnavailableOcrBackend,
    is_sparse_text_layer,
)
from lightgravity.sources.processing import ProcessingConfig, ProcessingEngine
from lightgravity.sources.store import SourceStore
from lightgravity.sources.worker import IntakeWorker

from test_intake_worker import FakeOcr, job_status, make_service, receive_deferred, wait_for


def make_pdf(pages: list[str]) -> bytes:
    """Build a real PDF whose pages contain Helvetica text (or are blank)."""

    page_count = len(pages)
    font_id = 3 + 2 * page_count
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids ["
            + " ".join(f"{3 + 2 * index} 0 R" for index in range(page_count))
            + f"] /Count {page_count} >>"
        ).encode("ascii"),
    }
    for index, text in enumerate(pages):
        page_id = 3 + 2 * index
        content_id = page_id + 1
        stream = (
            b""
            if not text
            else f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET".encode("ascii")
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id in range(1, font_id + 1):
        offsets.append(len(output))
        output += f"{object_id} 0 obj\n".encode("ascii")
        output += objects[object_id] + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {font_id + 1}\n".encode("ascii")
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode("ascii")
    output += (
        f"trailer\n<< /Size {font_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(output)


def _receive(store: SourceStore, name: str, data: bytes) -> str:
    service = IntakeService(store)
    result = service.receive(
        ReceiveRequest(
            request_id=f"req-lg224-{name}",
            filename=name,
            data=data,
            media_type="application/pdf",
        )
    )
    return result.source.source_id


class ForbiddenRasterizer(PdfiumRasterizer):
    """Fail the test if an electronic text-layer page is rasterised."""

    def render(self, data, *, scale=2.0, max_pages=None):  # type: ignore[override]
        raise AssertionError("electronic PDF must not be rasterised for OCR")


class ScriptedOcr:
    """Deterministic fallback backend; no network, no credentials."""

    def __init__(self, text: str = "SCANNED PAGE OCR FALLBACK") -> None:
        self.text = text
        self.calls: list[object] = []

    @property
    def model_id(self) -> str:
        return "scripted-ocr"

    def transcribe(self, request) -> OcrPageResult:  # type: ignore[no-untyped-def]
        self.calls.append(request)
        return OcrPageResult(
            page=request.page,
            text=self.text,
            model=self.model_id,
            media_type=request.media_type,
            input_sha256=hashlib.sha256(request.data).hexdigest(),
            input_bytes=len(request.data),
            prompt_tokens=1,
            completion_tokens=1,
            latency_seconds=0.0,
            finish_reason="stop",
            raw_response="{}",
        )


def test_electronic_pdf_uses_text_layer_with_no_ocr_configuration(tmp_path) -> None:
    store = SourceStore(tmp_path / "data")
    pdf = make_pdf(["ELECTRONIC PDF BODY FROM THE EMBEDDED TEXT LAYER"])
    source_id = _receive(store, "electronic.pdf", pdf)

    engine = ProcessingEngine(
        store,
        backend=UnavailableOcrBackend("no OCR configured"),
        rasterizer=ForbiddenRasterizer(),
    )
    outcome = engine.process(source_id)

    assert outcome.status == "succeeded"
    assert outcome.extractor == PDF_TEXT_LAYER_EXTRACTOR
    assert outcome.model == "none"
    assert outcome.succeeded_pages == 1

    content = ContentStore(source_root=store.source_dir(source_id))
    markdown = content.read_machine_markdown(1)
    assert markdown is not None
    assert "ELECTRONIC PDF BODY FROM THE EMBEDDED TEXT LAYER" in markdown
    assert "extractor: pdfium-text-layer" in markdown
    assert "record_type: machine_pdf_text_layer" in markdown
    assert "extractor=pdfium-text-layer" in markdown
    assert "Machine PDF text layer" in markdown

    pages = content.read_pages(1)
    assert pages is not None
    assert pages["extractor"] == PDF_TEXT_LAYER_EXTRACTOR
    assert pages["pages"][0]["extractor"] == PDF_TEXT_LAYER_EXTRACTOR
    assert pages["pages"][0]["model"] == "none"
    assert content.read_evidence() == []
    assert store.read_source(source_id).status == "extracted"


def test_sparse_text_layer_falls_back_to_ocr(tmp_path) -> None:
    store = SourceStore(tmp_path / "data")
    # The visible character count is below the threshold: this is a sparse
    # text layer (e.g. a stray page number), not a trustworthy body.
    pdf = make_pdf(["1"])
    source_id = _receive(store, "sparse.pdf", pdf)
    ocr = ScriptedOcr()

    engine = ProcessingEngine(
        store,
        backend=ocr,
        config=ProcessingConfig(min_text_layer_chars=16),
    )
    outcome = engine.process(source_id)

    assert outcome.status == "succeeded"
    assert outcome.extractor == "lg035-ocr"
    assert len(ocr.calls) == 1
    markdown = ContentStore(source_root=store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is not None
    assert "SCANNED PAGE OCR FALLBACK" in markdown
    assert "extractor: lg035-ocr" in markdown


def test_scanned_pdf_uses_ocr_fallback_per_page(tmp_path) -> None:
    store = SourceStore(tmp_path / "data")
    pdf = make_pdf(["", ""])
    source_id = _receive(store, "scan.pdf", pdf)
    ocr = ScriptedOcr("SCANNED TWO-PAGE OCR")

    engine = ProcessingEngine(store, backend=ocr)
    outcome = engine.process(source_id)

    assert outcome.status == "succeeded"
    assert outcome.extractor == "lg035-ocr"
    assert len(ocr.calls) == 2
    content = ContentStore(source_root=store.source_dir(source_id))
    pages = content.read_pages(1)
    assert pages is not None
    assert [page["extractor"] for page in pages["pages"]] == ["lg035-ocr", "lg035-ocr"]
    assert content.read_evidence()  # OCR requests are still traceable


def test_scanned_pdf_without_ocr_fails_honestly(tmp_path) -> None:
    store = SourceStore(tmp_path / "data")
    pdf = make_pdf([""])
    source_id = _receive(store, "scan-no-ocr.pdf", pdf)

    engine = ProcessingEngine(
        store,
        backend=UnavailableOcrBackend("no OCR configured"),
        rasterizer=PdfiumRasterizer(),
    )
    outcome = engine.process(source_id)

    assert outcome.status == "failed"
    assert outcome.extractor == "lg035-ocr"
    assert outcome.reason
    # The original is kept; the derivative never presents a fabricated body.
    assert (store.original_dir(source_id) / "scan-no-ocr.pdf").read_bytes() == pdf
    markdown = ContentStore(source_root=store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is not None
    assert "was not transcribed" in markdown
    assert "OCR backend unavailable" in markdown
    assert store.read_source(source_id).status == "failed"


def test_mixed_pdf_only_ocrs_the_sparse_page(tmp_path) -> None:
    store = SourceStore(tmp_path / "data")
    pdf = make_pdf(["FULL ELECTRONIC PAGE TEXT LAYER", ""])
    source_id = _receive(store, "mixed.pdf", pdf)
    ocr = ScriptedOcr("SECOND PAGE WAS SCANNED")

    engine = ProcessingEngine(store, backend=ocr)
    outcome = engine.process(source_id)

    assert outcome.status == "succeeded"
    assert outcome.extractor == PDF_TEXT_LAYER_OCR_EXTRACTOR
    assert len(ocr.calls) == 1
    content = ContentStore(source_root=store.source_dir(source_id))
    pages = content.read_pages(1)
    assert pages is not None
    assert [page["extractor"] for page in pages["pages"]] == [
        PDF_TEXT_LAYER_EXTRACTOR,
        "lg035-ocr",
    ]
    markdown = content.read_machine_markdown(1)
    assert markdown is not None
    assert "FULL ELECTRONIC PAGE TEXT LAYER" in markdown
    assert "SECOND PAGE WAS SCANNED" in markdown
    assert "record_type: machine_pdf_text_layer_ocr" in markdown


def test_sparse_threshold_counts_visible_characters() -> None:
    assert is_sparse_text_layer(" \n\t 1 \r\n", min_chars=16)
    assert not is_sparse_text_layer("This page has a real text layer.", min_chars=16)


async def test_electronic_pdf_receipt_reports_text_layer_without_ocr(settings) -> None:
    # Deliberately no OCR backend configuration: the product path must still
    # extract a real electronic PDF.
    service = build_source_service(
        data_dir=settings.data_dir,
        ocr_backend=UnavailableOcrBackend("no OCR configured"),
    )
    pdf = make_pdf(["RECEIPT PROVES THE PDF TEXT LAYER WAS USED"])
    result = receive_deferred(
        service,
        request_id="req-lg224-receipt-electronic",
        filename="electronic.pdf",
        data=pdf,
        media_type="application/pdf",
    )
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(
            lambda: job_status(service, result.job.job_id) not in ("queued", "running")
        )
    finally:
        await worker.stop()

    assert service.store.read_job(result.job.job_id).status == "succeeded"
    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"]["status"] == "ready"
    assert latest["text"]["extractor"] == PDF_TEXT_LAYER_EXTRACTOR
    assert latest["keyword"]["status"] == "searchable"


async def test_scanned_pdf_receipt_reports_ocr_fallback(settings) -> None:
    service = make_service(settings.data_dir, ocr=FakeOcr("OCR RECEIPT BODY"))
    pdf = make_pdf([""])
    result = receive_deferred(
        service,
        request_id="req-lg224-receipt-scanned",
        filename="scanned.pdf",
        data=pdf,
        media_type="application/pdf",
    )
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(
            lambda: job_status(service, result.job.job_id) not in ("queued", "running")
        )
    finally:
        await worker.stop()

    assert service.store.read_job(result.job.job_id).status == "succeeded"
    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"]["status"] == "ready"
    assert latest["text"]["extractor"] == "lg035-ocr"
    assert latest["keyword"]["status"] == "searchable"
