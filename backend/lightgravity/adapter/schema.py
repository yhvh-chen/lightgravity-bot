"""Typed parsing/validation of resource frontmatter (docs/02 §5, docs/08 §6.5).

``Store.read`` already guarantees ``schema``/``kind``/``id``/``revision`` and a
boolean ``enabled``.  This module adds the adapter-level contract: which fields
are required, which references exist, and which combinations are illegal.  It
does not resolve references or read other entities - that is the compiler's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from lightgravity.store import Versioned

from .errors import AdapterConfigInvalid
from .redaction import sensitive_paths

#: Skill sources allowed by the pinned SDK.  ``paths`` and ``inline`` are
#: mutually exclusive; a single Agent resource selects exactly one.
SKILL_SOURCES = ("paths", "inline")

#: Session continuation modes exposed by the pinned SDK.
SESSION_CONTINUATION_MODES = ("resume", "create_or_resume", "create_only")

#: Trigger kinds accepted for description (never auto-started in v1).
TRIGGER_TYPES = ("schedule", "event", "file_change")

#: MCP transports accepted for description (never auto-started in v1).
MCP_TRANSPORTS = ("stdio", "http")


def _diag(code: str, message: str, location: str, **detail: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "location": location, "detail": detail}


def _fail(
    message: str,
    *,
    code: str,
    location: str,
    **detail: Any,
) -> NoReturn:
    raise AdapterConfigInvalid(
        message,
        diagnostics=[_diag(code, message, location, **detail)],
        location=location,
    )


def _mapping(data: dict[str, Any], key: str, kind: str, *, required: bool = False) -> dict[str, Any] | None:
    if key not in data:
        if required:
            _fail(f"{kind}.{key} is required", code=f"{key}_missing", location=f"{kind}.{key}")
        return None
    value = data[key]
    if not isinstance(value, dict):
        _fail(f"{kind}.{key} must be a mapping", code=f"{key}_invalid", location=f"{kind}.{key}")
    return value


def _string_list(data: dict[str, Any], key: str, kind: str) -> tuple[str, ...]:
    if key not in data:
        return ()
    value = data[key]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        _fail(
            f"{kind}.{key} must be a list of non-empty strings",
            code=f"{key}_invalid",
            location=f"{kind}.{key}",
        )
    return tuple(value)


def _optional_str(data: dict[str, Any], key: str, kind: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        _fail(f"{kind}.{key} must be a non-empty string", code=f"{key}_invalid", location=f"{kind}.{key}")
    return value


def _optional_int(data: dict[str, Any], key: str, kind: str, *, minimum: int = 0) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(
            f"{kind}.{key} must be an int >= {minimum}",
            code=f"{key}_invalid",
            location=f"{kind}.{key}",
        )
    return value


def _enabled(data: dict[str, Any]) -> bool:
    return bool(data.get("enabled", True))


def _reject_plaintext_secrets(versioned: Versioned) -> None:
    """Reject accidental secret values on a resource (only refs are allowed)."""

    paths = sensitive_paths(versioned.entity)
    if not paths:
        return
    raise AdapterConfigInvalid(
        f"{versioned.kind} {versioned.entity_id!r} contains a secret-like field; "
        "resources must only reference a credential_ref",
        diagnostics=[
            _diag(
                "secret_in_resource",
                "secret-like field present in resource frontmatter",
                f"{versioned.kind}.{versioned.entity_id}",
                fields=paths,
            )
        ],
        location=versioned.path,
    )


@dataclass(frozen=True, slots=True)
class SkillSpec:
    source: str
    refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentResource:
    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    instructions: str
    connection_ref: str | None
    conversation_ref: str | None
    skills: SkillSpec
    tool_refs: tuple[str, ...]
    hook_refs: tuple[str, ...]
    mcp_refs: tuple[str, ...]
    trigger_refs: tuple[str, ...]
    subagents: tuple[str, ...]
    budget: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ConnectionResource:
    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    backend: str
    model: str | None
    credential_ref: str | None
    base_url: str | None
    #: LG-104 additive non-secret provider fields.  ``None`` means the old file
    #: did not store the field; callers infer the preset without rewriting it.
    auth_mode: str | None = None
    project: str | None = None
    location: str | None = None
    model_path: str | None = None
    litert_backend: str | None = None


@dataclass(frozen=True, slots=True)
class SessionProfileResource:
    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    continuation_mode: str | None
    conversation_id: str | None
    compaction_token_threshold: int | None
    agent_behavior: str | None


@dataclass(frozen=True, slots=True)
class SkillResource:
    id: str
    title: str
    description: str
    revision: int
    content_hash: str
    directory: str
    body: str


@dataclass(frozen=True, slots=True)
class ToolResource:
    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    implementation: str
    policy: str


@dataclass(frozen=True, slots=True)
class HookResource:
    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    handler: str
    events: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PassthroughResource:
    """Descriptor for MCP/Trigger resources that are resolved but not started."""

    id: str
    title: str
    enabled: bool
    revision: int
    content_hash: str
    detail: str
    extra: dict[str, Any] = field(default_factory=dict)


def _title(data: dict[str, Any], fallback: str) -> str:
    value = data.get("title")
    return value if isinstance(value, str) and value else fallback


def parse_agent(versioned: Versioned) -> AgentResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    if "skill_refs" in data:
        _fail(
            "agent.skill_refs is not supported; use skills.source/refs",
            code="parallel_skill_field",
            location="agent.skill_refs",
        )
    skills_raw = _mapping(data, "skills", "agent") or {}
    source = skills_raw.get("source")
    if source is None:
        source = "paths"
    if not isinstance(source, str) or source not in SKILL_SOURCES:
        _fail(
            "agent.skills.source must be one of " + ", ".join(SKILL_SOURCES),
            code="skills_source_invalid",
            location="agent.skills.source",
        )
    refs = _string_list(skills_raw, "refs", "agent.skills")
    budget = _mapping(data, "budget", "agent") or {}
    return AgentResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        instructions=versioned.body.strip(),
        connection_ref=_optional_str(data, "connection_ref", "agent"),
        conversation_ref=_optional_str(data, "conversation_ref", "agent"),
        skills=SkillSpec(source=source, refs=refs),
        tool_refs=_string_list(data, "tool_refs", "agent"),
        hook_refs=_string_list(data, "hook_refs", "agent"),
        mcp_refs=_string_list(data, "mcp_refs", "agent"),
        trigger_refs=_string_list(data, "trigger_refs", "agent"),
        subagents=_string_list(data, "subagents", "agent"),
        budget=dict(budget),
    )


def parse_connection(versioned: Versioned) -> ConnectionResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    backend = _optional_str(data, "backend", "connection")
    if backend is None:
        _fail("connection.backend is required", code="backend_missing", location="connection.backend")
    return ConnectionResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        backend=backend,
        model=_optional_str(data, "model", "connection"),
        credential_ref=_optional_str(data, "credential_ref", "connection"),
        base_url=_optional_str(data, "base_url", "connection"),
        auth_mode=_optional_str(data, "auth_mode", "connection"),
        project=_optional_str(data, "project", "connection"),
        location=_optional_str(data, "location", "connection"),
        model_path=_optional_str(data, "model_path", "connection"),
        litert_backend=_optional_str(data, "litert_backend", "connection"),
    )


def parse_session_profile(versioned: Versioned) -> SessionProfileResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    mode = _optional_str(data, "session_continuation_mode", "conversation")
    if mode is not None and mode not in SESSION_CONTINUATION_MODES:
        _fail(
            "conversation.session_continuation_mode must be one of "
            + ", ".join(SESSION_CONTINUATION_MODES),
            code="continuation_mode_invalid",
            location="conversation.session_continuation_mode",
        )
    conversation_id = _optional_str(data, "conversation_id", "conversation")
    if conversation_id is not None and (
        len(conversation_id) < 32 or not conversation_id.replace("-", "").isalnum()
    ):
        _fail(
            "conversation.conversation_id must be >=32 chars of [a-zA-Z0-9-]",
            code="conversation_id_invalid",
            location="conversation.conversation_id",
        )
    behavior = _optional_str(data, "agent_behavior", "conversation")
    if behavior is not None and behavior not in ("autonomous", "interactive", "minimal"):
        _fail(
            "conversation.agent_behavior must be autonomous, interactive or minimal",
            code="agent_behavior_invalid",
            location="conversation.agent_behavior",
        )
    return SessionProfileResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        continuation_mode=mode,
        conversation_id=conversation_id,
        compaction_token_threshold=_optional_int(
            data, "compaction_token_threshold", "conversation", minimum=1
        ),
        agent_behavior=behavior,
    )


def parse_skill(versioned: Versioned) -> SkillResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    directory = str(Path(versioned.path).parent)
    description = data.get("description")
    return SkillResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        description=description if isinstance(description, str) else "",
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        directory=directory,
        body=versioned.body.strip(),
    )


def parse_tool(versioned: Versioned) -> ToolResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    implementation = _optional_str(data, "implementation", "tool")
    if implementation is None:
        _fail(
            "tool.implementation is required",
            code="implementation_missing",
            location="tool.implementation",
        )
    policy = data.get("policy", "allow")
    if policy not in ("allow", "confirm", "deny"):
        _fail(
            "tool.policy must be allow, confirm or deny",
            code="tool_policy_invalid",
            location="tool.policy",
        )
    return ToolResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        implementation=implementation,
        policy=str(policy),
    )


def parse_hook(versioned: Versioned) -> HookResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    handler = _optional_str(data, "handler", "hook")
    if handler is None:
        _fail("hook.handler is required", code="handler_missing", location="hook.handler")
    return HookResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        handler=handler,
        events=_string_list(data, "events", "hook"),
    )


def parse_mcp(versioned: Versioned) -> PassthroughResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    transport = _optional_str(data, "transport", "mcp")
    if transport is None or transport not in MCP_TRANSPORTS:
        _fail(
            "mcp.transport must be one of " + ", ".join(MCP_TRANSPORTS),
            code="mcp_transport_invalid",
            location="mcp.transport",
        )
    return PassthroughResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        detail=f"transport={transport}",
        extra={"transport": transport},
    )


def parse_trigger(versioned: Versioned) -> PassthroughResource:
    data = versioned.entity
    _reject_plaintext_secrets(versioned)
    trigger_type = _optional_str(data, "type", "trigger")
    if trigger_type is None or trigger_type not in TRIGGER_TYPES:
        _fail(
            "trigger.type must be one of " + ", ".join(TRIGGER_TYPES),
            code="trigger_type_invalid",
            location="trigger.type",
        )
    return PassthroughResource(
        id=versioned.entity_id,
        title=_title(data, versioned.entity_id),
        enabled=_enabled(data),
        revision=versioned.revision,
        content_hash=versioned.content_hash,
        detail=f"type={trigger_type}",
        extra={"type": trigger_type},
    )


__all__ = [
    "SKILL_SOURCES",
    "SESSION_CONTINUATION_MODES",
    "TRIGGER_TYPES",
    "MCP_TRANSPORTS",
    "SkillSpec",
    "AgentResource",
    "ConnectionResource",
    "SessionProfileResource",
    "SkillResource",
    "ToolResource",
    "HookResource",
    "PassthroughResource",
    "parse_agent",
    "parse_connection",
    "parse_session_profile",
    "parse_skill",
    "parse_tool",
    "parse_hook",
    "parse_mcp",
    "parse_trigger",
]
