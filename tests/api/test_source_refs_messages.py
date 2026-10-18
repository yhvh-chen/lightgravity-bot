"""LG-144 integration: message ``source_refs`` + deferred worker on real lifespan.

These tests use the real ``create_app`` factory.  The worker test injects a
labelled in-process OCR/embedding fake *before* the lifespan starts, so it proves
the resident app really starts the deferred worker and drains a queued job; it
does not contact a model service.  Message tests use the normal app factory and
assert the server-normalized snapshot is persisted for both message surfaces.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX
from lightgravity.sources import build_source_service
from lightgravity.sources.ocr import OcrPageResult
from lightgravity.sources.vectors.embedder import EmbedResult
from lightgravity.sources.vectors.service import VectorSearchService


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class _FakeOcr:
    """Scripted OCR: no network, no credential, records real calls only."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    @property
    def model_id(self) -> str:
        return "fake-ocr"

    def transcribe(self, request: Any) -> OcrPageResult:
        self.calls.append(hashlib.sha256(request.data).hexdigest())
        return OcrPageResult(
            page=request.page,
            text=self.text,
            model=self.model_id,
            media_type=request.media_type,
            input_sha256=hashlib.sha256(request.data).hexdigest(),
            input_bytes=len(request.data),
            prompt_tokens=1,
            completion_tokens=1,
            latency_seconds=0.0,
            finish_reason="stop",
            raw_response=self.text,
        )


class _FakeEmbedding:
    """Scripted embedding fake; records text/image/audio part kinds."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def model_id(self) -> str:
        return "fake-embed"

    @property
    def configured(self) -> bool:
        return True

    def embed(self, item: Any) -> EmbedResult:
        self.calls.append(item.part_type)
        digest = hashlib.sha256(
            item.text.encode("utf-8") if item.part_type == "text" else (item.data or b"")
        ).hexdigest()
        return EmbedResult(
            vector=(1.0, 0.0),
            model=self.model_id,
            dim=2,
            input_kind=item.part_type,
            input_sha256=digest,
            input_bytes=len(item.data or b"") if item.part_type != "text" else len(item.text or ""),
            latency_seconds=0.0,
            prompt_tokens=None,
            raw_response="{}",
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


async def _create_task(api: httpx.AsyncClient, *, request_id: str) -> str:
    response = await api.post(
        f"{API_PREFIX}/tasks",
        json={
            "request_id": request_id,
            "title": "source refs",
            "objective": "exercise message refs",
            "acceptance_criteria": ["n/a"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["task_id"]


async def _create_source(
    api: httpx.AsyncClient,
    *,
    request_id: str,
    body: bytes = b"shared source body",
    filename: str = "note.txt",
    task_ref: str | None = None,
) -> dict[str, Any]:
    scope = {"task_ref": task_ref} if task_ref else {}
    response = await api.post(
        f"{API_PREFIX}/sources",
        json={
            "request_id": request_id,
            "filename": filename,
            "content_base64": _b64(body),
            "media_type": "text/plain",
            "scope": scope,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def worker_app(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, Any, _FakeOcr, _FakeEmbedding]]:
    """Real app lifespan with a labelled fake upstream injected before startup."""

    settings = _settings(tmp_path)
    ocr = _FakeOcr("worker-ocr-token")
    embedding = _FakeEmbedding()
    service = build_source_service(data_dir=settings.data_dir, ocr_backend=ocr)
    service.set_vector(VectorSearchService(service.store, backend=embedding))
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
        enable_intake_worker=True,
    )
    # The app provider deliberately prefers an injected service so the real
    # lifespan can be proven without contacting a model service.
    app.state.source_service = service
    async with app.router.lifespan_context(app):
        yield app, service, ocr, embedding


async def test_real_lifespan_worker_drains_deferred_receive(
    worker_app: tuple[FastAPI, Any, _FakeOcr, _FakeEmbedding],
) -> None:
    app, service, ocr, embedding = worker_app
    assert app.state.intake_worker is not None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as api:
        health = await api.get(f"{API_PREFIX}/health")
        assert health.status_code == 200
        capabilities = health.json()["capabilities"]
        assert capabilities["material_intake_v2"] is True
        assert capabilities["semantic_search"] is True
        assert capabilities["media_direct_embedding"] is True

        created = await api.post(
            f"{API_PREFIX}/sources",
            json={
                "request_id": "req-lifespan-worker",
                "filename": "scan.png",
                "content_base64": _b64(b"\x89PNG worker image"),
                "media_type": "image/png",
                "intake_mode": "deferred",
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["intake_mode"] == "deferred"
        assert payload["job"]["status"] == "queued"
        # The response is before the worker's OCR/embedding calls.
        assert ocr.calls == []
        assert embedding.calls == []
        assert (await api.get(f"{API_PREFIX}/sources")).json()["items"][0]["status"] == "received"

        job_id = payload["job"]["job_id"]
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            job = await api.get(f"{API_PREFIX}/intake/jobs/{job_id}")
            if job.json()["status"] not in ("queued", "running"):
                break
            await asyncio.sleep(0.02)
        assert service.store.read_job(job_id).status == "succeeded"
        assert ocr.calls and "text" in embedding.calls and "image" in embedding.calls

        receipt = await api.get(
            f"{API_PREFIX}/sources/{payload['source']['source_id']}/receipt"
        )
        assert receipt.status_code == 200, receipt.text
        latest = receipt.json()["latest"]
        assert receipt.json()["receipt_version"] == 2
        # LG147 repair: the authoritative receipt carries the real producing job
        # id (verified against job.source_ref/content hash), so Files cancel/retry
        # controls are reachable after refresh instead of being invented.
        assert latest["job_id"] == job_id
        assert latest["text"]["status"] == "ready"
        assert latest["keyword"]["status"] == "searchable"
        assert latest["semantic"]["status"] == "searchable"
        assert latest["semantic"]["kinds"] == ["text", "image"]
        # Intake never creates a delivery Task/Run.
        assert (await api.get(f"{API_PREFIX}/tasks")).json()["items"] == []


async def test_task_message_persists_normalized_source_refs(
    client: httpx.AsyncClient,
) -> None:
    task_id = await _create_task(client, request_id="req-refs-task")
    source = await _create_source(client, request_id="req-refs-global")
    source_id = source["source"]["source_id"]

    response = await client.post(
        f"{API_PREFIX}/tasks/{task_id}/messages",
        json={
            "message_id": "msg_refs_task",
            "content": "with receipt link",
            # Client-supplied metadata is never trusted.
            "source_refs": [
                {
                    "source_id": source_id,
                    "source_version": 99,
                    "content_hash": "not-the-real-hash",
                    "scope": {"task_ref": "task_forged"},
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    history = await client.get(f"{API_PREFIX}/tasks/{task_id}/messages")
    item = next(i for i in history.json()["items"] if i["message_id"] == "msg_refs_task")
    assert item["message"]["source_refs"] == [
        {
            "source_id": source_id,
            "source_version": 1,
            "content_hash": source["source"]["content_hash"],
            "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
        }
    ]
    # Receipt-only: it never becomes the explicit model context selector.
    assert "selected_context" not in item["message"]


async def test_global_message_accepts_only_global_sources(
    client: httpx.AsyncClient,
) -> None:
    global_source = await _create_source(client, request_id="req-refs-global-msg")
    global_id = global_source["source"]["source_id"]
    ok = await client.post(
        f"{API_PREFIX}/conversations/global/messages",
        json={
            "message_id": "msg_global_refs",
            "content": "global receipt link",
            "source_refs": [{"source_id": global_id}],
        },
    )
    assert ok.status_code == 200, ok.text
    listed = await client.get(f"{API_PREFIX}/conversations/global/messages")
    item = next(i for i in listed.json()["items"] if i["message_id"] == "msg_global_refs")
    assert item["message"]["source_refs"][0]["source_id"] == global_id
    assert item["message"]["source_refs"][0]["scope"] == {
        "task_ref": None,
        "project_ref": None,
        "inbox_ref": None,
    }

    task_id = await _create_task(client, request_id="req-refs-cross")
    task_source = await _create_source(
        client, request_id="req-refs-cross-source", task_ref=task_id
    )
    cross = await client.post(
        f"{API_PREFIX}/conversations/global/messages",
        json={
            "message_id": "msg_global_cross",
            "content": "should fail",
            "source_refs": [{"source_id": task_source["source"]["source_id"]}],
        },
    )
    assert cross.status_code == 422, cross.text
    assert cross.json()["error"]["code"] == "reference_invalid"
    history = await client.get(f"{API_PREFIX}/conversations/global/messages")
    assert all(i["message_id"] != "msg_global_cross" for i in history.json()["items"])


async def test_task_message_cross_task_and_revoked_refs_fail(
    client: httpx.AsyncClient,
) -> None:
    owner_task = await _create_task(client, request_id="req-refs-owner")
    other_task = await _create_task(client, request_id="req-refs-other")
    source = await _create_source(
        client, request_id="req-refs-owner-source", task_ref=owner_task
    )
    source_id = source["source"]["source_id"]

    cross = await client.post(
        f"{API_PREFIX}/tasks/{other_task}/messages",
        json={
            "message_id": "msg_cross_task",
            "content": "wrong task",
            "source_refs": [{"source_id": source_id}],
        },
    )
    assert cross.status_code == 422, cross.text
    assert cross.json()["error"]["code"] == "reference_invalid"

    revoked = await client.post(
        f"{API_PREFIX}/sources/{source_id}/actions", json={"action": "revoke"}
    )
    assert revoked.status_code == 200, revoked.text
    gone = await client.post(
        f"{API_PREFIX}/tasks/{owner_task}/messages",
        json={
            "message_id": "msg_revoked_ref",
            "content": "revoked",
            "source_refs": [{"source_id": source_id}],
        },
    )
    assert gone.status_code == 404, gone.text
    error = gone.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"]["revoked"] is True


async def test_source_refs_bounds_and_personal_guidance(
    client: httpx.AsyncClient,
) -> None:
    source = await _create_source(client, request_id="req-refs-bounds")
    source_id = source["source"]["source_id"]
    task_id = await _create_task(client, request_id="req-refs-bounds-task")

    too_many = await client.post(
        f"{API_PREFIX}/tasks/{task_id}/messages",
        json={
            "message_id": "msg_too_many",
            "content": "too many",
            "source_refs": [{"source_id": source_id} for _ in range(11)],
        },
    )
    assert too_many.status_code == 422, too_many.text
    assert too_many.json()["error"]["code"] == "validation_failed"

    duplicate = await client.post(
        f"{API_PREFIX}/tasks/{task_id}/messages",
        json={
            "message_id": "msg_duplicate",
            "content": "duplicate",
            "source_refs": [{"source_id": source_id}, {"source_id": source_id}],
        },
    )
    assert duplicate.status_code == 422, duplicate.text
    assert duplicate.json()["error"]["code"] == "validation_failed"

    personal = await client.post(
        f"{API_PREFIX}/conversations/personal/messages",
        json={
            "message_id": "msg_personal_refs",
            "content": "no shared refs",
            "source_refs": [{"source_id": source_id}],
        },
    )
    assert personal.status_code == 503, personal.text
    error = personal.json()["error"]
    assert error["code"] == "capability_unavailable"
    assert error["details"]["hint"] == "switch_to_team"
    assert error["details"]["field"] == "source_refs"
    # No shared source/message was created by the rejected Personal call.
    global_history = await client.get(f"{API_PREFIX}/conversations/global/messages")
    assert all(i["message_id"] != "msg_personal_refs" for i in global_history.json()["items"])


async def test_material_gate_stays_false_without_started_worker(tmp_path: Path) -> None:
    """A sync-only app must not advertise the v2 intake experience."""

    settings = _settings(tmp_path)
    app = create_app(
        settings,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
        enable_intake_worker=False,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as api:
            body = (await api.get(f"{API_PREFIX}/health")).json()
            assert body["contract_version"] == "1.22.0"
            assert body["capabilities"]["material_intake_v2"] is False
            # Semantic/search routes and the media path are still really mounted.
            assert body["capabilities"]["semantic_search"] is True
            assert body["capabilities"]["media_direct_embedding"] is True
