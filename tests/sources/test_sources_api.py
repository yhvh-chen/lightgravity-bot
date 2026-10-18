"""LG-034 API tests: original receipt, idempotency, conflict, attribution.

These drive the real mounted router over HTTP against a real app + FileStore.
They cover the task acceptance conditions:

* global material goes to a controlled inbox and does **not** create a Task/Run;
* Task/Project attribution is program-checked (unknown Task is refused);
* request idempotency, same-key different-payload conflict, scope-local dedup;
* path escapes / symlink escapes are refused;
* a "successful" receipt never claims a fabricated extracted body.
"""

from __future__ import annotations

import base64
import hashlib

import httpx
import pytest


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _create_task(api: httpx.AsyncClient, *, title: str = "source task") -> str:
    response = await api.post(
        "/api/v1/tasks",
        json={
            "request_id": f"req-{title.replace(' ', '-')}",
            "title": title,
            "objective": "hold sources",
            "acceptance_criteria": ["n/a"],
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["task_id"])


async def test_global_inline_source_creates_inbox_ref_not_task(api: httpx.AsyncClient) -> None:
    body = "hello source material\n".encode()
    response = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-global-1",
            "filename": "notes.txt",
            "content_base64": _b64(body),
            "media_type": "text/plain",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["created"] is True
    assert payload["deduplicated"] is False
    assert payload["source"]["scope"] == {"task_ref": None, "project_ref": None, "inbox_ref": None}
    assert payload["source"]["content_hash"] == hashlib.sha256(body).hexdigest()
    # A native text/plain upload is extracted synchronously by the model-free
    # UTF-8 path (F-INTAKE-FIX-R1), so the real job reaches a terminal value.
    assert payload["source"]["status"] == "extracted"
    assert payload["job"]["status"] == "succeeded"
    assert payload["job"]["stage"] == "done"

    # No Task was created as a side effect.
    tasks = await api.get("/api/v1/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["items"] == []

    # Receipt reads the same file state and records the real extraction.
    source_id = payload["source"]["source_id"]
    receipt = await api.get(f"/api/v1/sources/{source_id}/receipt")
    assert receipt.status_code == 200, receipt.text
    latest = receipt.json()["latest"]
    assert latest["status"] == "extracted"
    assert latest["searchable"] is True
    assert latest["formal_path"] == "derivative/machine.v1.md"


async def test_request_id_idempotent_and_payload_conflict(api: httpx.AsyncClient) -> None:
    first = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-idem-1",
            "filename": "a.txt",
            "content_base64": _b64(b"same bytes"),
        },
    )
    assert first.status_code == 201, first.text
    source_id = first.json()["source"]["source_id"]

    # Same request_id + same payload -> first result, no duplicate source.
    replay = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-idem-1",
            "filename": "a.txt",
            "content_base64": _b64(b"same bytes"),
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["deduplicated"] is True
    assert replay.json()["source"]["source_id"] == source_id

    # Same request_id, different payload -> source_conflict (never overwrite).
    conflict = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-idem-1",
            "filename": "a.txt",
            "content_base64": _b64(b"different bytes"),
        },
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "source_conflict"

    listing = await api.get("/api/v1/sources")
    assert len(listing.json()["items"]) == 1


async def test_scope_local_dedup_does_not_merge_across_tasks(api: httpx.AsyncClient) -> None:
    task_a = await _create_task(api, title="task a")
    task_b = await _create_task(api, title="task b")
    data = b"identical content"

    a = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-a",
            "filename": "x.txt",
            "content_base64": _b64(data),
            "scope": {"task_ref": task_a},
        },
    )
    assert a.status_code == 201, a.text
    assert a.json()["deduplicated"] is False

    b = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-b",
            "filename": "x.txt",
            "content_base64": _b64(data),
            "scope": {"task_ref": task_b},
        },
    )
    assert b.status_code == 201, b.text
    # Same bytes, different Task -> distinct source; authorization never merges.
    assert b.json()["deduplicated"] is False
    assert b.json()["source"]["source_id"] != a.json()["source"]["source_id"]

    # Same Task + same bytes -> deduplicated to the first source.
    a2 = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-a2",
            "filename": "x.txt",
            "content_base64": _b64(data),
            "scope": {"task_ref": task_a},
        },
    )
    assert a2.status_code == 200, a2.text
    assert a2.json()["deduplicated"] is True
    assert a2.json()["source"]["source_id"] == a.json()["source"]["source_id"]

    scoped = await api.get(f"/api/v1/sources?task_ref={task_a}")
    assert [item["source_id"] for item in scoped.json()["items"]] == [a.json()["source"]["source_id"]]


async def test_unknown_task_ref_is_refused(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-bad-task",
            "filename": "x.txt",
            "content_base64": _b64(b"data"),
            "scope": {"task_ref": "task_00000000000000000000000000"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reference_invalid"


async def test_project_ref_is_refused_without_registry(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-project",
            "filename": "x.txt",
            "content_base64": _b64(b"data"),
            "scope": {"project_ref": "some-project"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reference_invalid"


async def test_path_escape_and_symlink_escape_refused(
    api: httpx.AsyncClient, workspace
) -> None:
    outside = workspace.parent / "outside.txt"
    outside.write_text("secret", "utf-8")
    link = workspace / "escape.txt"
    link.symlink_to(outside)

    escape = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-escape",
            "filename": "outside.txt",
            "path": "../outside.txt",
        },
    )
    assert escape.status_code == 403
    assert escape.json()["error"]["code"] == "path_outside_workspace"

    symlink = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-symlink",
            "filename": "escape.txt",
            "path": "escape.txt",
        },
    )
    assert symlink.status_code == 403
    assert symlink.json()["error"]["code"] == "path_outside_workspace"


async def test_workspace_path_intake_persists_original(
    api: httpx.AsyncClient, workspace
) -> None:
    target = workspace / "input.txt"
    data = b"from workspace\n"
    target.write_bytes(data)

    response = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-path",
            "filename": "input.txt",
            "path": "input.txt",
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()["source"]
    assert source["content_hash"] == hashlib.sha256(data).hexdigest()
    assert source["original"]["bytes"] == len(data)
    # The response never echoes an absolute filesystem path.
    assert not str(source["path"]).startswith("/")
    assert ".." not in source["path"]


async def test_inbox_message_does_not_create_task(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/api/v1/inbox/messages",
        json={
            "message_id": "msg-inbox-1",
            "content": "unattributed material",
            "attachment_filename": "raw.bin",
            "attachment_base64": _b64(b"\x00\x01raw"),
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["task_created"] is False
    assert payload["run_created"] is False
    inbox_ref = payload["inbox_ref"]

    # Inbox material can then be attributed by reference without inventing a Task.
    source = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-inbox",
            "filename": "raw.bin",
            "content_base64": _b64(b"\x00\x01raw"),
            "scope": {"inbox_ref": inbox_ref},
        },
    )
    assert source.status_code == 201, source.text
    assert source.json()["source"]["scope"]["inbox_ref"] == inbox_ref

    tasks = await api.get("/api/v1/tasks")
    assert tasks.json()["items"] == []


async def test_unknown_inbox_ref_refused(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-bad-inbox",
            "filename": "x.txt",
            "content_base64": _b64(b"data"),
            "scope": {"inbox_ref": "inbox_00000000000000000000000000"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reference_invalid"


async def test_job_stage_change_emits_frozen_event(api: httpx.AsyncClient, app) -> None:
    created = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-events",
            "filename": "e.txt",
            "content_base64": _b64(b"event body"),
        },
    )
    source_id = created.json()["source"]["source_id"]
    job_id = created.json()["job"]["job_id"]

    app.state.source_service.intake.set_stage(job_id, status="running", stage="extracting")

    events = app.state.store.read_events(source_id)
    types = [event.type for event in events]
    assert "source.received" in types
    assert "intake.stage_changed" in types


# ---------------------------------------------------------------- LG-141 API
from lightgravity.contracts import AppError, ErrorCode  # noqa: E402
from lightgravity.sources.worker import IntakeWorker  # noqa: E402

from test_intake_worker import FakeEmbedding, FakeOcr, make_service, wait_for  # noqa: E402


async def test_deferred_create_returns_before_processing(api: httpx.AsyncClient, app, settings) -> None:
    ocr = FakeOcr(text="deferred-api-token")
    embedding = FakeEmbedding()
    service = make_service(settings.data_dir, ocr=ocr, embedding=embedding)
    app.state.source_service = service

    created = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-deferred-api",
            "filename": "photo.png",
            "content_base64": _b64(b"\x89PNG deferred photo"),
            "media_type": "image/png",
            "intake_mode": "deferred",
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["intake_mode"] == "deferred"
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["intake_mode"] == "deferred"
    assert payload["source"]["status"] == "received"
    assert ocr.calls == []
    assert embedding.calls == []

    worker = IntakeWorker(service, poll_interval=0.01)
    worker.start()
    try:
        job_id = payload["job"]["job_id"]
        await wait_for(lambda: service.store.read_job(job_id).status not in ("queued", "running"))
        assert service.store.read_job(job_id).status == "succeeded"
        receipt = await api.get(f"/api/v1/sources/{payload['source']['source_id']}/receipt")
        assert receipt.json()["receipt_version"] == 2
        assert receipt.json()["latest"]["text"]["status"] == "ready"
    finally:
        await worker.stop()
    assert (await api.get("/api/v1/tasks")).json()["items"] == []


async def test_message_source_refs_are_normalized_and_scope_checked(api: httpx.AsyncClient, app) -> None:
    task = await api.post(
        "/api/v1/tasks",
        json={
            "request_id": "req-refs-task",
            "title": "refs task",
            "objective": "source refs",
            "acceptance_criteria": ["n/a"],
        },
    )
    assert task.status_code == 200, task.text
    task_id = task.json()["task_id"]

    global_source = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-refs-global",
            "filename": "global.txt",
            "content_base64": _b64(b"global source"),
            "media_type": "text/plain",
        },
    )
    task_source = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-refs-task-source",
            "filename": "task.txt",
            "content_base64": _b64(b"task source"),
            "media_type": "text/plain",
            "scope": {"task_ref": task_id},
        },
    )
    global_id = global_source.json()["source"]["source_id"]
    task_source_id = task_source.json()["source"]["source_id"]
    service = app.state.source_service

    normalized = service.resolve_message_source_refs(
        task_ref=None, refs=[{"source_id": global_id}]
    )
    assert normalized == [
        {
            "source_id": global_id,
            "source_version": 1,
            "content_hash": global_source.json()["source"]["content_hash"],
            "scope": {"task_ref": None, "project_ref": None, "inbox_ref": None},
        }
    ]
    # Task messages accept same-Task and global sources.
    assert len(
        service.resolve_message_source_refs(
            task_ref=task_id,
            refs=[{"source_id": global_id}, {"source_id": task_source_id}],
        )
    ) == 2
    # Global messages may not attach a Task-scoped source.
    with pytest.raises(AppError) as cross_scope:
        service.resolve_message_source_refs(
            task_ref=None, refs=[{"source_id": task_source_id}]
        )
    assert cross_scope.value.code is ErrorCode.REFERENCE_INVALID

    with pytest.raises(AppError) as duplicate:
        service.resolve_message_source_refs(
            task_ref=None, refs=[{"source_id": global_id}, {"source_id": global_id}]
        )
    assert duplicate.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(AppError) as too_many:
        service.resolve_message_source_refs(
            task_ref=None,
            refs=[{"source_id": f"source_{index:026d}"} for index in range(11)],
        )
    assert too_many.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(AppError) as unknown:
        service.resolve_message_source_refs(
            task_ref=None, refs=[{"source_id": "source_01MISSINGMISSINGMISSING"}]
        )
    assert unknown.value.code is ErrorCode.REFERENCE_INVALID

    revoked = await api.post(
        f"/api/v1/sources/{global_id}/actions", json={"action": "revoke"}
    )
    assert revoked.status_code == 200, revoked.text
    with pytest.raises(AppError) as revoked_ref:
        service.resolve_message_source_refs(
            task_ref=None, refs=[{"source_id": global_id}]
        )
    assert revoked_ref.value.code is ErrorCode.NOT_FOUND
    assert revoked_ref.value.details["revoked"] is True


async def test_deferred_retry_budget_is_enforced_via_api(api: httpx.AsyncClient, app) -> None:
    created = await api.post(
        "/api/v1/sources",
        json={
            "request_id": "req-deferred-retry-api",
            "filename": "retry.txt",
            "content_base64": _b64(b"retry budget"),
            "media_type": "text/plain",
            "intake_mode": "deferred",
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]
    service = app.state.source_service
    service.intake.set_stage(job_id, status="failed", fail_reason="scripted failure")

    first = await api.post(f"/api/v1/intake/jobs/{job_id}/actions", json={"action": "retry"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "queued"
    job = (await api.get(f"/api/v1/intake/jobs/{job_id}")).json()
    assert job["attempt"] == 2

    service.intake.set_stage(job_id, status="failed", fail_reason="scripted failure again")
    exhausted = await api.post(f"/api/v1/intake/jobs/{job_id}/actions", json={"action": "retry"})
    assert exhausted.status_code == 429, exhausted.text
    assert exhausted.json()["error"]["code"] == "budget_exhausted"
