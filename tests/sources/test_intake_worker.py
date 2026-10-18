"""LG-141 worker behaviour: deferred return, FIFO/concurrency, cancellation, retry.

All extraction/embedding calls use explicit in-process test doubles.  They are
labelled fakes, never product credentials or real vendor services.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.sources import build_source_service
from lightgravity.sources.ocr import OcrPageResult, OcrUnavailable
from lightgravity.sources.vectors.embedder import EmbedResult
from lightgravity.sources.vectors.service import VectorSearchService
from lightgravity.sources.worker import IntakeWorker


class FakeOcr:
    """Scripted OCR backend; no network and no model credential."""

    def __init__(self, text: str = "ocr-token", *, block: threading.Event | None = None, release: threading.Event | None = None) -> None:
        self.text = text
        self.calls: list[str] = []
        self.fail = False
        self.block = block
        self.release = release

    @property
    def model_id(self) -> str:
        return "fake-ocr"

    def transcribe(self, request: Any) -> OcrPageResult:
        self.calls.append(hashlib.sha256(request.data).hexdigest())
        if self.block is not None:
            self.block.set()
        if self.release is not None:
            assert self.release.wait(10), "test release event was not set"
        if self.fail:
            raise OcrUnavailable("scripted OCR unavailable")
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
            raw_response=self.text,
        )


class FakeEmbedding:
    """Scripted embedding backend; records direct text/image/audio inputs."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def model_id(self) -> str:
        return "fake-embed"

    @property
    def configured(self) -> bool:
        return True

    def embed(self, item: Any) -> EmbedResult:
        self.calls.append(item.part_type)
        digest = hashlib.sha256(
            item.text.encode("utf-8") if item.part_type == "text" else (item.data or b"")
        ).hexdigest()
        return EmbedResult(
            vector=(1.0, 0.0),
            model=self.model_id,
            dim=2,
            input_kind=item.part_type,
            input_sha256=digest,
            input_bytes=len(item.data or b"") if item.part_type != "text" else len(item.text or ""),
            latency_seconds=0.0,
            prompt_tokens=None,
            raw_response="{}",
        )


def make_service(tmp_path: Path, *, ocr: FakeOcr | None = None, embedding: FakeEmbedding | None = None):
    service = build_source_service(
        data_dir=tmp_path / "data",
        ocr_backend=ocr or FakeOcr(),
    )
    if embedding is not None:
        service.set_vector(VectorSearchService(service.store, backend=embedding))
    return service


def receive_deferred(service: Any, *, request_id: str, filename: str, data: bytes, media_type: str):
    return service.receive_inline(
        request_id=request_id,
        filename=filename,
        content_base64=base64.b64encode(data).decode("ascii"),
        media_type=media_type,
        intake_mode="deferred",
    )


async def wait_for(predicate: Callable[[], bool], *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def job_status(service: Any, job_id: str) -> str:
    return service.store.read_job(job_id).status


async def test_deferred_returns_before_ocr_and_worker_runs_text(api, app, settings) -> None:
    ocr = FakeOcr(text="deferred-body-token")
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=ocr, embedding=embedding)
    app.state.source_service = service
    payload = {
        "request_id": "req-deferred-api",
        "filename": "scan.png",
        "content_base64": base64.b64encode(b"\x89PNG deferred image").decode("ascii"),
        "media_type": "image/png",
        "intake_mode": "deferred",
    }
    created = await api.post("/api/v1/sources", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["intake_mode"] == "deferred"
    assert body["source"]["status"] == "received"
    assert body["job"]["status"] == "queued"
    assert body["job"]["intake_mode"] == "deferred"
    assert body["job"]["budget"]["max_model_calls"] == 102
    assert ocr.calls == []
    assert embedding.calls == []

    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(service, body["job"]["job_id"]) not in ("queued", "running"))
        job = service.store.read_job(body["job"]["job_id"])
        assert job.status == "succeeded"
        assert job.entity["started_at"]
        assert job.entity["finished_at"]
        assert ocr.calls
        receipt = (await api.get(f"/api/v1/sources/{body['source']['source_id']}/receipt")).json()
        assert receipt["receipt_version"] == 2
        assert receipt["latest"]["text"]["status"] == "ready"
        assert receipt["latest"]["keyword"]["status"] == "searchable"
        assert sorted(receipt["latest"]["semantic"]["kinds"]) == ["image", "text"]
    finally:
        await worker.stop()


async def test_duplicate_request_id_does_not_create_second_job_or_calls(settings) -> None:
    ocr = FakeOcr()
    service = make_service(settings.data_dir, ocr=ocr)
    first = receive_deferred(
        service,
        request_id="req-duplicate",
        filename="a.png",
        data=b"same-image-bytes",
        media_type="image/png",
    )
    replay = receive_deferred(
        service,
        request_id="req-duplicate",
        filename="a.png",
        data=b"same-image-bytes",
        media_type="image/png",
    )
    assert replay.source.source_id == first.source.source_id
    assert replay.job.job_id == first.job.job_id
    assert len(service.store.list_sources()) == 1
    assert len(service.store.list_jobs()) == 1

    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(service, first.job.job_id) not in ("queued", "running"))
        assert len(ocr.calls) == 1
        assert len(service.store.list_jobs()) == 1
    finally:
        await worker.stop()


async def test_worker_fifo_and_concurrency_bound(settings) -> None:
    second_recorded = threading.Event()
    release = threading.Event()
    # FakeOcr records its call before signaling block. Gate the earliest job
    # until the second job records OCR, deterministically reversing arrival.
    ocr = FakeOcr(block=second_recorded, release=release)
    service = make_service(settings.data_dir, ocr=ocr)
    digests: dict[str, str] = {}
    for index in range(3):
        data = f"image-{index}".encode()
        result = receive_deferred(
            service,
            request_id=f"req-concurrent-{index}",
            filename=f"f{index}.png",
            data=data,
            media_type="image/png",
        )
        digests[result.job.job_id] = hashlib.sha256(data).hexdigest()
    ordered = sorted(
        service.store.list_jobs(),
        key=lambda job: (str(job.entity.get("created_at") or ""), job.job_id),
    )
    jobs = [job.job_id for job in ordered]
    claimed: list[str] = []

    class ObservedWorker(IntakeWorker):
        def _claim(self, job_id: str) -> bool:
            accepted = super()._claim(job_id)
            if accepted:
                # This runs on the scheduler before it starts the job thread.
                claimed.append(job_id)
            return accepted

        def _run_job(self, job_id: str) -> None:
            if job_id == jobs[0]:
                assert second_recorded.wait(10), "second job did not reach OCR"
            super()._run_job(job_id)

    worker = ObservedWorker(service, max_concurrency=2, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: len(ocr.calls) >= 2)
        # Two earliest jobs occupy the slots; the third cannot overtake them.
        await wait_for(
            lambda: len(service.store.read_job(jobs[2]).entity.get("waiting_reason") or "") > 0
        )
        third = service.store.read_job(jobs[2])
        assert third.status == "queued"
        assert third.entity["waiting_reason"] == "worker_limit"
        assert [job_status(service, job_id) for job_id in jobs[:2]] == ["running", "running"]
        assert claimed == jobs[:2]
        assert len(ocr.calls) == 2
        assert set(ocr.calls) == {digests[job_id] for job_id in jobs[:2]}
        # Arrival is deliberately opposite to FIFO dispatch, not merely allowed
        # to race. Neither thread's progress changes which jobs were claimed.
        assert ocr.calls == [digests[jobs[1]], digests[jobs[0]]]
        release.set()
        await wait_for(lambda: all(job_status(service, job_id) == "succeeded" for job_id in jobs))
        assert claimed == jobs
        assert sorted(ocr.calls) == sorted(digests.values())  # all three exactly once
    finally:
        second_recorded.set()
        release.set()
        await worker.stop()


async def test_running_cancel_is_confirmed_only_after_stop(settings) -> None:
    block = threading.Event()
    release = threading.Event()
    ocr = FakeOcr(block=block, release=release)
    service = make_service(settings.data_dir, ocr=ocr)
    result = receive_deferred(
        service,
        request_id="req-cancel-running",
        filename="c.png",
        data=b"cancel-image",
        media_type="image/png",
    )
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(block.is_set)
        with pytest.raises(AppError) as unconfirmed:
            service.intake.cancel(result.job.job_id, confirmed=True)
        assert unconfirmed.value.code is ErrorCode.CANCELLATION_UNCONFIRMED
        assert job_status(service, result.job.job_id) == "running"

        release.set()
        await wait_for(lambda: job_status(service, result.job.job_id) == "cancelled")
        job = service.store.read_job(result.job.job_id)
        assert job.cancel == {"requested": True, "confirmed": True}
        assert job.entity["finished_at"]
    finally:
        release.set()
        await worker.stop()


async def test_queued_cancel_is_immediate_and_terminal(settings) -> None:
    service = make_service(settings.data_dir, ocr=FakeOcr())
    result = receive_deferred(
        service,
        request_id="req-cancel-queued",
        filename="q.png",
        data=b"queued-image",
        media_type="image/png",
    )
    cancelled = service.intake.cancel(result.job.job_id, confirmed=True, reason="user")
    assert cancelled.status == "cancelled"
    again = service.intake.cancel(result.job.job_id, confirmed=True)
    assert again.status == "cancelled"

    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await asyncio.sleep(0.1)
        assert job_status(service, result.job.job_id) == "cancelled"
        assert [entry.status for entry in service.store.read_receipts(result.source.source_id)] == ["received"]
    finally:
        await worker.stop()


async def test_retry_budget_and_successful_branch_reuse(settings) -> None:
    ocr = FakeOcr()
    ocr.fail = True
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=ocr, embedding=embedding)
    result = receive_deferred(
        service,
        request_id="req-retry",
        filename="r.png",
        data=b"retry-image",
        media_type="image/png",
    )
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(service, result.job.job_id) == "partial")
        first = service.receipt(result.source.source_id)
        assert first["latest"]["text"]["status"] == "failed"
        assert first["latest"]["semantic"]["status"] == "searchable"
        assert embedding.calls == ["image"]

        ocr.fail = False
        retried = service.intake.retry(result.job.job_id)
        assert retried.status == "queued"
        assert retried.attempt == 2
        await wait_for(lambda: job_status(service, result.job.job_id) == "succeeded")
        # Semantic success was reused; only the failed text/keyword branch reran.
        assert embedding.calls == ["image"]
        assert len(ocr.calls) == 2
        final = service.receipt(result.source.source_id)
        assert final["latest"]["text"]["status"] == "ready"
        assert final["latest"]["keyword"]["status"] == "searchable"

        service.intake.set_stage(result.job.job_id, status="failed", fail_reason="for test")
        with pytest.raises(AppError) as exhausted:
            service.intake.retry(result.job.job_id)
        assert exhausted.value.code is ErrorCode.BUDGET_EXHAUSTED
    finally:
        await worker.stop()


async def test_stop_parks_inflight_job_as_recovery_required(settings) -> None:
    block = threading.Event()
    release = threading.Event()
    ocr = FakeOcr(block=block, release=release)
    service = make_service(settings.data_dir, ocr=ocr)
    result = receive_deferred(
        service,
        request_id="req-stop",
        filename="s.png",
        data=b"stop-image",
        media_type="image/png",
    )
    worker = IntakeWorker(service, poll_interval=0.01, stop_timeout=0.05)
    worker.start()
    await wait_for(block.is_set)
    await worker.stop()
    release.set()
    job = service.store.read_job(result.job.job_id)
    assert job.status == "recovery_required"
    assert "not replayed" in (job.entity.get("fail_reason") or "")
    # A later worker start must not auto-replay the unknown-side-effect job.
    calls_before = len(ocr.calls)
    second = IntakeWorker(service, poll_interval=0.01)
    second.start()
    try:
        await asyncio.sleep(0.1)
        assert job_status(service, result.job.job_id) == "recovery_required"
        assert len(ocr.calls) == calls_before
    finally:
        await second.stop()


async def test_restart_recovers_running_and_resumes_queued(settings) -> None:
    service = make_service(settings.data_dir, ocr=FakeOcr())
    running = receive_deferred(
        service,
        request_id="req-restart-running",
        filename="run.png",
        data=b"running-image",
        media_type="image/png",
    )
    queued = receive_deferred(
        service,
        request_id="req-restart-queued",
        filename="queued.png",
        data=b"queued-image",
        media_type="image/png",
    )
    service.intake.set_stage(running.job.job_id, status="running", stage="extracting")

    fresh = make_service(settings.data_dir, ocr=FakeOcr())
    worker = IntakeWorker(fresh, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(fresh, queued.job.job_id) == "succeeded")
        assert job_status(fresh, running.job.job_id) == "recovery_required"
    finally:
        await worker.stop()


async def test_deadline_parks_job_as_recovery_required(settings) -> None:
    block = threading.Event()
    release = threading.Event()
    ocr = FakeOcr(block=block, release=release)
    service = make_service(settings.data_dir, ocr=ocr)
    result = receive_deferred(
        service,
        request_id="req-deadline",
        filename="d.png",
        data=b"deadline-image",
        media_type="image/png",
    )
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(block.is_set)
        current = service.store.read_job(result.job.job_id)
        service.store.update_job(
            result.job.job_id,
            {"deadline_at": "2000-01-01T00:00:00.000Z"},
            expected_revision=current.revision,
        )
        release.set()
        await wait_for(lambda: job_status(service, result.job.job_id) == "recovery_required")
        assert "deadline" in (service.store.read_job(result.job.job_id).entity.get("fail_reason") or "")
    finally:
        release.set()
        await worker.stop()


async def test_revoked_queued_source_is_not_processed_or_resurrected(settings) -> None:
    ocr = FakeOcr()
    service = make_service(settings.data_dir, ocr=ocr)
    result = receive_deferred(
        service,
        request_id="req-revoked-before-worker",
        filename="revoked.png",
        data=b"revoked-image",
        media_type="image/png",
    )
    revoked = service.source_actions(result.source.source_id, action="revoke")
    assert revoked["status"] == "archived"

    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(service, result.job.job_id) not in ("queued", "running"))
        assert service.store.read_job(result.job.job_id).status == "failed"
        assert service.store.read_source(result.source.source_id).status == "archived"
        assert ocr.calls == []
    finally:
        await worker.stop()


async def test_scope_dedup_replay_reuses_terminal_work_without_model_calls(settings) -> None:
    ocr = FakeOcr()
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=ocr, embedding=embedding)
    first = receive_deferred(
        service,
        request_id="req-replay-first",
        filename="same.png",
        data=b"same-scope-image",
        media_type="image/png",
    )
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: job_status(service, first.job.job_id) == "succeeded")
        calls = (len(ocr.calls), len(embedding.calls))
        replay = receive_deferred(
            service,
            request_id="req-replay-second",
            filename="same.png",
            data=b"same-scope-image",
            media_type="image/png",
        )
        assert replay.source.source_id == first.source.source_id
        assert replay.job.job_id != first.job.job_id
        await wait_for(lambda: job_status(service, replay.job.job_id) == "succeeded")
        assert (len(ocr.calls), len(embedding.calls)) == calls
        assert len(service.store.list_sources()) == 1
    finally:
        await worker.stop()


@pytest.mark.parametrize("interruption", ["cancel", "deadline", "shutdown"])
async def test_embedding_input_boundary_stops_after_inflight_input(settings, interruption: str) -> None:
    """A blocked fake input remains running until it returns; no second input."""
    entered = threading.Event()
    release = threading.Event()

    class BlockingEmbedding(FakeEmbedding):
        def embed(self, item: Any) -> EmbedResult:
            result = super().embed(item)
            entered.set()
            assert release.wait(10)
            return result

    embedding = BlockingEmbedding()
    service = make_service(settings.data_dir, embedding=embedding)
    result = receive_deferred(
        service, request_id=f"req-input-boundary-{interruption}",
        filename="boundary.png", data=b"fake-image", media_type="image/png",
    )
    worker = IntakeWorker(service, poll_interval=0.01, stop_timeout=0)
    worker.start()
    try:
        await wait_for(entered.is_set)
        if interruption == "cancel":
            with pytest.raises(AppError) as raised:
                service.intake.cancel(result.job.job_id, confirmed=True)
            assert raised.value.code == ErrorCode.CANCELLATION_UNCONFIRMED
            assert job_status(service, result.job.job_id) == "running"
            assert not service.store.read_job(result.job.job_id).cancel["confirmed"]
        elif interruption == "deadline":
            current = service.store.read_job(result.job.job_id)
            service.store.update_job(result.job.job_id,
                {"deadline_at": "2000-01-01T00:00:00.000Z"}, expected_revision=current.revision)
            assert job_status(service, result.job.job_id) == "running"
        else:
            await worker.stop()
            assert job_status(service, result.job.job_id) == "recovery_required"
        release.set()
        expected = "cancelled" if interruption == "cancel" else "recovery_required"
        await wait_for(lambda: job_status(service, result.job.job_id) == expected)
        await wait_for(lambda: not worker._active)
        assert embedding.calls == ["text"]
        latest = service.receipt(result.source.source_id)["latest"]
        assert latest["text"]["status"] == "ready"
        assert latest["keyword"]["status"] == "searchable"
        assert latest["semantic"]["status"] == "searchable"
        assert latest["semantic"]["kinds"] == ["text"]
        assert latest["semantic"]["failed_kinds"] == ["image"]
        assert [entry.kind for entry in service.vector.index.entries_for(result.source.source_id)] == ["text"]
    finally:
        release.set()
        await worker.stop()


async def test_timeout_with_cancel_request_does_not_falsely_confirm_stop(settings) -> None:
    from lightgravity.sources.vectors.embedder import EmbeddingTimeout

    entered = threading.Event()
    release = threading.Event()

    class BlockingTimeout(FakeEmbedding):
        def embed(self, item: Any) -> EmbedResult:
            self.calls.append(item.part_type)
            entered.set()
            assert release.wait(10)
            raise EmbeddingTimeout(timeout_seconds=0.01)

    embedding = BlockingTimeout()
    service = make_service(settings.data_dir, embedding=embedding)
    result = receive_deferred(service, request_id="cancel-with-unknown-timeout",
                              filename="unknown.png", data=b"image", media_type="image/png")
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(entered.is_set)
        with pytest.raises(AppError):
            service.intake.cancel(result.job.job_id, confirmed=True)
        assert job_status(service, result.job.job_id) == "running"
        release.set()
        await wait_for(lambda: job_status(service, result.job.job_id) == "recovery_required")
        assert not service.store.read_job(result.job.job_id).cancel["confirmed"]
        assert embedding.calls == ["text"]
    finally:
        release.set()
        await worker.stop()
