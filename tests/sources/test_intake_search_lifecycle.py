"""Real ASGI intake/search regressions; no seeded derivatives or formal edits."""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path

import httpx
import pytest


async def _upload(
    api: httpx.AsyncClient, workspace: Path, name: str, text: str, *, via_path: bool,
    task_ref: str | None = None,
) -> dict:
    payload: dict = {
        "request_id": f"request-{name}", "filename": f"{name}.txt", "media_type": "text/plain",
        "scope": {"task_ref": task_ref} if task_ref else {},
    }
    if via_path:
        (workspace / f"{name}.txt").write_text(text)
        payload["path"] = f"{name}.txt"
    else:
        payload["content_base64"] = base64.b64encode(text.encode()).decode()
    response = await api.post("/api/v1/sources", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["source"]["status"] == "extracted"
    return response.json()


@pytest.mark.parametrize("via_path", [False, True], ids=["inline", "workspace-path"])
async def test_intake_adds_native_text_to_existing_search_cache(
    api: httpx.AsyncClient, workspace: Path, via_path: bool,
) -> None:
    first = await _upload(api, workspace, "first", "earlymaterialtoken", via_path=via_path)
    # The normal lazy missing-cache path establishes a real existing cache on
    # the old implementation too. No edits, seeded bodies, or rebuild after
    # receiving the second file are permitted in this regression.
    cached = await api.get("/api/v1/search", params={
        "q": "earlymaterialtoken", "include_global": True, "rebuild_if_missing": True,
    })
    assert cached.status_code == 200, cached.text
    assert [h["source_id"] for h in cached.json()["hits"]] == [first["source"]["source_id"]]
    second = await _upload(api, workspace, "second", "newmaterialtoken", via_path=via_path)
    fresh = await api.get("/api/v1/search", params={"q": "newmaterialtoken", "include_global": True})
    assert fresh.status_code == 200, fresh.text
    assert [h["source_id"] for h in fresh.json()["hits"]] == [second["source"]["source_id"]]
    assert fresh.json()["hits"][0]["source_version"] == second["source"]["source_version"]
    assert (await api.get("/api/v1/tasks")).json()["items"] == []


async def test_first_intake_is_searchable_and_replay_does_not_write_again(
    api: httpx.AsyncClient, workspace: Path,
) -> None:
    received = await _upload(api, workspace, "first", "freshcachetoken", via_path=False)
    source = received["source"]
    found = await api.get("/api/v1/search", params={"q": "freshcachetoken"})
    assert found.status_code == 200, found.text
    assert [h["source_id"] for h in found.json()["hits"]] == [source["source_id"]]
    replay = await api.post("/api/v1/sources", json={
        "request_id": "request-first", "filename": "first.txt", "media_type": "text/plain",
        "content_base64": base64.b64encode(b"freshcachetoken").decode(),
    })
    assert replay.status_code == 200, replay.text
    assert replay.json()["deduplicated"] is True
    assert replay.json()["source"]["revision"] == source["revision"]
    assert replay.json()["source"]["source_version"] == source["source_version"]


async def test_intake_index_keeps_task_scope_and_revocation(
    api: httpx.AsyncClient, workspace: Path,
) -> None:
    task = await api.post("/api/v1/tasks", json={
        "request_id": "task-source-scope", "title": "Scoped material", "objective": "Keep scope",
        "acceptance_criteria": ["scoped search only"],
    })
    assert task.status_code == 200, task.text
    task_id = task.json()["task_id"]
    received = await _upload(api, workspace, "scoped", "restrictedtoken", via_path=False, task_ref=task_id)
    source_id = received["source"]["source_id"]
    global_hits = await api.get("/api/v1/search", params={"q": "restrictedtoken", "include_global": True, "rebuild_if_missing": True})
    assert global_hits.status_code == 200, global_hits.text
    assert global_hits.json()["hits"] == []
    scoped = await api.get("/api/v1/search", params={"q": "restrictedtoken", "task_ref": task_id})
    assert scoped.status_code == 200, scoped.text
    assert [h["source_id"] for h in scoped.json()["hits"]] == [source_id]
    revoked = await api.post(f"/api/v1/sources/{source_id}/actions", json={"action": "revoke"})
    assert revoked.status_code == 200, revoked.text
    replay = await api.post("/api/v1/sources", json={
        "request_id": "request-scoped", "filename": "scoped.txt", "media_type": "text/plain",
        "content_base64": base64.b64encode(b"restrictedtoken").decode(), "scope": {"task_ref": task_id},
    })
    assert replay.status_code == 200, replay.text
    assert replay.json()["source"]["status"] == "archived"
    assert replay.json()["source"]["source_version"] == received["source"]["source_version"]
    hidden = await api.get("/api/v1/search", params={"q": "restrictedtoken", "task_ref": task_id})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["hits"] == []


async def test_reprocessing_native_version_refreshes_existing_index(
    api: httpx.AsyncClient, workspace: Path, app,
) -> None:
    received = await _upload(api, workspace, "versioned", "oldversiontoken", via_path=False)
    source_id = received["source"]["source_id"]
    cached = await api.get("/api/v1/search", params={
        "q": "oldversiontoken", "rebuild_if_missing": True,
    })
    assert cached.status_code == 200, cached.text
    assert [h["source_id"] for h in cached.json()["hits"]] == [source_id]
    # Use the existing program-controlled original-version API, then run the
    # actual HTTP reprocess action. No extraction, formal body, or index is seeded.
    app.state.source_service.intake.record_version(source_id, b"newversiontoken")
    processed = await api.post(f"/api/v1/sources/{source_id}/actions", json={"action": "reprocess"})
    assert processed.status_code == 200, processed.text
    assert processed.json()["source_version"] == 2
    old = await api.get("/api/v1/search", params={"q": "oldversiontoken"})
    assert old.status_code == 200, old.text
    assert old.json()["hits"] == []
    new = await api.get("/api/v1/search", params={"q": "newversiontoken"})
    assert new.status_code == 200, new.text
    assert [h["source_id"] for h in new.json()["hits"]] == [source_id]
    assert new.json()["hits"][0]["source_version"] == 2


async def test_deferred_worker_makes_native_text_searchable(
    api: httpx.AsyncClient, app, settings,
) -> None:
    from lightgravity.sources.worker import IntakeWorker

    received = await api.post("/api/v1/sources", json={
        "request_id": "req-deferred-search",
        "filename": "deferred.txt",
        "media_type": "text/plain",
        "content_base64": base64.b64encode(b"deferredsearchtoken").decode(),
        "intake_mode": "deferred",
    })
    assert received.status_code == 201, received.text
    payload = received.json()
    assert payload["job"]["status"] == "queued"
    assert (await api.get("/api/v1/search", params={"q": "deferredsearchtoken"})).json()["hits"] == []

    service = app.state.source_service
    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if service.store.read_job(payload["job"]["job_id"]).status not in ("queued", "running"):
                break
            await asyncio.sleep(0.01)
        assert service.store.read_job(payload["job"]["job_id"]).status == "succeeded"
    finally:
        await worker.stop()
    found = await api.get("/api/v1/search", params={"q": "deferredsearchtoken"})
    assert found.status_code == 200, found.text
    assert [hit["source_id"] for hit in found.json()["hits"]] == [payload["source"]["source_id"]]
