"""LG-222: explicit audio reprocess uses the configured ASR branch, not OCR.

The only fake is the Google HTTP transport replaying the recorded LG-235 H1
response.  Original persistence, the new reprocess intake job, the worker,
transcript persistence, receipt and keyword index are the real code paths.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from lightgravity.asr import build_english_asr_service
from lightgravity.contracts import AppError, ErrorCode
from lightgravity.settings import FileSecretStore
from lightgravity.sources import build_source_service
from lightgravity.sources.worker import IntakeWorker

from asr_helpers import make_repository, receive_deferred, wav_bytes

FIXTURES = Path(__file__).with_name("fixtures")
H1_TEXT = (
    "On April 9th 2027 the North Harbor market opens at 6:45 and the ferry to "
    "Cedar Island carries 38 passengers."
)


class RecordedTransport:
    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.payload = (FIXTURES / "lg235_h1_response.json").read_bytes()

    def post(
        self, *, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        self.calls.append(body)
        return 200, self.payload


def configured_google(tmp_path: Path, transport: RecordedTransport):
    secrets = FileSecretStore(tmp_path / "secrets")
    asr = build_english_asr_service(
        make_repository(tmp_path), secret_store=secrets, google_transport=transport
    )
    asr.update(
        0,
        {
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "credential_ref": "google-asr-api",
            "credential_value": "fake-google-key",
        },
        actor="test",
    )
    return asr


async def wait_for(predicate: Callable[[], bool], *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


async def run_worker(service: Any, job_id: str) -> None:
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        await wait_for(lambda: service.store.read_job(job_id).status not in ("queued", "running"))
    finally:
        await worker.stop()


async def test_old_audio_reprocess_gets_one_new_google_attempt_and_is_searchable(
    tmp_path: Path,
) -> None:
    transport = RecordedTransport()
    secrets = FileSecretStore(tmp_path / "secrets")
    asr = build_english_asr_service(
        make_repository(tmp_path), secret_store=secrets, google_transport=transport
    )
    service = build_source_service(data_dir=tmp_path / "data", english_asr=asr)
    audio = wav_bytes()
    received = receive_deferred(service, request_id="req-lg222-old-audio", data=audio)
    source_id = received.source.source_id
    old_job_id = received.job.job_id
    # ASR was off when this audio was received: the persisted old job budget
    # reflects that state, and the reprocess action must not silently OCR it.
    assert received.job.budget["max_asr_calls"] == 0
    await run_worker(service, old_job_id)

    before = service.get_source(source_id)
    assert before["reprocess"]["kind"] == "asr"
    assert before["reprocess"]["available"] is False
    with pytest.raises(AppError) as unavailable:
        service.source_actions(source_id, action="reprocess", expected_revision=before["revision"])
    assert unavailable.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert transport.calls == []

    # ASR is enabled later; the old source now exposes an available reprocess
    # path and a new job carries exactly one ASR attempt.
    asr.update(
        0,
        {
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "credential_ref": "google-asr-api",
            "credential_value": "fake-google-key",
        },
        actor="test",
    )
    after = service.get_source(source_id)
    assert after["reprocess"] == {
        "kind": "asr",
        "available": True,
        "reason": None,
        "configured": True,
        "enabled": True,
    }
    result = service.source_actions(
        source_id, action="reprocess", expected_revision=after["revision"]
    )
    assert result["kind"] == "asr"
    assert result["queued"] is True
    job_id = result["job_id"]
    assert job_id != old_job_id
    job = service.store.read_job(job_id)
    assert job.budget["max_asr_calls"] == 1
    assert service.store.read_job(old_job_id).budget["max_asr_calls"] == 0

    await run_worker(service, job_id)

    assert service.store.read_job(job_id).status == "succeeded"
    assert len(transport.calls) == 1
    receipt = service.receipt(source_id)["latest"]
    assert receipt["text"]["status"] == "ready"
    assert receipt["text"]["machine"]["provider"] == "google"
    assert receipt["keyword"]["status"] == "searchable"
    assert service.content_view(source_id, kind="machine")["content"] == H1_TEXT
    hits = service.search(
        type(
            "Req",
            (),
            {
                "query": "ferry",
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


async def test_manual_retry_refreshes_old_zero_asr_budget_once(tmp_path: Path) -> None:
    transport = RecordedTransport()
    secrets = FileSecretStore(tmp_path / "secrets")
    asr = build_english_asr_service(
        make_repository(tmp_path), secret_store=secrets, google_transport=transport
    )
    service = build_source_service(data_dir=tmp_path / "data", english_asr=asr)
    received = receive_deferred(service, request_id="req-lg222-retry", data=wav_bytes())
    job_id = received.job.job_id
    assert received.job.budget["max_asr_calls"] == 0
    # A terminal partial job is the only retryable state; the point here is that
    # the old persisted zero budget is refreshed when ASR has since been enabled.
    service.store.update_job(
        job_id,
        {
            "status": "partial",
            "stage": "extracting",
            "fail_reason": "asr_disabled",
        },
        expected_revision=service.store.read_job(job_id).revision,
    )
    asr.update(
        0,
        {
            "enabled": True,
            "provider": "google-native",
            "runtime": "google-native",
            "credential_ref": "google-asr-api",
            "credential_value": "fake-google-key",
        },
        actor="test",
    )
    retried = service.intake.retry(job_id)
    assert retried.status == "queued"
    assert retried.budget["max_asr_calls"] == 1
    await run_worker(service, job_id)
    assert len(transport.calls) == 1
    assert service.receipt(received.source.source_id)["latest"]["text"]["status"] == "ready"
