"""Shared-source audio branch: transcript derivative, provenance and failures."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from lightgravity.asr import build_english_asr_service
from lightgravity.sources import build_source_service
from lightgravity.sources.vectors.embedder import EmbedResult
from lightgravity.sources.vectors.service import VectorSearchService
from lightgravity.sources.worker import IntakeWorker

from asr_helpers import FakeRuntime, make_repository, receive_deferred, wav_bytes


class FakeEmbedding:
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
        data = item.text.encode("utf-8") if item.part_type == "text" else (item.data or b"")
        return EmbedResult(
            vector=(1.0, 0.0),
            model=self.model_id,
            dim=2,
            input_kind=item.part_type,
            input_sha256=hashlib.sha256(data).hexdigest(),
            input_bytes=len(data),
            latency_seconds=0.0,
            prompt_tokens=None,
            raw_response="{}",
        )


@dataclass
class Outcome:
    status: str
    reason: str | None = None
    error_code: str | None = None
    text: str | None = None
    machine: dict[str, Any] | None = None
    latency_seconds: float = 0.0
    audio_seconds: float = 0.0
    stop_confirmed: bool = True


class FakeAsrService:
    def __init__(self, outcome: Outcome | None = None, *, enabled: bool = True) -> None:
        self.outcome = outcome or Outcome(
            "ready",
            text="hello world",
            machine={
                "engine": "eg2-reader-v2",
                "encoder": {"id": "google/embeddinggemma-2"},
                "reader": {"id": "mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader"},
                "runtime": "inprocess",
                "model_version": "eg2-reader-v2+embeddinggemma-2@914f7f89",
                "content_variant": "machine",
                "generated_at": "2026-10-18T00:00:00Z",
            },
        )
        self.enabled = enabled
        self.calls: list[bytes] = []

    def settings_enabled(self) -> bool:
        return self.enabled

    def transcribe(self, data: bytes, *, filename: str, cancel_check: Any = None) -> Outcome:
        self.calls.append(data)
        return self.outcome


def make_service(tmp_path: Path, asr: Any, *, embedding: FakeEmbedding | None = None):
    service = build_source_service(data_dir=tmp_path / "data", english_asr=asr)
    if embedding is not None:
        service.set_vector(VectorSearchService(service.store, backend=embedding))
    return service


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


def configured_asr(tmp_path: Path, fake_models: tuple[Path, Path], runtime: Any):
    asr = build_english_asr_service(
        make_repository(tmp_path), runtime_factory=lambda config: runtime
    )
    encoder, reader = fake_models
    asr.update(
        0,
        {"enabled": True, "model_dir": str(encoder), "reader_dir": str(reader), "threads": 1},
        actor="test",
    )
    return asr


async def test_ready_transcript_provenance_content_and_independent_audio_vector(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    runtime = FakeRuntime(text="hello world")
    asr = configured_asr(tmp_path, fake_models, runtime)
    embedding = FakeEmbedding()
    service = make_service(tmp_path, asr, embedding=embedding)
    audio = wav_bytes()
    result = receive_deferred(service, request_id="req-asr-ready", data=audio)
    assert result.job.budget["max_asr_calls"] == 1

    await run_worker(service, result.job.job_id)
    job = service.store.read_job(result.job.job_id)
    assert job.status == "succeeded"
    assert len(runtime.calls) == 1

    receipt = service.receipt(result.source.source_id)
    latest = receipt["latest"]
    assert latest["text"]["status"] == "ready"
    assert latest["text"]["language"] == "en"
    assert latest["text"]["timestamps"] is None
    assert latest["text"]["machine"]["engine"] == "eg2-reader-v2"
    assert latest["text"]["machine"]["encoder"]["sha256"]
    assert latest["text"]["machine"]["reader"]["license"] == "apache-2.0"
    assert latest["keyword"]["status"] == "searchable"
    assert sorted(latest["semantic"]["kinds"]) == ["audio", "text"]
    assert embedding.calls == ["text", "audio"]

    source = service.get_source(result.source.source_id)
    assert source["language"] == "en"
    assert source["text_status"] == "ready"
    transcript = [item for item in source["derivatives"] if item.get("kind") == "transcript"]
    assert len(transcript) == 1
    assert transcript[0]["model_version"] == "eg2-reader-v2+embeddinggemma-2@914f7f89"
    assert transcript[0]["content_hash"]

    content = service.content_view(result.source.source_id, kind="machine")
    assert content["content"] == "hello world"
    assert content["media_type"] == "text/markdown; charset=utf-8"
    assert service.download_view(result.source.source_id, kind="machine")["bytes"] == b"hello world"
    assert service.download_view(result.source.source_id)["bytes"] == audio

    hits = service.search(type("Req", (), {
        "query": "hello",
        "task_ref": None,
        "project_ref": None,
        "inbox_ref": None,
        "include_global": True,
        "limit": 20,
        "rebuild_if_missing": False,
    })())
    assert any(hit["source_id"] == result.source.source_id for hit in hits["hits"])


async def test_asr_failure_keeps_original_and_direct_audio_branch(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    class FailingRuntime(FakeRuntime):
        def transcribe(self, data: bytes, *, filename: str = "audio", cancel_check: Any = None) -> Any:
            self.calls.append(data)
            raise RuntimeError("scripted inference failure")

    runtime = FailingRuntime()
    asr = configured_asr(tmp_path, fake_models, runtime)
    embedding = FakeEmbedding()
    service = make_service(tmp_path, asr, embedding=embedding)
    audio = wav_bytes()
    result = receive_deferred(service, request_id="req-asr-fail", data=audio)
    await run_worker(service, result.job.job_id)

    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"]["status"] == "failed"
    assert latest["text"]["reason"] == "asr_failed"
    assert latest["keyword"]["status"] == "no_text"
    assert latest["semantic"]["status"] == "searchable"
    assert latest["semantic"]["kinds"] == ["audio"]
    assert service.store.read_job(result.job.job_id).status == "partial"
    assert service.store.read_source(result.source.source_id).entity.get("derivatives") == []
    assert service.download_view(result.source.source_id)["bytes"] == audio
    with pytest.raises(Exception) as missing:
        service.content_view(result.source.source_id, kind="machine")
    assert getattr(missing.value, "details", {}).get("reason") == "asr_failed"


async def test_budget_zero_job_never_calls_asr(tmp_path: Path) -> None:
    asr = FakeAsrService(enabled=False)
    runtime = FakeRuntime()
    service = make_service(tmp_path, asr)
    result = receive_deferred(service, request_id="req-asr-off", data=wav_bytes())
    assert result.job.budget["max_asr_calls"] == 0
    await run_worker(service, result.job.job_id)
    assert asr.calls == []
    assert runtime.calls == []
    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"] == {
        "status": "unavailable",
        "reason": "asr_disabled",
        "error_code": None,
    }


async def test_oversize_bytes_fail_before_model_call(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    runtime = FakeRuntime()
    asr = configured_asr(tmp_path, fake_models, runtime)
    asr.update(0, {"enabled": True, "max_audio_bytes": 10}, actor="test")
    service = make_service(tmp_path, asr)
    result = receive_deferred(service, request_id="req-asr-big", data=b"R" * 20)
    await run_worker(service, result.job.job_id)
    assert runtime.calls == []
    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"]["status"] == "failed"
    assert latest["text"]["reason"] == "audio_too_long"
    assert service.store.read_source(result.source.source_id).entity.get("derivatives") == []


async def test_unconfirmed_stop_parks_whole_job_and_never_replays(tmp_path: Path) -> None:
    asr = FakeAsrService(
        Outcome(
            "extracting",
            reason="asr_stop_unconfirmed",
            error_code="capability_unavailable",
            stop_confirmed=False,
        )
    )
    service = make_service(tmp_path, asr)
    result = receive_deferred(service, request_id="req-asr-unconfirmed", data=wav_bytes())
    await run_worker(service, result.job.job_id)

    job = service.store.read_job(result.job.job_id)
    assert job.status == "recovery_required"
    assert "not replayed" in (job.entity.get("fail_reason") or "")
    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"]["status"] == "extracting"
    assert latest["text"]["reason"] == "asr_stop_unconfirmed"
    calls = len(asr.calls)
    await run_worker(service, result.job.job_id)
    assert len(asr.calls) == calls
    assert service.store.read_job(result.job.job_id).status == "recovery_required"


async def test_confirmed_timeout_is_terminal_failed_not_recovery(tmp_path: Path) -> None:
    asr = FakeAsrService(
        Outcome(
            "failed",
            reason="asr_timeout",
            error_code="capability_unavailable",
            stop_confirmed=True,
        )
    )
    service = make_service(tmp_path, asr)
    result = receive_deferred(service, request_id="req-asr-timeout", data=wav_bytes())
    await run_worker(service, result.job.job_id)
    job = service.store.read_job(result.job.job_id)
    assert job.status == "failed"
    latest = service.receipt(result.source.source_id)["latest"]
    assert latest["text"]["status"] == "failed"
    assert latest["text"]["reason"] == "asr_timeout"


async def test_scope_dedup_reuses_transcript_without_second_asr_call(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    runtime = FakeRuntime(text="hello world")
    asr = configured_asr(tmp_path, fake_models, runtime)
    service = make_service(tmp_path, asr)
    audio = wav_bytes()
    first = receive_deferred(service, request_id="req-asr-dedup-1", data=audio)
    await run_worker(service, first.job.job_id)
    assert len(runtime.calls) == 1

    replay = receive_deferred(service, request_id="req-asr-dedup-2", data=audio)
    assert replay.source.source_id == first.source.source_id
    assert replay.job.job_id != first.job.job_id
    await run_worker(service, replay.job.job_id)
    assert len(runtime.calls) == 1
    assert service.store.read_job(replay.job.job_id).status == "succeeded"
    derivatives = service.store.read_source(first.source.source_id).entity.get("derivatives") or []
    assert len([item for item in derivatives if item.get("kind") == "transcript"]) == 1


async def test_config_change_does_not_rewrite_old_transcript_provenance(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    runtime = FakeRuntime(text="hello world")
    asr = configured_asr(tmp_path, fake_models, runtime)
    service = make_service(tmp_path, asr)
    result = receive_deferred(service, request_id="req-asr-provenance", data=wav_bytes())
    await run_worker(service, result.job.job_id)
    before = service.receipt(result.source.source_id)["latest"]["text"]["machine"]
    before_derivatives = service.store.read_source(result.source.source_id).entity["derivatives"]

    asr.update(0, {"enabled": False}, actor="test")
    after = service.receipt(result.source.source_id)["latest"]["text"]["machine"]
    assert after == before
    assert service.store.read_source(result.source.source_id).entity["derivatives"] == before_derivatives


@pytest.mark.parametrize("integers", [[1, 65536, 8388608], [0, 1073741824, -1073741824]])
def test_pcm32_wav_decodes_integer_samples_without_float_guess(integers: list[int]) -> None:
    """PCM32 bit patterns can also look like plausible finite float samples."""
    import io
    import wave

    np = pytest.importorskip("numpy")
    from lightgravity.asr.audio import decode_audio

    raw = np.asarray(integers, dtype="<i4")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(4)
        handle.setframerate(16000)
        handle.writeframes(raw.tobytes())
    samples = decode_audio(buffer.getvalue(), filename="pcm32.wav", max_seconds=1)
    np.testing.assert_array_equal(samples, raw.astype(np.float32) / 2147483648.0)
    assert samples.dtype == np.float32
