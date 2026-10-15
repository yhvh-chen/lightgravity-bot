"""Shared API context and request-scoped dependency accessor (LG-012).

``create_app`` builds one :class:`ApiContext` per process and stores it on
``app.state``; routers read it through :func:`get_context` instead of importing
singletons, so tests and integrations can inject a Store/Coordinator/service.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from ..config import Settings
from ..coordinator import Coordinator
from ..notifications import NotificationService, NotificationStateStore
from ..settings import ConnectionService, ConnectionTester, FileSecretStore
from ..store.protocol import Store
from ..verify import VerificationService

from .access import AccessPolicy
from .eventbus import EventBroker


#: Resolves the **program-authenticated** worker identity for a request.
#:
#: Returns the authenticated member ref, or ``None`` when the caller could not
#: be authenticated.  A request body's self-reported member ref is never
#: consulted here.  The real injection is the coordinator execution-identity
#: seam (LG-031); until it is wired the default is ``None`` (default-deny) so no
#: local caller can act as an arbitrary run member.
WorkerIdentityResolver = Callable[[Request], str | None]


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
    verification: VerificationService | None = None
    notifications: NotificationService | None = None
    #: LG-030/LG-031 execution-identity seam. ``None`` means the runtime has no
    #: way to authenticate a worker, so worker-scoped collaboration endpoints
    #: default-deny instead of trusting a body-supplied member ref.
    worker_identity: WorkerIdentityResolver | None = None

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


def get_notifications(request: Request) -> NotificationService:
    """Resolve the notification service, building a default when unwired."""

    context = get_context(request)
    service = context.notifications
    if service is None:  # pragma: no cover - create_app always wires it
        service = NotificationService(
            context.store, NotificationStateStore(context.data_dir)
        )
        context.notifications = service
    return service


__all__ = ["ApiContext", "get_context", "get_notifications"]
