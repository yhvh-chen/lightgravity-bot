"""Team authentication endpoints (LG-050, additive ``/api/v1/auth``).

Registered only when team mode is on (``/auth/login``/``/auth/logout``); the
read-only ``/auth/me`` endpoint exists in both modes so the frontend can decide
whether to show a login gate without guessing.  Identity always comes from the
server-side session; the request body can never self-report a username/role.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from ..contracts import AppError, ErrorCode
from ..team import (
    COOKIE_NAME,
    TeamAuthService,
)
from ..team.service import LOGIN_WINDOW_SECONDS


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


def _same_origin(request: Request) -> bool:
    """Reject a cross-origin mutating request when the browser sent ``Origin``.

    The :class:`~lightgravity.runtime.hostguard.HostGuardMiddleware` already
    applies this to the whole service; this re-checks the auth surface so the
    login/logout endpoints stay safe even when the app factory is used without
    that middleware (tests, embedding).
    """

    origin = request.headers.get("origin")
    if not origin:
        return True
    host = (request.headers.get("host") or "").lower()
    parsed = urlparse(origin)
    return parsed.netloc.lower() == host


def _client_host(request: Request) -> str | None:
    client = request.client
    return client.host if client is not None else None


def build_auth_router(service: TeamAuthService | None) -> APIRouter:
    """Build the auth router; ``service=None`` yields single-user ``/auth/me``."""

    router = APIRouter(tags=["auth"])

    @router.get("/auth/me")
    def me(request: Request) -> dict[str, Any]:
        if service is None:
            return {
                "mode": "single",
                "authenticated": True,
                "username": None,
                "role": "admin",
            }
        identity = service.resolve(request.cookies.get(COOKIE_NAME))
        if identity is None:
            return {
                "mode": "team",
                "authenticated": False,
                "username": None,
                "role": None,
            }
        return {
            "mode": "team",
            "authenticated": True,
            "username": identity.username,
            "role": identity.role,
        }

    if service is None:
        return router

    @router.post("/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        if not _same_origin(request):
            raise AppError(
                ErrorCode.FORBIDDEN,
                "cross-origin login is not accepted",
                details={"origin": request.headers.get("origin")},
            )
        client = _client_host(request)
        if not service.login_allowed(payload.username, client):
            response.headers["Retry-After"] = str(int(LOGIN_WINDOW_SECONDS))
            raise AppError(
                ErrorCode.BUDGET_EXHAUSTED,
                "too many login attempts; try again later",
                details={"retry_after_seconds": int(LOGIN_WINDOW_SECONDS)},
            )
        identity = service.authenticate(payload.username, payload.password)
        if identity is None:
            service.record_failure(payload.username, client)
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "invalid username or password",
            )
        service.record_success(payload.username, client)
        session_id = service.create_session(identity)
        response.set_cookie(
            key=COOKIE_NAME,
            value=session_id,
            max_age=service.ttl_seconds,
            httponly=True,
            samesite="lax",
            secure=service.cookie_secure,
            path="/",
        )
        return {"username": identity.username, "role": identity.role}

    @router.post("/auth/logout", status_code=204)
    def logout(request: Request) -> Response:
        # A request with no session cookie is anonymous -> 401.  A request that
        # still carries a cookie is an idempotent logout (even if the session
        # was already revoked/expired): clear it and return 204.
        session_id = request.cookies.get(COOKIE_NAME)
        if session_id is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "no active team session",
            )
        service.revoke(session_id)
        cleared = Response(status_code=204)
        cleared.delete_cookie(
            COOKIE_NAME,
            path="/",
            httponly=True,
            samesite="lax",
            secure=service.cookie_secure,
        )
        return cleared

    return router


__all__ = ["LoginRequest", "build_auth_router"]
