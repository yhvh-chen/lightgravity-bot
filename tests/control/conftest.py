"""Fixtures for LG-016 control/recovery tests.

Reuses the LG-007/008 coordinator helpers so the control tests exercise the
same single-slot coordinator seam.  All state lives under pytest ``tmp_path``;
no test touches the default ``bot-data`` directory or the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lightgravity.store import FileStore

_COORD_TESTS = Path(__file__).resolve().parent.parent / "coordinator"
_API_TESTS = Path(__file__).resolve().parent.parent / "api"
for _p in (_COORD_TESTS, _API_TESTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


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
