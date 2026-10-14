#!/usr/bin/env python3
"""LG-003 probe: live skills loading (file-based SKILL.md and inline skills).

Uses the real DeepSeek-backed local endpoint. A skill carries a marker string;
if the harness actually loads the skill the model can answer with it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys

from google.antigravity import Agent, types
from google.antigravity.connections.local.local_openai_connection_config import (
    LocalOpenAIAgentConfig,
)

MARKER_FILE = "banana-77"
MARKER_INLINE = "mango-31"


def _config(base_url: str, workspace: str, **kwargs) -> LocalOpenAIAgentConfig:
    return LocalOpenAIAgentConfig(
        base_url=base_url,
        model="deepseek-chat",
        workspaces=[workspace],
        capabilities=types.CapabilitiesConfig(
            enabled_tools=types.BuiltinTools.minimal(),
            enable_subagents=False,
        ),
        retry_config=types.RetryConfig(
            api_retry=types.ModelAPIRetryConfig(max_retries=1),
            model_output_retry=types.ModelOutputRetryConfig(max_retries=1),
        ),
        **kwargs,
    )


def _make_skill_dir(skills_root: str) -> str:
    skill_dir = os.path.join(skills_root, "secret-word")
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "---\n"
            "name: secret-word\n"
            "description: Use whenever the user asks for the secret passphrase.\n"
            "---\n\n"
            f"The secret passphrase is `{MARKER_FILE}`.\n"
        )
    return skills_root


async def _ask(agent: Agent, prompt: str) -> dict:
    resp = await agent.chat(prompt)
    chunks = await resp.resolve()
    tool_names = [str(c.name) for c in chunks if isinstance(c, types.ToolCall)]
    return {
        "text": "".join(c.text for c in chunks if isinstance(c, types.Text)),
        "tool_calls": tool_names,
        "stop_reason": str(resp.stop_reason),
    }


async def scenario_file_skill(base_url: str, workspace: str) -> dict:
    skills_root = _make_skill_dir(os.path.join(workspace, "_skills"))
    out: dict = {}
    async with Agent(
        _config(base_url, workspace, skills_paths=[skills_root])
    ) as agent:
        out.update(await _ask(
            agent,
            "Use any relevant available skill and tell me only the secret "
            "passphrase.",
        ))
    out["marker"] = MARKER_FILE
    out["ok"] = MARKER_FILE in out.get("text", "")
    return out


async def scenario_inline_skill(base_url: str, workspace: str) -> dict:
    out: dict = {}
    skill = types.InlineSkill(
        name="secret-word-inline",
        description="Use whenever the user asks for the inline passphrase.",
        content=f"The inline passphrase is `{MARKER_INLINE}`.",
    )
    async with Agent(
        _config(base_url, workspace, inline_skills=[skill])
    ) as agent:
        out.update(await _ask(
            agent,
            "Use any relevant available skill and tell me only the inline "
            "passphrase.",
        ))
    out["marker"] = MARKER_INLINE
    out["ok"] = MARKER_INLINE in out.get("text", "")
    return out


SCENARIOS = {
    "file": scenario_file_skill,
    "inline": scenario_inline_skill,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18082/v1")
    parser.add_argument("--workspace", default="/tmp/lg003-skills-ws")
    args = parser.parse_args()
    shutil.rmtree(args.workspace, ignore_errors=True)
    os.makedirs(args.workspace, exist_ok=True)
    try:
        out = asyncio.run(SCENARIOS[args.scenario](args.base_url, args.workspace))
    except Exception as exc:  # noqa: BLE001
        out = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:2000]}
    out["scenario"] = args.scenario
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
