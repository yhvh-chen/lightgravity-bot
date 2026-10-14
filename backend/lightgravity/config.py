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

DEFAULT_DATA_DIR = "bot-data"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


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
        return cls(
            data_dir=data_dir,
            workspace_root=workspace_root,
            secret_store=secret_store,
            host=host,
            port=port,
        )

    def ensure_data_dir(self) -> Path:
        """Create the data root if missing and return it."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir
