"""FastAPI application factory and LG-012 integration wiring.

This factory is the single place that assembles the resident process:

* builds the ``FileStore`` (LG-004) and wraps it so every persisted event is
  republished to the SSE broker;
* builds the ``ConnectionService``/``FileSecretStore`` (LG-025) on the same
  Store and ``LIGHTGRAVITY_SECRET_STORE`` resolved by :class:`Settings`;
* builds the ``Coordinator`` (LG-007) with an injectable ``Dispatcher`` seam so
  LG-008 can supply the graph dispatcher and LG-006/LG-010 can supply the real
  ``AntigravityExecutor`` without editing this file again;
* builds the ``VerificationService`` (LG-009) with an injectable
  ``ResourceStopper`` port so LG-010/LG-016 can supply a stronger
  session-stop confirmation without editing this file again, and mounts the
  read-only acceptance router while accept/reject live in ``api/tasks.py``;
* mounts the singleton global-conversation messages router (docs/08 §5.2);
* starts/stops the coordinator in the lifespan (background worker independent of
  any HTTP request) and mounts the frozen ``/api/v1`` routers.

Run with::

    uv run uvicorn --factory lightgravity.api.app:create_app
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..adapter import ExecutorAdapter
from ..config import Settings
from ..contracts import (
    API_PREFIX,
    CONTRACT_VERSION,
    AppError,
    ErrorCode,
    error_envelope,
)
from ..coordinator import Coordinator, build_router as build_coordinator_router
from ..coordinator.dispatcher import (
    Dispatcher,
    SingleSlotDispatcher,
    UnavailableExecutor,
)
from ..notifications import (
    NotificationService,
    NotificationStateStore,
)
from ..settings import (
    ConnectionService,
    ConnectionTester,
    FileSecretStore,
    build_settings_router,
)
from ..store import FileStore
from ..store.protocol import Store
from ..verify import ResourceStopper, VerificationService, build_acceptance_router

from .access import AccessPolicy, LocalAccessPolicy, require_access
from .context import ApiContext
from .collaboration import build_collaboration_router
from .conversations import build_conversations_router
from .eventbus import BroadcastingStore, EventBroker
from .events import build_events_router
from .files import build_files_router
from .health import router as health_router
from .notifications import build_notifications_router
from .resources import build_resource_router
from .search import build_search_router
from .sources import build_sources_router
from .tasks import build_task_router
from .vector import build_vector_router

_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.PATH_OUTSIDE_WORKSPACE,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.INVALID_REQUEST,
    409: ErrorCode.REVISION_CONFLICT,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.BUDGET_EXHAUSTED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.CAPABILITY_UNAVAILABLE,
}


def _dump(envelope: Any) -> dict[str, Any]:
    return envelope.model_dump(mode="json")


def create_app(
    settings: Settings | None = None,
    *,
    store: Store | None = None,
    coordinator: Coordinator | None = None,
    dispatcher: Dispatcher | None = None,
    executor: ExecutorAdapter | None = None,
    connection_service: ConnectionService | None = None,
    access_policy: AccessPolicy | None = None,
    tester: ConnectionTester | None = None,
    verification: VerificationService | None = None,
    resource_stopper: ResourceStopper | None = None,
    #: Optional direct-answer responder (LG-013).  When omitted the coordinator
    #: keeps its built-in deterministic responder; bootstrap injects a real
    #: tool-less model handler when a coordinator connection is configured.
    responder: Callable[[str, Any], str] | None = None,
    #: LG-031 execution-identity resolver.  ``None`` (default) leaves the
    #: worker-scoped collaboration endpoints default-deny, so no caller can
    #: impersonate a run member with a body field.
    worker_identity: Any | None = None,
) -> FastAPI:
    """Build the application; every heavy dependency is injectable for tests."""

    resolved = settings or Settings.from_env()
    resolved.ensure_data_dir()

    broker = EventBroker()
    base_store: Store = store or FileStore(resolved.data_dir, resolved.workspace_root)
    broadcasting = BroadcastingStore(base_store, broker)
    secret_store = FileSecretStore(resolved.secret_store)
    connections = connection_service or ConnectionService(
        broadcasting, secret_store=secret_store
    )

    policy = access_policy or LocalAccessPolicy()

    verification_service = verification or VerificationService(
        broadcasting, stopper=resource_stopper
    )

    if dispatcher is None and coordinator is None:
        dispatcher = SingleSlotDispatcher(executor or UnavailableExecutor())
    resolved_coordinator = coordinator or Coordinator(
        broadcasting,
        dispatcher=dispatcher,
        verification=verification_service,
        responder=responder,
    )
    # An injected coordinator must share this app's verification service so the
    # normal POST /tasks delivery path auto-verifies there too, not only in the
    # default construction branch.
    resolved_coordinator.set_verification(verification_service)

    effective_executor: ExecutorAdapter | None = executor
    if effective_executor is None and isinstance(dispatcher, SingleSlotDispatcher):
        effective_executor = dispatcher.executor
    real_executor = effective_executor is not None and not isinstance(
        effective_executor, UnavailableExecutor
    )

    context = ApiContext(
        settings=resolved,
        store=broadcasting,
        coordinator=resolved_coordinator,
        connections=connections,
        secret_store=secret_store,
        broker=broker,
        access=policy,
        real_executor=real_executor,
        tester=tester,
        verification=verification_service,
        notifications=NotificationService(
            broadcasting, NotificationStateStore(resolved.data_dir)
        ),
        worker_identity=worker_identity,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved.ensure_data_dir()
        resolved_coordinator.start()
        try:
            yield
        finally:
            await resolved_coordinator.stop()

    app = FastAPI(
        title="LightGravity Bot API",
        version=CONTRACT_VERSION,
        lifespan=lifespan,
        dependencies=[Depends(require_access)],
    )

    # Services are available immediately (e.g. ``__main__`` reads settings
    # before the lifespan runs); the lifespan only starts the background worker.
    app.state.settings = resolved
    app.state.context = context
    app.state.access_policy = policy
    app.state.store = broadcasting
    app.state.coordinator = resolved_coordinator
    app.state.connection_service = connections
    app.state.verification = verification_service

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        response = JSONResponse(
            status_code=exc.http_status,
            content=_dump(exc.to_envelope(request_id=request_id)),
        )
        etag = exc.details.get("etag") if isinstance(exc.details, dict) else None
        if isinstance(etag, str) and etag:
            response.headers["ETag"] = etag
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        envelope = error_envelope(
            ErrorCode.VALIDATION_FAILED,
            "request failed schema validation",
            details={"errors": exc.errors()},
        )
        return JSONResponse(status_code=422, content=_dump(envelope))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        envelope = error_envelope(code, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=_dump(envelope))

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(build_coordinator_router(resolved_coordinator), prefix=API_PREFIX)
    app.include_router(build_task_router(), prefix=API_PREFIX)
    app.include_router(build_resource_router(), prefix=API_PREFIX)
    app.include_router(build_files_router(), prefix=API_PREFIX)
    app.include_router(build_sources_router(), prefix=API_PREFIX)
    app.include_router(build_search_router(), prefix=API_PREFIX)
    app.include_router(build_vector_router(), prefix=API_PREFIX)
    app.include_router(build_collaboration_router(), prefix=API_PREFIX)
    app.include_router(build_events_router(), prefix=API_PREFIX)
    app.include_router(build_notifications_router(), prefix=API_PREFIX)
    app.include_router(build_conversations_router(), prefix=API_PREFIX)
    app.include_router(build_acceptance_router(verification_service), prefix=API_PREFIX)
    app.include_router(build_settings_router(connections, tester=tester), prefix=API_PREFIX)
    return app


__all__ = ["create_app"]
