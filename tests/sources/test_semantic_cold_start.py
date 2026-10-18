"""LG256 functional reproduction: no provider/model calls, explicit fixture doubles."""
import base64
import json
import threading

import httpx
import pytest

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.sources.vectors.embedder import EmbeddingServiceError
from test_embedding_refresh import save
from test_intake_worker import FakeEmbedding, FakeOcr, wait_for


@pytest.mark.parametrize("outcome", ["success", "unconfigured", "failure"])
async def test_first_image_receipt_preserves_running_semantic(settings, monkeypatch, outcome):
    for name in ("LIGHTGRAVITY_VECTOR_BASE_URL", "LIGHTGRAVITY_VECTOR_MODEL", "LIGHTGRAVITY_VECTOR_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    entered, release = threading.Event(), threading.Event()

    class ControlledEmbedding(FakeEmbedding):
        def embed(self, item):
            entered.set()
            assert release.wait(10), "fixture release missing"
            if outcome == "failure":
                raise EmbeddingServiceError(status=503, message="controlled fixture failure")
            return super().embed(item)

    backend = ControlledEmbedding()
    monkeypatch.setattr("lightgravity.settings.embedding.backend_from_values", lambda **_: backend)
    monkeypatch.setattr("lightgravity.sources.ocr.backend_from_env", lambda: FakeOcr())
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    async with app.router.lifespan_context(app):
        assert not app.state.source_service.vector.enabled
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            if outcome != "unconfigured":
                await save(client, model="fake-embed")
            assert not entered.is_set()  # configuration never warmed/tested a model
            result = (await client.post("/api/v1/sources", json={
                "request_id": "cold-first-image", "filename": "scan.png", "media_type": "image/png",
                "content_base64": base64.b64encode(b"fixture image bytes").decode(),
                "intake_mode": "deferred",
            })).json()
            source_id = result["source"]["source_id"]
            job_id = result["job"]["job_id"]
            try:
                if outcome != "unconfigured":
                    await wait_for(entered.is_set)
                    # Extraction left the initial vector index disabled, but the
                    # explicit worker branch is still pending while embed runs.
                    raw = app.state.source_service.store.read_receipts(source_id)[-1]
                    interim = (await client.get(f"/api/v1/sources/{source_id}/receipt")).json()["latest"]
                    print(json.dumps({"phase": "blocked-first-embedding", "raw_semantic": raw.semantic,
                                      "api_semantic": interim["semantic"]}))
                    assert raw.semantic["status"] == "pending"
                    assert interim["text"]["status"] == "ready"
                    assert interim["keyword"]["status"] == "searchable"
                    assert interim["semantic"]["status"] == "pending"
            finally:
                release.set()
            await wait_for(lambda: app.state.source_service.get_job(job_id)["status"] not in ("queued", "running"))
            receipt = (await client.get(f"/api/v1/sources/{source_id}/receipt")).json()
            source = app.state.source_service.store.read_source(source_id)
            expected = {"success": "searchable", "unconfigured": "disabled", "failure": "failed"}[outcome]
            print(json.dumps({"outcome": outcome, "receipt": receipt["latest"]["semantic"], "index": source.entity["index"]}))
            assert receipt["latest"]["semantic"]["status"] == expected
            assert source.entity["index"]["vector"] == {"success": "indexed", "unconfigured": "disabled", "failure": "failed"}[outcome]
            if outcome == "success":
                assert receipt["latest"]["semantic"]["kinds"] == ["text", "image"]
            if outcome == "unconfigured":
                assert not entered.is_set()
                assert receipt["latest"]["semantic"]["reason"] == "vector_backend_unavailable"


def test_only_absent_legacy_branch_fields_use_current_index(settings):
    from test_intake_worker import make_service, receive_deferred

    service = make_service(settings.data_dir)
    result = receive_deferred(service, request_id="legacy-projection", filename="old.txt",
                              data=b"legacy fixture", media_type="text/plain")
    source_id = result.source.source_id
    source = service.store.read_source(source_id)
    service.store.update_source(source_id, {"status": "extracted", "index": {
        "lexical": "indexed", "vector": "indexed", "vector_model": "legacy-model",
    }}, expected_revision=source.revision)
    path = service.store.receipt_path(source_id)
    entry = json.loads(path.read_text().splitlines()[-1])
    assert "branch_fields" not in entry  # internal provenance adds no persisted/API field
    # Modern pending remains authoritative even after source index changes.
    assert service.receipt(source_id)["latest"]["semantic"]["status"] == "pending"
    entry.pop("semantic")
    path.write_text(json.dumps(entry) + "\n")
    # A genuine pre-v2 missing field still gets the existing legacy projection.
    latest = make_service(settings.data_dir).receipt(source_id)["latest"]
    assert latest["semantic"]["status"] == "searchable"
    assert latest["semantic"]["model"] == "legacy-model"
    assert latest["text"]["status"] == "pending"
    assert "branch_fields" not in latest
