"""Fixtures for the LG-007 coordinator tests.

All data is written under pytest ``tmp_path``; no test touches the default
``bot-data`` directory, the user's real data or the network.
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
