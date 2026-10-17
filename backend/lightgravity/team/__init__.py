"""LG-050 team mode: accounts, sessions, identity and the access policy.

This package is additive and only active when ``LIGHTGRAVITY_TEAM_MODE`` is on.
It keeps the per-process session table in memory and the account fact source in
a single controlled JSON file (no database, no second authority).  Nothing here
is imported in single-user mode except the policy factory, which simply falls
back to the existing :class:`~lightgravity.api.access.LocalAccessPolicy`.
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
from .sessions import SessionRegistry

__all__ = [
    "ADMIN_ONLY_PREFIXES",
    "ANONYMOUS_PATHS",
    "COOKIE_NAME",
    "DEFAULT_ADMIN_PASSWORD",
    "DEFAULT_ADMIN_USERNAME",
    "PBKDF2_ITERATIONS",
    "PUBLIC_PATHS",
    "Account",
    "SessionRegistry",
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
