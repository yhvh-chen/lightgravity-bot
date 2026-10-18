"""LG-141 receipt v2: independent text/keyword/semantic branch outcomes."""

from __future__ import annotations

import base64
from pathlib import Path

from lightgravity.sources.vectors.embedder import EmbeddingTimeout
from lightgravity.sources.worker import IntakeWorker

from test_intake_worker import (
    FakeEmbedding,
    FakeOcr,
    job_status,
    make_service,
    receive_deferred,
    wait_for,
)


class TimeoutEmbedding(FakeEmbedding):
    def embed(self, item):  # type: ignore[no-untyped-def]
        self.calls.append(item.part_type)
        raise EmbeddingTimeout(timeout_seconds=0.01)


async def _run(service, job_id: str) -> None:  # type: ignore[no-untyped-def]
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(service, job_id) not in ("queued", "running"))
    finally:
        await worker.stop()


async def test_native_text_has_independent_ready_branches(settings) -> None:
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=FakeOcr(), embedding=embedding)
    result = receive_deferred(
        service,
        request_id="req-receipt-text",
        filename="note.txt",
        data=b"searchable-text-token",
        media_type="text/plain",
    )
    await _run(service, result.job.job_id)

    receipt = service.receipt(result.source.source_id)
    assert receipt["receipt_version"] == 2
    assert receipt["partial"] is False
    latest = receipt["latest"]
    assert latest["text"] == {"status": "ready", "reason": None, "error_code": None}
    assert latest["keyword"] == {"status": "searchable", "reason": None, "error_code": None}
    assert latest["semantic"]["status"] == "searchable"
    assert latest["semantic"]["kinds"] == ["text"]
    assert latest["semantic"]["failed_kinds"] == []
    assert latest["searchable"] is True
    assert service.store.read_job(result.job.job_id).status == "succeeded"


async def test_audio_is_unavailable_but_can_be_directly_embedded(settings) -> None:
    embedding = FakeEmbedding()
    ocr = FakeOcr()
    service = make_service(settings.data_dir, ocr=ocr, embedding=embedding)
    result = receive_deferred(
        service,
        request_id="req-receipt-audio",
        filename="meeting.wav",
        data=b"RIFF fake audio bytes",
        media_type="audio/wav",
    )
    await _run(service, result.job.job_id)

    receipt = service.receipt(result.source.source_id)
    latest = receipt["latest"]
    assert latest["text"]["status"] == "unavailable"
    assert latest["text"]["reason"] == "asr_unavailable"
    assert latest["text"]["error_code"] == "capability_unavailable"
    assert latest["keyword"]["status"] == "no_text"
    assert latest["semantic"]["status"] == "searchable"
    assert latest["semantic"]["kinds"] == ["audio"]
    assert "transcript" not in str(receipt).lower()
    assert receipt["partial"] is True
    assert service.store.read_job(result.job.job_id).status == "partial"
    assert ocr.calls == []
    assert embedding.calls == ["audio"]


async def test_ocr_failure_does_not_erase_media_semantic_success(settings) -> None:
    ocr = FakeOcr()
    ocr.fail = True
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=ocr, embedding=embedding)
    result = receive_deferred(
        service,
        request_id="req-receipt-image-partial",
        filename="scan.png",
        data=b"\x89PNG image without readable text",
        media_type="image/png",
    )
    await _run(service, result.job.job_id)

    receipt = service.receipt(result.source.source_id)
    latest = receipt["latest"]
    assert latest["text"]["status"] == "failed"
    assert latest["keyword"]["status"] == "no_text"
    assert latest["semantic"]["status"] == "searchable"
    assert latest["semantic"]["kinds"] == ["image"]
    assert receipt["partial"] is True
    # The original remains available even though OCR failed.
    assert service.download_view(result.source.source_id)["bytes"] == b"\x89PNG image without readable text"


async def test_unknown_binary_is_honestly_unsupported(settings) -> None:
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=FakeOcr(), embedding=embedding)
    result = receive_deferred(
        service,
        request_id="req-receipt-binary",
        filename="archive.zip",
        data=b"PK\x03\x04 fake zip",
        media_type="application/zip",
    )
    await _run(service, result.job.job_id)

    receipt = service.receipt(result.source.source_id)
    latest = receipt["latest"]
    assert latest["text"]["status"] == "unavailable"
    assert latest["text"]["reason"] == "no_text_path"
    assert latest["keyword"]["status"] == "no_text"
    assert latest["semantic"]["status"] == "unsupported"
    assert receipt["partial"] is False
    assert embedding.calls == []
    assert service.store.read_job(result.job.job_id).status == "succeeded"


async def test_disabled_embedding_is_not_reported_as_success(settings) -> None:
    service = make_service(settings.data_dir, ocr=FakeOcr(), embedding=None)
    result = receive_deferred(
        service,
        request_id="req-receipt-disabled",
        filename="talk.wav",
        data=b"RIFF disabled audio",
        media_type="audio/wav",
    )
    await _run(service, result.job.job_id)

    receipt = service.receipt(result.source.source_id)
    latest = receipt["latest"]
    assert latest["text"]["status"] == "unavailable"
    assert latest["keyword"]["status"] == "no_text"
    assert latest["semantic"]["status"] == "disabled"
    assert latest["semantic"]["kinds"] == []
    assert receipt["partial"] is False


async def test_model_mismatch_fails_semantic_without_rebuild_or_embedding(settings) -> None:
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=FakeOcr(), embedding=embedding)
    vector = service.vector
    assert vector is not None
    # A cache written by another model must fail closed, not be wiped/rebuilt.
    vector.index.replace_all([], model="other-model", dim=2)

    result = receive_deferred(
        service,
        request_id="req-receipt-mismatch",
        filename="mismatch.txt",
        data=b"mismatch text token",
        media_type="text/plain",
    )
    await _run(service, result.job.job_id)

    receipt = service.receipt(result.source.source_id)
    latest = receipt["latest"]
    assert latest["text"]["status"] == "ready"
    assert latest["keyword"]["status"] == "searchable"
    assert latest["semantic"]["status"] == "failed"
    assert latest["semantic"]["reason"] == "model_mismatch_rebuild_required"
    assert embedding.calls == []
    assert vector.index.header()["model"] == "other-model"
    assert receipt["partial"] is True


async def test_embedding_timeout_parks_job_as_recovery_required(settings) -> None:
    service = make_service(settings.data_dir, ocr=FakeOcr(), embedding=TimeoutEmbedding())
    result = receive_deferred(
        service,
        request_id="req-receipt-timeout",
        filename="timeout.txt",
        data=b"timeout text token",
        media_type="text/plain",
    )
    await _run(service, result.job.job_id)

    job = service.store.read_job(result.job.job_id)
    assert job.status == "recovery_required"
    receipt = service.receipt(result.source.source_id)
    assert receipt["latest"]["text"]["status"] == "ready"
    assert receipt["latest"]["keyword"]["status"] == "searchable"
    assert receipt["latest"]["semantic"]["status"] == "failed"
    assert "timeout" in (receipt["latest"]["semantic"]["reason"] or "").lower()


async def test_receipt_job_id_survives_reload_and_deduplicated_receive(settings) -> None:
    """Each item links its producing job, even when two jobs share one source."""
    for mode in ("sync", "deferred"):
        directory = settings.data_dir / mode
        service = make_service(directory)
        first = service.receive_inline(
            request_id=f"receipt-job-{mode}", filename="job.txt",
            content_base64=base64.b64encode(b"receipt association").decode(),
            media_type="text/plain", intake_mode=mode,
        )
        if mode == "deferred":
            await _run(service, first.job.job_id)
        fresh = make_service(directory)
        receipt = fresh.receipt(first.source.source_id)
        assert receipt["latest"]["job_id"] == first.job.job_id
        assert all(item["job_id"] == first.job.job_id for item in receipt["items"])
        duplicate = fresh.receive_inline(
            request_id=f"receipt-job-{mode}-duplicate", filename="job.txt",
            content_base64=base64.b64encode(b"receipt association").decode(),
            media_type="text/plain", intake_mode=mode,
        )
        assert duplicate.source.source_id == first.source.source_id
        assert duplicate.job.job_id != first.job.job_id
        reloaded = make_service(directory)
        receipt = reloaded.receipt(first.source.source_id)
        assert receipt["latest"]["job_id"] == duplicate.job.job_id
        assert receipt["items"][0]["job_id"] == first.job.job_id
        for item in receipt["items"]:
            assert reloaded.get_job(item["job_id"])["source_ref"] == first.source.source_id


def test_legacy_and_invalid_receipt_job_ids_are_not_guessed(settings) -> None:
    import json
    service = make_service(settings.data_dir)
    result = receive_deferred(service, request_id="legacy-job", filename="old.txt",
                              data=b"legacy", media_type="text/plain")
    other = receive_deferred(service, request_id="other-job", filename="other.txt",
                             data=b"different", media_type="text/plain")
    path = service.store.receipt_path(result.source.source_id)
    original = json.loads(path.read_text().splitlines()[0])
    for value in (None, other.job.job_id, "job_missing", "invalid/id"):
        entry = dict(original)
        if value is None:
            entry.pop("job_id", None)
        else:
            entry["job_id"] = value
        path.write_text(json.dumps(entry) + "\n")
        fresh = make_service(settings.data_dir)
        assert fresh.receipt(result.source.source_id)["latest"]["job_id"] is None


async def test_timeout_after_text_embedding_keeps_success_and_stops_remaining_inputs(settings) -> None:
    class MediaTimeout(FakeEmbedding):
        def embed(self, item):  # type: ignore[no-untyped-def]
            if item.part_type != "text":
                self.calls.append(item.part_type)
                raise EmbeddingTimeout(timeout_seconds=0.01)
            return super().embed(item)

    for backend, kinds, calls in (
        (TimeoutEmbedding(), [], ["text"]),
        (MediaTimeout(), ["text"], ["text", "image"]),
    ):
        service = make_service(settings.data_dir / str(len(kinds)), embedding=backend)
        result = receive_deferred(service, request_id="timeout-image", filename="timeout.png",
                                  data=b"fake-timeout-image", media_type="image/png")
        await _run(service, result.job.job_id)
        assert service.store.read_job(result.job.job_id).status == "recovery_required"
        semantic = service.receipt(result.source.source_id)["latest"]["semantic"]
        assert semantic["kinds"] == kinds
        assert semantic["status"] == ("searchable" if kinds else "failed")
        assert "timeout" in semantic["reason"]
        assert backend.calls == calls
        assert [entry.kind for entry in service.vector.index.entries_for(result.source.source_id)] == kinds
