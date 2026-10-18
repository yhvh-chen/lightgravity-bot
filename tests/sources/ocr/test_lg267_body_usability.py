"""Failed extraction artifacts are previews, not selected model context."""

from pathlib import Path

import pytest

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.sources import build_source_service
from lightgravity.sources.content import ContentStore, MachineDraft, PageText
from lightgravity.sources.ocr import UnavailableOcrBackend
from lightgravity.sources.selection import SelectedSourceRef, resolve_selected_sources

from .conftest import make_png
from .test_lg222_reprocess_preserve import _receive


def test_failed_image_artifact_is_readable_but_cannot_be_selected(tmp_path: Path) -> None:
    service = build_source_service(
        data_dir=tmp_path / "data", ocr_backend=UnavailableOcrBackend("no OCR configured")
    )
    source_id = _receive(service, request_id="lg267", data=make_png())
    # Direct processing models old failed files as well as PDF OCR fallback.
    result = service.process_source(source_id, force=True)
    assert result["status"] == "failed"
    preview = service.content_view(source_id, kind="machine")["content"]
    assert "extraction_status: failed" in preview
    assert service.get_source(source_id)["context_selectable"] is False
    assert service.get_source(source_id)["context_unavailable_reason"] == "extraction_failed"
    with pytest.raises(AppError) as unavailable:
        resolve_selected_sources(service, (SelectedSourceRef(source_id),))
    assert unavailable.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert service.content_view(source_id, kind="machine")["content"] == preview


@pytest.mark.parametrize("status,text,usable", [
    ("failed", "", False),
    ("succeeded", "", False),
    ("partial", "real extracted body", True),
])
def test_structured_pages_require_successful_nonempty_text(
    tmp_path: Path, status: str, text: str, usable: bool
) -> None:
    content = ContentStore(tmp_path)
    content.write_machine(MachineDraft(
        source_version=1, filename="scan.pdf", model="none", extractor="lg035-ocr",
        status=status, pages=[PageText(1, text, "hash", "none", status="succeeded" if text else "failed")],
    ))
    assert (content.read_usable_machine_markdown(1) is not None) is usable


def test_legacy_without_page_map_uses_explicit_failure_metadata(tmp_path: Path) -> None:
    content = ContentStore(tmp_path)
    content.derivative_dir().mkdir()
    path = content.machine_markdown_path(1)
    path.write_text("---\nkind: source_derivative\nextraction_status: failed\n---\n\nAny failure explanation\n")
    assert content.read_usable_machine_markdown(1) is None
    # Legacy plain bodies carry no extraction evidence; preserve compatibility.
    path.write_text("Legacy body with no structured extraction metadata")
    assert content.read_usable_machine_markdown(1) == path.read_text()


def test_failed_attempt_preserves_machine_context_without_formal(tmp_path: Path) -> None:
    from lightgravity.sources.ocr import OcrServiceError
    from .conftest import ScriptedBackend

    service = build_source_service(data_dir=tmp_path / "data", ocr_backend=ScriptedBackend(
        script=["trusted machine body", OcrServiceError(status=500, message="later failure")]
    ))
    source_id = _receive(service, request_id="lg267-preserved-machine", data=make_png())
    service.source_actions(source_id, action="reprocess")
    before = resolve_selected_sources(service, (SelectedSourceRef(source_id),))
    failed = service.source_actions(source_id, action="reprocess")
    assert failed["status"] == "failed"
    assert failed["preserved_existing_body"] is True
    assert service.get_source(source_id)["context_selectable"] is True
    after = resolve_selected_sources(service, (SelectedSourceRef(source_id),))
    assert after.body == before.body
    assert after.bindings[0].layer == "machine"
