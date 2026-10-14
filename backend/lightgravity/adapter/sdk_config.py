"""Build concrete Antigravity SDK config objects from a compiled plan.

This is the only module in the adapter allowed to import the SDK, and it does so
lazily.  Building an SDK config object proves the resource description *maps to
the installed SDK types*; it does **not** prove the backend is authenticated or
executable.  Callers must consult :attr:`CompiledAgentConfig.executable` and the
capability snapshot instead of treating "config built" as "run will succeed".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import SDK_PINNED_VERSION, installed_sdk_version
from .compiler import CompiledAgentConfig, CompiledHook
from .errors import CapabilityUnavailable


@dataclass(frozen=True, slots=True)
class SdkConfigResult:
    """A constructed SDK config plus compile-time notes (no execution)."""

    config: Any
    kind: str
    sdk_version: str
    warnings: tuple[str, ...]


def sdk_available() -> bool:
    """Return whether the pinned SDK is importable in this environment."""

    try:
        import google.antigravity  # noqa: F401
    except Exception:  # noqa: BLE001 - any import failure means unavailable
        return False
    return True


def _import_sdk() -> Any:
    try:
        import google.antigravity as ag
    except Exception as exc:  # noqa: BLE001 - surface as contract error
        raise CapabilityUnavailable(
            "Antigravity SDK is not importable", capability="sdk"
        ) from exc
    return ag


def _enabled_builtin_tools(compiled: CompiledAgentConfig, types_mod: Any) -> list[Any]:
    tools: list[Any] = []
    seen: set[str] = set()
    for tool in compiled.tools:
        if tool.sdk_tool and tool.sdk_tool not in seen:
            tools.append(types_mod.BuiltinTools(tool.sdk_tool))
            seen.add(tool.sdk_tool)
    # ``finish`` terminates the turn / returns structured output; it is a
    # baseline control tool, not a data/permission grant.
    if "finish" not in seen:
        tools.append(types_mod.BuiltinTools.FINISH)
    return tools


def _skill_kwargs(compiled: CompiledAgentConfig, types_mod: Any) -> dict[str, Any]:
    if compiled.skills.source == "paths":
        return {"skills_paths": list(compiled.skills.paths)} if compiled.skills.paths else {}
    return {
        "inline_skills": [
            types_mod.InlineSkill(
                name=item["name"],
                description=item["description"],
                content=item["content"],
            )
            for item in compiled.skills.inline
        ]
    } if compiled.skills.inline else {}


def _hook_objects(compiled: CompiledAgentConfig) -> list[Any]:
    objects: list[Any] = []
    for hook in compiled.hooks:
        if isinstance(hook, CompiledHook) and hook.factory is not None:
            objects.append(hook.factory())
    return objects


def build_sdk_config(
    compiled: CompiledAgentConfig,
    *,
    workspaces: list[str] | None = None,
) -> SdkConfigResult:
    """Construct an SDK ``AgentConfig`` for ``compiled`` without executing it.

    Raises :class:`CapabilityUnavailable` when the SDK is missing or the plan
    has no resolvable connection backend.  Missing credentials remain a
    *readiness* concern, not a build error.
    """

    ag = _import_sdk()
    from google.antigravity import types as types_mod

    if compiled.connection is None:
        raise CapabilityUnavailable(
            "compiled plan has no connection backend", capability="connection"
        )

    warnings: list[str] = []
    capabilities = types_mod.CapabilitiesConfig(
        enabled_tools=_enabled_builtin_tools(compiled, types_mod),
        enable_subagents=False,
    )

    kwargs: dict[str, Any] = {
        "capabilities": capabilities,
        "system_instructions": compiled.instructions or None,
        "workspaces": workspaces,
    }
    kwargs.update(_skill_kwargs(compiled, types_mod))
    hooks = _hook_objects(compiled)
    if hooks:
        kwargs["hooks"] = hooks
    if compiled.budget:
        kwargs["budget_config"] = types_mod.BudgetConfig(**compiled.budget)

    profile = compiled.session_profile
    conversation_id = profile.conversation_id if profile else None
    if profile and profile.continuation_mode:
        mode = profile.continuation_mode
        if mode == "resume" and not conversation_id:
            warnings.append(
                "session profile requested RESUME without a conversation_id; "
                "downgraded to create_or_resume"
            )
            mode = "create_or_resume"
        kwargs["session_continuation_mode"] = types_mod.SessionContinuationMode(mode)
        if conversation_id:
            kwargs["conversation_id"] = conversation_id
    if profile and profile.compaction_token_threshold:
        kwargs["compaction_config"] = types_mod.CompactionConfig(
            token_threshold=profile.compaction_token_threshold
        )

    kind = compiled.connection.sdk_config_kind
    if kind == "local":
        config = ag.LocalAgentConfig(model=compiled.connection.model, **kwargs)
    elif kind == "openai":
        config = ag.LocalOpenAIAgentConfig(
            base_url=compiled.connection.base_url,
            model=compiled.connection.model,
            **kwargs,
        )
    else:  # pragma: no cover - registry only produces the two kinds above
        raise CapabilityUnavailable(
            f"unsupported sdk_config_kind {kind!r}", capability="connection"
        )

    installed = installed_sdk_version()
    return SdkConfigResult(
        config=config,
        kind=kind,
        sdk_version=installed or SDK_PINNED_VERSION,
        warnings=tuple(warnings),
    )


__all__ = ["SdkConfigResult", "build_sdk_config", "sdk_available"]
