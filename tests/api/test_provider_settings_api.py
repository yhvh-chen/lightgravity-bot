"""LG-104 provider fields through the real settings HTTP surface."""

from __future__ import annotations

from pathlib import Path

import httpx

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.settings import ConnectionService, ConnectionTester, FileSecretStore
from lightgravity.store import FileStore


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )


def _app(settings: Settings, *, allow_sensitive: bool = True):
    settings.ensure_data_dir()
    service = ConnectionService(
        FileStore(settings.data_dir, settings.workspace_root),
        secret_store=FileSecretStore(settings.secret_store),
    )
    tester = ConnectionTester(service, allow_network=False)
    app = create_app(
        settings,
        connection_service=service,
        tester=tester,
        access_policy=LocalAccessPolicy(
            allow_sensitive_without_token=allow_sensitive
        ),
    )
    return app, service


async def test_create_and_update_provider_fields_through_api(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    app, service = _app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            created = await client.post(
                "/api/v1/settings/connections",
                json={
                    "id": "gemini",
                    "backend": "gemini",
                    "model": "gemini-3.8-flash",
                    "auth_mode": "api_key",
                    "credential_ref": "gemini-key",
                    "credential_value": "sk-gemini-secret",
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            assert body["auth_mode"] == "api_key"
            assert body["project"] is None
            assert body["capabilities"] == {
                "configurable": True,
                "testable": True,
                "executable": False,
                "vendor_verified": False,
            }
            assert "sk-gemini-secret" not in created.text
            assert created.headers["cache-control"] == "no-store"

            switched = await client.patch(
                "/api/v1/settings/connections/gemini",
                json={
                    "expected_revision": 0,
                    "backend": "vertex",
                    "auth_mode": "adc",
                    "model": "gemini-3.8-flash",
                    "project": "demo-project",
                    "location": "us-central1",
                    "credential_action": "remove",
                },
            )
            assert switched.status_code == 200, switched.text
            switched_body = switched.json()
            assert switched_body["backend"] == "vertex"
            assert switched_body["auth_mode"] == "adc"
            assert switched_body["project"] == "demo-project"
            assert switched_body["location"] == "us-central1"
            assert switched_body["credential_ref"] is None

            stale = await client.patch(
                "/api/v1/settings/connections/gemini",
                json={"expected_revision": 0, "title": "stale"},
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "revision_conflict"

    assert service.get_connection("gemini")["revision"] == 1


async def test_draft_is_sensitive_and_static_when_network_not_requested(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    denied_app, _ = _app(settings, allow_sensitive=False)
    async with denied_app.router.lifespan_context(denied_app):
        transport = httpx.ASGITransport(app=denied_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            denied = await client.post(
                "/api/v1/settings/connections/test-draft",
                json={
                    "connection": {
                        "backend": "gemini",
                        "model": "gemini-3.8-flash",
                        "auth_mode": "api_key",
                    },
                    "credential_value": "sk-secret",
                },
            )
            assert denied.status_code == 401
            assert "sk-secret" not in denied.text

    allowed_app, service = _app(settings)
    async with allowed_app.router.lifespan_context(allowed_app):
        transport = httpx.ASGITransport(app=allowed_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            result = await client.post(
                "/api/v1/settings/connections/test-draft",
                json={
                    "connection": {
                        "backend": "gemini",
                        "model": "gemini-3.8-flash",
                        "auth_mode": "api_key",
                    },
                    "credential_value": "sk-secret",
                    "allow_network": False,
                },
            )
            assert result.status_code == 200, result.text
            body = result.json()
            assert body["draft"] is True
            assert body["connection_id"] is None
            assert "sk-secret" not in result.text
            assert body["layers"][3]["status"] == "skipped"
    assert service.list_connections() == []
    assert service.secret_store.list_refs() == []
