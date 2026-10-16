"""Team access policy: session cookie identity + role matrix (LG-050).

Only an HttpOnly session cookie resolved by the server-side
:class:`~lightgravity.team.service.TeamAuthService` contributes identity.  The
legacy ``X-LG-Token`` header is deliberately ignored in team mode, so a token
can neither grant a session nor elevate a member to admin.

Role matrix (docs/08 LG-050 addendum / task interface):

* anonymous          -> 401 on every business/admin endpoint; public meta and
  ``/auth/*`` remain reachable;
* member             -> business read/write allowed; ``/settings*``,
  ``PATCH /resources/{kind}/{id}`` and resource proposals are 403 ``forbidden``;
* admin              -> everything.
"""

from __future__ import annotations

from fastapi import Request

from ..api.access import is_admin_only_request
from ..contracts import API_PREFIX, AppError, ErrorCode
from .service import COOKIE_NAME, TeamAuthService, TeamIdentity

#: Always reachable without a session (real liveness/version facts).
PUBLIC_PATHS = frozenset({"/api/v1/health", "/api/v1/version"})
#: Auth handshake endpoints; the routes themselves enforce logout/login rules.
ANONYMOUS_PATHS = frozenset(
    {"/api/v1/auth/me", "/api/v1/auth/login", "/api/v1/auth/logout"}
)
#: Prefixes whose *entire* surface (including reads) is admin-only.
ADMIN_ONLY_PREFIXES = ("/api/v1/settings",)


class TeamAccessPolicy:
    """Team-mode policy backed by the shared auth service."""

    def __init__(self, service: TeamAuthService) -> None:
        self._service = service

    @property
    def service(self) -> TeamAuthService:
        return self._service

    def resolve_identity(self, request: Request) -> TeamIdentity | None:
        session_id = request.cookies.get(COOKIE_NAME)
        return self._service.resolve(session_id)

    def authorize(
        self, request: Request, *, sensitive: bool, admin: bool = False
    ) -> None:
        path = request.url.path
        if path in PUBLIC_PATHS or path in ANONYMOUS_PATHS:
            return
        if not path.startswith(API_PREFIX):
            # Static frontend build/assets and the SPA fallback must load
            # anonymously so the login gate can render; they carry no product
            # data and never include the runtime token in team mode.
            return
        identity = self.resolve_identity(request)
        if identity is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "a valid team session is required",
                details={"endpoint": path},
            )
        required_admin = admin or is_admin_only_request(request)
        if required_admin and not identity.is_admin:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "administrator role required",
                details={"required_role": "admin", "endpoint": path},
            )
        # ``sensitive`` marks a protected write; in team mode an authenticated
        # session of either role already satisfies the local protection.  Role
        # restrictions are expressed through ``admin`` above, never through the
        # legacy token header.


__all__ = [
    "ADMIN_ONLY_PREFIXES",
    "ANONYMOUS_PATHS",
    "PUBLIC_PATHS",
    "TeamAccessPolicy",
]
