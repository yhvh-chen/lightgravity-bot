"""Resource metadata and root-restricted Files reads (LG-012)."""

from __future__ import annotations

import base64

import httpx
from fastapi import FastAPI


async def _create_agent(app: FastAPI, agent_id: str, title: str) -> None:
    app.state.store.create(
        "agent",
        agent_id,
        {"title": title, "enabled": True},
        actor="test",
        request_id=f"req-{agent_id}",
    )


async def test_resource_listing_and_detail(app: FastAPI, api: httpx.AsyncClient) -> None:
    created = await api.post(
        "/api/v1/settings/connections",
        json={"id": "deepseek", "credential_ref": "deepseek-default"},
    )
    assert created.status_code == 201
    await _create_agent(app, "developer", "Developer")
    await _create_agent(app, "reviewer", "Reviewer")

    connections = await api.get("/api/v1/resources/connection")
    assert connections.status_code == 200
    assert [item["id"] for item in connections.json()["items"]] == ["deepseek"]

    agents_page = await api.get("/api/v1/resources/agent", params={"limit": 1})
    assert agents_page.status_code == 200
    assert len(agents_page.json()["items"]) == 1
    assert agents_page.json()["next_cursor"] == "developer"

    detail = await api.get("/api/v1/resources/agent/reviewer")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Reviewer"
    assert detail.headers["etag"] == f'"{detail.json()["revision"]}"'


async def test_resource_unknown_kind_and_missing(api: httpx.AsyncClient) -> None:
    unknown = await api.get("/api/v1/resources/wizard")
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "invalid_request"

    missing = await api.get("/api/v1/resources/agent/nobody")
    assert missing.status_code == 404


async def test_files_listing_content_and_escape(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    root = app.state.settings.workspace_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "note.txt").write_text("hello files", encoding="utf-8")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02")

    listing = await api.get("/api/v1/files")
    assert listing.status_code == 200
    names = [item["name"] for item in listing.json()["items"]]
    assert names == ["blob.bin", "note.txt"]
    note = next(item for item in listing.json()["items"] if item["name"] == "note.txt")
    assert note["path"] == "note.txt"
    assert note["type"] == "file"

    content = await api.get("/api/v1/files/content", params={"path": "note.txt"})
    assert content.status_code == 200
    assert content.json()["content"] == "hello files"
    assert content.json()["encoding"] == "utf-8"

    binary = await api.get("/api/v1/files/content", params={"path": "blob.bin"})
    assert binary.status_code == 200
    assert binary.json()["encoding"] == "base64"
    assert base64.b64decode(binary.json()["content"]) == b"\x00\x01\x02"

    escape = await api.get("/api/v1/files", params={"path": ".."})
    assert escape.status_code == 403
    assert escape.json()["error"]["code"] == "path_outside_workspace"

    missing = await api.get("/api/v1/files/content", params={"path": "nope.txt"})
    assert missing.status_code == 404
