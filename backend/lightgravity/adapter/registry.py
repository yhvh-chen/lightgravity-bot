"""Program-registered implementations the Markdown resources may reference.

Markdown frontmatter never names an import path, module, callable or process:
it names a stable handler id that must exist here.  The registry is the only
gate between declarative resources and executable/attachable behavior, which
is what keeps ``handler``/``implementation`` fields from becoming arbitrary
``import``/``eval`` (docs/02 §2, §5; docs/08 §4, §8).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    """A tool handler declared to the adapter.

    ``sdk_tool`` is the Antigravity ``BuiltinTools`` value when the handler maps
    onto a builtin; ``None`` marks an in-process/MCP handler that cannot be
    attached as a builtin.  ``attaches`` records whether the first version can
    actually wire it into the SDK config.
    """

    handler_id: str
    permission: str
    sdk_tool: str | None = None
    source: str = "builtin"
    attaches: bool = True
    description: str = ""


@dataclass(frozen=True, slots=True)
class HookRegistration:
    """A registered lifecycle hook handler.

    ``factory`` builds the SDK hook object at config-build time.  A handler with
    ``factory=None`` is resolvable metadata only and is never attached, so an
    unimplemented hook cannot silently take effect.
    """

    handler_id: str
    factory: Callable[[], Any] | None = None
    events: tuple[str, ...] = ()
    attaches: bool = True
    description: str = ""


@dataclass(frozen=True, slots=True)
class ConnectionBackend:
    """A registered Antigravity connection backend."""

    backend_id: str
    sdk_config_kind: str  # "local" | "openai"
    requires_credential: bool
    supports_api_key_field: bool
    verified: bool
    endpoint_field: str | None = None
    description: str = ""


class ImplementationRegistry:
    """Mutable registry of the handlers the adapter is allowed to bind."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}
        self._hooks: dict[str, HookRegistration] = {}
        self._backends: dict[str, ConnectionBackend] = {}

    # ------------------------------------------------------------- tools
    def register_tool(self, registration: ToolRegistration) -> None:
        self._tools[registration.handler_id] = registration

    def tool(self, handler_id: str) -> ToolRegistration | None:
        return self._tools.get(handler_id)

    def tools(self) -> tuple[ToolRegistration, ...]:
        return tuple(self._tools.values())

    # ------------------------------------------------------------- hooks
    def register_hook(self, registration: HookRegistration) -> None:
        self._hooks[registration.handler_id] = registration

    def hook(self, handler_id: str) -> HookRegistration | None:
        return self._hooks.get(handler_id)

    def hooks(self) -> tuple[HookRegistration, ...]:
        return tuple(self._hooks.values())

    # ---------------------------------------------------------- backends
    def register_backend(self, backend: ConnectionBackend) -> None:
        self._backends[backend.backend_id] = backend

    def backend(self, backend_id: str) -> ConnectionBackend | None:
        return self._backends.get(backend_id)

    def backends(self) -> tuple[ConnectionBackend, ...]:
        return tuple(self._backends.values())


#: Builtin tool handler ids mapped to Antigravity ``BuiltinTools`` values.
#: The ids intentionally differ from SDK names; resolution is explicit.
_BUILTIN_TOOL_HANDLERS: tuple[ToolRegistration, ...] = (
    ToolRegistration(
        handler_id="view-file",
        permission="file.read",
        sdk_tool="view_file",
        description="Read a file from the authorized workspace.",
    ),
    ToolRegistration(
        handler_id="list-directory",
        permission="file.read",
        sdk_tool="list_directory",
        attaches=False,
        description="Deprecated in the pinned SDK default set.",
    ),
    ToolRegistration(
        handler_id="search-directory",
        permission="file.read",
        sdk_tool="search_directory",
        attaches=False,
        description="Deprecated in the pinned SDK default set.",
    ),
    ToolRegistration(
        handler_id="find-file",
        permission="file.read",
        sdk_tool="find_file",
        attaches=False,
        description="Deprecated in the pinned SDK default set.",
    ),
    ToolRegistration(
        handler_id="create-file",
        permission="file.write",
        sdk_tool="create_file",
        description="Create a file in the authorized workspace.",
    ),
    ToolRegistration(
        handler_id="edit-file",
        permission="file.write",
        sdk_tool="edit_file",
        description="Edit a file in the authorized workspace.",
    ),
    ToolRegistration(
        handler_id="run-command",
        permission="command.execute",
        sdk_tool="run_command",
        description="Run a shell command; policy still applies.",
    ),
    ToolRegistration(
        handler_id="read-url",
        permission="web.read",
        sdk_tool="read_url_content",
        description="Fetch a URL; probe-verified.",
    ),
    ToolRegistration(
        handler_id="search-web",
        permission="web.search",
        sdk_tool="search_web",
        attaches=False,
        description="Unavailable on the probe's non-Gemini endpoint.",
    ),
    ToolRegistration(
        handler_id="generate-image",
        permission="image.generate",
        sdk_tool="generate_image",
        attaches=False,
        description="Out of first-version scope.",
    ),
    ToolRegistration(
        handler_id="ask-question",
        permission="interaction.ask",
        sdk_tool="ask_question",
        attaches=False,
        description="Interactive behavior is out of first-version scope.",
    ),
    ToolRegistration(
        handler_id="invoke-subagent",
        permission="delegation.subagent",
        sdk_tool="invoke_subagent",
        attaches=False,
        description="SDK-internal delegation stays disabled.",
    ),
    ToolRegistration(
        handler_id="run-workflow",
        permission="delegation.workflow",
        sdk_tool="run_workflow",
        attaches=False,
        description="SDK-internal workflows stay disabled.",
    ),
    ToolRegistration(
        handler_id="schedule",
        permission="trigger.schedule",
        sdk_tool="schedule",
        attaches=False,
        description="Triggers stay off in the first version.",
    ),
    ToolRegistration(
        handler_id="finish",
        permission="run.finish",
        sdk_tool="finish",
        description="Required to terminate a turn / return structured output.",
    ),
)

#: Registered connection backends.  ``verified`` reflects the LG-003 probe:
#: only the non-Gemini OpenAI-compatible path was exercised; the product's
#: Gemini/Vertex contract remains unverified in this environment.
_CONNECTION_BACKENDS: tuple[ConnectionBackend, ...] = (
    ConnectionBackend(
        backend_id="gemini",
        sdk_config_kind="local",
        requires_credential=True,
        supports_api_key_field=True,
        verified=False,
        description="Gemini Developer API; product contract, not yet verified here.",
    ),
    ConnectionBackend(
        backend_id="vertex",
        sdk_config_kind="local",
        requires_credential=True,
        supports_api_key_field=True,
        verified=False,
        description="Vertex AI; product contract, not yet verified here.",
    ),
    ConnectionBackend(
        backend_id="openai-compat",
        sdk_config_kind="openai",
        requires_credential=True,
        supports_api_key_field=False,
        verified=True,
        endpoint_field="base_url",
        description="OpenAI-compatible endpoint; probe-verified (DeepSeek).",
    ),
)


def default_registry(
    *,
    tools: Iterable[ToolRegistration] | None = None,
    hooks: Iterable[HookRegistration] | None = None,
    backends: Iterable[ConnectionBackend] | None = None,
) -> ImplementationRegistry:
    """Build a registry with the pinned-version builtin mappings.

    Callers may pass additional registrations (used by LG-006/LG-007 and the
    adapter tests); nothing is registered implicitly from Markdown.
    """

    registry = ImplementationRegistry()
    for tool in _BUILTIN_TOOL_HANDLERS:
        registry.register_tool(tool)
    for backend in _CONNECTION_BACKENDS:
        registry.register_backend(backend)
    for hook in hooks or ():
        registry.register_hook(hook)
    for tool in tools or ():
        registry.register_tool(tool)
    for backend in backends or ():
        registry.register_backend(backend)
    return registry


__all__ = [
    "ToolRegistration",
    "HookRegistration",
    "ConnectionBackend",
    "ImplementationRegistry",
    "default_registry",
]
