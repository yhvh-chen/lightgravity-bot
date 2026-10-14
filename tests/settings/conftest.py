"""Fixtures for the LG-025 settings tests.

All data and secrets go to pytest ``tmp_path``; no test touches the default
``bot-data`` or ``secrets`` directories and no unit test reaches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def secret_dir(tmp_path: Path) -> Path:
    return tmp_path / "secrets"


@pytest.fixture
def store(data_dir: Path) -> FileStore:
    return FileStore(data_dir, data_dir / "workspaces")


@pytest.fixture
def secret_store(secret_dir: Path) -> FileSecretStore:
    return FileSecretStore(secret_dir)


@pytest.fixture
def service(store: FileStore, secret_store: FileSecretStore) -> ConnectionService:
    return ConnectionService(store, secret_store=secret_store)
