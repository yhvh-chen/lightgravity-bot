"""LG-109 draft endpoint admin/runtime/origin gates and secret-safe 422s."""

from __future__ import annotations

from typing import Any

import httpx

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.settings import ConnectionService, ConnectionTester, FileSecretStore
from lightgravity.store import FileStore

from team_helpers import error_code, login_admin, login_member, seeded_accounts, team_settings


def _team_app(settings: Settings) -> tuple[Any, ConnectionService]:
    service = ConnectionService(
        FileStore(settings.data_dir, settings.workspace_root),
        secret_store=FileSecretStore(settings.secret_store),
    )

    def runner(spec, credential, endpoint, timeout):  # type: ignore[no-untyped-def]
        return True, "fake admin draft stop_confirmed=True"

    tester = ConnectionTester(service, allow_network=True, native_runner=runner)
    return create_app(settings, connection_service=service, tester=tester), service


def _draft_body(*, secret: str | None = "sk-canary-secret") -> dict[str, Any]:
    body: dict[str, Any] = {
        "connection": {
            "backend": "gemini",
            "model": "gemini-3.8-flash",
            "auth_mode": "api_key",
        },
        "allow_network": True,
    }
    if secret is not None:
        body["credential_value"] = secret
    return body


async def test_draft_is_anonymous_401_member_403_admin_200(
    team_settings: Settings, seeded_accounts: object
) -> None:
    app, service = _team_app(team_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            anonymous = await client.post(
                "/api/v1/settings/connections/test-draft", json=_draft_body()
            )
            assert anonymous.status_code == 401
            assert error_code(anonymous) == "unauthorized"

            assert (await login_member(client)).status_code == 200
            member = await client.post(
                "/api/v1/settings/connections/test-draft", json=_draft_body()
            )
            assert member.status_code == 403
            assert error_code(member) == "forbidden"

            assert (await login_admin(client)).status_code == 200
            admin = await client.post(
                "/api/v1/settings/connections/test-draft", json=_draft_body()
            )
            assert admin.status_code == 200, admin.text
            body = admin.json()
            assert body["draft"] is True
            assert body["connection_id"] is None
            assert body["connection_revision"] is None
            assert "sk-canary-secret" not in admin.text
            assert body["layers"][3]["status"] == "passed"

    # Draft never creates a saved connection or secret.
    assert service.list_connections() == []
    assert service.secret_store.list_refs() == []


async def test_draft_validation_errors_do_not_echo_pydantic_secret_input(
    team_settings: Settings, seeded_accounts: object
) -> None:
    app, service = _team_app(team_settings)
    secret = "sk-very-secret-canary-do-not-echo"
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            assert (await login_admin(client)).status_code == 200
            # Extra fields at the envelope and nested-connection levels both make
            # Pydantic reject the body; neither may echo the submitted secret.
            bad_envelope = await client.post(
                "/api/v1/settings/connections/test-draft",
                json={**_draft_body(secret=secret), "unexpected": "x"},
            )
            assert bad_envelope.status_code == 422
            assert secret not in bad_envelope.text
            assert "credential_value" not in bad_envelope.text

            bad_connection = await client.post(
                "/api/v1/settings/connections/test-draft",
                json={
                    **_draft_body(secret=secret),
                    "connection": {
                        **_draft_body(secret=secret)["connection"],
                        "credential_ref": "client-chosen-ref",
                    },
                },
            )
            assert bad_connection.status_code == 422
            assert secret not in bad_connection.text
            assert "client-chosen-ref" not in bad_connection.text
    assert service.list_connections() == []


async def test_draft_cross_origin_is_rejected_after_admin_auth(
    team_settings: Settings, seeded_accounts: object
) -> None:
    app, _service = _team_app(team_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            assert (await login_admin(client)).status_code == 200
            response = await client.post(
                "/api/v1/settings/connections/test-draft",
                json=_draft_body(),
                headers={"Origin": "https://evil.example"},
            )
            assert response.status_code == 401
            assert "sk-canary-secret" not in response.text
