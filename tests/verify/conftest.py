"""Fixtures for the LG-009 verification/acceptance tests.

All data lives under pytest ``tmp_path``; no test touches ``bot-data``, the
network or a real model.  The executor/graph paths are exercised by the
coordinator's in-process fakes; the real SDK end-to-end path is LG-010.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.store import FileStore


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def store(data_dir: Path, workspace_root: Path) -> FileStore:
    return FileStore(data_dir, workspace_root)
