"""LG150: saved embedding settings reach the resident worker without a status GET."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import threading

import httpx
import pytest

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.sources.vectors import EmbedResult


class FakeBackend:
    configured = True

    def __init__(self, base_url, model):
        self.base_url = base_url
        self.model_id = model
        self.calls = []
        self.entered = None
        self.release = None

    def embed(self, item):
        self.calls.append(item.text)
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(10)
        return EmbedResult(vector=(1.0, 0.0), model=self.model_id, dim=2,
                           input_kind=item.part_type, input_sha256=hashlib.sha256((item.text or "").encode()).hexdigest(),
                           input_bytes=len(item.text or ""), latency_seconds=0,
                           prompt_tokens=None, raw_response="{}")


async def save(client, *, enabled=True, model="model-a", base_url="http://fake-a.invalid", **extra):
    revision = (await client.get("/api/v1/settings")).json()["revision"]
    response = await client.put("/api/v1/settings/embedding", json={
        "expected_revision": revision,
        "enabled": enabled, "model": model, "base_url": base_url,
        "credential_action": "keep", **extra})
    assert response.status_code == 200, response.text


async def intake(client, name):
    response = await client.post("/api/v1/sources", json={
        "request_id": name, "filename": f"{name}.txt", "media_type": "text/plain",
        "content_base64": base64.b64encode(name.encode()).decode(), "intake_mode": "deferred"})
    assert response.status_code == 201, response.text
    body = response.json()
    for _ in range(500):
        job = (await client.get(f"/api/v1/intake/jobs/{body['job']['job_id']}")).json()
        if job["status"] not in ("queued", "running"):
            return (await client.get(f"/api/v1/sources/{body['source']['source_id']}/receipt")).json()["latest"]
        await asyncio.sleep(.01)
    raise AssertionError("intake did not finish")


@pytest.fixture
def fake_backends(monkeypatch):
    monkeypatch.setenv("LIGHTGRAVITY_VECTOR_BASE_URL", "http://fake-a.invalid")
    monkeypatch.setenv("LIGHTGRAVITY_VECTOR_MODEL", "model-a")
    monkeypatch.delenv("LIGHTGRAVITY_VECTOR_TOKEN", raising=False)
    backends = []
    def factory(**values):
        backend = FakeBackend(values["base_url"], values["model"])
        backend.saw_fixture_credential = values.get("bearer_token") == "fixture-saved-key"
        backends.append(backend)
        return backend
    monkeypatch.setattr("lightgravity.settings.embedding.backend_from_values", factory)
    return backends


@pytest.mark.parametrize("change", ["disabled", "model", "address"])
async def test_save_then_immediate_intake_refreshes_backend(settings, fake_backends, change):
    backends = fake_backends
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await save(client)
            first = await intake(client, "first")
            assert first["semantic"]["status"] == "searchable"
            vector = app.state.source_service.vector
            cache_path = vector.index.path
            original_cache = cache_path.read_bytes()
            initial_calls = sum(len(backend.calls) for backend in backends)
            await save(client, enabled=change != "disabled", model="model-b" if change == "model" else "model-a",
                       base_url="http://fake-b.invalid" if change == "address" else "http://fake-a.invalid")
            assert sum(len(backend.calls) for backend in backends) == initial_calls
            # No status/search/settings GET occurs between save and this intake.
            latest = await intake(client, "second")
            print({"change": change, "semantic": latest["semantic"],
                   "backend_calls": [(backend.base_url, backend.model_id, len(backend.calls)) for backend in backends]})
            assert latest["semantic"]["status"] == ("disabled" if change == "disabled" else "failed")
            if change != "disabled":
                assert latest["semantic"]["reason"] == "model_mismatch_rebuild_required"
            assert sum(len(backend.calls) for backend in backends) == initial_calls
            assert cache_path.read_bytes() == original_cache
            status = (await client.get("/api/v1/vector/status")).json()
            assert status["enabled"] is (change != "disabled")
            if change != "disabled":
                assert status["model_mismatch_rebuild_required"] is True
                search = (await client.get("/api/v1/vector/search", params={"q": "first"})).json()
                assert search["index_status"] == "index_unavailable"
                assert search["index_unavailable_reason"] == "model_mismatch_rebuild_required"
                assert sum(len(backend.calls) for backend in backends) == initial_calls


async def test_first_enable_and_fixture_credential_priority_without_status(settings, monkeypatch, fake_backends):
    monkeypatch.delenv("LIGHTGRAVITY_VECTOR_BASE_URL")
    monkeypatch.delenv("LIGHTGRAVITY_VECTOR_MODEL")
    monkeypatch.setenv("LIGHTGRAVITY_VECTOR_TOKEN", "fixture-environment-key")
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await save(client, base_url="http://fake-a.invalid/custom", credential_action="set",
                       credential_value="fixture-saved-key")
            assert not any(backend.calls for backend in fake_backends)
            latest = await intake(client, "enabled-first")
            assert latest["semantic"]["status"] == "searchable"
            backend = app.state.source_service.vector.backend
            assert backend.base_url == "http://fake-a.invalid/custom"
            assert backend.saw_fixture_credential
            assert len(backend.calls) == 1
            header = app.state.source_service.vector.index.header()
            assert "fixture-saved-key" not in str(header)
            assert "fixture-environment-key" not in str(header)


async def test_same_model_address_change_remains_incompatible_after_restart(settings, fake_backends):
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await save(client)
            assert (await intake(client, "restart-before"))["semantic"]["status"] == "searchable"
            cache_path = app.state.source_service.vector.index.path
            old_cache = cache_path.read_bytes()
            calls_before = sum(len(backend.calls) for backend in fake_backends)
            await save(client, base_url="http://fake-b.invalid/custom")
    fresh = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    async with fresh.router.lifespan_context(fresh):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fresh), base_url="http://testserver") as client:
            latest = await intake(client, "restart-after")
            assert latest["semantic"]["reason"] == "model_mismatch_rebuild_required"
            assert cache_path.read_bytes() == old_cache
            assert sum(len(backend.calls) for backend in fake_backends) == calls_before
            backend = fresh.state.source_service.vector.backend
            assert backend.base_url == "http://fake-b.invalid/custom"
            assert backend.model_id == "model-a"
            status = (await client.get("/api/v1/vector/status")).json()
            assert status["model_mismatch_rebuild_required"]
            search = (await client.get("/api/v1/vector/search", params={"q": "restart"})).json()
            assert search["index_unavailable_reason"] == "model_mismatch_rebuild_required"
            assert sum(len(item.calls) for item in fake_backends) == calls_before
            rebuilt = await client.post("/api/v1/vector/rebuild")
            assert rebuilt.status_code == 200, rebuilt.text
            assert rebuilt.json()["rebuilt"]
            assert len(backend.calls) == 2
            assert (await intake(client, "restart-third"))["semantic"]["status"] == "searchable"
            assert len(backend.calls) == 3
            assert fresh.state.source_service.vector.index.header()["backend_fingerprint"] == '["http://fake-b.invalid/custom","model-a"]'


async def test_settings_save_does_not_mutate_inflight_backend_snapshot(settings, fake_backends):
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    entered, release = threading.Event(), threading.Event()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await save(client)
            # Resolve the operation's initial backend; no model call occurs.
            old = app.state.source_service.vector.backend
            old.entered, old.release = entered, release
            task = asyncio.create_task(intake(client, "inflight-old"))
            try:
                for _ in range(500):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.01)
                assert entered.is_set()
                await save(client, model="model-b", base_url="http://fake-b.invalid")
                assert old.model_id == "model-a"
                release.set()
                latest = await task
                assert latest["semantic"]["model"] == "model-a"
                assert latest["semantic"]["status"] == "searchable"
                assert len(old.calls) == 1
                subsequent = await intake(client, "inflight-new")
                assert subsequent["semantic"]["model"] == "model-b"
                assert subsequent["semantic"]["reason"] == "model_mismatch_rebuild_required"
                assert app.state.source_service.vector.backend is not old
            finally:
                release.set()
                await task


@pytest.mark.parametrize("operation", ["status", "search"])
async def test_direct_vector_read_refreshes_without_source_request(settings, fake_backends, operation):
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await save(client)
            await intake(client, "direct-read-before")
            before = app.state.source_service.vector.index.path.read_bytes()
            calls_before = sum(len(backend.calls) for backend in fake_backends)
            await save(client, model="model-b")
            response = await client.get(f"/api/v1/vector/{operation}", params={"q": "direct"})
            assert response.status_code == 200
            body = response.json()
            if operation == "status":
                assert body["backend"]["model"] == "model-b"
                assert body["cache"]["compatible"] is False
                assert body["model_mismatch_rebuild_required"]
            else:
                assert body["vector_model"] == "model-b"
                assert body["index_unavailable_reason"] == "model_mismatch_rebuild_required"
            assert sum(len(backend.calls) for backend in fake_backends) == calls_before
            assert app.state.source_service.vector.index.path.read_bytes() == before
