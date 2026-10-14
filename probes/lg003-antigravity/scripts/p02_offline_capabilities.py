#!/usr/bin/env python3
"""LG-003 probe: offline capability and configuration surface of the installed SDK.

Verifies what compiles/validates without any model call: supported endpoint
classes, backend selection, skills source exclusivity, tool policy exclusivity,
budget/retry/structured-output/session config, and the sandbox status type.
Reported separately from live runtime evidence.
"""

from __future__ import annotations

import json
import os
import sys

import pydantic

import google.antigravity as ag
from google.antigravity import types
from google.antigravity.connections.local import local_connection_config
from google.antigravity.connections.local.local_openai_connection_config import (
    LocalOpenAIAgentConfig,
)
from google.antigravity.proto import localharness_pb2


def _expect_error(fn, *exc_types):
    try:
        fn()
    except exc_types as exc:  # type: ignore[misc]
        return {"raised": type(exc).__name__, "message": str(exc)[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"raised_unexpected": type(exc).__name__, "message": str(exc)[:300]}
    return {"raised": None}


def main() -> int:
    out: dict = {}

    # 1. Public surface.
    out["public_names"] = sorted(n for n in dir(ag) if not n.startswith("_"))
    out["endpoint_classes"] = [
        name for name in ("GeminiAPIEndpoint", "VertexEndpoint")
        if hasattr(ag, name)
    ]
    out["local_openai_config_present"] = True  # imported above from connections.local

    # 2. Builtin tools and defaults.
    out["builtin_tools"] = [t.value for t in types.BuiltinTools]
    out["builtin_default"] = [t.value for t in types.BuiltinTools.default()]
    out["builtin_read_only"] = [t.value for t in types.BuiltinTools.read_only()]
    out["local_agent_default_policies"] = [
        {"tool": p.tool, "decision": str(p.decision)}
        for p in local_connection_config.LocalAgentConfig(
            api_key="dummy", workspaces=["/tmp"]
        ).policies
    ]

    # 3. Endpoint validation / credential requirements.
    out["gemini_endpoint_no_key"] = _expect_error(
        ag.GeminiAPIEndpoint().validate_endpoint, ValueError
    )
    out["gemini_endpoint_with_key"] = _expect_error(
        lambda: ag.GeminiAPIEndpoint(api_key="dummy").validate_endpoint(), ValueError
    )
    out["vertex_endpoint_no_auth"] = _expect_error(
        ag.VertexEndpoint().validate_endpoint, ValueError
    )
    out["vertex_endpoint_with_project"] = _expect_error(
        lambda: ag.VertexEndpoint(project="p", location="l").validate_endpoint(),
        ValueError,
    )
    out["openai_endpoint_requires_base_url"] = _expect_error(
        lambda: LocalOpenAIAgentConfig(model="m", base_url="")
        .create_strategy(tool_runner=None, hook_runner=None)
        ._validate_connection(),  # noqa: SLF001
        types.AntigravityValidationError,
    )

    # 4. Skills source exclusivity (the documented LocalHarness constraint).
    from google.antigravity.hooks import policy

    out["skills_paths_and_inline_conflict"] = _expect_error(
        lambda: LocalOpenAIAgentConfig(
            base_url="http://127.0.0.1:1/v1", model="m",
            skills_paths=["/tmp/skills"],
            inline_skills=[types.InlineSkill(name="s", description="d", content="c")],
        ),
        ValueError,
    )
    out["skills_paths_only_ok"] = _expect_error(
        lambda: LocalOpenAIAgentConfig(
            base_url="http://127.0.0.1:1/v1", model="m", skills_paths=["/tmp/skills"]
        )
    )
    out["inline_skills_only_ok"] = _expect_error(
        lambda: LocalOpenAIAgentConfig(
            base_url="http://127.0.0.1:1/v1", model="m",
            inline_skills=[types.InlineSkill(name="s", description="d", content="c")],
        )
    )

    # 5. Tool visibility exclusivity and subagent guard.
    out["enabled_and_disabled_conflict"] = _expect_error(
        lambda: types.CapabilitiesConfig(
            enabled_tools=[types.BuiltinTools.VIEW_FILE],
            disabled_tools=[types.BuiltinTools.RUN_COMMAND],
        ),
        ValueError,
    )
    out["subagent_depth_without_subagents"] = _expect_error(
        lambda: types.CapabilitiesConfig(enable_subagents=False, max_subagent_depth=2),
        ValueError,
    )

    # 6. Budget / retry / structured output / session continuation.
    budget = types.BudgetConfig(
        max_model_calls=5, max_tool_calls=10, max_total_tokens=1000,
        scope=types.BudgetScope.FORWARD_LOOKING,
    )
    out["budget_model_dump"] = budget.model_dump()
    out["stop_reasons"] = [s.value for s in types.StopReason]
    out["retry_config"] = types.RetryConfig(
        api_retry=types.ModelAPIRetryConfig(max_retries=2),
        model_output_retry=types.ModelOutputRetryConfig(max_retries=1),
    ).model_dump()
    out["session_continuation_modes"] = [m.value for m in types.SessionContinuationMode]

    class Sample(pydantic.BaseModel):
        answer: str
        score: int

    cfg = LocalOpenAIAgentConfig(
        base_url="http://127.0.0.1:1/v1", model="m", response_schema=Sample
    )
    agent = ag.Agent(cfg)
    out["response_schema_injected_into_finish_tool"] = (
        agent._config.capabilities.finish_tool_schema_json is not None  # noqa: SLF001
    )

    # 7. Sandbox status type + proto fields.
    out["sandbox_status_fields"] = sorted(types.SandboxStatus.model_fields)
    out["proto_gemma_endpoint_fields"] = [
        f.name for f in localharness_pb2.GemmaEndpoint.DESCRIPTOR.fields
    ]
    out["proto_model_config_endpoints"] = [
        f.name for f in localharness_pb2.ModelConfig.DESCRIPTOR.fields
    ]

    # 8. InlineSkill fields.
    out["inline_skill_fields"] = sorted(types.InlineSkill.model_fields)

    out["env"] = {
        "GEMINI_API_KEY_present": bool(os.environ.get("GEMINI_API_KEY")),
        "DEEPSEEK_API_KEY_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
