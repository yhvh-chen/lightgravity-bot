"""LG-117: the optional vector source path uses the independent Embedding config.

A local deterministic HTTP server implements the verified embeddings protocol;
no real embedding service/key is contacted.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.sources import SourceStore
from lightgravity.sources.vectors import VectorSearchRequest, VectorSearchService
from lightgravity.store import FileStore

from .conftest import make_source, write_formal


class _FakeEmbeddingProtocol:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.authorizations: list[str | None] = []


@contextmanager
def _server(fake: _FakeEmbeddingProtocol) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            fake.requests.append(body)
            fake.authorizations.append(self.headers.get("Authorization"))
            # Deterministic finite vector; the input text is hashed into the
            # first component so repeated calls are stable.
            text = str((body.get("input") or [""])[0])
            first = (sum(text.encode("utf-8")) % 97) / 97
            payload = json.dumps(
                {
                    "model": body.get("model"),
                    "data": [{"embedding": [first, 0.5, 0.25]}],
                    "usage": {"prompt_tokens": len(text)},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _service(data_dir: Path, secret_dir: Path) -> ConnectionService:
    return ConnectionService(
        FileStore(data_dir, data_dir / "workspaces"),
        secret_store=FileSecretStore(secret_dir),
        env={},
    )


def test_saved_embedding_settings_drive_optional_vector_source(tmp_path: Path) -> None:
    fake = _FakeEmbeddingProtocol()
    data_dir = tmp_path / "data"
    with _server(fake) as base_url:
        service = _service(data_dir, tmp_path / "secrets")
        saved = service.embedding.update(
            expected_revision=0,
            enabled=True,
            base_url=base_url,
            model="embedding-settings-model",
            credential_action="set",
            credential_value="local-test-token",
            timeout_seconds=5,
            cold_timeout_seconds=10,
            actor="test",
        )
        assert saved["enabled"] is True

        source_store = SourceStore(data_dir)
        record = make_source(source_store, source_id="settings_vector", title="settings vector")
        write_formal(source_store, record.source_id, "alpha beta gamma")

        vector_service = VectorSearchService(
            source_store, backend=service.embedding.backend()
        )
        assert vector_service.enabled is True
        rebuilt = vector_service.rebuild()
        assert rebuilt["rebuilt"] is True
        assert rebuilt["documents"] == 1
        assert rebuilt["model"] == "embedding-settings-model"

        result = vector_service.search(
            VectorSearchRequest(query="alpha", include_global=True)
        )
        assert result["index_status"] == "ok"
        assert [hit["source_id"] for hit in result["hits"]] == [record.source_id]
        assert result["vector_model"] == "embedding-settings-model"

    assert fake.requests
    assert all(request["model"] == "embedding-settings-model" for request in fake.requests)
    assert fake.authorizations[0] == "Bearer local-test-token"
    assert "local-test-token" not in json.dumps(saved)


def test_saved_disabled_embedding_keeps_lexical_fallback(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    service = _service(data_dir, tmp_path / "secrets")
    service.embedding.update(
        expected_revision=0,
        enabled=False,
        base_url="http://127.0.0.1:9/v1",
        model="disabled-model",
        credential_action="keep",
        credential_value=None,
        timeout_seconds=None,
        cold_timeout_seconds=None,
        actor="test",
    )
    source_store = SourceStore(data_dir)
    record = make_source(source_store, source_id="disabled_vector", title="disabled")
    write_formal(source_store, record.source_id, "alpha")

    vector_service = VectorSearchService(
        source_store, backend=service.embedding.backend()
    )
    assert vector_service.enabled is False
    result = vector_service.search(VectorSearchRequest(query="alpha", include_global=True))
    assert result["index_status"] == "index_unavailable"
    assert result["index_unavailable_reason"] == "vector_backend_unavailable"
    assert result["lexical_fallback"] is True
    assert result["hits"] == []
