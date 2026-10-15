"""Runtime assembly for local startup/distribution (LG-020).

This is the **new, independent** startup module.  It does not edit the frozen
``api/app.py`` factory: it only calls the public :func:`create_app` with
injected dependencies and then adds the parts the factory explicitly leaves to
LG-020 (runtime token policy, Host guard, static frontend, process reporting).

What it wires, reusing the formal product components:

* the LG-004 ``FileStore`` (``LIGHTGRAVITY_DATA_DIR``/workspace isolation);
* the LG-025 ``FileSecretStore`` + ``ConnectionService`` + ``ConnectionTester``
  (no second SDK and no second model list are created);
* the LG-006 ``AntigravityExecutor`` (real DeepSeek loopback auth proxy) with
  the settings-layer credential resolver, so a missing credential becomes an
  honest ``capability_unavailable`` block instead of a crash or a fake run;
* the LG-008 ``GraphDispatcher`` over that executor, so the process is
  executable once an explicit connection/agent/credential exists (no permanent
  ``UnavailableExecutor`` is left in place);
* a per-process :class:`~lightgravity.runtime.token.RuntimeToken`, the
  :class:`~lightgravity.runtime.hostguard.HostGuardMiddleware` and the static
  frontend mount.

It never reads a full ``.env`` file, never prints a credential or the token, and
never copies a secret value into Markdown.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from ..adapter import (
    AntigravityExecutor,
    DirectoryArtifactSink,
    ResourceCompiler,
    configure_generation_ledger,
)
from ..adapter.compiler import ConnectionPin
from ..adapter.proxy import global_generation_counter
from ..config import Settings
from ..coordinator import GraphDispatcher
from ..collaboration import (
    ClaimPolicyReader,
    CollaborationService,
    default_registry as default_grant_registry,
    resolve_worker_identity,
)
from ..workspaces import GraphWorkspaceProvider, WorktreeManager
from ..coordinator.dialogue import (
    ModelDialogue,
    make_sync_responder,
    resolve_dialogue_support,
)
from ..verify.review import resolve_reviewer_support
from ..coordinator.graph import DEFAULT_CAPABILITIES
from ..coordinator.recruiter import RoleCatalog
from ..settings import (
    ROLE_COORDINATOR,
    ROLE_REVIEWER,
    ConnectionService,
    ConnectionTestLog,
    ConnectionTester,
    FileSecretStore,
)
from ..store import ConfigInvalid, EntityNotFound, FileStore, Store
from ..store.entities import RESOURCE_DIRS
from .access import AccessPolicy, LocalAccessPolicy
from .app import create_app
from .collaboration import resolve_request_grant
from ..runtime.frontend import mount_frontend
from ..runtime.hostguard import HostGuardMiddleware
from ..runtime.minimal import DEFAULT_AGENT_ID, seed_default_agent
from ..runtime.token import RuntimeToken, resolve_runtime_token

#: Optional JSON ``{capability: [agent_ref, ...]}`` role catalog override.
ROLE_CATALOG_ENV = "LIGHTGRAVITY_ROLE_CATALOG"
#: Optional frontend dist override for the one-process static service.
FRONTEND_DIST_ENV = "LIGHTGRAVITY_FRONTEND_DIST"
#: Optional comma-separated extra Hosts (e.g. a stable ``.localhost`` name).
ALLOWED_HOSTS_ENV = "LIGHTGRAVITY_ALLOWED_HOSTS"

LogSink = Callable[[str], None]


def _noop(_message: str) -> None:  # pragma: no cover - default sink
    return None


def repo_root() -> Path:
    """Repository root inferred from this file (``backend/lightgravity/api/...``)."""

    return Path(__file__).resolve().parents[3]


def default_frontend_dist() -> Path:
    return repo_root() / "frontend" / "dist"


@dataclass(frozen=True, slots=True)
class StartupOptions:
    """Everything the operator can choose at start time."""

    settings: Settings
    token: RuntimeToken | None = None
    frontend_dist: Path | None = None
    serve_frontend: bool = True
    allowed_hosts: tuple[str, ...] = ()
    wire_real_executor: bool = True
    role_catalog: Mapping[str, Sequence[str]] | None = None
    seed_minimal_agent: bool = True
    tester: bool = True
    #: Hard caps forwarded to the real executor (used by the gated real-model
    #: verification; ``None`` keeps the adapter default).
    max_proxy_calls: int = 8
    model_calls_cap: int | None = None
    log: LogSink = _noop


@dataclass(slots=True)
class RuntimeState:
    """Resolved runtime facts for the CLI/status output (never a token value)."""

    app: FastAPI
    settings: Settings
    token: RuntimeToken
    store: Store
    connections: ConnectionService
    executor_wired: bool
    frontend_served: bool
    frontend_dist: Path
    #: The wired executor when real execution is enabled (for honest reporting).
    executor: Any | None = None
    #: LG-017 R1: the assembled reviewer status (``model``/``program``/
    #: ``unavailable``) so readiness is honest about independent review.
    reviewer: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def execution_report(self) -> dict[str, object]:
        """Honest readiness report: what is configured, what is missing."""

        reasons: list[str] = []
        agents = _enabled_agents(self.store, self.settings.data_dir)
        settings_view = self.connections.get_settings()
        worker_ref = settings_view.get("default_worker_connection_ref")
        if not self.executor_wired:
            reasons.append("executor adapter is not wired")
        if not agents:
            reasons.append("no enabled agent resource (execution has no team candidate)")
        if not worker_ref:
            reasons.append("no default worker connection configured")
        credential_configured = False
        if isinstance(worker_ref, str) and worker_ref:
            try:
                status = self.connections.credential_status(_connection_credential_ref(self, worker_ref))
            except Exception:  # noqa: BLE001 - status must never crash startup
                status = None
            credential_configured = bool(status and status.configured)
            if not credential_configured:
                reasons.append("default worker credential is not configured/resolvable")
        return {
            "execution_ready": not reasons,
            "reasons": reasons,
            "default_worker_connection_ref": worker_ref,
            "credential_configured": credential_configured,
            "agent_refs": list(agents),
            "token_source": self.token.source,
            "frontend_served": self.frontend_served,
            "frontend_dist": str(self.frontend_dist),
            "reviewer": dict(self.reviewer),
            "warnings": list(self.warnings),
        }


def _connection_credential_ref(state: RuntimeState, connection_id: str) -> str | None:
    try:
        return state.connections.get_connection(connection_id).get("credential_ref")
    except Exception:  # noqa: BLE001 - missing/invalid connection is a readiness gap
        return None


class _ServiceConnectionPins:
    """Adapt :class:`ConnectionService` to the adapter connection-pin protocol.

    This is the only place the two layers meet; the adapter never imports the
    settings package and no secret value crosses the boundary (only the opaque
    credential version token).
    """

    def __init__(self, service: ConnectionService) -> None:
        self._service = service

    def resolve_default(self, role: str) -> ConnectionPin | None:
        pinned = self._service.resolve_default(role)
        if pinned is None:
            return None
        return ConnectionPin(
            connection_id=pinned.connection_id,
            role=pinned.role,
            revision=pinned.revision,
            content_hash=pinned.content_hash,
            backend=pinned.backend,
            model=pinned.model,
            base_url=pinned.base_url,
            credential_ref=pinned.credential_ref,
            credential_version=pinned.credential_version,
            config_hash=pinned.config_hash,
        )

    def pinned_is_current(self, pinned: ConnectionPin) -> bool:
        connection = self._service.repository.get_connection_or_none(pinned.connection_id)
        if connection is None:
            return False
        status = self._service.credential_status(connection.credential_ref)
        return (
            connection.revision == pinned.revision
            and connection.content_hash == pinned.content_hash
            and (status.version or None) == (pinned.credential_version or None)
        )


def _dialogue_responder(
    connections: ConnectionService, log: LogSink
) -> Callable[[str, Any], str] | None:
    """Build a real tool-less direct-answer responder when one is configured.

    Returns ``None`` when no coordinator connection/credential resolves, so the
    coordinator keeps its built-in responder and the UI does not claim a model
    answered a question it never asked.  The handler never prints the credential.
    """

    try:
        pinned = connections.resolve_default(ROLE_COORDINATOR)
    except Exception as exc:  # noqa: BLE001 - startup must never crash here
        log(f"dialogue responder not wired: {type(exc).__name__}: {exc}")
        return None
    support = resolve_dialogue_support(pinned)
    if support is None:
        log(
            "dialogue responder not wired: no default coordinator connection "
            "(plain questions will report unavailable instead of a real answer)"
        )
        return None
    dialogue = ModelDialogue(support, connections.credential_resolver.resolve)
    log(
        "dialogue responder wired: tool-less single turn on the default "
        "coordinator connection (no team, no write tools)"
    )
    return make_sync_responder(dialogue)


def _wire_independent_reviewer(
    app: FastAPI, connections: ConnectionService, log: LogSink
) -> dict[str, Any]:
    """Assemble the LG-017 reviewer from the *reviewer* default connection.

    The reviewer runs on its own default connection/credential (a separate role
    from the implementer), so its context is genuinely independent.  When no
    reviewer connection is configured, the coordinator's honest
    ``UnavailableReviewer`` default stays in place: a program-only machine gate
    is **not** called independent QA and acceptance never opens without a real
    review.  Returns a non-secret status dict for the readiness report.
    """

    coordinator = getattr(app.state, "coordinator", None)
    if coordinator is None:
        return {"reviewer": "unavailable", "reason": "no coordinator assembled"}
    try:
        pinned = connections.resolve_default(ROLE_REVIEWER)
    except Exception as exc:  # noqa: BLE001 - startup must never crash here
        log(f"reviewer not wired: {type(exc).__name__}: {exc}")
        return {"reviewer": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    support = resolve_reviewer_support(pinned)
    if support is None:
        log(
            "reviewer not wired: no default reviewer connection configured; "
            "candidates will report an honest 'review unavailable' instead of a "
            "fake independent pass"
        )
        return {"reviewer": "unavailable", "reason": "no default reviewer connection"}
    from ..verify.review import ModelReviewer
    from ..verify.rework import ReworkOrchestrator

    reviewer = ModelReviewer(support, connections.credential_resolver.resolve)
    coordinator.set_rework(
        ReworkOrchestrator(
            getattr(app.state, "store", None) or connections.repository.store,
            reviewer=reviewer,
            spawner=coordinator,
            actor="review",
        )
    )
    log(
        "independent model reviewer wired: one tool-less turn on the default "
        "reviewer connection (separate role/context from the implementer)"
    )
    return {
        "reviewer": "model",
        "connection_id": support.model,
        "credential_configured": reviewer.available(),
    }


def _enabled_agents(store: Store, data_dir: Path) -> tuple[str, ...]:
    directory = data_dir / "resources" / RESOURCE_DIRS["agent"]
    if not directory.is_dir():
        return ()
    ids: list[str] = []
    for path in sorted(directory.glob("*.md")):
        try:
            versioned = store.read("agent", path.stem)
        except (EntityNotFound, ConfigInvalid):
            continue
        if bool(versioned.entity.get("enabled", True)):
            ids.append(path.stem)
    return tuple(ids)


def load_role_catalog(
    store: Store, data_dir: Path, env: Mapping[str, str] | None = None
) -> RoleCatalog | None:
    """Resolve a minimal capability catalog: explicit JSON, else one agent."""

    source = os.environ if env is None else env
    raw = source.get(ROLE_CATALOG_ENV)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise ConfigInvalid(f"{ROLE_CATALOG_ENV} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ConfigInvalid(f"{ROLE_CATALOG_ENV} must be a JSON object")
        mapping: dict[str, list[str]] = {}
        for capability, refs in parsed.items():
            if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                raise ConfigInvalid(
                    f"{ROLE_CATALOG_ENV}.{capability} must be a list of agent refs"
                )
            mapping[str(capability)] = refs
        return RoleCatalog(mapping)
    agents = _enabled_agents(store, data_dir)
    if not agents:
        return None
    # Prefer operator templates over the built-in seeded worker so the seed is a
    # fallback, never a shadow over a user's own agent.
    ordered = sorted(agents, key=lambda agent_id: (agent_id == DEFAULT_AGENT_ID, agent_id))
    return RoleCatalog({capability: list(ordered) for capability in DEFAULT_CAPABILITIES})


def build_runtime(options: StartupOptions) -> RuntimeState:
    """Build the resident app plus its real dependencies; never prints secrets."""

    log: LogSink = options.log if options.log is not None else _noop
    settings = options.settings
    settings.ensure_data_dir()

    store = FileStore(settings.data_dir, settings.workspace_root)
    secret_store = FileSecretStore(settings.secret_store)
    connections = ConnectionService(store, secret_store=secret_store)
    connection_pins = _ServiceConnectionPins(connections)

    if options.seed_minimal_agent:
        try:
            seeded = seed_default_agent(store)
        except Exception as exc:  # noqa: BLE001 - seeding must never block startup
            seeded = None
            warnings_seed = f"default agent seed skipped: {type(exc).__name__}: {exc}"
            log(warnings_seed)
        else:
            warnings_seed = ""
            if seeded:
                log(f"seeded built-in worker agent {seeded!r} (no agent template existed)")
    else:
        seeded = None
        warnings_seed = ""

    tester = None
    if options.tester:
        tester = ConnectionTester(
            connections,
            diagnostics=ConnectionTestLog(settings.data_dir / "diagnostics"),
            allow_network=False,
            max_network_calls=1,
        )

    warnings: list[str] = []
    if warnings_seed:
        warnings.append(warnings_seed)
    executor = None
    dispatcher = None
    # LG-031 phase3: the process-wide grant registry is the single seam the
    # graph dispatcher (mint) and the API context (resolve) share.  Wiring the
    # same instance here means an autonomously claimed node grant is resolvable
    # by the request identity seam; disabled paths simply never mint a grant.
    grant_registry = default_grant_registry()
    # LG-022 R2: root the persistent generation-budget ledger at the resolved
    # data dir so the real global upstream cap survives restarts and is shared
    # across worker/reviewer/session.  Configured before any proxy starts.
    configure_generation_ledger(settings.data_dir)
    if options.wire_real_executor:
        try:
            compiler = ResourceCompiler(store, default_connections=connection_pins)
            executor = AntigravityExecutor(
                store,
                compiler,
                credential_resolver=connections.credential_resolver,
                artifacts=DirectoryArtifactSink(settings.data_dir / "artifacts"),
                workspace_root=settings.workspace_root,
                max_proxy_calls=options.max_proxy_calls,
                model_calls_cap=options.model_calls_cap,
                # LG-031 R2: the default assembly shares the one process-global
                # generation counter, so every worker/reviewer session and SDK
                # retry consumes the same real hard cap
                # (``LIGHTGRAVITY_MAX_GENERATION_CALLS``) instead of a
                # per-worker budget that silently resets.
                generation_budget=global_generation_counter(),
            )
            catalog: RoleCatalog | None = None
            if options.role_catalog is not None:
                catalog = RoleCatalog(dict(options.role_catalog))
            else:
                catalog = load_role_catalog(store, settings.data_dir)
            # LG-031 phase3: read the decentralized switches so the *product*
            # coordinator path can actually enable the autonomous claim tool
            # (R2 proved the probe path; the default dispatcher never wired it).
            # When the switch is off/absent this is identical to the old rules
            # path: no autonomous tool, no grants, deterministic plan_source.
            collab_policy = ClaimPolicyReader(store).read()
            decentralized = bool(getattr(collab_policy, "enabled", False))
            dispatcher = GraphDispatcher(
                store,
                executor,
                catalog=catalog,
                compiler=compiler,
                connections=connection_pins,
                workspaces=GraphWorkspaceProvider(WorktreeManager(settings.workspace_root)),
                collaboration=CollaborationService(store, policy=collab_policy),
                grant_registry=grant_registry if decentralized else None,
                autonomous_claim=decentralized,
                # LG-031 POOL-FIX: with decentralized claim enabled the product
                # dispatches *candidate-pool* worker slots, so a worker selects
                # one of the legal ready nodes itself instead of receiving a
                # single program-pre-bound node (the LG-032 F1 gap).  Off keeps
                # the exact deterministic rules path.
                autonomous_pool=decentralized,
            )
            log(
                "executor wired: antigravity/openai-compat via loopback auth proxy"
                + ("; capability catalog present" if catalog else "; no catalog")
                + (
                    "; decentralized claim enabled (candidate-pool autonomous selection active)"
                    if decentralized
                    else "; decentralized claim disabled (deterministic path)"
                )
            )
        except Exception as exc:  # noqa: BLE001 - start degraded, report honestly
            executor = None
            dispatcher = None
            warnings.append(f"real executor could not be wired: {type(exc).__name__}: {exc}")
            log(warnings[-1])
    else:
        warnings.append("real executor disabled by option; execution will be unavailable")
        log(warnings[-1])

    token = options.token or resolve_runtime_token(os.environ)
    access: AccessPolicy = LocalAccessPolicy(token=token.value)

    responder = _dialogue_responder(connections, log)

    app = create_app(
        settings,
        store=store,
        dispatcher=dispatcher,
        executor=executor,
        connection_service=connections,
        access_policy=access,
        tester=tester,
        responder=responder,
        # Program-frozen execution identity (LG-031): an in-process worker
        # request presenting an execution grant is bound to the member the graph
        # minted; a body field is never consulted as authentication.
        worker_identity=resolve_worker_identity,
        # LG-029 F2: the discovery/claim/lease endpoints enforce the full minted
        # grant (member + run/subtask scope + fence), not just a member ref.
        worker_grant=resolve_request_grant,
    )
    allowed_hosts = options.allowed_hosts
    env_hosts = os.environ.get(ALLOWED_HOSTS_ENV, "")
    if env_hosts.strip():
        allowed_hosts = tuple(allowed_hosts) + tuple(
            item.strip() for item in env_hosts.split(",") if item.strip()
        )
    app.add_middleware(HostGuardMiddleware, allowed_hosts=allowed_hosts)  # type: ignore[arg-type]

    dist = options.frontend_dist or Path(
        os.environ.get(FRONTEND_DIST_ENV) or default_frontend_dist()
    )
    frontend_served = False
    if options.serve_frontend:
        frontend_served = mount_frontend(app, dist, token.value, log=log)
        if not frontend_served:
            warnings.append(
                f"frontend build not found at {dist}; serving minimal bootstrap page"
            )

    agents = _enabled_agents(store, settings.data_dir)
    reviewer_status = _wire_independent_reviewer(app, connections, log)
    state = RuntimeState(
        app=app,
        settings=settings,
        token=token,
        store=store,
        connections=connections,
        executor_wired=executor is not None,
        frontend_served=frontend_served,
        frontend_dist=Path(dist),
        executor=executor,
        warnings=warnings,
        reviewer=reviewer_status,
    )
    if agents:
        log(f"executable agent candidates: {', '.join(agents)}")
    else:
        log("no enabled agent resource; execution has no team candidate yet")
    log(f"runtime token resolved from {token.source} (value never logged)")
    return state


__all__ = [
    "ALLOWED_HOSTS_ENV",
    "FRONTEND_DIST_ENV",
    "ROLE_CATALOG_ENV",
    "RuntimeState",
    "StartupOptions",
    "build_runtime",
    "default_frontend_dist",
    "load_role_catalog",
    "repo_root",
]
