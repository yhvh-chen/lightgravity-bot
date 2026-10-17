"""Cross-cutting configuration resolved from environment variables.

This module is part of the shared engineering skeleton owned by the
integration executor (LG-002). It does not belong to any single business
package so that `store`, `adapter`, `api` and future `settings` code can share
one resolution rule for the data root, workspace root and secret store, as
required by docs/08-interface-contract.md §2.3 and §10.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ENV_DATA_DIR = "LIGHTGRAVITY_DATA_DIR"
ENV_WORKSPACE_ROOT = "LIGHTGRAVITY_WORKSPACE_ROOT"
ENV_SECRET_STORE = "LIGHTGRAVITY_SECRET_STORE"
ENV_HOST = "LIGHTGRAVITY_HOST"
ENV_PORT = "LIGHTGRAVITY_PORT"
# LG-050 additive team-mode settings (all default to the single-user behaviour).
ENV_TEAM_MODE = "LIGHTGRAVITY_TEAM_MODE"
ENV_TEAM_ACCOUNTS = "LIGHTGRAVITY_TEAM_ACCOUNTS"
ENV_TEAM_SESSION_TTL_SECONDS = "LIGHTGRAVITY_TEAM_SESSION_TTL_SECONDS"
ENV_TEAM_COOKIE_SECURE = "LIGHTGRAVITY_TEAM_COOKIE_SECURE"
ENV_TEAM_BOT_MENTION = "LIGHTGRAVITY_TEAM_BOT_MENTION"
# LG-126: global multi-Task capacity (non-secret, validated at startup).
ENV_MAX_ACTIVE_TASKS = "LIGHTGRAVITY_MAX_ACTIVE_TASKS"
ENV_MAX_GLOBAL_SESSIONS = "LIGHTGRAVITY_MAX_GLOBAL_SESSIONS"
ENV_MAX_REVIEWER_SESSIONS = "LIGHTGRAVITY_MAX_REVIEWER_SESSIONS"
ENV_MAX_PARALLEL_NODES_PER_TASK = "LIGHTGRAVITY_MAX_PARALLEL_NODES_PER_TASK"

DEFAULT_DATA_DIR = "bot-data"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_TEAM_SESSION_TTL_SECONDS = 28800
DEFAULT_TEAM_BOT_MENTION = "@bot"
DEFAULT_MAX_ACTIVE_TASKS = 2
DEFAULT_MAX_GLOBAL_SESSIONS = 3
DEFAULT_MAX_REVIEWER_SESSIONS = 1
DEFAULT_MAX_PARALLEL_NODES_PER_TASK = 2
_TEAM_TRUE = frozenset({"1", "true", "yes", "on"})


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TEAM_TRUE


def _positive_int(
    source: Mapping[str, str],
    name: str,
    default: int,
    *,
    problems: list[str],
) -> int:
    raw = source.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        problems.append(f"{name} must be an integer (actual={raw!r})")
        return default
    if value < 1:
        problems.append(f"{name} must be >= 1 (actual={value})")
        return default
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved runtime paths and bind address.

    All paths are relative to the process working directory unless an absolute
    value is provided, so a checkout runs without machine-specific paths. The
    data directory is created lazily by ``ensure_data_dir`` (startup) and is
    gitignored.
    """

    data_dir: Path
    workspace_root: Path
    secret_store: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    # --- LG-050 additive team mode (default = single-user, no behaviour change).
    #: Explicit team mode switch; when false the accounts file is never read or
    #: created and no existing endpoint changes behaviour.
    team_mode: bool = False
    #: Accounts JSON fact source.  ``None`` resolves to
    #: ``<data_dir>/team/accounts.json`` (gitignored, inside the data root).
    team_accounts: Path | None = None
    team_session_ttl_seconds: int = DEFAULT_TEAM_SESSION_TTL_SECONDS
    team_cookie_secure: bool = False
    team_bot_mention: str = DEFAULT_TEAM_BOT_MENTION
    # --- LG-126 global capacity.  These are bounded admission values, not a
    # promise of unlimited concurrency.  ``from_env`` validates the joint rule
    # ``max_active_tasks <= max_global_sessions - max_reviewer_sessions``.
    max_active_tasks: int = DEFAULT_MAX_ACTIVE_TASKS
    max_global_sessions: int = DEFAULT_MAX_GLOBAL_SESSIONS
    max_reviewer_sessions: int = DEFAULT_MAX_REVIEWER_SESSIONS
    max_parallel_nodes_per_task: int = DEFAULT_MAX_PARALLEL_NODES_PER_TASK

    @property
    def team_accounts_path(self) -> Path:
        """Resolved accounts file path (never the env var literal when unset)."""

        if self.team_accounts is not None:
            return self.team_accounts
        return self.data_dir / "team" / "accounts.json"

    @property
    def team_root(self) -> Path:
        """Controlled team-state directory (accounts and future derived files)."""

        return self.team_accounts_path.parent

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        data_dir = Path(source.get(ENV_DATA_DIR, DEFAULT_DATA_DIR))
        workspace_root = Path(
            source.get(ENV_WORKSPACE_ROOT, str(data_dir / "workspaces"))
        )
        secret_store = Path(source.get(ENV_SECRET_STORE, "secrets"))
        host = source.get(ENV_HOST, DEFAULT_HOST)
        port = int(source.get(ENV_PORT, str(DEFAULT_PORT)))
        accounts_raw = source.get(ENV_TEAM_ACCOUNTS)
        team_accounts = (
            Path(accounts_raw) if accounts_raw and accounts_raw.strip() else None
        )
        ttl_raw = source.get(
            ENV_TEAM_SESSION_TTL_SECONDS, str(DEFAULT_TEAM_SESSION_TTL_SECONDS)
        )
        try:
            session_ttl = int(ttl_raw)
        except ValueError:
            session_ttl = DEFAULT_TEAM_SESSION_TTL_SECONDS
        if session_ttl <= 0:
            session_ttl = DEFAULT_TEAM_SESSION_TTL_SECONDS
        capacity_problems: list[str] = []
        max_active_tasks = _positive_int(
            source, ENV_MAX_ACTIVE_TASKS, DEFAULT_MAX_ACTIVE_TASKS,
            problems=capacity_problems,
        )
        max_global_sessions = _positive_int(
            source, ENV_MAX_GLOBAL_SESSIONS, DEFAULT_MAX_GLOBAL_SESSIONS,
            problems=capacity_problems,
        )
        max_reviewer_sessions = _positive_int(
            source, ENV_MAX_REVIEWER_SESSIONS, DEFAULT_MAX_REVIEWER_SESSIONS,
            problems=capacity_problems,
        )
        max_parallel_nodes_per_task = _positive_int(
            source, ENV_MAX_PARALLEL_NODES_PER_TASK,
            DEFAULT_MAX_PARALLEL_NODES_PER_TASK, problems=capacity_problems,
        )
        if max_reviewer_sessions > max_global_sessions:
            capacity_problems.append(
                f"{ENV_MAX_REVIEWER_SESSIONS} must be <= {ENV_MAX_GLOBAL_SESSIONS}"
            )
        if max_active_tasks > max_global_sessions - max_reviewer_sessions:
            capacity_problems.append(
                f"{ENV_MAX_ACTIVE_TASKS} must be <= "
                f"{ENV_MAX_GLOBAL_SESSIONS} - {ENV_MAX_REVIEWER_SESSIONS}"
            )
        if capacity_problems:
            from .store.errors import ConfigInvalid

            raise ConfigInvalid(
                "invalid multi-task capacity configuration",
                diagnostics=[
                    {"code": "capacity_invalid", "location": problem}
                    for problem in capacity_problems
                ],
            )
        return cls(
            data_dir=data_dir,
            workspace_root=workspace_root,
            secret_store=secret_store,
            host=host,
            port=port,
            team_mode=_truthy(source.get(ENV_TEAM_MODE)),
            team_accounts=team_accounts,
            team_session_ttl_seconds=session_ttl,
            team_cookie_secure=_truthy(source.get(ENV_TEAM_COOKIE_SECURE)),
            team_bot_mention=source.get(ENV_TEAM_BOT_MENTION, DEFAULT_TEAM_BOT_MENTION)
            or DEFAULT_TEAM_BOT_MENTION,
            max_active_tasks=max_active_tasks,
            max_global_sessions=max_global_sessions,
            max_reviewer_sessions=max_reviewer_sessions,
            max_parallel_nodes_per_task=max_parallel_nodes_per_task,
        )

    def ensure_data_dir(self) -> Path:
        """Create the data root if missing and return it."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir
