"""LG-050 team mode: accounts, sessions, identity and the access policy.

This package is additive and only active when ``LIGHTGRAVITY_TEAM_MODE`` is on.
It keeps the account fact source in a single controlled JSON file (no database,
no second authority) and, since LG-210, can keep the server-side session table
in a sibling hash-only JSON store so a restart does not force a new login.
Nothing here is imported in single-user mode except the policy factory, which
simply falls back to the existing
:class:`~lightgravity.api.access.LocalAccessPolicy`.
"""

from __future__ import annotations

from .accounts import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    PBKDF2_ITERATIONS,
    Account,
    TeamAccounts,
    TeamAccountsConflictError,
    TeamAccountsError,
    TeamAccountsLastAdminError,
    hash_password,
    verify_password,
)
from .policy import (
    ADMIN_ONLY_PREFIXES,
    ANONYMOUS_PATHS,
    PUBLIC_PATHS,
    TeamAccessPolicy,
)
from .service import COOKIE_NAME, TeamAuthService, TeamIdentity
from .sessions import SESSION_SCHEMA, SessionRegistry, SessionStoreError

__all__ = [
    "ADMIN_ONLY_PREFIXES",
    "ANONYMOUS_PATHS",
    "COOKIE_NAME",
    "DEFAULT_ADMIN_PASSWORD",
    "DEFAULT_ADMIN_USERNAME",
    "PBKDF2_ITERATIONS",
    "PUBLIC_PATHS",
    "SESSION_SCHEMA",
    "Account",
    "SessionRegistry",
    "SessionStoreError",
    "TeamAccessPolicy",
    "TeamAccounts",
    "TeamAccountsConflictError",
    "TeamAccountsError",
    "TeamAccountsLastAdminError",
    "TeamAuthService",
    "TeamIdentity",
    "hash_password",
    "verify_password",
]
