"""Compile Markdown resources into a fixed, permission-bounded SDK plan.

The compiler is intentionally *static*: it reads authoritative entities through
the ``Store`` protocol, resolves references, checks the registered-implementation
boundary, computes the effective (never expanded) tool/budget set and hashes the
resolved version.  It never imports or starts the SDK; :mod:`sdk_config` builds
the concrete SDK objects from the resulting plan and marks execution readiness
separately.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from lightgravity.store import EntityNotFound, Store, Versioned
from lightgravity.store.models import Diagnostic

from .capabilities import AdapterCapabilities, SDK_PINNED_VERSION, adapter_capabilities
from .errors import AdapterConfigInvalid, ReferenceInvalid
from .provider_matrix import (
    auth_requires_credential,
    capabilities_for_connection,
    effective_auth_mode,
)
from .redaction import redact, sensitive_paths
from .registry import (
    HookRegistration,
    ImplementationRegistry,
    default_registry,
)
from .schema import (
    AgentResource,
    ConnectionResource,
    HookResource,
    PassthroughResource,
    SessionProfileResource,
    SkillResource,
    ToolResource,
    parse_agent,
    parse_connection,
    parse_hook,
    parse_mcp,
    parse_session_profile,
    parse_skill,
    parse_tool,
    parse_trigger,
)

#: Budget knobs the adapter forwards to the SDK, most-restrictive-wins.
_BUDGET_KEYS = ("max_model_calls", "max_tool_calls", "max_total_tokens")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConnectionPin:
    """A resolved, non-secret snapshot of the connection chosen for a Run/member.

    It carries no credential value: only the opaque ``credential_version`` token
    (docs/07 §3).  A pin is fixed at recruitment and reused for every subtask of
    that Run so a later default/credential edit cannot silently hot-swap an
    active member; :meth:`DefaultConnectionResolver.pinned_is_current` detects
    drift so the coordinator can fail honestly instead of swapping.
    """

    connection_id: str
    role: str
    revision: int
    content_hash: str
    backend: str
    model: str | None
    base_url: str | None
    credential_ref: str | None
    credential_version: str | None
    config_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "role": self.role,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "credential_ref": self.credential_ref,
            "credential_version": self.credential_version,
            "config_hash": self.config_hash,
        }


@runtime_checkable
class DefaultConnectionResolver(Protocol):
    """Resolve a role's current default connection without exposing secrets.

    Implemented by the settings layer's :class:`ConnectionService` and adapted
    in the runtime bootstrap; the adapter only depends on this narrow protocol.
    """

    def resolve_default(self, role: str) -> ConnectionPin | None: ...

    def pinned_is_current(self, pinned: ConnectionPin) -> bool: ...


@dataclass(frozen=True, slots=True)
class CompileConstraints:
    """Task/run authorization passed in by the coordinator (LG-007).

    ``allowed_tools`` is an upper bound over application tool-ref slugs.  When
    ``None`` the agent template's own requests apply; a provided set can only
    remove tools, never add them.  Budget values are likewise ceilings.

    Connection selection precedence: an explicit ``agent.connection_ref`` always
    wins.  Otherwise ``connection_pin`` (the Run's frozen selection) is used,
    then ``connection_ref_override`` (a caller-supplied ref such as the
    ``ExecuteRequest``), then the role default via the injected resolver.
    """

    allowed_tools: frozenset[str] | None = None
    max_model_calls: int | None = None
    max_tool_calls: int | None = None
    max_total_tokens: int | None = None
    timeout_seconds: float | None = None
    workspace_path: str | None = None
    conversation_id: str | None = None
    connection_pin: ConnectionPin | None = None
    connection_ref_override: str | None = None
    connection_role: str = "worker"


@dataclass(frozen=True, slots=True)
class ResourceVersion:
    kind: str
    id: str
    revision: int
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "revision": self.revision,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class UnavailableResource:
    ref: str
    kind: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class CompiledTool:
    ref: str
    handler_id: str
    sdk_tool: str | None
    permission: str
    policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "handler_id": self.handler_id,
            "sdk_tool": self.sdk_tool,
            "permission": self.permission,
            "policy": self.policy,
        }


@dataclass(frozen=True, slots=True)
class CompiledHook:
    ref: str
    handler_id: str
    events: tuple[str, ...] = ()
    factory: Callable[[], Any] | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "handler_id": self.handler_id, "events": list(self.events)}


@dataclass(frozen=True, slots=True)
class CompiledSkills:
    source: str
    refs: tuple[str, ...]
    paths: tuple[str, ...]
    inline: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "refs": list(self.refs),
            "paths": list(self.paths),
            "inline": [dict(item) for item in self.inline],
        }


@dataclass(frozen=True, slots=True)
class CompiledConnection:
    ref: str
    backend: str
    model: str | None
    base_url: str | None
    credential_ref: str | None
    sdk_config_kind: str
    supports_api_key_field: bool
    verified: bool
    #: LG-104 additive non-secret provider fields.  Old files leave them
    #: ``None``; the effective auth mode is inferred without rewriting.
    auth_mode: str | None = None
    project: str | None = None
    location: str | None = None
    model_path: str | None = None
    litert_backend: str | None = None
    #: How the connection was chosen (``explicit`` | ``pinned`` | ``override``
    #: | ``default`` | ``missing``); informational and hash-relevant only.
    connection_source: str = "explicit"
    #: Opaque credential version token when a default/pinned selection carried
    #: one; it is never a secret value.
    credential_version: str | None = None
    #: Separate capability facts; ``None`` means not declared.
    configurable: bool | None = None
    testable: bool | None = None
    executable: bool | None = None
    vendor_verified: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "backend": self.backend,
            "model": self.model,
            "base_url": self.base_url,
            "credential_ref": self.credential_ref,
            "sdk_config_kind": self.sdk_config_kind,
            "supports_api_key_field": self.supports_api_key_field,
            "verified": self.verified,
            "auth_mode": self.auth_mode,
            "project": self.project,
            "location": self.location,
            "model_path": self.model_path,
            "litert_backend": self.litert_backend,
            "connection_source": self.connection_source,
            "credential_version": self.credential_version,
            "capabilities": {
                "configurable": self.configurable,
                "testable": self.testable,
                "executable": self.executable,
                "vendor_verified": self.vendor_verified,
            },
        }


@dataclass(frozen=True, slots=True)
class CompiledSessionProfile:
    ref: str
    continuation_mode: str | None
    conversation_id: str | None
    compaction_token_threshold: int | None
    agent_behavior: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "continuation_mode": self.continuation_mode,
            "conversation_id": self.conversation_id,
            "compaction_token_threshold": self.compaction_token_threshold,
            "agent_behavior": self.agent_behavior,
        }


@dataclass(frozen=True, slots=True)
class CompiledAgentConfig:
    """A versioned, permission-bounded, redacted plan for one Member."""

    agent_id: str
    agent_title: str
    sdk_version: str
    instructions: str
    connection: CompiledConnection | None
    session_profile: CompiledSessionProfile | None
    skills: CompiledSkills
    tools: tuple[CompiledTool, ...]
    hooks: tuple[CompiledHook, ...]
    budget: dict[str, int]
    unavailable: tuple[UnavailableResource, ...]
    diagnostics: tuple[Diagnostic, ...]
    resource_versions: tuple[ResourceVersion, ...]
    executable: bool
    executable_reasons: tuple[str, ...]
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "agent_title": self.agent_title,
            "sdk_version": self.sdk_version,
            "instructions": self.instructions,
            "connection": self.connection.to_dict() if self.connection else None,
            "session_profile": self.session_profile.to_dict() if self.session_profile else None,
            "skills": self.skills.to_dict(),
            "tools": [tool.to_dict() for tool in self.tools],
            "hooks": [hook.to_dict() for hook in self.hooks],
            "budget": dict(self.budget),
            "unavailable": [item.to_dict() for item in self.unavailable],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "resource_versions": [item.to_dict() for item in self.resource_versions],
            "executable": self.executable,
            "executable_reasons": list(self.executable_reasons),
            "config_hash": self.config_hash,
        }
        return redact(payload)


class ResourceCompiler:
    """Resolve and compile ``agent`` resources against the store + registry."""

    def __init__(
        self,
        store: Store,
        *,
        registry: ImplementationRegistry | None = None,
        capabilities: AdapterCapabilities | None = None,
        default_connections: DefaultConnectionResolver | None = None,
    ) -> None:
        self._store = store
        self._registry = registry or default_registry()
        self._capabilities = capabilities or adapter_capabilities()
        self._default_connections = default_connections

    @property
    def registry(self) -> ImplementationRegistry:
        return self._registry

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    # ------------------------------------------------------------------ read
    def _read(
        self, kind: str, entity_id: str, versions: list[ResourceVersion]
    ) -> Versioned:
        try:
            versioned = self._store.read(kind, entity_id)
        except EntityNotFound as exc:
            raise ReferenceInvalid(
                f"{kind} {entity_id!r} referenced by an agent does not exist",
                kind=kind,
                ref=entity_id,
            ) from exc
        versions.append(
            ResourceVersion(
                kind=kind,
                id=entity_id,
                revision=versioned.revision,
                content_hash=versioned.content_hash,
            )
        )
        leaked = sensitive_paths(versioned.entity)
        if leaked:
            raise AdapterConfigInvalid(
                f"{kind} {entity_id!r} contains a secret-like field; only "
                "credential_ref is allowed",
                diagnostics=[
                    {
                        "code": "secret_in_resource",
                        "message": "secret-like field present in resource frontmatter",
                        "location": f"{kind}.{entity_id}",
                        "detail": {"fields": leaked},
                    }
                ],
                location=versioned.path,
            )
        return versioned

    # ------------------------------------------------------------- compile
    def compile_agent(
        self, agent_id: str, *, constraints: CompileConstraints | None = None
    ) -> CompiledAgentConfig:
        constraints = constraints or CompileConstraints()
        versions: list[ResourceVersion] = []
        diagnostics: list[Diagnostic] = []
        unavailable: list[UnavailableResource] = []

        agent_versioned = self._read("agent", agent_id, versions)
        agent = parse_agent(agent_versioned)

        executable_reasons: list[str] = []
        if not agent.enabled:
            unavailable.append(
                UnavailableResource(agent.id, "agent", "agent_disabled", "enabled=false")
            )
            executable_reasons.append("agent_disabled")

        connection = self._compile_connection(
            agent, constraints, versions, unavailable, executable_reasons
        )
        session_profile = self._compile_session(agent, constraints, versions, unavailable)
        skills = self._compile_skills(agent, versions)
        tools = self._compile_tools(agent, constraints, versions, diagnostics, unavailable)
        hooks = self._compile_hooks(agent, versions, unavailable)

        self._note_not_started(
            agent.mcp_refs, "mcp", "mcp_not_started", versions, unavailable, parse_mcp
        )
        self._note_not_started(
            agent.trigger_refs,
            "trigger",
            "triggers_not_started",
            versions,
            unavailable,
            parse_trigger,
        )
        if agent.subagents:
            unavailable.append(
                UnavailableResource(
                    agent.id,
                    "agent",
                    "subagents_disabled",
                    "SDK-internal delegation is off in the first version",
                )
            )

        budget = self._compile_budget(agent, constraints)

        payload = {
            "agent_id": agent.id,
            "sdk_version": SDK_PINNED_VERSION,
            "instructions": agent.instructions,
            "connection": connection.to_dict() if connection else None,
            "session_profile": session_profile.to_dict() if session_profile else None,
            "skills": skills.to_dict(),
            "tools": [tool.to_dict() for tool in tools],
            "hooks": [hook.to_dict() for hook in hooks],
            "budget": budget,
            "resource_versions": [version.to_dict() for version in versions],
        }
        config_hash = _hash_payload(payload)

        return CompiledAgentConfig(
            agent_id=agent.id,
            agent_title=agent.title,
            sdk_version=SDK_PINNED_VERSION,
            instructions=agent.instructions,
            connection=connection,
            session_profile=session_profile,
            skills=skills,
            tools=tuple(tools),
            hooks=tuple(hooks),
            budget=budget,
            unavailable=tuple(unavailable),
            diagnostics=tuple(diagnostics),
            resource_versions=tuple(versions),
            executable=not executable_reasons,
            executable_reasons=tuple(executable_reasons),
            config_hash=config_hash,
        )

    # ------------------------------------------------------------ connection
    def _compile_connection(
        self,
        agent: AgentResource,
        constraints: CompileConstraints,
        versions: list[ResourceVersion],
        unavailable: list[UnavailableResource],
        executable_reasons: list[str],
    ) -> CompiledConnection | None:
        pin: ConnectionPin | None = None
        connection_source = "explicit"
        if agent.connection_ref is not None:
            # A template's own connection_ref is authoritative.  An invalid or
            # missing ref raises in ``_read`` - never a silent default fallback.
            ref = agent.connection_ref
        elif constraints.connection_pin is not None:
            pin = constraints.connection_pin
            ref = pin.connection_id
            connection_source = "pinned"
        elif constraints.connection_ref_override:
            ref = constraints.connection_ref_override
            connection_source = "override"
        elif self._default_connections is not None:
            pin = self._default_connections.resolve_default(constraints.connection_role)
            if pin is None:
                unavailable.append(
                    UnavailableResource(
                        agent.id,
                        "agent",
                        "connection_missing",
                        "no explicit connection_ref and no default "
                        f"{constraints.connection_role} connection configured",
                    )
                )
                executable_reasons.append("connection_missing")
                return None
            ref = pin.connection_id
            connection_source = "default"
        else:
            unavailable.append(
                UnavailableResource(agent.id, "agent", "connection_missing", "no connection_ref")
            )
            executable_reasons.append("connection_missing")
            return None
        connection = parse_connection(self._read("connection", ref, versions))
        if connection.backend == "litert" and connection.model_path:
            # Keep the local model path under the same authorized workspace root
            # the existing path policy uses.  This resolves/stats only; it never
            # reads model contents or starts LiteRT.
            try:
                self._store.resolve_path(connection.model_path, write=False)
            except Exception as exc:  # noqa: BLE001 - bind every escape to config_invalid
                raise AdapterConfigInvalid(
                    f"LiteRT model_path {connection.model_path!r} is outside the "
                    "authorized model roots",
                    diagnostics=[
                        {
                            "code": "model_path_outside_roots",
                            "message": "LiteRT model_path escaped the allowed root",
                            "location": "connection.model_path",
                            "detail": {"backend": connection.backend},
                        }
                    ],
                    location="connection.model_path",
                ) from exc
        if pin is not None and (
            pin.revision != connection.revision or pin.content_hash != connection.content_hash
        ):
            raise AdapterConfigInvalid(
                f"pinned connection {ref!r} changed after it was selected; refusing to "
                "silently swap an active member",
                diagnostics=[
                    {
                        "code": "connection_pin_stale",
                        "message": "pinned connection revision/content hash changed",
                        "location": "connection.ref",
                        "detail": {"connection_ref": ref},
                    }
                ],
            )
        backend = self._registry.backend(connection.backend)
        if backend is None:
            raise AdapterConfigInvalid(
                f"connection backend {connection.backend!r} is not registered",
                diagnostics=[
                    {
                        "code": "backend_unsupported",
                        "message": "connection backend is not registered for this version",
                        "location": "connection.backend",
                        "detail": {"backend": connection.backend},
                    }
                ],
            )
        effective_auth = effective_auth_mode(
            connection.backend,
            connection.auth_mode,
            project=connection.project,
            location=connection.location,
            credential_ref=connection.credential_ref,
        )
        facts = capabilities_for_connection(
            backend,
            backend=connection.backend,
            base_url=connection.base_url,
            # Preserve the existing loopback constructor test seam.  Public
            # Settings/default capability checks stay strict and never mark a
            # saved loopback/custom host executable.
            allow_loopback=True,
        )
        compiled = CompiledConnection(
            ref=connection.id,
            backend=connection.backend,
            model=connection.model,
            base_url=connection.base_url,
            credential_ref=connection.credential_ref,
            sdk_config_kind=backend.sdk_config_kind,
            supports_api_key_field=backend.supports_api_key_field,
            # The legacy ``verified`` summary describes the concrete endpoint,
            # not just its provider enum: a custom OpenAI-compatible host is not
            # silently badged as the verified DeepSeek path.
            verified=bool(backend.verified and facts["executable"] is True),
            auth_mode=connection.auth_mode,
            project=connection.project,
            location=connection.location,
            model_path=connection.model_path,
            litert_backend=connection.litert_backend,
            connection_source=connection_source,
            credential_version=pin.credential_version if pin else None,
            configurable=facts["configurable"],
            testable=facts["testable"],
            executable=facts["executable"],
            vendor_verified=facts["vendor_verified"],
        )
        if not connection.enabled:
            unavailable.append(
                UnavailableResource(connection.id, "connection", "connection_disabled", "enabled=false")
            )
            executable_reasons.append("connection_disabled")
        if facts["executable"] is not True:
            if backend.executable and connection.backend == "openai-compat":
                reason = "endpoint_not_authorized"
                detail = (
                    "this custom OpenAI-compatible endpoint is configurable/testable "
                    "but only the existing DeepSeek host is executable in this build"
                )
            else:
                reason = "backend_unverified"
                detail = (
                    f"{connection.backend} is configurable/testable but not an "
                    "executable product backend in this build"
                )
            unavailable.append(
                UnavailableResource(
                    connection.id,
                    "connection",
                    reason,
                    detail,
                )
            )
            executable_reasons.append(reason)
        if auth_requires_credential(connection.backend, effective_auth) and not connection.credential_ref:
            unavailable.append(
                UnavailableResource(
                    connection.id,
                    "connection",
                    "credential_unresolved",
                    "connection declares no credential_ref",
                )
            )
            executable_reasons.append("credential_unresolved")
        if backend.endpoint_field == "base_url" and not connection.base_url:
            unavailable.append(
                UnavailableResource(
                    connection.id,
                    "connection",
                    "endpoint_missing",
                    "openai-compatible backend requires base_url",
                )
            )
            executable_reasons.append("endpoint_missing")
        return compiled

    # --------------------------------------------------------------- session
    def _compile_session(
        self,
        agent: AgentResource,
        constraints: CompileConstraints,
        versions: list[ResourceVersion],
        unavailable: list[UnavailableResource],
    ) -> CompiledSessionProfile | None:
        profile: SessionProfileResource | None = None
        if agent.conversation_ref is not None:
            profile = parse_session_profile(
                self._read("conversation", agent.conversation_ref, versions)
            )
            if not profile.enabled:
                unavailable.append(
                    UnavailableResource(
                        profile.id, "conversation", "session_profile_disabled", "enabled=false"
                    )
                )
                return None
        conversation_id = constraints.conversation_id or (
            profile.conversation_id if profile else None
        )
        return CompiledSessionProfile(
            ref=profile.id if profile else "",
            continuation_mode=profile.continuation_mode if profile else None,
            conversation_id=conversation_id,
            compaction_token_threshold=profile.compaction_token_threshold if profile else None,
            agent_behavior=profile.agent_behavior if profile else None,
        )

    # ---------------------------------------------------------------- skills
    def _compile_skills(
        self, agent: AgentResource, versions: list[ResourceVersion]
    ) -> CompiledSkills:
        paths: list[str] = []
        inline: list[dict[str, str]] = []
        for ref in agent.skills.refs:
            skill = parse_skill(self._read("skill", ref, versions))
            if agent.skills.source == "paths":
                paths.append(skill.directory)
            else:
                inline.append(
                    {
                        "name": skill.id,
                        "description": skill.description or skill.title,
                        "content": skill.body,
                    }
                )
        return CompiledSkills(
            source=agent.skills.source,
            refs=agent.skills.refs,
            paths=tuple(paths),
            inline=tuple(inline),
        )

    # ----------------------------------------------------------------- tools
    def _compile_tools(
        self,
        agent: AgentResource,
        constraints: CompileConstraints,
        versions: list[ResourceVersion],
        diagnostics: list[Diagnostic],
        unavailable: list[UnavailableResource],
    ) -> list[CompiledTool]:
        ceiling = constraints.allowed_tools
        compiled: list[CompiledTool] = []
        for ref in agent.tool_refs:
            if ceiling is not None and ref not in ceiling:
                diagnostics.append(
                    Diagnostic(
                        code="permission_denied",
                        message=f"tool {ref!r} is not authorized by the task/run constraint",
                        level="warning",
                        location=f"agent.{agent.id}.tool_refs",
                        detail={"ref": ref},
                    )
                )
                continue
            tool = parse_tool(self._read("tool", ref, versions))
            if not tool.enabled:
                unavailable.append(
                    UnavailableResource(tool.id, "tool", "tool_disabled", "enabled=false")
                )
                continue
            registration = self._registry.tool(tool.implementation)
            if registration is None:
                raise ReferenceInvalid(
                    f"tool {ref!r} references unregistered implementation {tool.implementation!r}",
                    kind="tool",
                    ref=ref,
                    detail="implementation not registered",
                )
            if not registration.attaches or registration.sdk_tool is None:
                unavailable.append(
                    UnavailableResource(
                        tool.id,
                        "tool",
                        "tool_unavailable",
                        registration.description or f"handler {registration.handler_id} not attachable",
                    )
                )
                continue
            compiled.append(
                CompiledTool(
                    ref=tool.id,
                    handler_id=registration.handler_id,
                    sdk_tool=registration.sdk_tool,
                    permission=registration.permission,
                    policy=tool.policy,
                )
            )
        return compiled

    # ----------------------------------------------------------------- hooks
    def _compile_hooks(
        self,
        agent: AgentResource,
        versions: list[ResourceVersion],
        unavailable: list[UnavailableResource],
    ) -> list[CompiledHook]:
        compiled: list[CompiledHook] = []
        for ref in agent.hook_refs:
            hook: HookResource = parse_hook(self._read("hook", ref, versions))
            if not hook.enabled:
                unavailable.append(
                    UnavailableResource(hook.id, "hook", "hook_disabled", "enabled=false")
                )
                continue
            registration: HookRegistration | None = self._registry.hook(hook.handler)
            if registration is None:
                raise ReferenceInvalid(
                    f"hook {ref!r} references unregistered handler {hook.handler!r}",
                    kind="hook",
                    ref=ref,
                    detail="handler not registered",
                )
            if not registration.attaches or registration.factory is None:
                unavailable.append(
                    UnavailableResource(
                        hook.id,
                        "hook",
                        "hook_unavailable",
                        registration.description or f"handler {registration.handler_id} not attachable",
                    )
                )
                continue
            compiled.append(
                CompiledHook(
                    ref=hook.id,
                    handler_id=registration.handler_id,
                    events=hook.events or registration.events,
                    factory=registration.factory,
                )
            )
        return compiled

    # ----------------------------------------------------- not-started kinds
    def _note_not_started(
        self,
        refs: Sequence[str],
        kind: str,
        reason: str,
        versions: list[ResourceVersion],
        unavailable: list[UnavailableResource],
        parser: Callable[[Versioned], PassthroughResource],
    ) -> None:
        for ref in refs:
            resource = parser(self._read(kind, ref, versions))
            detail = resource.detail
            if not resource.enabled:
                detail = f"{detail}; enabled=false"
            unavailable.append(UnavailableResource(resource.id, kind, reason, detail))

    # ---------------------------------------------------------------- budget
    def _compile_budget(
        self, agent: AgentResource, constraints: CompileConstraints
    ) -> dict[str, int]:
        budget: dict[str, int] = {}
        for key in _BUDGET_KEYS:
            values: list[int] = []
            agent_value = agent.budget.get(key)
            if isinstance(agent_value, int) and not isinstance(agent_value, bool):
                values.append(agent_value)
            task_value = getattr(constraints, key)
            if isinstance(task_value, int) and not isinstance(task_value, bool):
                values.append(task_value)
            if values:
                budget[key] = min(values)
        return budget


__all__ = [
    "CompileConstraints",
    "ConnectionPin",
    "DefaultConnectionResolver",
    "ResourceVersion",
    "UnavailableResource",
    "CompiledTool",
    "CompiledHook",
    "CompiledSkills",
    "CompiledConnection",
    "CompiledSessionProfile",
    "CompiledAgentConfig",
    "ResourceCompiler",
]
