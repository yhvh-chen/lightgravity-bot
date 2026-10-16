"""Team account-management and self password endpoints (LG-062, additive).

Registered only in team mode; single-user mode keeps the exact 1.14 routes and
never exposes an account-management surface (the frontend hides it and an old
backend simply 404s, which the UI explains honestly).

Authority rules:

* ``GET/POST /api/v1/accounts``, ``PATCH /api/v1/accounts/{username}`` and
  ``POST /api/v1/accounts/{username}/password`` are **admin only**.  The global
  :func:`~lightgravity.api.access.require_access` dependency and the route-level
  guard both enforce it; hiding the UI is never the authorization boundary.
* ``POST /api/v1/account/password`` is available to every authenticated team
  user for their **own** account only; identity comes from the session cookie,
  never from a body/query field, so a member cannot change someone else's
  password.

The response DTO is an explicit whitelist (``username``/``role``/``enabled``/
``created_at``/``revision``); password records, salts and hashes never leave the
store.  Request validation errors are additionally redacted in ``app.py``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..contracts import AppError, ErrorCode
from ..team import (
    COOKIE_NAME,
    Account,
    TeamAccounts,
    TeamAccountsConflictError,
    TeamAccountsError,
    TeamAccountsLastAdminError,
    TeamAuthService,
    TeamIdentity,
    verify_password,
)
from .context import ApiContext, get_context


class AccountView(BaseModel):
    """Whitelisted account state; never contains password/salt/hash."""

    model_config = ConfigDict(extra="forbid")

    username: str
    role: str
    enabled: bool
    created_at: str
    revision: int

    @classmethod
    def from_account(cls, account: Account) -> "AccountView":
        return cls(
            username=account.username,
            role=account.role,
            enabled=account.enabled,
            created_at=account.created_at,
            revision=account.revision,
        )


class AccountListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accounts: list[AccountView]


class AccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    role: Literal["admin", "member"] = "member"


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["admin", "member"] | None = None
    enabled: bool | None = None
    expected_revision: int | None = Field(default=None, ge=0)


class AccountPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str
    expected_revision: int | None = Field(default=None, ge=0)


class OwnPasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str
    confirmation: str


class OwnPasswordChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    signed_out: bool


def _service(ctx: ApiContext) -> TeamAuthService:
    if ctx.team is None:  # pragma: no cover - router only mounted in team mode
        raise AppError(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "account management is only available in team mode",
        )
    return ctx.team


def _resolve_identity(request: Request, ctx: ApiContext) -> TeamIdentity | None:
    service = _service(ctx)
    return service.resolve(request.cookies.get(COOKIE_NAME))


def _require_admin(request: Request, ctx: ApiContext) -> TeamIdentity:
    """Defense-in-depth admin guard (the global policy already enforces it)."""

    identity = _resolve_identity(request, ctx)
    if identity is None:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "a valid team session is required",
            details={"endpoint": request.url.path},
        )
    if not identity.is_admin:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "administrator role required",
            details={"required_role": "admin", "endpoint": request.url.path},
        )
    return identity


def _store(ctx: ApiContext) -> TeamAccounts:
    return _service(ctx).accounts


def _existing(store: TeamAccounts, username: str) -> Account:
    account = store.get(username)
    if account is None:
        raise AppError(
            ErrorCode.NOT_FOUND,
            f"account {username!r} does not exist",
            details={"reason": "account_not_found"},
        )
    return account


def _translate(exc: TeamAccountsError) -> AppError:
    if isinstance(exc, TeamAccountsConflictError):
        return AppError(
            ErrorCode.REVISION_CONFLICT,
            "the account changed since it was loaded; reload and retry",
            details={"reason": "revision_conflict"},
        )
    if isinstance(exc, TeamAccountsLastAdminError):
        return AppError(
            ErrorCode.ILLEGAL_TRANSITION,
            "cannot disable or demote the last active administrator; "
            "promote or enable another admin first",
            details={"reason": "last_active_admin"},
        )
    return AppError(
        ErrorCode.INVALID_REQUEST,
        str(exc),
        details={"reason": "invalid_account_operation"},
    )


def build_accounts_router() -> APIRouter:
    router = APIRouter(tags=["accounts"])

    @router.get("/accounts", response_model=AccountListResponse)
    def list_accounts(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> AccountListResponse:
        _require_admin(request, ctx)
        store = _store(ctx)
        try:
            accounts = store.list_accounts()
        except TeamAccountsError as exc:
            raise _translate(exc) from exc
        return AccountListResponse(
            accounts=[AccountView.from_account(account) for account in accounts]
        )

    @router.post("/accounts", response_model=AccountView, status_code=201)
    def create_account(
        payload: AccountCreateRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> AccountView:
        _require_admin(request, ctx)
        store = _store(ctx)
        if store.get(payload.username) is not None:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"account {payload.username!r} already exists",
                details={"reason": "username_exists"},
            )
        try:
            account = store.add(payload.username, payload.password, payload.role)
        except TeamAccountsError as exc:
            raise _translate(exc) from exc
        return AccountView.from_account(account)

    @router.patch("/accounts/{username}", response_model=AccountView)
    def update_account(
        username: str,
        payload: AccountUpdateRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> AccountView:
        _require_admin(request, ctx)
        store = _store(ctx)
        _existing(store, username)
        try:
            account = store.update_account(
                username,
                role=payload.role,
                enabled=payload.enabled,
                expected_revision=payload.expected_revision,
            )
        except TeamAccountsError as exc:
            raise _translate(exc) from exc
        return AccountView.from_account(account)

    @router.post("/accounts/{username}/password", response_model=AccountView)
    def reset_password(
        username: str,
        payload: AccountPasswordResetRequest,
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> AccountView:
        _require_admin(request, ctx)
        store = _store(ctx)
        _existing(store, username)
        if not payload.password:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "password must be a non-empty string",
                details={"reason": "empty_password"},
            )
        try:
            account = store.set_password(
                username,
                payload.password,
                expected_revision=payload.expected_revision,
            )
        except TeamAccountsError as exc:
            raise _translate(exc) from exc
        return AccountView.from_account(account)

    @router.post("/account/password", response_model=OwnPasswordChangeResponse)
    def change_own_password(
        payload: OwnPasswordChangeRequest,
        request: Request,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> OwnPasswordChangeResponse:
        service = _service(ctx)
        identity = _resolve_identity(request, ctx)
        if identity is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "a valid team session is required",
                details={"endpoint": request.url.path},
            )
        store = service.accounts
        account = store.get(identity.username)
        if account is None:  # pragma: no cover - session implies the account
            raise AppError(ErrorCode.UNAUTHORIZED, "account no longer exists")
        if not verify_password(payload.current_password, account.password):
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "current password is incorrect",
                details={"reason": "invalid_current_password"},
            )
        if payload.new_password != payload.confirmation:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "new password and confirmation do not match",
                details={"reason": "confirmation_mismatch"},
            )
        if not payload.new_password:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                "new password must be a non-empty string",
                details={"reason": "empty_password"},
            )
        try:
            store.set_password(identity.username, payload.new_password)
        except TeamAccountsError as exc:
            raise _translate(exc) from exc
        # The credential revision bump already invalidates this and every other
        # session for the account; clear the cookie too so the browser drops it
        # immediately and the UI returns to the login gate.
        response.delete_cookie(
            COOKIE_NAME,
            path="/",
            httponly=True,
            samesite="lax",
            secure=service.cookie_secure,
        )
        return OwnPasswordChangeResponse(username=identity.username, signed_out=True)

    return router


__all__ = [
    "AccountCreateRequest",
    "AccountListResponse",
    "AccountPasswordResetRequest",
    "AccountUpdateRequest",
    "AccountView",
    "OwnPasswordChangeRequest",
    "OwnPasswordChangeResponse",
    "build_accounts_router",
]
