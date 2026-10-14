"""Fixtures for the LG-005 adapter tests.

All entities are created in pytest ``tmp_path``; no test touches ``bot-data``
or the network, and no test call reaches a real model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lightgravity.adapter import ImplementationRegistry, ResourceCompiler
from lightgravity.store import FileStore

from helpers import make_registry, make_store


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return make_store(tmp_path)


@pytest.fixture
def registry() -> ImplementationRegistry:
    return make_registry()


@pytest.fixture
def compiler(store: FileStore, registry: ImplementationRegistry) -> ResourceCompiler:
    return ResourceCompiler(store, registry=registry)
