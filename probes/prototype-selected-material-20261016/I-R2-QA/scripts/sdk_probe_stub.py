#!/usr/bin/env python3
"""Zero-REAL-model probe: drive the antigravity SDK worker turn against a local
OpenAI-compatible stub so the harness/turn path can be exercised without any
real upstream call.  This is a DIAGNOSTIC probe only (not a product claim).

It reproduces the exact turn mechanics the executor uses:
  - a loopback HTTP stub answering /v1/chat/completions (non-stream) with a
    tiny valid completion (either plain text or a create-file tool call),
  - the SDK Agent with LocalOpenAIAgentConfig(base_url=stub),
  - one agent.chat(prompt) turn, capturing all chunks and any crash.

Usage:
    python sdk_probe_stub.py --mode text|toolcall
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Stub(BaseHTTPRequestHandler):
    mode = "text"

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length)
        if self.mode == "toolcall":
            msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "create_file",
                            "arguments": json.dumps(
                                {"path": "orion-summary.md", "content": "# ORION-71\n"}
                            ),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        else:
            msg = {"role": "assistant", "content": "ORION-71 probe ack."}
            finish = "stop"
        body = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-v4-flash",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_stub(port: int, mode: str) -> HTTPServer:
    handler = type("H", (_Stub,), {"mode": mode})
    srv = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


async def main_async(args) -> int:
    srv = start_stub(args.port, args.mode)
    result: dict = {"mode": args.mode, "port": args.port}
    try:
        from google.antigravity import Agent, LocalOpenAIAgentConfig

        cfg = LocalOpenAIAgentConfig(
            base_url=f"http://127.0.0.1:{args.port}/v1",
            model="deepseek-v4-flash",
            workspaces=[args.workspace],
        )
        agent = Agent(cfg)
        await agent.__aenter__()
        result["entered"] = True
        chunks = []
        try:
            resp = await agent.chat("Write a short file.")
            async for ch in resp.chunks:
                chunks.append(type(ch).__name__)
            result["chunks"] = chunks
            result["stop_reason"] = str(getattr(resp, "stop_reason", None))
        except Exception as exc:
            result["turn_error"] = f"{type(exc).__name__}: {exc}"
            result["trace"] = traceback.format_exc()[-1500:]
        finally:
            try:
                await agent.__aexit__(None, None, None)
                result["exited"] = True
            except Exception as exc:
                result["exit_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        result["start_error"] = f"{type(exc).__name__}: {exc}"
        result["trace"] = traceback.format_exc()[-1500:]
    finally:
        srv.shutdown()
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["text", "toolcall"], default="text")
    ap.add_argument("--port", type=int, default=59987)
    ap.add_argument("--workspace", default="/tmp/lg047-sdk-probe-ws")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
