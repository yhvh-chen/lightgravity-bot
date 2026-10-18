"""Focused fixtures for the optional English ASR backend tests.

Routine tests never download a model and never run real inference.  Model
directories are tiny files whose hashes replace the pinned values for that test
only, so the real validation code path (absolute dir + exact filename + SHA-256)
still runs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from lightgravity.asr import pins


def _write_fake(directory: Path, name: str, content: str) -> str:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    encoder = tmp_path / "models" / "encoder"
    reader = tmp_path / "models" / "reader"
    for pin, directory in ((pins.ENCODER_PIN, encoder), (pins.READER_PIN, reader)):
        for name in list(pin.files):
            digest = _write_fake(directory, name, f"fake {pin.role} {name}\n")
            monkeypatch.setitem(pin.files, name, digest)
    return encoder, reader
