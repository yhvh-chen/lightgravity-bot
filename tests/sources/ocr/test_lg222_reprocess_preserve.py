"""LG-222: reprocess is type-aware and a failed attempt preserves old bodies."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.sources import build_source_service
from lightgravity.sources.ocr import OcrServiceError, UnavailableOcrBackend

from .conftest import ScriptedBackend, make_png


def _service(tmp_path: Path, backend: Any):
    return build_source_service(data_dir=tmp_path / "data", ocr_backend=backend)


def _receive(service: Any, *, request_id: str, data: bytes, media_type: str = "image/png") -> str:
    result = service.receive_inline(
        request_id=request_id,
        filename="scan.png",
        content_base64=base64.b64encode(data).decode("ascii"),
        media_type=media_type,
    )
    return result.source.source_id


def test_failed_reprocess_keeps_previous_machine_body_formal_and_index(tmp_path: Path) -> None:
    backend = ScriptedBackend(script=["old OCR body", OcrServiceError(status=500, message="scripted OCR failure")])
    service = _service(tmp_path, backend)
    source_id = _receive(service, request_id="req-lg222-preserve", data=make_png())

    first = service.source_actions(source_id, action="reprocess")
    assert first["status"] == "succeeded"
    assert service.content_view(source_id, kind="machine")["content"].count("old OCR body") == 1
    service.edit_formal(source_id, content="human formal body", edited_by="user")
    formal_before = service.content_view(source_id, kind="formal")["content"]
    index_before = service.get_source(source_id)["index"]
    assert index_before["lexical"] == "indexed"

    failed = service.source_actions(
        source_id,
        action="reprocess",
        expected_revision=service.get_source(source_id)["revision"],
    )

    assert failed["status"] == "failed"
    assert failed["preserved_existing_body"] is True
    assert failed["derivative_path"] is None
    # The failed attempt is visible in the action result, while the old layers
    # are still readable and searchable.
    assert "old OCR body" in service.content_view(source_id, kind="machine")["content"]
    assert "was not transcribed" not in service.content_view(source_id, kind="machine")["content"]
    assert service.content_view(source_id, kind="formal")["content"] == formal_before
    view = service.get_source(source_id)
    assert view["status"] == "partial"
    assert view["index"]["lexical"] == "indexed"
    assert view["context_selectable"] is True
    hits = service.search(
        type(
            "Req",
            (),
            {
                "query": '"human formal body"',
                "task_ref": None,
                "project_ref": None,
                "inbox_ref": None,
                "include_global": True,
                "limit": 20,
                "rebuild_if_missing": False,
            },
        )()
    )
    assert [hit["source_id"] for hit in hits["hits"]] == [source_id]


def test_unconfigured_image_reprocess_is_disabled_without_any_write(tmp_path: Path) -> None:
    service = _service(tmp_path, UnavailableOcrBackend("test OCR is not configured"))
    source_id = _receive(service, request_id="req-lg222-no-ocr", data=make_png())
    before = service.get_source(source_id)
    assert before["reprocess"] == {
        "kind": "ocr",
        "available": False,
        "reason": "ocr_unconfigured",
        "ocr_configured": False,
    }

    with pytest.raises(AppError) as unavailable:
        service.source_actions(source_id, action="reprocess")
    assert unavailable.value.code is ErrorCode.CAPABILITY_UNAVAILABLE

    after = service.get_source(source_id)
    assert after["status"] == before["status"] == "received"
    assert after["revision"] == before["revision"]
    assert after["derivatives"] == []
    with pytest.raises(AppError):
        service.content_view(source_id, kind="machine")


def test_unsupported_media_reprocess_is_rejected_before_writes(tmp_path: Path) -> None:
    service = _service(tmp_path, ScriptedBackend(script=["unused"]))
    source_id = _receive(
        service,
        request_id="req-lg222-unsupported",
        data=b"not an image or audio file",
        media_type="application/octet-stream",
    )
    before = service.get_source(source_id)
    assert before["reprocess"] == {
        "kind": "none",
        "available": False,
        "reason": "unsupported_media_type",
    }
    with pytest.raises(AppError) as unavailable:
        service.source_actions(source_id, action="reprocess")
    assert unavailable.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    after = service.get_source(source_id)
    assert after["revision"] == before["revision"]
    assert after["status"] == before["status"]
