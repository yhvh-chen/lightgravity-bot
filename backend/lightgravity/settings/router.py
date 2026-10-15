"""LG-025 settings HTTP router factory (docs/08 §4.3).

This module is intentionally **not** registered in ``lightgravity.api.app``:
LG-012 owns ``backend/lightgravity/api/**`` and will include this router under
the ``/api/v1`` prefix during integration.  Keeping it here lets LG-025 own the
settings surface without a concurrent edit to the app factory (docs/08 §11).

Routes (all relative; mount with the API prefix):

* ``GET  /settings``                                   - defaults + resolution
* ``PATCH /settings``                                  - set defaults (additive)
* ``GET  /settings/connections``                       - list (no secrets)
* ``POST /settings/connections``                       - create (write-only value)
* ``GET  /settings/connections/{id}``                  - detail (additive)
* ``PATCH /settings/connections/{id}``                 - optimistic update
* ``POST /settings/connections/{id}/test``             - layered test
* ``PUT  /settings/credentials/{ref}``                 - set/keep (never echoes)
* ``DELETE /settings/credentials/{ref}``               - remove (blocked if used)

Credential routes reject non-loopback browser origins and always send
``Cache-Control: no-store``; the value is never returned, logged or stored in
the Connection/SETTINGS Markdown.  The remaining local-token check is owned by
LG-012/LG-020 (docs/08 §4.1) and must wrap the whole API.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from lightgravity.contracts import AppError, ErrorCode

from .models import DEFAULT_BASE_URL, DEFAULT_EXECUTABLE_BACKEND, PREFERRED_MODEL
from .service import ConnectionService
from .testing import ConnectionTester

_LOOPBACK_ORIGIN_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ConnectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str | None = None
    backend: str = DEFAULT_EXECUTABLE_BACKEND
    model: str | None = PREFERRED_MODEL
    base_url: str | None = DEFAULT_BASE_URL
    credential_ref: str | None = None
    credential_value: str | None = None
    enabled: bool = True


class ConnectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    title: str | None = None
    enabled: bool | None = None
    model: str | None = None
    base_url: str | None = None
    credential_ref: str | None = None
    credential_action: Literal["keep", "set", "remove"] = "keep"
    credential_value: str | None = None
    clear_defaults: bool = False


class CredentialUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["set", "keep"] = "set"
    value: str | None = None


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = None
    default_coordinator_connection_ref: str | None = None
    default_worker_connection_ref: str | None = None
    #: LG-017 additive: set the independent reviewer's default connection
    #: (``null`` clears it, so the runtime reports ``unavailable``).
    default_reviewer_connection_ref: str | None = None


class ConnectionTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = None
    allow_network: bool = False
    probe_tools: bool = False
    probe_structured: bool = False


def _require_loopback_origin(request: Request) -> None:
    """Reject cross-site browser origins on sensitive credential writes."""

    origin = request.headers.get("origin")
    if not origin:
        return
    host = urlparse(origin).hostname
    if host not in _LOOPBACK_ORIGIN_HOSTS:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "credential endpoints only accept loopback browser origins",
            details={"origin_host": host},
        )


def _actor(header_actor: str | None) -> str:
    return header_actor or "settings-api"


def _etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'"{revision}"'


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def build_settings_router(
    service: ConnectionService,
    *,
    tester: ConnectionTester | None = None,
) -> APIRouter:
    """Build the settings router; LG-012 mounts it under ``/api/v1``."""

    router = APIRouter(tags=["settings"])

    @router.get("/settings")
    def get_settings(response: Response) -> dict[str, Any]:
        _no_store(response)
        return service.get_settings()

    @router.patch("/settings")
    def update_settings(
        payload: SettingsUpdateRequest,
        response: Response,
        x_lg_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        expected = data.pop("expected_revision", None)
        result = service.update_settings(
            expected_revision=expected, actor=_actor(x_lg_actor), **data
        )
        _no_store(response)
        _etag(response, int(result["revision"]))
        return result

    @router.get("/settings/connections")
    def list_connections(response: Response) -> dict[str, Any]:
        _no_store(response)
        return {"items": service.list_connections()}

    @router.post("/settings/connections", status_code=201)
    def create_connection(
        payload: ConnectionCreateRequest,
        response: Response,
        x_lg_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        result = service.create_connection(
            payload.id,
            title=payload.title,
            backend=payload.backend,
            model=payload.model,
            base_url=payload.base_url,
            credential_ref=payload.credential_ref,
            credential_value=payload.credential_value,
            enabled=payload.enabled,
            actor=_actor(x_lg_actor),
            request_id=f"conn-{payload.id}",
        )
        _no_store(response)
        _etag(response, int(result["revision"]))
        return result

    @router.get("/settings/connections/{connection_id}")
    def get_connection(connection_id: str, response: Response) -> dict[str, Any]:
        result = service.get_connection(connection_id)
        _no_store(response)
        _etag(response, int(result["revision"]))
        return result

    @router.patch("/settings/connections/{connection_id}")
    def update_connection(
        connection_id: str,
        payload: ConnectionUpdateRequest,
        response: Response,
        x_lg_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        expected = int(data.pop("expected_revision"))
        result = service.update_connection(
            connection_id,
            expected_revision=expected,
            actor=_actor(x_lg_actor),
            **data,
        )
        _no_store(response)
        _etag(response, int(result["revision"]))
        return result

    @router.post("/settings/connections/{connection_id}/test")
    def test_connection(
        connection_id: str,
        payload: ConnectionTestRequest,
        response: Response,
    ) -> dict[str, Any]:
        if tester is None:
            raise HTTPException(status_code=503, detail="connection tester is not configured")
        result = tester.test(
            connection_id,
            expected_revision=payload.expected_revision,
            allow_network=payload.allow_network,
            probe_tools=payload.probe_tools,
            probe_structured=payload.probe_structured,
        )
        _no_store(response)
        return result.to_dict()

    @router.put("/settings/credentials/{credential_ref}")
    def put_credential(
        credential_ref: str,
        payload: CredentialUpsertRequest,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        _require_loopback_origin(request)
        _no_store(response)
        if payload.action == "keep":
            return service.credential_status(credential_ref).to_dict()
        if not payload.value or not payload.value.strip():
            raise HTTPException(
                status_code=422,
                detail="setting a credential requires a non-empty value",
            )
        return service.set_credential(credential_ref, payload.value).to_dict()

    @router.delete("/settings/credentials/{credential_ref}")
    def delete_credential(
        credential_ref: str,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        _require_loopback_origin(request)
        _no_store(response)
        return service.remove_credential(credential_ref).to_dict()

    return router


__all__ = [
    "build_settings_router",
    "ConnectionCreateRequest",
    "ConnectionUpdateRequest",
    "CredentialUpsertRequest",
    "SettingsUpdateRequest",
    "ConnectionTestRequest",
]
