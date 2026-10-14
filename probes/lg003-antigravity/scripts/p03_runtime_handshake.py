#!/usr/bin/env python3
"""LG-003 probe: real platform runtime handshake and credential gating.

Starts the bundled native `localharness` runtime, initializes a conversation and
reads the reported sandbox status WITHOUT a model call. Then records what
happens when the Gemini backend is selected without credentials.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from google.antigravity import Agent, LocalAgentConfig, types


async def _handshake() -> dict:
    out: dict = {}
    cfg = LocalAgentConfig(
        model="gemini-3.8-flash",
        api_key="dummy-not-a-real-key",  # lets endpoint validation pass; no call made
        workspaces=[os.getcwd()],
        capabilities=types.CapabilitiesConfig(
            enabled_tools=types.BuiltinTools.minimal(),
            enable_subagents=False,
            run_command_config=types.RunCommandConfig(enable_sandbox=True),
        ),
        retry_config=types.RetryConfig(
            api_retry=types.ModelAPIRetryConfig(max_retries=0),
            model_output_retry=types.ModelOutputRetryConfig(max_retries=0),
        ),
    )
    async with Agent(cfg) as agent:
        out["started"] = agent.is_started
        out["is_idle"] = agent.conversation.is_idle
        out["conversation_id_before_first_turn"] = agent.conversation_id
        out["history_len"] = len(agent.conversation.history)
        sandbox = agent.sandbox_status
        out["sandbox_status"] = None if sandbox is None else sandbox.model_dump()
        out["total_usage"] = agent.conversation.total_usage.model_dump()
    return out


async def _gemini_without_credentials() -> dict:
    cfg = LocalAgentConfig(model="gemini-3.8-flash", workspaces=[os.getcwd()])
    try:
        async with Agent(cfg):
            return {"blocked": False, "note": "session started without Gemini key"}
    except types.AntigravityValidationError as exc:
        return {"blocked": True, "error_type": type(exc).__name__, "message": str(exc)[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"blocked": True, "error_type": type(exc).__name__, "message": str(exc)[:300]}


def main() -> int:
    out: dict = {}
    try:
        out["handshake"] = asyncio.run(_handshake())
    except Exception as exc:  # noqa: BLE001
        out["handshake"] = {
            "error_type": type(exc).__name__,
            "error": str(exc)[:1500],
        }
    out["gemini_backend_without_credentials"] = asyncio.run(
        _gemini_without_credentials()
    )
    out["env"] = {
        "GEMINI_API_KEY_present": bool(os.environ.get("GEMINI_API_KEY")),
        "GOOGLE_API_KEY_present": bool(os.environ.get("GOOGLE_API_KEY")),
        "DEEPSEEK_API_KEY_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
