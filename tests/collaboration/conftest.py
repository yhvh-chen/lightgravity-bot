"""Fixtures and helpers for LG-029 collaboration tests.

All data lives under pytest ``tmp_path``; no test touches ``bot-data``, the
network, the SDK or a real model.  The "workers" are program identities, and the
concurrency tests drive the real :class:`FileStore` (real flock, atomic replace,
JSONL append) — never a stub lease class.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.store import FileStore

from collab_helpers import (  # noqa: F401 - re-exported fixtures/helpers
    FakeClock,
    create_run,
    create_subtask,
    create_task,
)


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


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def task_run(store: FileStore) -> tuple[str, str]:
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    return task_id, run_id
