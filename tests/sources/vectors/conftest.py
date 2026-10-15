"""Fixtures for the LG-037 optional-vector tests.

These build a **real** ``SourceStore`` + ``VectorSearchService`` over pytest
``tmp_path`` and mount the real ``build_vector_router()`` onto a real
``create_app`` app, so the tests exercise the endpoint the way the integration
owner assembles it (``api/app.py`` is untouched).

The default backend is a **deterministic stand-in** (:class:`FakeEmbeddingBackend`)
that produces a synthetic vector from the exact input.  This verifies the
*mechanism* (dimension/model/hash/cache version, model-switch rebuild, delete and
rebuild, failure downgrade,回源 re-verification) **without any network call**.
It is explicitly NOT a real embedding service and NEVER evidences retrieval
quality.  ``tests/sources/vectors/test_real_quality.py`` is the only place that
would touch a real service, and it is skipped unless explicitly authorized.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.api.sources import build_sources_router
from lightgravity.api.vector import build_vector_router
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX
from lightgravity.sources import SourceStore
from lightgravity.sources.vectors import (
    EmbedInput,
    EmbedResult,
    VectorSearchService,
    fragment_hash,
)

#: A fixed, deliberately small dimension so tests are cheap and readable.
FAKE_DIM = 8


class FakeEmbeddingBackend:
    """Deterministic stand-in embedder (NO network; NOT a quality claim).

    The vector is a hash-derived pattern so identical inputs give identical
    vectors and different inputs generally differ.  ``configured`` controls
    whether the optional path is reported enabled.  This is a test替身, never a
    real model.
    """

    def __init__(self, model: str = "fake-embed-v1", dim: int = FAKE_DIM, *, configured: bool = True) -> None:
        self._model = model
        self._dim = dim
        self._configured = configured
        self.calls = 0
        self.fail_with: Exception | None = None

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def configured(self) -> bool:
        return self._configured

    def embed(self, item: EmbedInput) -> EmbedResult:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        if item.part_type == "text":
            payload = (item.text or "").encode("utf-8")
        else:
            payload = item.data or b""
        digest = hashlib.sha256(payload).digest()
        # Expand the digest to ``dim`` finite floats, deterministic per input.
        values: list[float] = []
        counter = 0
        while len(values) < self._dim:
            block = hashlib.sha256(digest + struct.pack(">I", counter)).digest()
            for i in range(0, len(block), 4):
                if len(values) >= self._dim:
                    break
                number = struct.unpack(">i", block[i : i + 4])[0] / 2**31
                values.append(number)
            counter += 1
        return EmbedResult(
            vector=tuple(values),
            model=self._model,
            dim=self._dim,
            input_kind=item.part_type,
            input_sha256=hashlib.sha256(payload).hexdigest(),
            input_bytes=len(payload),
            latency_seconds=0.0,
            prompt_tokens=None,
            raw_response="{}",
        )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


@pytest.fixture
def backend() -> FakeEmbeddingBackend:
    return FakeEmbeddingBackend()


def build_app(settings: Settings, backend: Any) -> FastAPI:
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
    )
    # One-line wiring the integration owner applies to api/app.py.
    app.include_router(build_sources_router(), prefix=API_PREFIX)
    app.include_router(build_vector_router(), prefix=API_PREFIX)
    # Inject the stand-in backend so no test contacts a network service.
    app.state.vector_test_backend = backend
    return app


@pytest.fixture
def app(settings: Settings, backend: FakeEmbeddingBackend) -> FastAPI:
    return build_app(settings, backend)


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
def source_store(settings: Settings) -> SourceStore:
    return SourceStore(settings.data_dir)


@pytest.fixture
def service(source_store: SourceStore, backend: FakeEmbeddingBackend) -> VectorSearchService:
    return VectorSearchService(source_store, backend=backend)


def make_source(
    store: SourceStore,
    *,
    source_id: str,
    title: str = "doc",
    scope: dict[str, Any] | None = None,
    original: dict[str, Any] | None = None,
) -> Any:
    """Create a minimal ``source`` record on the real store.

    ``source_id`` may be a short label; it is expanded to a valid
    ``source_<ULID>`` identifier (the store enforces the frozen ID regex).
    """

    entity_id = source_id if source_id.startswith("source_") and len(source_id) == 33 else _ulid(source_id)
    entity: dict[str, Any] = {
        "schema": "lightgravity.bot/v1",
        "kind": "source",
        "id": entity_id,
        "title": title,
        "title_origin": "user",
        "status": "extracted",
        "revision": 0,
        "scope": scope or {"task_ref": None, "project_ref": None, "inbox_ref": None},
        "origin": {"kind": "upload", "external_ref": None, "fetched": False},
        "content_hash": fragment_hash(title),
        "stat_revision": None,
        "source_version": 1,
        "original": original or {"path": None, "media_type": None, "bytes": None, "archived_at": None},
        "derivatives": [],
        "formal": {"path": None, "revision": None, "edited_by": None},
        "index": {"lexical": "not_indexed", "lexical_hash": None, "vector": "disabled", "vector_model": None},
        "receipt_ref": None,
        "created_at": None,
        "updated_at": None,
    }
    return store.create_source(entity_id, entity)


def _ulid(label: str) -> str:
    """Derive a stable, valid 26-char Crockford-base32 ULID-like id from a label."""

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    value = int.from_bytes(digest[:16], "big")
    chars: list[str] = []
    for _ in range(26):
        chars.append(alphabet[value % 32])
        value //= 32
    return "source_" + "".join(reversed(chars))


def write_formal(source_store: SourceStore, source_id: str, text: str) -> None:
    from lightgravity.sources.content import ContentStore

    ContentStore(source_root=source_store.source_dir(source_id)).write_formal(
        text, edited_by="test", expected_revision=None
    )


def write_original_media(source_store: SourceStore, source_id: str, name: str, data: bytes) -> None:
    source_store.persist_original(source_id, name, data)
