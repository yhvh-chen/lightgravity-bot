"""Minimal real-SDK cancel-order probe (0 real model calls).

Question: with the real ``google-antigravity==0.1.22`` ``Agent`` +
``LocalOpenAIAgentConfig`` + real product ``LocalAuthProxy`` pointed at a
controlled loopback fake OpenAI-compatible SSE upstream, does the *documented*
SDK cancel entry (``Conversation.cancel()`` / ``connection.cancel()``) actually
stop an in-flight streaming turn and let ``wait_for_idle()`` / ``agent.__aexit__``
return within a bounded time?

This isolates the SDK contract from the product wiring, so we can tell whether
the prior "5s unconfirmed" comes from the SDK (no cancel support) or from the
product's stop path never calling the SDK cancel entry.

Per-run budget: the process is intended to be wrapped in ``timeout 45``.

Run: .venv/bin/python qa/lg022-r2/sdk-cancel-investigation/sdk_min_cancel_probe.py <out.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# QA-harness-only provider substitution: widen the product proxy allow-list so
# the real LocalAuthProxy may forward to the loopback fake.  Product code is
# untouched.
import lightgravity.adapter.proxy as _proxy_module  # noqa: E402

_proxy_module.AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com", "127.0.0.1"})

from lightgravity.adapter.proxy import LocalAuthProxy, upstream_chat_completions  # noqa: E402
from fake_upstream import FakeUpstream  # noqa: E402


class _FakeCredential:
    def reveal(self) -> str:
        return "sk-fake-local-upstream-not-a-secret"


async def _probe(*, cancel_after_s: float = 1.0, idle_timeout_s: float = 6.0) -> dict:
    import google.antigravity as ag
    from google.antigravity import Agent, types

    upstream = FakeUpstream(hold_seconds=20.0)
    proxy = LocalAuthProxy(
        credential=_FakeCredential(),
        upstream_url=upstream_chat_completions(upstream.base_url),
        max_calls=4,
    )
    out: dict = {"provider": "provider-substitute", "real_model_calls": 0}
    agent = None
    try:
        proxy.start()
        config = ag.LocalOpenAIAgentConfig(
            base_url=proxy.base_url,
            model="fake-reviewer",
            system_instructions="you are a fake reviewer",
            capabilities=types.CapabilitiesConfig(
                enabled_tools=[], enable_subagents=False
            ),
            workspaces=None,
        )
        agent = Agent(config)
        await agent.__aenter__()
        conversation = agent.conversation

        # Start the turn: chat() returns a lazy ChatResponse after send().
        response = await agent.chat("review this")
        out["chat_returned"] = True
        out["is_idle_after_send"] = conversation.is_idle

        # Drain a little of the stream so the upstream has opened and is holding.
        stream_count = 0
        started = time.monotonic()

        async def drain_then_cancel() -> dict:
            nonlocal stream_count
            chunks = []
            try:
                async for chunk in response.chunks:
                    stream_count += 1
                    chunks.append(type(chunk).__name__)
                    if time.monotonic() - started >= cancel_after_s:
                        break
            except BaseException as exc:  # noqa: BLE001
                chunks.append(f"ERR:{type(exc).__name__}")
            return {"chunks": chunks}

        drain = asyncio.ensure_future(drain_then_cancel())
        # Wait until the upstream opened the stream (bounded).
        opened_deadline = time.monotonic() + 8.0
        while not upstream.gate.opened.is_set() and time.monotonic() < opened_deadline:
            await asyncio.sleep(0.02)
        out["stream_opened"] = upstream.gate.opened.is_set()
        out["is_idle_while_streaming"] = conversation.is_idle

        # Leave the drain task pending mid-stream, then exercise the DOCUMENTED
        # SDK cancel entry (this is what the product never does).
        drain.cancel()
        try:
            await drain
        except BaseException:  # noqa: BLE001
            pass

        cancel_t0 = time.monotonic()
        cancel_exc = None
        try:
            await conversation.cancel()
        except BaseException as exc:  # noqa: BLE001
            cancel_exc = f"{type(exc).__name__}: {exc}"
        out["cancel_call_ok"] = cancel_exc is None
        out["cancel_exc"] = cancel_exc

        idle_ok = None
        idle_exc = None
        try:
            await asyncio.wait_for(conversation.wait_for_idle(), timeout=idle_timeout_s)
            idle_ok = True
        except asyncio.TimeoutError:
            idle_ok = False
        except BaseException as exc:  # noqa: BLE001
            idle_ok = False
            idle_exc = f"{type(exc).__name__}: {exc}"
        idle_elapsed = time.monotonic() - cancel_t0
        out["wait_for_idle_returned"] = idle_ok
        out["wait_for_idle_elapsed_s"] = round(idle_elapsed, 3)
        out["wait_for_idle_exc"] = idle_exc
        out["is_idle_after_cancel"] = conversation.is_idle
        out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
        out["upstream_requests"] = upstream.gate.requests
    finally:
        exit_t0 = time.monotonic()
        exit_ok = None
        exit_exc = None
        if agent is not None:
            try:
                await asyncio.wait_for(
                    agent.__aexit__(None, None, None), timeout=15.0
                )
                exit_ok = True
            except BaseException as exc:  # noqa: BLE001
                exit_ok = False
                exit_exc = f"{type(exc).__name__}: {exc}"
        out["agent_aexit_ok"] = exit_ok
        out["agent_aexit_elapsed_s"] = round(time.monotonic() - exit_t0, 3)
        out["agent_aexit_exc"] = exit_exc
        try:
            proxy.stop(timeout=5.0)
            out["proxy_stopped"] = True
        except BaseException as exc:  # noqa: BLE001
            out["proxy_stopped"] = False
            out["proxy_stop_exc"] = f"{type(exc).__name__}: {exc}"
        upstream.close()

    out["verdict_cancel_order_proven"] = bool(
        out.get("cancel_call_ok")
        and out.get("wait_for_idle_returned")
        and out.get("is_idle_after_cancel")
    )
    return out


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-sdk-min-cancel.json")
    result = asyncio.run(_probe())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("verdict_cancel_order_proven") else 1


if __name__ == "__main__":
    raise SystemExit(main())
