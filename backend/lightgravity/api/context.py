"""Shared API context and request-scoped dependency accessor (LG-012).

``create_app`` builds one :class:`ApiContext` per process and stores it on
``app.state``; routers read it through :func:`get_context` instead of importing
singletons, so tests and integrations can inject a Store/Coordinator/service.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from ..config import Settings
from ..coordinator import Coordinator
from ..settings import ConnectionService, ConnectionTester, FileSecretStore
from ..store.protocol import Store

from .access import AccessPolicy
from .eventbus import EventBroker


@dataclass(slots=True)
class ApiContext:
    """Everything the API routers need, resolved once at startup."""

    settings: Settings
    store: Store
    coordinator: Coordinator
    connections: ConnectionService
    secret_store: FileSecretStore
    broker: EventBroker
    access: AccessPolicy
    real_executor: bool = False
    tester: ConnectionTester | None = None

    @property
    def data_dir(self) -> Path:
        return Path(getattr(self.store, "data_dir", self.settings.data_dir))

    @property
    def workspace_root(self) -> Path:
        return Path(getattr(self.store, "workspace_root", self.settings.workspace_root))


def get_context(request: Request) -> ApiContext:
    context: ApiContext | None = getattr(request.app.state, "context", None)
    if context is None:  # pragma: no cover - misconfigured app wiring
        raise RuntimeError("API context is not initialized")
    return context


__all__ = ["ApiContext", "get_context"]
