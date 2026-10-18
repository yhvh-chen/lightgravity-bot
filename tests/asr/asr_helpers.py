"""Focused fakes/helpers for the optional English ASR backend tests."""

from __future__ import annotations

import base64
import hashlib
import io
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FakeStore:
    data_dir: Path


@dataclass
class FakeRepository:
    store: FakeStore


def make_repository(tmp_path: Path) -> FakeRepository:
    return FakeRepository(store=FakeStore(data_dir=tmp_path / "data"))


@dataclass
class FakeRuntimeValue:
    text: str = "hello world"
    latency_seconds: float = 0.01
    audio_seconds: float = 0.01


class FakeRuntime:
    def __init__(self, *, text: str = "hello world") -> None:
        self.text = text
        self.calls: list[Any] = []
        self.closed = False

    def transcribe(self, data: bytes, *, filename: str = "audio", cancel_check: Any = None) -> FakeRuntimeValue:
        self.calls.append(data)
        if cancel_check is not None and cancel_check():
            raise RuntimeError("cancelled")
        return FakeRuntimeValue(text=self.text)

    def close(self) -> None:
        self.closed = True


def wav_bytes(seconds: float = 0.2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\x00\x00" * int(16_000 * seconds))
    return buffer.getvalue()


def receive_deferred(service: Any, *, request_id: str, data: bytes, media_type: str = "audio/wav") -> Any:
    return service.receive_inline(
        request_id=request_id,
        filename="clip.wav",
        content_base64=base64.b64encode(data).decode("ascii"),
        media_type=media_type,
        intake_mode="deferred",
    )
