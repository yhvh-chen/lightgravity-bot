"""LG-117 draft Embedding test: no persistence, explicit network, real protocol.

All network traffic is a local deterministic HTTP server implementing the same
OpenAI-compatible ``/v1/embeddings`` response shape.  No existing service,
product key or external endpoint is used.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from lightgravity.contracts import AppError
from lightgravity.settings import (
    ConnectionService,
    DraftEmbeddingSpec,
    EmbeddingDraftTester,
    FileSecretStore,
    build_settings_router,
)
from lightgravity.settings.embedding import EMBEDDING_CREDENTIAL_REF
from lightgravity.store import FileStore


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.authorizations: list[str | None] = []
        self.vector: list[float] = [0.1, 0.2, 0.3]
        self.reported_model: str | None = None
        self.status = 200

    def payload(self, requested_model: str) -> dict:
        reported = self.reported_model or requested_model
        return {
            "model": reported,
            "data": [{"embedding": list(self.vector)}],
            "usage": {"prompt_tokens": 5},
        }


@contextmanager
def _server(fake: _FakeEmbeddings) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8"))
            fake.requests.append(body)
            fake.authorizations.append(self.headers.get("Authorization"))
            payload = json.dumps(fake.payload(str(body.get("model")))).encode("utf-8")
            self.send_response(fake.status)
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


def _client(service: ConnectionService) -> TestClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope().model_dump(mode="json"),
        )

    app.include_router(build_settings_router(service), prefix="/api/v1")
    return TestClient(app)


def test_static_draft_makes_no_call_and_writes_nothing(tmp_path: Path) -> None:
    fake = _FakeEmbeddings()
    with _server(fake) as base_url:
        service = _service(tmp_path / "data", tmp_path / "secrets")
        tester = EmbeddingDraftTester(service.embedding)
        result = tester.test_draft(
            DraftEmbeddingSpec(
                base_url=base_url,
                model="embeddinggemma-2-Q8_0",
                credential_value="draft-secret-not-for-network",
                allow_network=False,
            )
        )
    assert result["draft"] is True
    assert result["overall"] == "not_run"
    assert result["requested_model"] == "embeddinggemma-2-Q8_0"
    assert result["reported_model"] is None
    assert result["dim"] is None
    assert result["latency_seconds"] is None
    assert [check["name"] for check in result["checks"]] == [
        "config_parse",
        "runtime_network",
    ]
    assert result["checks"][0]["status"] == "passed"
    assert result["checks"][1]["status"] == "skipped"
    assert fake.requests == []
    assert service.repository.read_settings().exists is False
    assert service.secret_store.list_refs() == []
    assert "draft-secret-not-for-network" not in json.dumps(result)


def test_invalid_static_draft_does_not_call_network(tmp_path: Path) -> None:
    fake = _FakeEmbeddings()
    with _server(fake) as base_url:
        service = _service(tmp_path / "data", tmp_path / "secrets")
        tester = EmbeddingDraftTester(service.embedding)
        result = tester.test_draft(
            DraftEmbeddingSpec(
                base_url=base_url,
                model="",
                allow_network=True,
            )
        )
    assert result["overall"] == "failed"
    assert result["error"]["code"] == "embedding_config_invalid"
    assert result["checks"][0]["status"] == "failed"
    assert result["checks"][1]["status"] == "skipped"
    assert fake.requests == []


def test_network_draft_reports_actual_model_dimension_and_latency(tmp_path: Path) -> None:
    fake = _FakeEmbeddings()
    with _server(fake) as base_url:
        service = _service(tmp_path / "data", tmp_path / "secrets")
        tester = EmbeddingDraftTester(service.embedding)
        secret = "draft-bearer-secret"
        result = tester.test_draft(
            DraftEmbeddingSpec(
                base_url=base_url,
                model="embeddinggemma-2-Q8_0",
                credential_value=secret,
                allow_network=True,
                timeout_seconds=5,
                cold_timeout_seconds=10,
            )
        )
    assert result["overall"] == "verified"
    assert result["requested_model"] == "embeddinggemma-2-Q8_0"
    assert result["reported_model"] == "embeddinggemma-2-Q8_0"
    assert result["dim"] == 3
    assert result["latency_seconds"] is not None
    assert result["latency_seconds"] >= 0
    assert result["credential_source"] == "none"
    assert result["cache_impact"] == "none"
    assert len(fake.requests) == 1
    assert fake.requests[0]["input"] == ["lightgravity embedding connectivity test"]
    assert fake.authorizations[0] == f"Bearer {secret}"
    assert secret not in json.dumps(result)
    assert service.repository.read_settings().exists is False
    assert service.secret_store.list_refs() == []


def test_network_draft_reports_requested_vs_reported_model(tmp_path: Path) -> None:
    fake = _FakeEmbeddings()
    fake.reported_model = "upstream-normalized-model"
    fake.vector = [0.5, 0.25]
    with _server(fake) as base_url:
        service = _service(tmp_path / "data", tmp_path / "secrets")
        tester = EmbeddingDraftTester(service.embedding)
        result = tester.test_draft(
            DraftEmbeddingSpec(
                base_url=base_url,
                model="requested-model",
                allow_network=True,
            )
        )
    assert result["overall"] == "partial"
    assert result["requested_model"] == "requested-model"
    assert result["reported_model"] == "upstream-normalized-model"
    assert result["dim"] == 2
    assert "differs from requested" in result["checks"][1]["detail"]


def test_network_draft_rejects_non_finite_vectors(tmp_path: Path) -> None:
    fake = _FakeEmbeddings()
    fake.vector = [0.1, float("nan")]
    with _server(fake) as base_url:
        service = _service(tmp_path / "data", tmp_path / "secrets")
        tester = EmbeddingDraftTester(service.embedding)
        result = tester.test_draft(
            DraftEmbeddingSpec(
                base_url=base_url,
                model="m",
                allow_network=True,
            )
        )
    assert result["overall"] == "failed"
    assert result["dim"] is None
    assert result["error"]["code"] == "embedding_test_failed"
    assert result["checks"][1]["status"] == "failed"
    assert len(fake.requests) == 1


def test_existing_credential_missing_is_reported_without_network(tmp_path: Path) -> None:
    fake = _FakeEmbeddings()
    with _server(fake) as base_url:
        service = _service(tmp_path / "data", tmp_path / "secrets")
        client = _client(service)
        saved = client.put(
            "/api/v1/settings/embedding",
            json={
                "expected_revision": 0,
                "enabled": True,
                "base_url": base_url,
                "model": "m",
                "credential_action": "set",
                "credential_value": "saved-secret",
            },
        )
        assert saved.status_code == 200
        service.secret_store.delete(EMBEDDING_CREDENTIAL_REF)
        tester = EmbeddingDraftTester(service.embedding)
        result = tester.test_draft(
            DraftEmbeddingSpec(
                base_url=base_url,
                model="m",
                use_existing_credential=True,
                allow_network=True,
            )
        )
    assert result["overall"] == "failed"
    assert "existing credential is not configured" in result["checks"][0]["detail"]
    assert fake.requests == []


def test_route_never_persists_or_echoes_draft_secret(tmp_path: Path) -> None:
    service = _service(tmp_path / "data", tmp_path / "secrets")
    client = _client(service)
    secret = "route-draft-secret-must-not-persist"
    response = client.post(
        "/api/v1/settings/embedding/test-draft",
        json={
            "base_url": "http://127.0.0.1:9/v1",
            "model": "draft-model",
            "credential_value": secret,
            "use_existing_credential": False,
            "allow_network": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert secret not in response.text
    body = response.json()
    assert body["draft"] is True
    assert body["overall"] == "not_run"
    assert service.repository.read_settings().exists is False
    assert service.secret_store.list_refs() == []


def test_cache_impact_prompts_rebuild_for_other_model(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    service = _service(data_dir, tmp_path / "secrets")
    client = _client(service)
    created = client.put(
        "/api/v1/settings/embedding",
        json={
            "expected_revision": 0,
            "enabled": True,
            "base_url": "http://127.0.0.1:9/v1",
            "model": "cached-model",
            "credential_action": "keep",
        },
    )
    assert created.status_code == 200

    from lightgravity.sources.vectors.index import VectorIndex

    VectorIndex(data_dir / "sources-index" / "vectors").replace_all(
        [], model="cached-model", dim=3
    )
    tester = EmbeddingDraftTester(service.embedding)
    result = tester.test_draft(
        DraftEmbeddingSpec(
            base_url="http://127.0.0.1:9/v1",
            model="different-model",
            allow_network=False,
        )
    )
    assert result["cache_impact"] == "rebuild_required"
