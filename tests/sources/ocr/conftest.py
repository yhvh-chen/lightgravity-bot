"""Fixtures for the LG-035 OCR / content-version tests.

The tests use a **scripted** OCR backend so the orchestration, page
back-reference, partial-failure, cancel and formal-protection logic is
deterministic and offline.  Real HTTP OCR quality is measured separately in
``probes/lg035`` against the authorized candidate and is **not** replaced by
these tests (LG-035 brief: mock must not stand in for the product quality
evidence).
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from lightgravity.sources.ocr import OcrPageResult, OcrRequest
from lightgravity.sources.processing import ProcessingConfig, ProcessingEngine
from lightgravity.sources.store import SourceStore


def make_png(width: int = 32, height: int = 16, *, rgb: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    """Build a tiny valid PNG with the standard library (no Pillow)."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


@dataclass
class ScriptedBackend:
    """Deterministic per-page OCR outcomes keyed by call order."""

    #: One entry per call: text, or an exception instance, or a status name.
    script: list[object] = field(default_factory=list)
    model: str = "scripted-ocr"
    calls: list[OcrRequest] = field(default_factory=list)

    @property
    def model_id(self) -> str:
        return self.model

    def transcribe(self, request: OcrRequest) -> OcrPageResult:
        import hashlib

        self.calls.append(request)
        index = len(self.calls) - 1
        outcome = self.script[index] if index < len(self.script) else f"page {request.page}"
        if isinstance(outcome, BaseException):
            raise outcome
        text = str(outcome)
        return OcrPageResult(
            page=request.page,
            text=text,
            model=self.model,
            media_type=request.media_type,
            input_sha256=hashlib.sha256(request.data).hexdigest(),
            input_bytes=len(request.data),
            prompt_tokens=10,
            completion_tokens=5,
            latency_seconds=0.01,
            finish_reason="stop",
            raw_response='{"choices":[]}',
        )


@pytest.fixture
def source_store(tmp_path: Path) -> SourceStore:
    return SourceStore(tmp_path / "data")


@pytest.fixture
def engine_factory(source_store: SourceStore) -> Iterator[object]:
    def build(backend: object, **kwargs: object) -> ProcessingEngine:
        return ProcessingEngine(
            source_store,
            backend=backend,  # type: ignore[arg-type]
            config=kwargs.pop("config", ProcessingConfig()),  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )

    yield build
