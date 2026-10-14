#!/usr/bin/env python3
"""LG-003 probe: bounded live verification through a real OpenAI-compatible model.

Speaks to a local LG-003 proxy (`scripts/openai_compat_proxy.py --mode deepseek`)
which forwards to the real DeepSeek API and injects the bearer token. The model
that answers is real. Scenarios are intentionally tiny to bound cost.

Scenarios:
    text        minimal chat; asserts non-empty assistant text
    file        file create + view tool calls against a scratch workspace
    structured  response_schema structured output
    budget      BudgetConfig(max_model_calls=1) forces a budget stop reason
    cancel      cancel an in-flight turn and report the resulting state
    resume      save a conversation, then resume it in a new process/session

Usage:
    uv run python scripts/p05_live_deepseek.py --scenario text --base-url http://127.0.0.1:18082/v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time

import pydantic

from google.antigravity import Agent, types
from google.antigravity.connections.local.local_openai_connection_config import (
    LocalOpenAIAgentConfig,
)


def _bounded_retry() -> types.RetryConfig:
    return types.RetryConfig(
        api_retry=types.ModelAPIRetryConfig(max_retries=1),
        model_output_retry=types.ModelOutputRetryConfig(max_retries=1),
    )


def _config(
    base_url: str,
    workspace: str,
    *,
    tools: list | None = None,
    save_dir: str | None = None,
    conversation_id: str | None = None,
    continuation: types.SessionContinuationMode | None = None,
    budget: types.BudgetConfig | None = None,
    response_schema: type[pydantic.BaseModel] | dict | None = None,
    sandbox: bool = False,
) -> LocalOpenAIAgentConfig:
    return LocalOpenAIAgentConfig(
        base_url=base_url,
        model="deepseek-chat",
        workspaces=[workspace],
        tools=tools or [],
        save_dir=save_dir,
        conversation_id=conversation_id,
        session_continuation_mode=continuation,
        budget_config=budget,
        response_schema=response_schema,
        capabilities=types.CapabilitiesConfig(
            enabled_tools=types.BuiltinTools.minimal(),
            enable_subagents=False,
            run_command_config=types.RunCommandConfig(enable_sandbox=sandbox),
        ),
        retry_config=_bounded_retry(),
    )


async def scenario_text(base_url: str, workspace: str) -> dict:
    out: dict = {}
    async with Agent(_config(base_url, workspace)) as agent:
        started = time.monotonic()
        resp = await agent.chat("Reply with the single word: pong")
        text = await resp.text()
        out["elapsed_seconds"] = round(time.monotonic() - started, 2)
        out["text"] = text
        out["stop_reason"] = str(resp.stop_reason)
        usage = resp.usage_metadata
        out["usage"] = usage.model_dump() if usage else None
        out["ok"] = bool(text.strip())
    return out


async def scenario_file(base_url: str, workspace: str) -> dict:
    out: dict = {}
    observed_calls: list[dict] = []
    async with Agent(_config(base_url, workspace)) as agent:
        resp = await agent.chat(
            "Use your file tools to create a file named hello.txt in the "
            "workspace containing exactly the text: hello-lg003"
        )
        chunks = await resp.resolve()
        for chunk in chunks:
            if isinstance(chunk, types.ToolCall):
                observed_calls.append({"name": str(chunk.name), "args": chunk.args})
        out["tool_calls"] = observed_calls
        out["text"] = "".join(
            c.text for c in chunks if isinstance(c, types.Text)
        )[:500]
        hello = os.path.join(workspace, "hello.txt")
        out["file_exists"] = os.path.exists(hello)
        if out["file_exists"]:
            with open(hello, encoding="utf-8") as fh:
                out["file_content"] = fh.read()
        out["ok"] = out["file_exists"] and "hello" in (out.get("file_content") or "")
    return out


class Verdict(pydantic.BaseModel):
    summary: str
    risk_level: int


async def scenario_structured(base_url: str, workspace: str) -> dict:
    out: dict = {}
    async with Agent(
        _config(base_url, workspace, response_schema=Verdict)
    ) as agent:
        resp = await agent.chat(
            "Call the finish tool with a one-sentence summary that the probe "
            "ran, and risk_level 1."
        )
        structured = await resp.structured_output()
        out["structured_output"] = structured
        out["finish_schema_present"] = bool(
            agent._config.capabilities.finish_tool_schema_json  # noqa: SLF001
        )
        out["ok"] = bool(structured)
    return out


async def scenario_budget(base_url: str, workspace: str) -> dict:
    out: dict = {}
    budget = types.BudgetConfig(max_model_calls=1, scope=types.BudgetScope.LIFETIME)
    async with Agent(_config(base_url, workspace, budget=budget)) as agent:
        resp = await agent.chat(
            "Create three separate files one at a time: a.txt, b.txt, c.txt."
        )
        try:
            chunks = await resp.resolve()
            out["text"] = "".join(
                c.text for c in chunks if isinstance(c, types.Text)
            )[:300]
        except Exception as exc:  # noqa: BLE001
            out["stream_error"] = f"{type(exc).__name__}: {exc}"[:300]
        out["stop_reason"] = str(resp.stop_reason)
        usage = resp.usage_metadata
        out["usage"] = usage.model_dump() if usage else None
    out["ok"] = out["stop_reason"] in (
        "StopReason.MAX_MODEL_CALLS_EXCEEDED",
        "StopReason.MAX_TOOL_CALLS_EXCEEDED",
    )
    return out


async def scenario_cancel(base_url: str, workspace: str) -> dict:
    out: dict = {}
    async with Agent(_config(base_url, workspace)) as agent:
        resp = await agent.chat(
            "Write a very long numbered list from 1 to 300, one number per line."
        )

        async def drain() -> None:
            try:
                async for _ in resp.chunks:
                    pass
            except BaseException as exc:  # noqa: BLE001
                out["drain_error"] = f"{type(exc).__name__}: {exc}"[:200]

        task = asyncio.create_task(drain())
        await asyncio.sleep(2.5)
        started = time.monotonic()
        await resp.cancel()
        out["cancel_returned"] = True
        await asyncio.wait_for(task, timeout=30)
        out["cancel_seconds"] = round(time.monotonic() - started, 2)
        out["is_idle_after_cancel"] = agent.conversation.is_idle
        out["stop_reason"] = str(resp.stop_reason)
        out["ok"] = out["is_idle_after_cancel"]
    return out


async def scenario_resume(base_url: str, workspace: str) -> dict:
    out: dict = {}
    save_dir = os.path.join(workspace, "_session")
    shutil.rmtree(save_dir, ignore_errors=True)
    os.makedirs(save_dir, exist_ok=True)
    secret = "zebra-4271"

    async with Agent(
        _config(base_url, workspace, save_dir=save_dir)
    ) as agent:
        await (await agent.chat(f"Remember this code for later: {secret}")).resolve()
        conv_id = agent.conversation_id
    out["conversation_id"] = conv_id

    async with Agent(
        _config(
            base_url,
            workspace,
            save_dir=save_dir,
            conversation_id=conv_id,
            continuation=types.SessionContinuationMode.RESUME,
        )
    ) as agent2:
        resp = await agent2.chat("What code did I ask you to remember?")
        text = await resp.text()
        out["resumed_text"] = text[:300]
        out["resumed_turn_count"] = agent2.conversation.turn_count
    out["ok"] = secret in (out.get("resumed_text") or "")
    return out


SCENARIOS = {
    "text": scenario_text,
    "file": scenario_file,
    "structured": scenario_structured,
    "budget": scenario_budget,
    "cancel": scenario_cancel,
    "resume": scenario_resume,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18082/v1")
    parser.add_argument("--workspace", default="/tmp/lg003-live-ws")
    args = parser.parse_args()
    os.makedirs(args.workspace, exist_ok=True)
    started = time.monotonic()
    try:
        out = asyncio.run(SCENARIOS[args.scenario](args.base_url, args.workspace))
    except Exception as exc:  # noqa: BLE001 - probe diagnostics
        out = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:2000]}
    out["scenario"] = args.scenario
    out["wall_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
