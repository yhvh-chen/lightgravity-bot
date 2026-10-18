"""Local access policy for the frozen API (LG-012, docs/08 §4.1/§10).

The first version runs single-user on loopback.  This module owns the *API
layer* of the access boundary:

* every request from a non-loopback peer must carry the local access token
  (``X-LG-Token``); the token source is started by LG-020;
* sensitive writes (``/api/v1/settings`` mutations: connections, credentials,
  defaults) additionally require an *injected* authorization mechanism.  With
  no token/policy configured the default is **deny**, never "open" — LG-020
  wires the real startup authorization and the frontend handshake later.

The policy is injectable for tests through :func:`create_app`; the router layer
never re-implements secret protection.  Secret *values* are still only handled
by LG-025's ``FileSecretStore``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import Request

from ..contracts import AppError, ErrorCode

#: Frozen sensitive prefix: settings/connection/credential mutations.
SENSITIVE_PREFIX = "/api/v1/settings"
#: LG-144/LG-148 (docs/08 §20.10): full rebuilds require protected access.
VECTOR_REBUILD_PATH = "/api/v1/vector/rebuild"
_SENSITIVE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

TOKEN_HEADER = "X-LG-Token"


@runtime_checkable
class AccessPolicy(Protocol):
    """Decides whether a request may proceed (raises :class:`AppError` if not)."""

    def authorize(
        self, request: Request, *, sensitive: bool, admin: bool = False
    ) -> None: ...


class LocalAccessPolicy:
    """Default single-user policy.

    ``token`` is the expected ``X-LG-Token`` value (``None`` means "not
    configured yet").  ``allow_sensitive_without_token`` is an explicit escape
    hatch for tests/tools; the production default denies sensitive writes when no
    authorization mechanism has been injected.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        allow_sensitive_without_token: bool = False,
    ) -> None:
        self._token = token
        self._allow_sensitive_without_token = allow_sensitive_without_token

    @property
    def token_configured(self) -> bool:
        return bool(self._token)

    def authorize(
        self, request: Request, *, sensitive: bool, admin: bool = False
    ) -> None:
        # ``admin`` is a team-mode role concept; in single-user mode the local
        # operator is implicitly the administrator, so it is ignored here and
        # the frozen token/loopback rules are unchanged.
        supplied = request.headers.get(TOKEN_HEADER)
        if not _is_loopback(request):
            if not self._token:
                raise AppError(
                    ErrorCode.UNAUTHORIZED,
                    "non-loopback requests require a configured local access token",
                    details={
                        "reason": "token_not_configured",
                        "header": TOKEN_HEADER,
                        "endpoint": request.url.path,
                    },
                )
            if supplied != self._token:
                raise AppError(
                    ErrorCode.UNAUTHORIZED,
                    "missing or invalid local access token",
                    details={"header": TOKEN_HEADER, "endpoint": request.url.path},
                )
            return
        if not sensitive:
            return
        if self._allow_sensitive_without_token:
            return
        if not self._token:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "sensitive endpoint requires an injected authorization mechanism "
                "(LG-020 wires the local access token)",
                details={
                    "reason": "authorization_not_configured",
                    "endpoint": request.url.path,
                },
            )
        if supplied != self._token:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "missing or invalid local access token",
                details={"header": TOKEN_HEADER, "endpoint": request.url.path},
            )


def _is_legacy_rebuild_request(request: Request) -> bool:
    """Classify the deprecated explicit opt-in before any search side effects.

    Match FastAPI/Pydantic's accepted true boolean spellings. QueryParams.get
    uses the last repeated value, as does the route's parsed boolean parameter.
    Invalid spellings remain normal validation errors and cannot invoke search.
    """

    return (
        request.method.upper() == "GET"
        and request.url.path in {"/api/v1/search", "/api/v1/vector/search"}
        and getattr(request, "query_params", {}).get("rebuild_if_missing", "").lower()
        in {"1", "true", "on", "yes", "t", "y"}
    )


def is_sensitive_request(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()
    if (method == "POST" and path == VECTOR_REBUILD_PATH) or _is_legacy_rebuild_request(request):
        # Protected full rebuild: single-user local token, team session/admin.
        return True
    if method in _SENSITIVE_METHODS and (
        path == SENSITIVE_PREFIX or path.startswith(SENSITIVE_PREFIX + "/")
    ):
        return True
    # LG-050 additive: a controlled resource mutation is a protected write too
    # (the route already re-checks; this keeps the global dependency honest).
    return method in {"PATCH", "PUT", "DELETE"} and (
        path == "/api/v1/resources" or path.startswith("/api/v1/resources/")
    )


def is_admin_only_request(request: Request) -> bool:
    """Whether the request targets an admin-only surface (team mode).

    In single-user mode this is not consulted for behaviour; it exists so the
    team policy and the global dependency agree on exactly one classification.
    """

    path = request.url.path
    if path == VECTOR_REBUILD_PATH or _is_legacy_rebuild_request(request):
        # 1.19 tightens this optional global model operation to admin/protected
        # writers (single-user operator is implicitly the administrator).
        return True
    if path == SENSITIVE_PREFIX or path.startswith(SENSITIVE_PREFIX + "/"):
        return True
    # LG-062: the admin account-management surface is admin-only for *every*
    # method, including the list read.  The self password route lives under
    # ``/api/v1/account/`` and stays available to any authenticated user.
    if path == "/api/v1/accounts" or path.startswith("/api/v1/accounts/"):
        return True
    return request.method.upper() in {"PATCH", "PUT", "DELETE"} and (
        path == "/api/v1/resources" or path.startswith("/api/v1/resources/")
    )


def require_access(request: Request) -> None:
    """FastAPI global dependency applying the app's :class:`AccessPolicy`."""

    policy: AccessPolicy | None = getattr(request.app.state, "access_policy", None)
    if policy is None:
        policy = LocalAccessPolicy()
    policy.authorize(
        request,
        sensitive=is_sensitive_request(request),
        admin=is_admin_only_request(request),
    )


def _is_loopback(request: Request) -> bool:
    client = request.client
    if client is None:
        # ASGI deployments with a Unix socket / in-process transport are local.
        return True
    return client.host in _LOOPBACK_HOSTS


__all__ = [
    "AccessPolicy",
    "LocalAccessPolicy",
    "SENSITIVE_PREFIX",
    "TOKEN_HEADER",
    "VECTOR_REBUILD_PATH",
    "is_admin_only_request",
    "is_sensitive_request",
    "require_access",
]
