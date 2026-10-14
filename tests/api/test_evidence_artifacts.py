"""Canonical evidence preview/download from the Task artifacts API (docs/08 §6.2/§6.3).

LG-010's rework imports a trusted executor artifact into the Store-owned Task/Run
evidence root and records a canonical ``evidence:<run_id>/<name>@sha256:<hex>``
ref.  Those artifacts are **not** under the workspace root, so the Files API must
resolve them through an explicit Task/Run evidence resolver rather than a blanket
path allowance.

This is a real API regression using a temporary file: the artifact is produced by
a temp file, imported exactly as the coordinator does, then listed/previewed/
downloaded over the real ``create_app`` wiring.  Rejections (raw absolute path,
another task, wrong run, digest mismatch) are asserted to be honest refusals.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.app import create_app
from lightgravity.api.access import LocalAccessPolicy
from lightgravity.config import Settings
from lightgravity.evidence import canonical_evidence_ref, import_evidence
from lightgravity.store.ids import new_id


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings, access_policy=LocalAccessPolicy(token="sesame"))
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _create_task(app: FastAPI, workspace_ref: str | None) -> str:
    task_id = new_id("task")
    app.state.store.create(
        "task",
        task_id,
        {
            "title": "Evidence task",
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
            "acceptance": {"status": "pending", "candidate_ref": None, "evidence_refs": []},
            "budget": {},
            "archived": False,
        },
        actor="test",
        request_id=f"req-{task_id}",
    )
    return task_id


def _import(app: FastAPI, task_id: str, run_id: str, source: Path, name: str) -> str:
    return import_evidence(
        app.state.context.data_dir, task_id, run_id, source, name=name
    )


async def test_evidence_ref_is_listed_previewed_and_downloaded(
    app: FastAPI, api: httpx.AsyncClient, tmp_path: Path
) -> None:
    task_id = _create_task(app, workspace_ref=None)
    source = tmp_path / "deliverable.txt"
    source.write_text("hello evidence\n", encoding="utf-8")
    ref = _import(app, task_id, "run_1", source, "deliverable.txt")
    digest = hashlib.sha256(b"hello evidence\n").hexdigest()
    assert ref == canonical_evidence_ref("run_1", "deliverable.txt", digest)

    listed = await api.get(f"/api/v1/tasks/{task_id}/artifacts")
    assert listed.status_code == 200
    body = listed.json()
    # No workspace_ref, yet the evidence root is still surfaced.
    assert [item["evidence_ref"] for item in body["evidence"]] == [ref]
    assert body["evidence"][0]["run_id"] == "run_1"
    assert body["evidence"][0]["artifact_name"] == "deliverable.txt"

    preview = await api.get(
        f"/api/v1/tasks/{task_id}/artifacts/content", params={"evidence_ref": ref}
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["content"] == "hello evidence\n"
    assert preview_body["run_id"] == "run_1"
    assert preview_body["encoding"] == "utf-8"
    revision = preview_body["revision"]
    assert revision

    download = await api.get(
        f"/api/v1/tasks/{task_id}/artifacts/download",
        params={"evidence_ref": ref, "revision": revision},
    )
    assert download.status_code == 200
    assert download.content == b"hello evidence\n"
    assert download.headers["x-lg-revision"] == revision

    stale = await api.get(
        f"/api/v1/tasks/{task_id}/artifacts/download",
        params={"evidence_ref": ref, "revision": "1-1"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"


async def test_evidence_resolver_rejects_raw_path_other_task_and_digest(
    app: FastAPI, api: httpx.AsyncClient, tmp_path: Path
) -> None:
    owner = _create_task(app, workspace_ref=None)
    other = _create_task(app, workspace_ref=None)
    source = tmp_path / "secret.txt"
    source.write_text("owned\n", encoding="utf-8")
    ref = _import(app, owner, "run_1", source, "secret.txt")

    # A raw absolute path is never accepted as an evidence reference.
    raw = await api.get(
        f"/api/v1/tasks/{owner}/artifacts/content",
        params={"evidence_ref": str(source)},
    )
    assert raw.status_code == 400
    assert raw.json()["error"]["code"] == "invalid_request"

    # A ref owned by another Task is not readable through this Task.
    cross = await api.get(
        f"/api/v1/tasks/{other}/artifacts/content", params={"evidence_ref": ref}
    )
    assert cross.status_code == 404

    # A wrong run in the ref does not resolve.
    wrong_run = ref.replace("evidence:run_1/", "evidence:run_2/")
    wrong = await api.get(
        f"/api/v1/tasks/{owner}/artifacts/content", params={"evidence_ref": wrong_run}
    )
    assert wrong.status_code == 404

    # A tampered digest is refused even though the bytes exist.
    bad_digest = ref[: ref.index("@sha256:")] + "@sha256:" + ("0" * 64)
    tampered = await api.get(
        f"/api/v1/tasks/{owner}/artifacts/content", params={"evidence_ref": bad_digest}
    )
    assert tampered.status_code == 404
