"""LG-035 optional table-aware OCR mode tests (focused, offline, deterministic).

These cover the *behaviour* of the new, default-OFF option, not OCR quality:

* the option is OFF by default and ordinary pages keep the default prompt;
* an explicit invalid env value is rejected, never silently ignored;
* the program-side classifier fires on a real ruled grid and does **not** fire
  on ordinary single-column prose (true gating, not a decorative flag);
* the classification is bounded: an over-size / decompression-bomb PNG is
  refused, and an undecodable input is honestly "not a table";
* the option is wired through the **actual** ``ProcessingEngine.process`` path:
  a table page sends the explicit-grid prompt and records the layout decision in
  evidence, while an ordinary page sends the unchanged default prompt.

No network, no model, no ground truth is used here.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

import pytest

from lightgravity.sources.intake import IntakeService, ReceiveRequest
from lightgravity.sources.ocr import (
    ENV_OCR_TABLE_MODE,
    OCR_PROMPT,
    OCR_TABLE_PROMPT,
    OcrTableModeInvalid,
    classify_image_bytes,
    parse_table_mode_env,
)
from lightgravity.sources.ocr.layout import MAX_PAGE_SIDE
from lightgravity.sources.processing import ProcessingConfig, ProcessingEngine

from .conftest import ScriptedBackend


def _png(width: int, height: int, pixels: bytes) -> bytes:
    """Encode an 8-bit grayscale PNG from a raw row-major buffer (stdlib only)."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + pixels[y * width : (y + 1) * width] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _ruled_table_png() -> bytes:
    """A synthetic 3-column, ruled (booktabs-style) grid: a *real* table layout.

    Mirrors the real fixture: full-width horizontal rules above/below the header
    and at the bottom, with columns separated by **whitespace gutters** (no
    vertical rules) and rows separated by whitespace, so ink appears in >= 2
    columns on nearly every row — exactly what the classifier looks for.  This is
    a *layout* fixture, never used as ground truth.
    """

    w, h = 240, 200
    buf = bytearray([255]) * (w * h)

    def hline(y: int) -> None:
        for x in range(0, w):
            buf[y * w + x] = 0

    def word(x: int, y0: int, y1: int, length: int = 22) -> None:
        for y in range(y0, y1 + 1):
            for i in range(length):
                buf[y * w + (x + i)] = 0

    for y in (10, 30, 170):  # top rule, rule under the header, bottom rule
        hline(y)
    # Three visually separated columns: left [12..70], middle [90..150], right [170..225].
    for (y0, y1) in ((40, 60), (75, 95), (108, 128), (140, 160)):
        word(12, y0, y1)
        word(90, y0, y1)
        word(170, y0, y1)
    word(12, 14, 26)  # header row cells
    word(90, 14, 26)
    word(170, 14, 26)
    return _png(w, h, bytes(buf))


def _prose_png() -> bytes:
    """An ordinary single-column paragraph: no rules, no stable gutters."""

    w, h = 240, 120
    buf = bytearray([255]) * (w * h)
    for row, y in enumerate(range(12, 110, 14)):
        start = 10 + (row % 3)
        for i in range(0, 210, 3):
            buf[y * w + start + i] = 0
    return _png(w, h, bytes(buf))


# ------------------------------------------------------------------ env / config
def test_table_mode_env_default_off_and_valid_values() -> None:
    assert parse_table_mode_env({}, default=False) is False
    assert parse_table_mode_env({ENV_OCR_TABLE_MODE: ""}, default=False) is False
    assert parse_table_mode_env({ENV_OCR_TABLE_MODE: "  "}, default=False) is False
    assert parse_table_mode_env({ENV_OCR_TABLE_MODE: "1"}, default=False) is True
    assert parse_table_mode_env({ENV_OCR_TABLE_MODE: "true"}, default=False) is True
    assert parse_table_mode_env({ENV_OCR_TABLE_MODE: "OFF"}, default=True) is False
    # The default ProcessingConfig keeps the option OFF.
    assert ProcessingConfig().table_mode is False
    assert ProcessingConfig.from_env({}).table_mode is False
    assert ProcessingConfig.from_env({ENV_OCR_TABLE_MODE: "on"}).table_mode is True


def test_table_mode_env_invalid_is_rejected_not_silently_off() -> None:
    for raw in ("maybe", "2", "enabled", "tru"):
        with pytest.raises(OcrTableModeInvalid) as excinfo:
            parse_table_mode_env({ENV_OCR_TABLE_MODE: raw}, default=False)
        assert excinfo.value.details["env"] == ENV_OCR_TABLE_MODE
        assert excinfo.value.details["value"] == raw
    with pytest.raises(OcrTableModeInvalid):
        ProcessingConfig.from_env({ENV_OCR_TABLE_MODE: "perhaps"})


# ------------------------------------------------------------------ classifier
def test_classifier_fires_on_ruled_grid_and_not_on_prose() -> None:
    table = classify_image_bytes(_ruled_table_png())
    assert table.is_table is True
    assert table.column_count >= 2
    assert table.rules_in_region >= 2

    prose = classify_image_bytes(_prose_png())
    assert prose.is_table is False
    assert prose.reason


def test_classifier_is_bounded_and_never_guesses_on_undecodable_or_oversize() -> None:
    # A non-PNG (e.g. JPEG bytes) is not decoded here: it is honestly not a table.
    jpeg = classify_image_bytes(b"\xff\xd8\xff\xe0not-a-png")
    assert jpeg.is_table is False
    assert jpeg.format_supported is False

    # A PNG whose declared geometry exceeds the page cap is refused before any
    # inflation (decompression-bomb guard), not analysed into fake structure.
    oversized = _png(MAX_PAGE_SIDE + 1, 4, bytes([255]) * ((MAX_PAGE_SIDE + 1) * 4))
    refused = classify_image_bytes(oversized)
    assert refused.is_table is False
    assert refused.format_supported is False
    assert "too_large" in refused.reason or "rejected" in refused.reason


# ------------------------------------------------------------------ pipeline
def _receive(store, name: str, data: bytes, media_type: str) -> str:
    service = IntakeService(store)
    result = service.receive(
        ReceiveRequest(request_id=f"req-{name}", filename=name, data=data, media_type=media_type)
    )
    return result.source.source_id


def test_table_mode_off_uses_default_prompt_for_every_page(source_store) -> None:
    source_id = _receive(source_store, "grid.png", _ruled_table_png(), "image/png")
    backend = ScriptedBackend(script=["anything"])
    engine = ProcessingEngine(
        source_store, backend=backend, config=ProcessingConfig(table_mode=False)
    )
    engine.process(source_id)
    assert len(backend.calls) == 1
    # Default option: no prompt override at all, so the adapter's default is used.
    assert backend.calls[0].prompt is None


def test_table_mode_on_selects_table_prompt_only_for_grid(source_store) -> None:
    # 1. A confidently-classified grid page gets the explicit-grid table prompt.
    table_id = _receive(source_store, "grid2.png", _ruled_table_png(), "image/png")
    table_backend = ScriptedBackend(script=["| a | b | c |"])
    ProcessingEngine(
        source_store, backend=table_backend, config=ProcessingConfig(table_mode=True)
    ).process(table_id)
    assert table_backend.calls[0].prompt == OCR_TABLE_PROMPT

    # 2. An ordinary page keeps the unchanged default prompt (no override).
    prose_id = _receive(source_store, "prose.png", _prose_png(), "image/png")
    prose_backend = ScriptedBackend(script=["ordinary transcription"])
    ProcessingEngine(
        source_store, backend=prose_backend, config=ProcessingConfig(table_mode=True)
    ).process(prose_id)
    assert prose_backend.calls[0].prompt is None


def test_table_mode_records_layout_decision_and_prompt_hash_in_evidence(source_store) -> None:
    from lightgravity.sources.content import ContentStore

    source_id = _receive(source_store, "grid3.png", _ruled_table_png(), "image/png")
    backend = ScriptedBackend(script=["| a | b | c |"])
    ProcessingEngine(
        source_store, backend=backend, config=ProcessingConfig(table_mode=True)
    ).process(source_id)

    evidence = ContentStore(source_root=source_store.source_dir(source_id)).read_evidence()
    succeeded = [e for e in evidence if e["outcome"] == "succeeded"]
    assert succeeded, evidence
    detail = succeeded[0]["detail"]
    assert detail["prompt_kind"] == "table"
    assert detail["prompt_sha256"] == hashlib.sha256(OCR_TABLE_PROMPT.encode("utf-8")).hexdigest()
    classification = detail["table_classification"]
    assert classification["is_table"] is True
    assert classification["column_count"] >= 2
    # No ground-truth-like payload is recorded.
    assert "truth" not in detail and "cells" not in detail


def test_ordinary_page_default_prompt_hash_is_unchanged(source_store) -> None:
    """The default request is provably unchanged for an ordinary page."""

    from lightgravity.sources.content import ContentStore

    source_id = _receive(source_store, "prose2.png", _prose_png(), "image/png")
    backend = ScriptedBackend(script=["plain text"])
    ProcessingEngine(
        source_store, backend=backend, config=ProcessingConfig(table_mode=True)
    ).process(source_id)
    evidence = ContentStore(source_root=source_store.source_dir(source_id)).read_evidence()
    detail = [e for e in evidence if e["outcome"] == "succeeded"][0]["detail"]
    assert detail["prompt_kind"] == "default"
    assert detail["prompt_sha256"] == hashlib.sha256(OCR_PROMPT.encode("utf-8")).hexdigest()
