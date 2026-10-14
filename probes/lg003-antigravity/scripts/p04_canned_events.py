#!/usr/bin/env python3
"""LG-003 probe: offline event-shape self-test against a canned OpenAI SSE server.

Purpose: prove the SDK's streaming event parser (text deltas, tool calls,
finish/structured output) independent of any remote model. This is NOT a model
verification and is reported separately from the live DeepSeek probe.

Run:
    uv run python scripts/p04_canned_events.py --port 18081
The proxy must already be running in `canned` mode.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from google.antigravity import Agent, types
from google.antigravity.connections.local.local_openai_connection_config import (
    LocalOpenAIAgentConfig,
)


async def run(base_url: str, workspace: str) -> dict:
    result: dict = {}

    def echo_tool(text: str) -> str:
        """Echo the given text back to the caller."""
        return "echo:" + text

    cfg = LocalOpenAIAgentConfig(
        base_url=base_url,
        model="canned",
        workspaces=[workspace],
        capabilities=types.CapabilitiesConfig(
            enabled_tools=types.BuiltinTools.minimal(),
            enable_subagents=False,
        ),
        tools=[echo_tool],
        retry_config=types.RetryConfig(
            api_retry=types.ModelAPIRetryConfig(max_retries=0),
            model_output_retry=types.ModelOutputRetryConfig(max_retries=0),
        ),
    )
    result["compiled_active_tools"] = sorted(
        str(t) for t in types.BuiltinTools.minimal()
    )
    try:
        async with Agent(cfg) as agent:
            result["sandbox_status"] = (
                None if agent.sandbox_status is None
                else agent.sandbox_status.model_dump()
            )
            resp = await agent.chat("Reply with exactly: pong")
            result["text"] = await resp.text()
            result["stop_reason"] = str(resp.stop_reason)
            usage = resp.usage_metadata
            result["usage"] = usage.model_dump() if usage else None
            result["structured_output"] = await resp.structured_output()
            result["step_types"] = [str(s.type) for s in agent.conversation.history]
            result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - probe diagnostic
        result["ok"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:2000]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--workspace", default="/tmp/lg003-ws-canned")
    args = parser.parse_args()
    os.makedirs(args.workspace, exist_ok=True)
    out = asyncio.run(run(f"http://127.0.0.1:{args.port}/v1", args.workspace))
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
