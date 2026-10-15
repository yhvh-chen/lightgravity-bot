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
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["stage"] == "received"

    # No Task was created as a side effect.
    tasks = await api.get("/api/v1/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["items"] == []

    # Receipt reads the same file state and never fabricates a searchable body.
    source_id = payload["source"]["source_id"]
    receipt = await api.get(f"/api/v1/sources/{source_id}/receipt")
    assert receipt.status_code == 200, receipt.text
    latest = receipt.json()["latest"]
    assert latest["status"] == "received"
    assert latest["searchable"] is False
    assert latest["formal_path"] is None


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
