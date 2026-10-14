"""Shared helpers for the LG-025 settings tests (no network, no real secrets)."""

from __future__ import annotations

from typing import Any

from lightgravity.adapter.credentials import Secret
from lightgravity.contracts import AppError, ErrorCode
from lightgravity.settings import ConnectionService
from lightgravity.store import FileStore


class ToggleFailStore:
    """Delegate to a ``FileStore`` but fail selected ``write`` kinds on demand."""

    def __init__(self, inner: FileStore) -> None:
        self._inner = inner
        self.fail_kinds: set[str] = set()
        self.write_calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def inner(self) -> FileStore:
        return self._inner

    def write(
        self,
        kind: str,
        entity_id: str,
        content: dict[str, Any],
        *,
        expected_revision: int | None,
        actor: str,
    ) -> Any:
        self.write_calls.append(kind)
        if kind in self.fail_kinds:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                f"injected {kind} write failure",
            )
        return self._inner.write(
            kind,
            entity_id,
            content,
            expected_revision=expected_revision,
            actor=actor,
        )


class FakeProxy:
    """Minimal stand-in for ``LocalAuthProxy`` used by unit tests."""

    def __init__(self, credential: Secret, upstream_url: str, max_calls: int) -> None:
        self._credential = credential
        self._upstream = upstream_url
        self._max = max_calls
        self._started = False
        self._stopped = False
        self.call_count = 0
        self.upstream_model: str | None = None
        self.base_url = "http://127.0.0.1:1/token/v1"

    @property
    def is_running(self) -> bool:
        return self._started and not self._stopped

    def start(self) -> None:
        self._started = True

    def stop(self, *, timeout: float = 10.0) -> bool:
        self._stopped = True
        return True


def make_service_with_env(
    store: FileStore, secret_store: Any, env: dict[str, str]
) -> ConnectionService:
    from lightgravity.adapter.credentials import EnvCredentialResolver

    return ConnectionService(
        store,
        secret_store=secret_store,
        env_resolver=EnvCredentialResolver(env=env),
    )
