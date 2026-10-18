"""HTTP-level private Personal attachment semantics (LG-119).

Real ``create_app`` + the complete attachment router factory, authenticated
through actual team session cookies (and the single-user local policy).  No
product model/OCR/embedding call is made; the responder is a deterministic
fake that records the separate attachment context it receives.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.attachments import build_attachments_router
from lightgravity.config import Settings
from lightgravity.contracts import API_PREFIX
from lightgravity.store import new_id
from lightgravity.team import TeamAccounts

PERSONAL = f"{API_PREFIX}/conversations/personal/messages"
PRIVATE = f"{API_PREFIX}/attachments/private"
ALICE_PASSWORD = "temporary-test-password"


def _mount(app: FastAPI) -> FastAPI:
    # Integration owner wiring is exactly this line in api/app.py.
    app.include_router(build_attachments_router(), prefix=API_PREFIX)
    return app


def _team_settings(tmp_path: Path, *, workspace: Path | None = None) -> Settings:
    data = tmp_path / "data"
    return Settings(
        data_dir=data,
        workspace_root=workspace or (data / "workspaces"),
        secret_store=tmp_path / "secrets",
        team_mode=True,
    )


async def _login(client: httpx.AsyncClient, username: str, password: str = ALICE_PASSWORD) -> None:
    response = await client.post(
        f"{API_PREFIX}/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


async def _upload(
    client: httpx.AsyncClient,
    attachment_id: str,
    *,
    filename: str = "notes.txt",
    media_type: str = "text/plain",
    data: bytes = b"private sentinel",
) -> httpx.Response:
    return await client.post(
        PRIVATE,
        params={
            "attachment_id": attachment_id,
            "filename": filename,
            "media_type": media_type,
        },
        content=data,
    )


@pytest.fixture
async def team_app(tmp_path: Path) -> AsyncIterator[tuple[FastAPI, Settings, list[str | None]]]:
    settings = _team_settings(tmp_path)
    accounts = TeamAccounts(settings.team_accounts_path)
    accounts.add("alice", ALICE_PASSWORD, "member")
    accounts.add("bob", ALICE_PASSWORD, "member")
    accounts.add("admin", ALICE_PASSWORD, "admin")
    contexts: list[str | None] = []

    def responder(content: str, _classification: object, attachment_context: str | None = None) -> str:
        contexts.append(attachment_context)
        return "answer without echoing the sentinel"

    app = _mount(create_app(settings, responder=responder))
    async with app.router.lifespan_context(app):
        yield app, settings, contexts


async def test_upload_metadata_content_download_delete_and_owner_matrix(
    team_app: tuple[FastAPI, Settings, list[str | None]],
) -> None:
    app, _settings, _contexts = team_app
    attachment_id = new_id("att")
    async with _client(app) as alice, _client(app) as bob, _client(app) as admin:
        await _login(alice, "alice")
        await _login(bob, "bob")
        await _login(admin, "admin")

        uploaded = await _upload(
            alice, attachment_id, data=b"alice-private-sentinel-123"
        )
        assert uploaded.status_code == 201, uploaded.text
        attachment = uploaded.json()["attachment"]
        assert attachment["attachment_id"] == attachment_id
        assert attachment["filename"] == "notes.txt"
        assert attachment["size"] == len(b"alice-private-sentinel-123")
        assert attachment["status"] == "stored"
        assert "path" not in attachment and "owner" not in attachment

        replay = await _upload(alice, attachment_id, filename="other.txt", data=b"alice-private-sentinel-123")
        assert replay.status_code == 200
        assert replay.json()["attachment"]["filename"] == "notes.txt"
        conflict = await _upload(alice, attachment_id, data=b"different")
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "revision_conflict"

        metadata = await alice.get(f"{PRIVATE}/{attachment_id}")
        assert metadata.status_code == 200
        assert metadata.json()["attachment"] == attachment
        content = await alice.get(f"{PRIVATE}/{attachment_id}/content")
        assert content.status_code == 200
        body = content.json()
        assert body["encoding"] == "utf-8"
        assert body["content"] == "alice-private-sentinel-123"
        download = await alice.get(f"{PRIVATE}/{attachment_id}/download")
        assert download.status_code == 200
        assert download.content == b"alice-private-sentinel-123"
        revision = body["revision"]
        assert download.headers["x-lg-revision"] == revision
        assert download.headers["cache-control"] == "no-store"
        stale = await alice.get(
            f"{PRIVATE}/{attachment_id}/download", params={"revision": "stale"}
        )
        assert stale.status_code == 409

        # Bob and the admin cannot read metadata/content/download; no sentinel
        # and no existence leak (all 404 not_found).
        for viewer in (bob, admin):
            for suffix in ("", "/content", "/download"):
                denied = await viewer.get(f"{PRIVATE}/{attachment_id}{suffix}")
                assert denied.status_code == 404
                assert denied.json()["error"]["code"] == "not_found"
                assert "sentinel" not in denied.text

        deleted = await alice.delete(f"{PRIVATE}/{attachment_id}")
        assert deleted.status_code == 204
        assert (await alice.get(f"{PRIVATE}/{attachment_id}")).status_code == 404


async def test_upload_validation_and_identity_from_session(
    team_app: tuple[FastAPI, Settings, list[str | None]],
) -> None:
    app, _settings, _contexts = team_app
    async with _client(app) as alice, _client(app) as bob:
        await _login(alice, "alice")
        await _login(bob, "bob")
        assert (
            await alice.post(
                PRIVATE, params={"filename": "x.txt"}, content=b"x"
            )
        ).status_code == 400
        missing_name = await alice.post(
            PRIVATE, params={"attachment_id": new_id("att")}, content=b"x"
        )
        assert missing_name.status_code == 400
        invalid_id = await alice.post(
            PRIVATE,
            params={"attachment_id": "att_not-a-ulid", "filename": "x.txt"},
            content=b"x",
        )
        assert invalid_id.status_code == 400
        too_large = await alice.post(
            PRIVATE,
            params={"attachment_id": new_id("att"), "filename": "x.txt"},
            content=b"x" * 10_000_001,
        )
        assert too_large.status_code == 400

        # Same client id by two owners is two independent records, never a
        # shared owner override; an owner query field is not part of the route.
        shared_id = new_id("att")
        assert (await _upload(alice, shared_id, filename="alice.txt", data=b"a")).status_code == 201
        assert (await _upload(bob, shared_id, filename="bob.txt", data=b"b")).status_code == 201
        alice_meta = (await alice.get(f"{PRIVATE}/{shared_id}")).json()["attachment"]
        bob_meta = (await bob.get(f"{PRIVATE}/{shared_id}")).json()["attachment"]
        assert alice_meta["filename"] == "alice.txt"
        assert bob_meta["filename"] == "bob.txt"


async def test_personal_message_uses_responder_context_and_stays_private(
    team_app: tuple[FastAPI, Settings, list[str | None]],
) -> None:
    app, _settings, contexts = team_app
    attachment_id = new_id("att")
    sentinel = "EXACT-PRIVATE-FILE-SENTINEL-42"
    async with _client(app) as alice, _client(app) as bob, _client(app) as admin:
        await _login(alice, "alice")
        await _login(bob, "bob")
        await _login(admin, "admin")
        assert (await _upload(alice, attachment_id, data=sentinel.encode())).status_code == 201

        posted = await alice.post(
            PERSONAL,
            json={
                "message_id": "msg_with_file",
                "content": "summarize this",
                "attachments": [{"attachment_id": attachment_id, "filename": "forged.txt", "size": 1}],
            },
        )
        assert posted.status_code == 200, posted.text
        assert contexts[-1] is not None
        assert sentinel in contexts[-1]
        assert posted.json()["data"]["attachment_context_included"] is True

        history = (await alice.get(PERSONAL)).json()["items"]
        user_message = next(item for item in history if item["message_id"] == "msg_with_file")
        assert user_message["message"]["content"] == "summarize this"
        assert sentinel not in user_message["message"]["content"]
        snapshot = user_message["message"]["attachments"][0]
        assert snapshot["attachment_id"] == attachment_id
        # Client metadata was ignored: canonical filename/size/status apply.
        assert snapshot["filename"] == "notes.txt"
        assert snapshot["size"] == len(sentinel)
        assert snapshot["context_status"] == "included"
        assert snapshot["context_chars"] == len(sentinel)
        assert "path" not in snapshot

        # Idempotent retry of the same message is allowed even though the
        # attachment is now attached; the responder runs only once.
        call_count = len(contexts)
        replay = await alice.post(
            PERSONAL,
            json={
                "message_id": "msg_with_file",
                "content": "summarize this",
                "attachments": [{"attachment_id": attachment_id}],
            },
        )
        assert replay.status_code == 200
        assert len(contexts) == call_count
        # Reusing the attached file for a different message is not allowed.
        reused = await alice.post(
            PERSONAL,
            json={
                "message_id": "msg_other",
                "content": "again",
                "attachments": [{"attachment_id": attachment_id}],
            },
        )
        assert reused.status_code == 404
        assert len(contexts) == call_count
        # Deleting an attached file is an illegal transition.
        assert (await alice.delete(f"{PRIVATE}/{attachment_id}")).status_code == 409

        # Bob/admin cannot attach Alice's file; the responder is not called.
        for viewer in (bob, admin):
            denied = await viewer.post(
                PERSONAL,
                json={
                    "message_id": f"msg_{id(viewer)}",
                    "content": "steal",
                    "attachments": [{"attachment_id": attachment_id}],
                },
            )
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "not_found"
            assert len(contexts) == call_count

        # The shared global/Team conversation never accepted or leaked it.
        shared = await alice.get(f"{API_PREFIX}/conversations/global/messages")
        assert sentinel not in shared.text


async def test_personal_attachment_shape_and_unsupported_statuses(
    team_app: tuple[FastAPI, Settings, list[str | None]],
) -> None:
    app, _settings, contexts = team_app
    async with _client(app) as alice:
        await _login(alice, "alice")
        path_shape = await alice.post(
            PERSONAL,
            json={
                "message_id": "msg_path_shape",
                "content": "x",
                "attachments": [{"path": "workspace/file.txt"}],
            },
        )
        assert path_shape.status_code == 422
        assert path_shape.json()["error"]["code"] == "validation_failed"

        binary_id = new_id("att")
        unsupported_id = new_id("att")
        large_id = new_id("att")
        assert (await _upload(alice, binary_id, filename="bin.txt", data=b"\x00\x01\x02")).status_code == 201
        assert (
            await _upload(
                alice,
                unsupported_id,
                filename="scan.pdf",
                media_type="application/pdf",
                data=b"%PDF-1.7",
            )
        ).status_code == 201
        assert (
            await _upload(
                alice,
                large_id,
                filename="large.txt",
                data=b"x" * (64 * 1024 + 1),
            )
        ).status_code == 201

        posted = await alice.post(
            PERSONAL,
            json={
                "message_id": "msg_unsupported",
                "content": "what is in these?",
                "attachments": [
                    {"attachment_id": binary_id},
                    {"attachment_id": unsupported_id},
                    {"attachment_id": large_id},
                ],
            },
        )
        assert posted.status_code == 200, posted.text
        context = contexts[-1] or ""
        assert '"context_status": "binary_unsupported"' in context
        assert '"context_status": "unsupported_type"' in context
        assert '"context_status": "too_large"' in context
        assert "\x00" not in context and "%PDF-1.7" not in context
        reply = posted.json()["reply"]
        assert "Not read by the model" in reply
        assert "binary" in reply
        assert "unsupported type" in reply
        assert "64 KiB" in reply
        history = (await alice.get(PERSONAL)).json()["items"]
        user_message = next(item for item in history if item["message_id"] == "msg_unsupported")
        statuses = {
            item["attachment_id"]: item["context_status"]
            for item in user_message["message"]["attachments"]
        }
        assert statuses == {
            binary_id: "binary_unsupported",
            unsupported_id: "unsupported_type",
            large_id: "too_large",
        }
        assert all(
            item["context_chars"] == 0
            for item in user_message["message"]["attachments"]
        )


async def test_truncation_is_explicit_but_keeps_leading_text(
    team_app: tuple[FastAPI, Settings, list[str | None]],
) -> None:
    app, _settings, contexts = team_app
    first_id = new_id("att")
    second_id = new_id("att")
    async with _client(app) as alice:
        await _login(alice, "alice")
        first = "A" * 8000
        second = "B" * 8000
        assert (await _upload(alice, first_id, filename="a.txt", data=first.encode())).status_code == 201
        assert (await _upload(alice, second_id, filename="b.txt", data=second.encode())).status_code == 201
        posted = await alice.post(
            PERSONAL,
            json={
                "message_id": "msg_truncated",
                "content": "read both",
                "attachments": [
                    {"attachment_id": first_id},
                    {"attachment_id": second_id},
                ],
            },
        )
        assert posted.status_code == 200, posted.text
        context = contexts[-1] or ""
        assert "A" * 8000 in context
        assert context.count("B") < 8000
        assert "truncated" in (posted.json()["reply"] or "").lower()
        history = (await alice.get(PERSONAL)).json()["items"]
        user_message = next(item for item in history if item["message_id"] == "msg_truncated")
        statuses = {
            item["attachment_id"]: item["context_status"]
            for item in user_message["message"]["attachments"]
        }
        assert statuses[first_id] == "included"
        assert statuses[second_id] == "truncated"
        supplied = [
            chunk.partition("\n")[2].partition("\n--- end attachment ---")[0]
            for chunk in context.split("--- attachment: ")[1:]
        ]
        assert sum(item["context_chars"] for item in user_message["message"]["attachments"]) == sum(map(len, supplied))
        assert len(context) <= 12_000


async def test_global_and_task_messages_reject_private_attachment_id(
    team_app: tuple[FastAPI, Settings, list[str | None]],
) -> None:
    app, _settings, _contexts = team_app
    async with _client(app) as alice:
        await _login(alice, "alice")
        attachment_id = new_id("att")
        assert (await _upload(alice, attachment_id)).status_code == 201
        for path in (
            f"{API_PREFIX}/conversations/global/messages",
            f"{API_PREFIX}/tasks/does-not-matter/messages",
        ):
            response = await alice.post(
                path,
                json={
                    "message_id": f"msg_{path.rsplit('/', 2)[-2]}",
                    "content": "@bot hello",
                    "attachments": [{"attachment_id": attachment_id}],
                },
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "validation_failed"


async def test_private_root_is_excluded_from_files_sources_and_search(tmp_path: Path) -> None:
    # Overlap the workspace root with the data root on purpose: protected-root
    # checks must deny regardless of that overlap and regardless of admin role.
    settings = _team_settings(tmp_path, workspace=tmp_path / "data")
    accounts = TeamAccounts(settings.team_accounts_path)
    accounts.add("alice", ALICE_PASSWORD, "member")
    accounts.add("admin", ALICE_PASSWORD, "admin")
    app = _mount(create_app(settings))
    sentinel = "PRIVATE-FILE-NOT-FOR-SHARED-INDEX"
    async with app.router.lifespan_context(app), _client(app) as alice, _client(app) as admin:
        await _login(alice, "alice")
        await _login(admin, "admin")
        attachment_id = new_id("att")
        assert (await _upload(alice, attachment_id, data=sentinel.encode())).status_code == 201
        private_file = next((settings.data_dir / "private-attachments").glob("*/" + attachment_id + "/content.bin"))
        relative = private_file.relative_to(settings.workspace_root).as_posix()
        leaked = private_file.parent / "link.txt"
        leaked.symlink_to(private_file)

        for viewer in (alice, admin):
            for path in (relative, f"private-attachments/{private_file.parent.parent.name}/{attachment_id}/link.txt", str(private_file)):
                for endpoint in ("content", "download"):
                    denied = await viewer.get(
                        f"{API_PREFIX}/files/{endpoint}", params={"path": path}
                    )
                    assert denied.status_code == 403
                    assert denied.json()["error"]["code"] == "path_outside_workspace"
                    assert sentinel not in denied.text
            listing = await viewer.get(f"{API_PREFIX}/files", params={"path": "private-attachments"})
            assert listing.status_code == 403

        for index, path in enumerate((relative, str(private_file))):
            imported = await alice.post(
                f"{API_PREFIX}/sources",
                json={
                    "request_id": f"private-intake-{index}",
                    "filename": "imported.txt",
                    "path": path,
                    "media_type": "text/plain",
                },
            )
            assert imported.status_code == 403
            assert imported.json()["error"]["code"] == "path_outside_workspace"
        search = await admin.get(
            f"{API_PREFIX}/search",
            params={"q": sentinel, "include_global": "true"},
        )
        assert search.status_code == 200
        # The response may echo the query itself; no leaked hit/snippet/body.
        assert search.json()["hits"] == []
        assert sentinel not in str(search.json()["hits"])
        assert (await admin.get(f"{API_PREFIX}/sources")).json()["items"] == []


async def test_single_user_private_attachment_reaches_responder(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )
    contexts: list[str | None] = []

    def responder(content: str, _classification: object, attachment_context: str | None = None) -> str:
        contexts.append(attachment_context)
        return "single ok"

    app = _mount(
        create_app(
            settings,
            responder=responder,
            access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
        )
    )
    async with app.router.lifespan_context(app), _client(app) as client:
        attachment_id = new_id("att")
        assert (await _upload(client, attachment_id, data=b"single-sentinel")).status_code == 201
        posted = await client.post(
            PERSONAL,
            json={
                "message_id": "msg_single_private",
                "content": "read",
                "attachments": [{"attachment_id": attachment_id}],
            },
        )
        assert posted.status_code == 200, posted.text
        assert contexts[-1] is not None and "single-sentinel" in contexts[-1]
