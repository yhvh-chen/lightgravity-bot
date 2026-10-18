"""Google-native ASR through the real source intake pipeline (docs/08 §23.8).

The only fake is the HTTP transport, which replays the recorded LG-235 H1
response.  Original persistence, machine transcript, receipt, keyword index,
formal retention, idempotency and disable/reload history use the actual source
worker/service code.  No torch/numpy/Reader/model container is involved.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable

from lightgravity.asr import build_english_asr_service
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

    def post(self, *, url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
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


async def test_google_transcript_flows_through_canonical_source_pipeline(
    tmp_path: Path,
) -> None:
    transport = RecordedTransport()
    asr = configured_google(tmp_path, transport)
    service = build_source_service(data_dir=tmp_path / "data", english_asr=asr)
    audio = wav_bytes()
    result = receive_deferred(service, request_id="req-google-pipeline", data=audio)
    assert result.job.budget["max_asr_calls"] == 1
    await run_worker(service, result.job.job_id)

    job = service.store.read_job(result.job.job_id)
    assert job.status == "succeeded"
    assert len(transport.calls) == 1
    request = json.loads(transport.calls[0])
    assert "fake-google-key" not in transport.calls[0].decode("utf-8")
    assert request["model"] == "gemini-3.8-flash"

    receipt = service.receipt(result.source.source_id)["latest"]
    assert receipt["text"]["status"] == "ready"
    assert receipt["text"]["language"] == "en"
    assert receipt["text"]["timestamps"] is None
    machine = receipt["text"]["machine"]
    assert machine["engine"] == "google-native"
    assert machine["provider"] == "google"
    assert machine["runtime"] == "google-native"
    assert machine["model_version"] == "google-native:gemini-3.8-flash"
    assert machine["prompt_version"] == "google-native-transcribe-v1"
    assert machine["audio_sha256"]
    assert machine["usage"]["total_tokens"] == 320
    assert receipt["keyword"]["status"] == "searchable"

    source = service.get_source(result.source.source_id)
    assert source["language"] == "en"
    assert source["text_status"] == "ready"
    transcript = [item for item in source["derivatives"] if item.get("kind") == "transcript"]
    assert len(transcript) == 1
    assert transcript[0]["model_version"] == "google-native:gemini-3.8-flash"
    assert transcript[0]["content_hash"]
    assert service.content_view(result.source.source_id, kind="machine")["content"] == H1_TEXT
    assert service.download_view(result.source.source_id)["bytes"] == audio

    # A human formal version remains authoritative and never replaces machine.
    service.edit_formal(
        result.source.source_id,
        content="Human formal transcript.",
        edited_by="user",
    )
    formal = service.content_view(result.source.source_id, kind="formal")["content"]
    assert formal.endswith("Human formal transcript.")
    assert "human-edited" in formal
    assert service.content_view(result.source.source_id, kind="machine")["content"] == H1_TEXT

    # Disabling ASR does not hide/delete history or trigger another call.
    asr.update(0, {"enabled": False}, actor="test")
    after = service.receipt(result.source.source_id)["latest"]["text"]["machine"]
    assert after == machine
    assert service.content_view(result.source.source_id, kind="machine")["content"] == H1_TEXT

    # Re-uploading the same bytes reuses the terminal transcript (no new HTTP).
    replay = receive_deferred(service, request_id="req-google-pipeline-replay", data=audio)
    assert replay.job.budget["max_asr_calls"] == 0
    await run_worker(service, replay.job.job_id)
    assert len(transport.calls) == 1
    assert service.store.read_job(replay.job.job_id).status == "succeeded"
