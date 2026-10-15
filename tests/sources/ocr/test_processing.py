"""LG-035 processing tests: page back-reference, partial failure, cancel, versions.

Deterministic and offline (scripted backend, real file SoT).  Covers the task
acceptance conditions that are about *behavior*, not OCR quality:

* machine output is traceable to a page and the exact input hash;
* a source version change rebuilds a derivative without touching the formal copy;
* reprocessing never overwrites the human formal version;
* partial success is reported honestly and failed pages are never body text;
* cancellation after confirmed stop keeps the pages that completed;
* an unavailable backend keeps the original and records a clear failure.
"""

from __future__ import annotations

import json

import pytest

from lightgravity.sources.intake import ReceiveRequest
from lightgravity.sources.ocr import OcrServiceError, OcrTimeout, UnavailableOcrBackend
from lightgravity.sources.processing import ProcessingConfig

from .conftest import ScriptedBackend, make_png


def _receive(store, name: str, data: bytes, media_type: str = "image/png") -> str:
    from lightgravity.sources.intake import IntakeService

    service = IntakeService(store)
    result = service.receive(
        ReceiveRequest(request_id=f"req-{name}", filename=name, data=data, media_type=media_type)
    )
    return result.source.source_id


def test_machine_markdown_has_page_backref_and_input_hash(source_store) -> None:
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingEngine

    png = make_png()
    source_id = _receive(source_store, "scan.png", png)
    engine = ProcessingEngine(source_store, backend=ScriptedBackend(script=["HELLO WORLD"]))
    outcome = engine.process(source_id)

    assert outcome.status == "succeeded"
    assert outcome.succeeded_pages == 1
    markdown = ContentStore(source_root=source_store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is not None
    assert "input_sha256=" in markdown
    assert "page=1" in markdown
    assert "HELLO WORLD" in markdown

    # The recorded hash is the hash of the exact bytes the backend saw.
    import hashlib

    assert hashlib.sha256(png).hexdigest() in markdown

    # The evidence log records the same traceable hash.
    evidence = ContentStore(source_root=source_store.source_dir(source_id)).read_evidence()
    assert evidence and evidence[0]["input_sha256"] == hashlib.sha256(png).hexdigest()
    assert evidence[0]["outcome"] == "succeeded"

    # The source record lists the derivative with a real content hash.
    record = source_store.read_source(source_id)
    kinds = {d["kind"] for d in record.entity["derivatives"]}
    assert "machine_markdown" in kinds and "page_map" in kinds
    assert record.status == "extracted"


def test_actual_engine_receives_requested_scale(source_store) -> None:
    """The requested scale reaches the *actual* product processing path/rasteriser.

    This is deliberately not a mirror/standalone-backend test: it drives the
    real ``ProcessingEngine.process`` over a real PDF and records what scale the
    engine passes into the rasteriser, and that the explicit env value is what
    the composed config carries.
    """

    from lightgravity.sources.ocr import PdfiumRasterizer
    from lightgravity.sources.processing import ProcessingConfig, ProcessingEngine

    recorded: dict[str, float] = {}

    class RecordingRasterizer(PdfiumRasterizer):
        def render(self, data, *, scale=2.0, max_pages=100):  # type: ignore[override]
            recorded["scale"] = scale
            return super().render(data, scale=scale, max_pages=max_pages)

    source_id = _receive(source_store, "doc.pdf", _two_page_pdf())
    engine = ProcessingEngine(
        source_store,
        backend=ScriptedBackend(script=["A", "B"]),
        rasterizer=RecordingRasterizer(),
        config=ProcessingConfig.from_env(env={"LIGHTGRAVITY_OCR_SCALE": "4.0"}),
    )
    outcome = engine.process(source_id)
    assert outcome.status == "succeeded"
    assert recorded["scale"] == 4.0

    # Default composition (no env) keeps the historical 2.0 render scale.
    recorded.clear()
    engine_default = ProcessingEngine(
        source_store,
        backend=ScriptedBackend(script=["A", "B"]),
        rasterizer=RecordingRasterizer(),
        config=ProcessingConfig.from_env(env={}),
    )
    engine_default.process(source_id, force=True)
    assert recorded["scale"] == 2.0


def test_partial_failure_is_honest_and_failed_page_is_not_body(source_store) -> None:
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingEngine

    # Multi-page input is built by the PDF rasteriser; simulate two pages with a
    # scripted backend that fails the second call.
    source_id = _receive(source_store, "doc.pdf", _two_page_pdf())
    engine = ProcessingEngine(
        source_store,
        backend=ScriptedBackend(
            script=["PAGE ONE TEXT", OcrServiceError(status=500, message="boom")]
        ),
    )
    outcome = engine.process(source_id)
    assert outcome.status == "partial"
    assert outcome.succeeded_pages == 1
    assert outcome.failed_pages == 1

    markdown = ContentStore(source_root=source_store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is not None
    assert "PAGE ONE TEXT" in markdown
    assert "boom" not in markdown  # failure detail never leaks as body
    assert "Page 2 was not transcribed" in markdown
    record = source_store.read_source(source_id)
    assert record.status == "partial"


def test_timeout_is_recorded_and_never_auto_replayed(source_store) -> None:
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingEngine

    source_id = _receive(source_store, "to.png", make_png())
    backend = ScriptedBackend(script=[OcrTimeout(timeout_seconds=1.0, page=1)])
    engine = ProcessingEngine(source_store, backend=backend)
    outcome = engine.process(source_id)
    assert outcome.status == "failed"
    assert len(backend.calls) == 1  # exactly one attempt, no replay

    markdown = ContentStore(source_root=source_store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is not None
    assert "was not transcribed" in markdown


def test_unavailable_backend_keeps_original_and_records_failure(source_store) -> None:
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingEngine

    png = make_png()
    source_id = _receive(source_store, "u.png", png)
    engine = ProcessingEngine(source_store, backend=UnavailableOcrBackend("no backend"))
    outcome = engine.process(source_id)
    assert outcome.status == "failed"
    assert outcome.reason is not None

    # Original bytes are still on disk, untouched.
    assert (source_store.original_dir(source_id) / "u.png").read_bytes() == png
    record = source_store.read_source(source_id)
    assert record.status == "failed"
    # No fabricated body from the failure.
    markdown = ContentStore(source_root=source_store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is None or "unavailable" in markdown.lower() or "not transcribed" in markdown


def test_reprocess_does_not_overwrite_formal_and_page_map_versions(source_store) -> None:
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingEngine

    png = make_png()
    source_id = _receive(source_store, "v.png", png)
    content = ContentStore(source_root=source_store.source_dir(source_id))

    # First pass: machine draft + a human formal edit.
    first = ProcessingEngine(source_store, backend=ScriptedBackend(script=["MACHINE V1"]))
    first.process(source_id)
    assert content.initialize_formal_from_machine(1, edited_by="user") is True
    formal_before = content.read_formal()
    assert formal_before is not None and "MACHINE V1" in formal_before

    # Second pass (reprocess) produces a new machine text.
    second = ProcessingEngine(source_store, backend=ScriptedBackend(script=["MACHINE V2"]))
    outcome = second.process(source_id, force=True)
    assert outcome.status == "succeeded"

    # Formal file is byte-identical: reprocessing never overwrites it.
    assert content.read_formal() == formal_before
    assert "MACHINE V2" in (content.read_machine_markdown(1) or "")

    # A source version change yields a NEW derivative version, not an overwrite.
    from lightgravity.sources.intake import IntakeService

    store_intake = IntakeService(source_store)
    new_png = make_png(rgb=(1, 2, 3))
    updated = store_intake.record_version(source_id, new_png, filename="v.png")
    assert updated.source_version == 2
    assert content.read_machine_markdown(1) is not None  # old version kept
    third = ProcessingEngine(source_store, backend=ScriptedBackend(script=["MACHINE V2S2"]))
    third.process(source_id)
    assert content.read_machine_markdown(2) is not None
    assert content.read_formal() == formal_before  # still untouched


def test_cancel_after_confirmed_stop_keeps_completed_pages(source_store) -> None:
    from lightgravity.sources.content import ContentStore
    from lightgravity.sources.processing import ProcessingEngine

    source_id = _receive(source_store, "cancel.pdf", _two_page_pdf())
    state = {"stop": False}

    backend = ScriptedBackend(script=["FIRST PAGE"])

    def cancel_check() -> bool:
        # Stop before the second page: the first already succeeded.
        return len(backend.calls) >= 1

    engine = ProcessingEngine(source_store, backend=backend)
    outcome = engine.process(source_id, cancel_check=cancel_check)
    assert outcome.status == "cancelled"
    assert outcome.succeeded_pages == 1
    markdown = ContentStore(source_root=source_store.source_dir(source_id)).read_machine_markdown(1)
    assert markdown is not None and "FIRST PAGE" in markdown
    _ = state


def _two_page_pdf() -> bytes:
    """Build a real 2-page PDF at runtime with pypdfium2 (real rendering path)."""

    import io

    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(2):
        page = document.new_page(200, 100)
        page.close()
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _json(text: str) -> dict:
    return json.loads(text)


def test_invalid_scale_env_raises_explicit_diagnostic_not_silent_clamp() -> None:
    """A bad explicit scale is reported, never silently coerced into a pass."""

    from lightgravity.sources.ocr import OcrScaleInvalid
    from lightgravity.sources.processing import ProcessingConfig

    for bad in ("0", "-2", "nan", "inf", "9.9", "not-a-number"):
        with pytest.raises(OcrScaleInvalid):
            ProcessingConfig.from_env(env={"LIGHTGRAVITY_OCR_SCALE": bad})
