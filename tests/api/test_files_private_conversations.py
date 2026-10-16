"""Files must not bypass Personal ownership when workspace overlaps data."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.store import new_id
from lightgravity.team import TeamAccounts


@pytest.mark.parametrize("viewer", ["alice", "bob", "admin"])
@pytest.mark.parametrize("layout", ["same", "parent"])
async def test_files_deny_private_history_and_aliases(tmp_path: Path, viewer: str, layout: str) -> None:
    data = tmp_path / "data"
    workspace = data if layout == "same" else tmp_path
    settings = Settings(data_dir=data, workspace_root=workspace, secret_store=tmp_path / "secrets", team_mode=True)
    accounts = TeamAccounts(settings.team_accounts_path)
    for name in ("alice", "bob", "admin"):
        accounts.add(name, "temporary-test-password", "admin" if name == "admin" else "member")
    app = create_app(settings, responder=lambda text, _kind: f"local echo: {text}")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            async def login(name: str) -> None:
                assert (await client.post("/api/v1/auth/login", json={"username": name, "password": "temporary-test-password"})).status_code == 200

            await login("alice")
            secret = "alice-private-regression-message"
            assert (await client.post("/api/v1/conversations/personal/messages", json={"message_id": "msg_private", "content": secret})).status_code == 200
            history = await client.get("/api/v1/conversations/personal/messages")
            assert secret in history.text
            private_file = next((data / "conversations").glob("*/messages.jsonl"))
            original = private_file.read_bytes()
            private_ledger = data / "coordinator" / "requests.jsonl"
            assert secret in private_ledger.read_text()
            (workspace / "alias").symlink_to(data / "conversations", target_is_directory=True)
            (workspace / "alias.jsonl").symlink_to(private_file)
            (workspace / "public").mkdir()
            relative = private_file.relative_to(workspace).as_posix()
            alias_path = f"alias/{private_file.parent.name}/messages.jsonl"
            for directory in ("shared-tasks", "sources"):
                (workspace / directory).mkdir(exist_ok=True)
                (workspace / directory / "shared.txt").write_text("shared work")
            await login(viewer)
            for path in (relative, alias_path, "alias.jsonl", f"public/../{relative}", str(private_file), private_ledger.relative_to(workspace).as_posix()):
                for endpoint in ("content", "download"):
                    response = await client.get(f"/api/v1/files/{endpoint}", params={"path": path})
                    assert response.status_code == 403, (viewer, path, endpoint)
                    assert response.json()["error"]["code"] == "path_outside_workspace"
                    assert secret not in response.text
            for path in ((data / "conversations").relative_to(workspace).as_posix(), private_file.parent.relative_to(workspace).as_posix(), "alias"):
                assert (await client.get("/api/v1/files", params={"path": path})).status_code == 403
            for path in ("", data.relative_to(workspace).as_posix()):
                listing = await client.get("/api/v1/files", params={"path": path})
                assert listing.status_code == 200
                names = {item["name"] for item in listing.json()["items"]}
                assert not names.intersection({"conversations", "coordinator", "alias", "alias.jsonl"})
            upload = await client.post("/api/v1/files/upload", params={"path": relative}, content=b"must never overwrite")
            assert upload.status_code == 403
            assert private_file.read_bytes() == original
            for directory in ("shared-tasks", "sources"):
                assert (await client.get("/api/v1/files/content", params={"path": f"{directory}/shared.txt"})).json()["content"] == "shared work"
            # Path intake must not copy protected bytes into a shared Source.
            for index, path in enumerate((relative, alias_path, "alias.jsonl", f"public/../{relative}", str(private_file), private_ledger.relative_to(workspace).as_posix())):
                imported = await client.post("/api/v1/sources", json={
                    "request_id": f"private-import-{index}", "filename": "imported.txt",
                    "path": path, "media_type": "text/plain",
                })
                if imported.status_code == 201:
                    # Establish that a regression is a real read/copy bypass,
                    # rather than merely an unexpected HTTP status.
                    source_id = imported.json()["source"]["source_id"]
                    exposed = await client.get(f"/api/v1/sources/{source_id}/download")
                    assert secret in exposed.text
                assert imported.status_code == 403
                assert imported.json()["error"]["code"] == "path_outside_workspace"
            assert (await client.get("/api/v1/sources")).json()["items"] == []
            shared = await client.post("/api/v1/sources", json={
                "request_id": "shared-import", "filename": "shared.txt",
                "path": "sources/shared.txt", "media_type": "text/plain",
            })
            assert shared.status_code == 201
            shared_id = shared.json()["source"]["source_id"]
            assert (await client.get(f"/api/v1/sources/{shared_id}/download")).text == "shared work"
            # A task rooted at the overlapping workspace must not rediscover
            # protected files through its recursive artifact listing.
            task_id = new_id("task")
            app.state.store.create("task", task_id, {
                "title": "Shared task", "status": "todo", "phase": "intake",
                "requirements_revision": 1, "deliverable_revision": 0,
                "project_ref": None, "repository_ref": None, "workspace_ref": ".",
                "agent_ref": "coordinator", "depends_on": [], "active_run": None,
                "queue": {"state": "not_queued"}, "acceptance": {"status": "pending"},
                "budget": {}, "archived": False,
            }, actor="test", request_id="create-shared-task")
            artifacts = await client.get(f"/api/v1/tasks/{task_id}/artifacts")
            assert artifacts.status_code == 200
            paths = [item["path"] for group in artifacts.json()["categories"].values() for item in group]
            assert "shared-tasks/shared.txt" in paths
            assert not any("conversations/" in path or "coordinator/" in path or path in {"alias.jsonl", alias_path} for path in paths)
