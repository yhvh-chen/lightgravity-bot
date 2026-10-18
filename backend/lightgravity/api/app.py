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

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..adapter import ExecutorAdapter
from ..asr import build_english_asr_router, english_asr_safe_origin
from ..attachments import build_attachments_router
from ..config import Settings
from ..contracts import (
    API_PREFIX,
    CONTRACT_VERSION,
    AppError,
    ErrorCode,
    error_envelope,
)
from ..coordinator import Coordinator, build_router as build_coordinator_router
from ..coordinator.capacity import CapacityConfig
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
from ..team import TeamAccessPolicy, TeamAccounts, TeamAccountsError, TeamAuthService
from ..verify import (
    ResourceStopper,
    SessionStopConfirmer,
    StoreResourceStopper,
    VerificationService,
    build_acceptance_router,
)

from .access import AccessPolicy, LocalAccessPolicy, require_access
from .accounts import build_accounts_router
from .auth import build_auth_router
from .context import ApiContext
from .collaboration import build_collaboration_router
from .conversations import build_conversations_router
from .eventbus import BroadcastingStore, EventBroker
from .events import build_events_router
from .files import build_files_router
from .health import router as health_router
from .history import build_history_router
from .notifications import build_notifications_router
from .resources import build_resource_router
from .search import build_search_router
from .sources import build_sources_router
from .tasks import build_task_router
from .team_groups import build_team_groups_router
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
    #: LG-029 F2 full-grant resolver.  ``None`` (default) leaves the
    #: discovery/claim/lease endpoints default-deny; when wired it supplies the
    #: program-frozen scope (run/subtask/fence) the body can never grant.
    worker_grant: Any | None = None,
    #: LG-061: seed the requested default admin (``admin``/``admin123``) only
    #: when the team account store is empty.  Read-only callers (e.g.
    #: ``lightgravity status --deep``) pass ``False`` so diagnostics never
    #: touch the fact source.
    initialize_team_accounts: bool = True,
    #: LG-144: the real resident app starts the bounded deferred-intake worker.
    #: Sync-only test apps may opt out explicitly; production/bootstrap keeps the
    #: default.  Health advertises ``material_intake_v2`` only when it started.
    enable_intake_worker: bool = True,
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

    policy = access_policy
    team_service: TeamAuthService | None = None
    if resolved.team_mode:
        # LG-061 first initialisation: seed the requested default admin only
        # when the store has no account yet.  An existing store (including a
        # user-changed password) is never rewritten, so a restart cannot reset
        # a password.  Single-user mode never reads or creates this file.
        team_accounts = TeamAccounts(resolved.team_accounts_path)
        if initialize_team_accounts:
            try:
                team_accounts.ensure_default_admin()
            except TeamAccountsError:
                # A present-but-invalid store is surfaced lazily on auth; the
                # factory must not overwrite or crash on it.
                pass
        team_service = TeamAuthService(
            team_accounts,
            session_ttl_seconds=resolved.team_session_ttl_seconds,
            cookie_secure=resolved.team_cookie_secure,
            # LG-210: keep hash-only sessions beside the account fact source
            # (already protected from Files); a restart resolves the same
            # cookie while account/session_version revalidation stays live.
            session_store_path=team_accounts.path.parent / "sessions.json",
        )
        if policy is None:
            policy = TeamAccessPolicy(team_service)
    if policy is None:
        policy = LocalAccessPolicy()

    # The default stop gate may consult the real executor's stop facts (LG-022
    # R2) so a successful session-bearing Run is released only on a genuine
    # session/proxy stop, never a fabricated ``cleanup=done``.
    resolved_stopper = resource_stopper
    if resolved_stopper is None and executor is not None and hasattr(
        executor, "confirm_stopped"
    ):
        resolved_stopper = StoreResourceStopper(
            broadcasting, session_confirmer=cast(SessionStopConfirmer, executor)
        )

    verification_service = verification or VerificationService(
        broadcasting, stopper=resolved_stopper
    )

    if dispatcher is None and coordinator is None:
        dispatcher = SingleSlotDispatcher(executor or UnavailableExecutor())
    resolved_coordinator = coordinator or Coordinator(
        broadcasting,
        dispatcher=dispatcher,
        verification=verification_service,
        responder=responder,
        team_mode=resolved.team_mode,
        bot_mention=resolved.team_bot_mention,
        # LG-126: the app's real governor uses the already-validated Settings
        # values, so a directly-constructed app has the same bounded defaults as
        # the bootstrap path instead of silently reading a different env view.
        capacity=CapacityConfig(
            max_active_tasks=resolved.max_active_tasks,
            max_global_sessions=resolved.max_global_sessions,
            max_reviewer_sessions=resolved.max_reviewer_sessions,
            max_parallel_nodes_per_task=resolved.max_parallel_nodes_per_task,
        ),
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
        worker_grant=worker_grant,
        team=team_service,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved.ensure_data_dir()
        # The configured workspace is a startup resource, not a missing child
        # directory. Prepare it before accepting Files requests or queued work.
        context.workspace_root.mkdir(parents=True, exist_ok=True)
        resolved_coordinator.start()
        intake_worker = None
        try:
            if enable_intake_worker:
                # LG-144: one process-local worker over the same source service the
                # routers and coordinator use.  It is built with the live
                # ``ConnectionService`` so configured embedding settings keep their
                # saved-first/environment-fallback precedence even for recovered
                # queued jobs that run before the first Sources request.
                from ..sources.worker import IntakeWorker

                source_service = _source_service_provider()
                intake_worker = IntakeWorker(source_service, max_concurrency=2)
                application.state.intake_worker = intake_worker
                intake_worker.start()
            yield
        finally:
            if intake_worker is not None:
                # Never fake success for in-flight work: the worker parks unknown
                # outcomes as ``recovery_required`` when it cannot confirm a stop.
                await intake_worker.stop()
                application.state.intake_worker = None
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

    # LG-043: share the single per-app source service with the coordinator so a
    # message's ``selected_sources`` resolve against the same authoritative
    # store the sources router reads.  LG-144 also uses this provider for the
    # intake worker; an injected service (tests/embedding fixtures) wins so the
    # real lifespan can be exercised with a labelled fake upstream.
    def _source_service_provider() -> Any:
        cached = getattr(app.state, "source_service", None)
        if cached is not None:
            return cached
        from ..sources import build_source_service

        service = build_source_service(
            data_dir=resolved.data_dir,
            task_store=broadcasting,
            resolve_path=lambda relative, write: broadcasting.resolve_path(
                relative, write=write
            ),
            events=broadcasting,
            # Same configured embedding precedence as the vector router: saved
            # /settings/embedding first, then the environment fallback.
            connections=connections,
            # 1.20: the one optional English ASR service also owns the intake
            # text branch.  It is the same object exposed by GET /settings and
            # health, so a saved configuration applies to the next job without
            # a primer or a second settings store.
            english_asr=connections.english_asr,
        )
        app.state.source_service = service
        return service

    resolved_coordinator.set_source_service_provider(_source_service_provider)
    app.state.source_service_provider = _source_service_provider
    # These record real assembly by this factory, not merely a version claim.
    # The material gate additionally needs the lifespan worker to have started.
    app.state.material_intake_wired = enable_intake_worker
    app.state.semantic_search_wired = True
    app.state.media_direct_embedding_wired = True

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

    def _redact_validation_errors(
        errors: Sequence[Any],
    ) -> list[dict[str, Any]]:
        # LG-062: never echo the submitted value in a 422 envelope.  A rejected
        # password/credential field (secret canary) must not be reflected back
        # in ``details.errors[].input``.
        redacted: list[dict[str, Any]] = []
        for error in errors:
            clean = dict(error)
            clean.pop("input", None)
            redacted.append(clean)
        return redacted

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        envelope = error_envelope(
            ErrorCode.VALIDATION_FAILED,
            "request failed schema validation",
            details={"errors": _redact_validation_errors(exc.errors())},
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
    app.include_router(build_auth_router(team_service), prefix=API_PREFIX)
    if team_service is not None:
        # LG-062: team-only account management + self password.  Single-user
        # mode deliberately mounts no such route (the frontend hides it).
        app.include_router(build_accounts_router(), prefix=API_PREFIX)
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
    # LG-205: one read-only Team history projection over the same persisted
    # global/Task message logs; no message body or Personal conversation is
    # exposed.  Contract registration is reserved for final integration.
    app.include_router(build_history_router(), prefix=API_PREFIX)
    # LG-126 integration: the read-only Team groups projection is mounted in
    # the real factory (not only in tests), so health may advertise
    # ``team_groups`` truthfully.  It derives from persisted facts and writes
    # nothing.
    app.include_router(build_team_groups_router(), prefix=API_PREFIX)
    # LG-124 integration: the complete LG-119 private attachment factory is
    # mounted here (the package routes themselves were delivered complete).
    app.include_router(build_attachments_router(), prefix=API_PREFIX)
    app.include_router(build_acceptance_router(verification_service), prefix=API_PREFIX)
    app.include_router(build_settings_router(connections, tester=tester), prefix=API_PREFIX)
    # 1.20 integration: the protected English ASR settings write.  The global
    # access dependency already classifies every /settings mutation as
    # sensitive + admin; the route reuses the settings Host/Origin guard.
    app.include_router(
        build_english_asr_router(
            connections.english_asr,
            require_admin=None,
            safe_origin=english_asr_safe_origin,
        ),
        prefix=API_PREFIX,
    )
    return app


__all__ = ["create_app"]
