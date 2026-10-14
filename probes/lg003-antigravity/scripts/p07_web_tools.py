#!/usr/bin/env python3
"""LG-003 probe: live web tools (read_url_content, search_web).

read_url_content is pointed at a local HTTP server so the probe does not depend
on external sites. search_web is attempted against the live provider and its
actual behaviour is reported (supported or not).
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import json
import os
import shutil
import sys
import threading

from google.antigravity import Agent, types
from google.antigravity.connections.local.local_openai_connection_config import (
    LocalOpenAIAgentConfig,
)

MARKER = "WEB-TOOL-MARKER-9f3"


class _MarkerHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        body = (f"probe-page marker={MARKER}").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MarkerHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def _config(base_url: str, workspace: str) -> LocalOpenAIAgentConfig:
    return LocalOpenAIAgentConfig(
        base_url=base_url,
        model="deepseek-chat",
        workspaces=[workspace],
        capabilities=types.CapabilitiesConfig(
            enabled_tools=[
                types.BuiltinTools.VIEW_FILE,
                types.BuiltinTools.READ_URL_CONTENT,
                types.BuiltinTools.SEARCH_WEB,
                types.BuiltinTools.FINISH,
            ],
            enable_subagents=False,
        ),
        retry_config=types.RetryConfig(
            api_retry=types.ModelAPIRetryConfig(max_retries=1),
            model_output_retry=types.ModelOutputRetryConfig(max_retries=1),
        ),
    )


async def scenario_read_url(base_url: str, workspace: str) -> dict:
    httpd, port = _start_server()
    try:
        url = f"http://127.0.0.1:{port}/marker"
        out: dict = {"url": url}
        async with Agent(_config(base_url, workspace)) as agent:
            resp = await agent.chat(
                f"Use the read_url_content tool to fetch {url} and report the "
                "marker value it contains."
            )
            chunks = await resp.resolve()
            out["tool_calls"] = [str(c.name) for c in chunks if isinstance(c, types.ToolCall)]
            out["text"] = "".join(c.text for c in chunks if isinstance(c, types.Text))[:400]
        out["marker"] = MARKER
        out["ok"] = MARKER in out.get("text", "")
        return out
    finally:
        httpd.shutdown()


async def scenario_search_web(base_url: str, workspace: str) -> dict:
    out: dict = {}
    async with Agent(_config(base_url, workspace)) as agent:
        try:
            resp = await agent.chat(
                "Use the search_web tool to search for 'Antigravity SDK python' "
                "and summarize one result title."
            )
            chunks = await resp.resolve()
            out["tool_calls"] = [str(c.name) for c in chunks if isinstance(c, types.ToolCall)]
            out["text"] = "".join(c.text for c in chunks if isinstance(c, types.Text))[:400]
            out["stop_reason"] = str(resp.stop_reason)
        except Exception as exc:  # noqa: BLE001
            out["error_type"] = type(exc).__name__
            out["error"] = str(exc)[:600]
    out["ok"] = bool(out.get("text") or out.get("tool_calls"))
    return out


SCENARIOS = {"read_url": scenario_read_url, "search_web": scenario_search_web}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18082/v1")
    parser.add_argument("--workspace", default="/tmp/lg003-web-ws")
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
