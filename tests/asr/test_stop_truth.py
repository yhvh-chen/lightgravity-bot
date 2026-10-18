"""Stop truth for the in-process ASR runtime: timeout/cancel are not assumed."""

from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path
from typing import Any

from lightgravity.asr import build_english_asr_service
from lightgravity.asr.service import AsrSnapshot

from asr_helpers import FakeRuntime, FakeRuntimeValue, make_repository, wav_bytes


def _configured(tmp_path: Path, fake_models: tuple[Path, Path], runtime: Any):
    service = build_english_asr_service(
        make_repository(tmp_path), runtime_factory=lambda config: runtime
    )
    encoder, reader = fake_models
    service.update(
        0,
        {"enabled": True, "model_dir": str(encoder), "reader_dir": str(reader), "threads": 1},
        actor="test",
    )
    return service


def _short_timeout(service: Any, seconds: float) -> None:
    original = service._snapshot

    def snapshot() -> AsrSnapshot:
        snap = original()
        return dataclasses.replace(
            snap, config=dataclasses.replace(snap.config, timeout_seconds=seconds)
        )

    service._snapshot = snapshot


def test_timeout_without_real_stop_is_unconfirmed(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingRuntime(FakeRuntime):
        def transcribe(self, data: bytes, *, filename: str = "audio", cancel_check: Any = None) -> Any:
            self.calls.append(data)
            started.set()
            assert release.wait(5)
            return FakeRuntimeValue()

    runtime = BlockingRuntime()
    service = _configured(tmp_path, fake_models, runtime)
    _short_timeout(service, 0.05)
    try:
        outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    finally:
        release.set()
    assert started.is_set()
    assert outcome.status == "extracting"
    assert outcome.reason == "asr_stop_unconfirmed"
    assert outcome.stop_confirmed is False
    assert outcome.text is None


def test_timeout_after_real_stop_is_confirmed_failure(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    class SlowRuntime(FakeRuntime):
        def transcribe(self, data: bytes, *, filename: str = "audio", cancel_check: Any = None) -> Any:
            self.calls.append(data)
            time.sleep(0.12)
            return FakeRuntimeValue()

    runtime = SlowRuntime()
    service = _configured(tmp_path, fake_models, runtime)
    _short_timeout(service, 0.02)
    outcome = service.transcribe(wav_bytes(), filename="clip.wav")
    assert outcome.status == "failed"
    assert outcome.reason == "asr_timeout"
    assert outcome.stop_confirmed is True
    assert outcome.text is None


def test_cancel_before_start_calls_no_model(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    runtime = FakeRuntime()
    service = _configured(tmp_path, fake_models, runtime)
    outcome = service.transcribe(
        wav_bytes(), filename="clip.wav", cancel_check=lambda: True
    )
    assert outcome.status == "unavailable"
    assert outcome.reason == "cancelled"
    assert outcome.stop_confirmed is True
    assert runtime.calls == []


def test_cancel_after_start_waits_for_real_stop_and_discards_text(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    started = threading.Event()
    release = threading.Event()
    cancelled = threading.Event()

    class BlockingRuntime(FakeRuntime):
        def transcribe(self, data: bytes, *, filename: str = "audio", cancel_check: Any = None) -> Any:
            self.calls.append(data)
            started.set()
            assert release.wait(5)
            return FakeRuntimeValue(text="must not persist")

    runtime = BlockingRuntime()
    service = _configured(tmp_path, fake_models, runtime)
    result: dict[str, Any] = {}

    def run() -> None:
        result["outcome"] = service.transcribe(
            wav_bytes(),
            filename="clip.wav",
            cancel_check=lambda: cancelled.is_set(),
        )

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(5)
        cancelled.set()
        release.set()
        thread.join(5)
    finally:
        release.set()
    assert not thread.is_alive()
    outcome = result["outcome"]
    assert outcome.status == "unavailable"
    assert outcome.reason == "cancelled"
    assert outcome.text is None
    assert outcome.stop_confirmed is True
