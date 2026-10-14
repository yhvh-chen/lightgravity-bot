"""LG-014 Files upload/download and task artifact association (docs/08 §4.3).

All data lands in pytest ``tmp_path`` through the real ``create_app`` wiring.
Writes are exercised with an injected authorization mechanism (the same
``LocalAccessPolicy`` used by tests) so the protected-write path is real, and
the default (no token) path is asserted to honestly deny.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api import files as files_module
from lightgravity.api.access import TOKEN_HEADER, LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.store.ids import new_id


@pytest.fixture
async def token_app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings, access_policy=LocalAccessPolicy(token="sesame"))
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def token_api(token_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=token_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _auth(token: str = "sesame") -> dict[str, str]:
    return {TOKEN_HEADER: token}


async def _create_task(
    app: FastAPI, *, workspace_ref: str | None
) -> str:
    task_id = new_id("task")
    app.state.store.create(
        "task",
        task_id,
        {
            "title": "Files task",
            "status": "todo",
            "phase": "intake",
            "requirements_revision": 1,
            "deliverable_revision": 0,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": workspace_ref,
            "agent_ref": "coordinator",
            "depends_on": [],
            "active_run": None,
            "queue": {"state": "not_queued"},
            "acceptance": {
                "status": "pending",
                "candidate_ref": "run_candidate",
                "evidence_refs": ["artifacts/report.md"],
                "check_records": [{"check_id": "unit", "status": "passed"}],
            },
            "budget": {},
            "archived": False,
        },
        actor="test",
        request_id=f"req-{task_id}",
    )
    return task_id


async def test_upload_is_protected_when_no_token_configured(
    deny_client: httpx.AsyncClient, settings: Settings
) -> None:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    denied = await deny_client.post(
        "/api/v1/files/upload",
        params={"path": "new.txt"},
        content=b"data",
    )
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "unauthorized"
    assert denied.json()["error"]["details"]["reason"] == "authorization_not_configured"
    assert not (settings.workspace_root / "new.txt").exists()


async def test_upload_create_conflict_and_atomic_overwrite(
    token_api: httpx.AsyncClient, settings: Settings
) -> None:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)

    wrong_token = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "note.txt"},
        content=b"nope",
        headers=_auth("wrong"),
    )
    assert wrong_token.status_code == 401

    created = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "note.txt"},
        content=b"hello v1",
        headers=_auth(),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["created"] is True
    assert body["size"] == len(b"hello v1")
    revision = body["revision"]
    assert revision
    assert (settings.workspace_root / "note.txt").read_bytes() == b"hello v1"

    # A blind overwrite (no expected_revision) must not silently replace bytes.
    blind = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "note.txt"},
        content=b"blind",
        headers=_auth(),
    )
    assert blind.status_code == 409
    assert blind.json()["error"]["code"] == "revision_conflict"
    assert (settings.workspace_root / "note.txt").read_bytes() == b"hello v1"

    stale = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "note.txt", "expected_revision": "1-1"},
        content=b"stale",
        headers=_auth(),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["actual_revision"] == revision
    assert (settings.workspace_root / "note.txt").read_bytes() == b"hello v1"

    updated = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "note.txt", "expected_revision": revision},
        content=b"hello v2",
        headers=_auth(),
    )
    assert updated.status_code == 200
    assert updated.json()["created"] is False
    assert (settings.workspace_root / "note.txt").read_bytes() == b"hello v2"


async def test_upload_rejects_escape_symlink_and_secret_store(
    token_api: httpx.AsyncClient, settings: Settings, tmp_path: Path
) -> None:
    root = settings.workspace_root
    root.mkdir(parents=True, exist_ok=True)

    escape = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "../evil.txt"},
        content=b"x",
        headers=_auth(),
    )
    assert escape.status_code == 403
    assert escape.json()["error"]["code"] == "path_outside_workspace"
    assert not (tmp_path / "evil.txt").exists()

    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "link")
    through_link = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "link/evil.txt"},
        content=b"x",
        headers=_auth(),
    )
    assert through_link.status_code == 403
    assert through_link.json()["error"]["code"] == "path_outside_workspace"
    assert not (outside / "evil.txt").exists()

    # Secret store inside the workspace root is still refused.
    secret_settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data",
        secret_store=tmp_path / "data" / "secrets",
    )
    app = create_app(secret_settings, access_policy=LocalAccessPolicy(token="sesame"))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            guarded = await client.post(
                "/api/v1/files/upload",
                params={"path": "secrets/leak.txt"},
                content=b"leak",
                headers=_auth(),
            )
    assert guarded.status_code == 403
    assert guarded.json()["error"]["code"] == "path_outside_workspace"
    assert not (tmp_path / "data" / "secrets" / "leak.txt").exists()


async def test_upload_rejects_oversize_body(
    token_api: httpx.AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(files_module, "MAX_UPLOAD_BYTES", 4)
    too_big = await token_api.post(
        "/api/v1/files/upload",
        params={"path": "big.bin"},
        content=b"12345",
        headers=_auth(),
    )
    assert too_big.status_code == 400
    assert too_big.json()["error"]["code"] == "invalid_request"
    assert not (settings.workspace_root / "big.bin").exists()


async def test_download_revision_matches_preview(
    token_api: httpx.AsyncClient, settings: Settings
) -> None:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    target = settings.workspace_root / "data.bin"
    target.write_bytes(b"\x00\x01\x02\x03")

    content = await token_api.get("/api/v1/files/content", params={"path": "data.bin"})
    assert content.status_code == 200
    revision = content.json()["revision"]
    assert revision

    download = await token_api.get(
        "/api/v1/files/download", params={"path": "data.bin", "revision": revision}
    )
    assert download.status_code == 200
    assert download.content == b"\x00\x01\x02\x03"
    assert download.headers["x-lg-revision"] == revision
    assert download.headers["etag"] == f'"{revision}"'
    assert "attachment" in download.headers["content-disposition"]

    stale = await token_api.get(
        "/api/v1/files/download", params={"path": "data.bin", "revision": "0-0"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"

    missing = await token_api.get("/api/v1/files/download", params={"path": "nope.bin"})
    assert missing.status_code == 404


async def test_task_artifacts_classifies_workspace_files(
    token_app: FastAPI, token_api: httpx.AsyncClient, settings: Settings
) -> None:
    root = settings.workspace_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "taskws" / "inputs").mkdir(parents=True)
    (root / "taskws" / "artifacts").mkdir(parents=True)
    (root / "taskws" / "deliverables").mkdir(parents=True)
    (root / "taskws" / "runs" / "run_1").mkdir(parents=True)
    (root / "taskws" / "inputs" / "spec.md").write_text("spec", encoding="utf-8")
    (root / "taskws" / "artifacts" / "candidate.txt").write_text("c", encoding="utf-8")
    (root / "taskws" / "deliverables" / "final.txt").write_text("f", encoding="utf-8")
    (root / "taskws" / "runs" / "run_1" / "events.jsonl").write_text("{}\n", encoding="utf-8")

    task_id = await _create_task(token_app, workspace_ref="taskws")
    response = await token_api.get(f"/api/v1/tasks/{task_id}/artifacts")
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_ref"] == "taskws"
    assert body["candidate_ref"] == "run_candidate"
    assert body["evidence_refs"] == ["artifacts/report.md"]
    assert body["check_records"] == [{"check_id": "unit", "status": "passed"}]
    assert [item["path"] for item in body["categories"]["inputs"]] == ["inputs/spec.md"]
    assert [item["path"] for item in body["categories"]["candidates"]] == [
        "artifacts/candidate.txt"
    ]
    assert [item["path"] for item in body["categories"]["deliverables"]] == [
        "deliverables/final.txt"
    ]
    assert [item["path"] for item in body["categories"]["evidence"]] == [
        "runs/run_1/events.jsonl"
    ]
    assert body["note"] is None

    unscoped = await _create_task(token_app, workspace_ref=None)
    unscoped_body = (await token_api.get(f"/api/v1/tasks/{unscoped}/artifacts")).json()
    assert unscoped_body["categories"]["inputs"] == []
    assert "no workspace_ref" in unscoped_body["note"]

    missing = await token_api.get(f"/api/v1/tasks/{new_id('task')}/artifacts")
    assert missing.status_code == 404
