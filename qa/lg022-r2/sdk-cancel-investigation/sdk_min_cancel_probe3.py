"""Minimal real-SDK cancel probe, v3 — drain stays live across cancel (no confound).

v2 cancelled the local drain task *before* calling ``conversation.cancel()``.
Cancelling the drain task closes the SDK's ``receive_steps`` async generator on
the client side, which could itself clear the turn and set ``is_idle`` — a
confound.  v3 keeps the drain task **live** while cancel is called and observes
how the SDK's own stream terminates (``AntigravityCancelledError`` expected),
so the idle transition is attributed to the SDK cancel and not to a local
client-side generator close.

Control = same live drain, no cancel, bounded idle window.

0 real model calls.  Wrap in ``timeout 45``.
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

import lightgravity.adapter.proxy as _proxy_module  # noqa: E402

_proxy_module.AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com", "127.0.0.1"})

from lightgravity.adapter.proxy import LocalAuthProxy, upstream_chat_completions  # noqa: E402
from fake_upstream import FakeUpstream  # noqa: E402


class _FakeCredential:
    def reveal(self) -> str:
        return "sk-fake-local-upstream-not-a-secret"


async def _scenario(*, do_cancel: bool, hold_seconds: float = 20.0) -> dict:
    import google.antigravity as ag
    from google.antigravity import Agent, types

    upstream = FakeUpstream(hold_seconds=hold_seconds)
    proxy = LocalAuthProxy(
        credential=_FakeCredential(),
        upstream_url=upstream_chat_completions(upstream.base_url),
        max_calls=4,
    )
    out: dict = {"do_cancel": do_cancel}
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
        response = await agent.chat("review this")

        drain_result: dict = {}

        async def drain() -> None:
            count = 0
            try:
                async for _chunk in response.chunks:
                    count += 1
            except BaseException as exc:  # noqa: BLE001
                drain_result["exc"] = type(exc).__name__
                drain_result["exc_msg"] = str(exc)[:120]
            finally:
                drain_result["chunks"] = count
                drain_result["finished_at"] = round(time.monotonic() - t0, 3)

        t0 = time.monotonic()
        drain_task = asyncio.ensure_future(drain())
        deadline = time.monotonic() + 8.0
        while not upstream.gate.opened.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        out["stream_opened"] = upstream.gate.opened.is_set()
        out["is_idle_pre"] = conversation.is_idle
        out["drain_still_running_pre"] = not drain_task.done()

        # IMPORTANT: do NOT cancel the drain task.  Keep it live so the idle
        # signal can be attributed to the SDK cancel, not a local close.
        if do_cancel:
            await conversation.cancel()

        try:
            await asyncio.wait_for(asyncio.shield(drain_task), timeout=6.0)
            out["drain_done_within_6s"] = True
        except asyncio.TimeoutError:
            out["drain_done_within_6s"] = False
        out["drain_result"] = dict(drain_result)
        out["is_idle_post"] = conversation.is_idle
        out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
    finally:
        if agent is not None:
            try:
                await asyncio.wait_for(agent.__aexit__(None, None, None), timeout=15.0)
                out["agent_aexit_ok"] = True
            except BaseException as exc:  # noqa: BLE001
                out["agent_aexit_ok"] = False
                out["agent_aexit_exc"] = f"{type(exc).__name__}: {exc}"
        try:
            proxy.stop(timeout=5.0)
            out["proxy_stopped"] = True
        except BaseException:  # noqa: BLE001
            out["proxy_stopped"] = False
        upstream.close()
    return out


async def _main() -> dict:
    control = await _scenario(do_cancel=False)
    cancel = await _scenario(do_cancel=True)
    verdict = {
        # With no cancel the live SDK stream stays open (control).
        "control_stream_open_6s": control.get("drain_done_within_6s") is False,
        "control_not_idle": control.get("is_idle_post") is False,
        # With cancel the live SDK stream terminates and the SDK reports the
        # client-side cancellation on its own generator.
        "cancel_drain_ended": cancel.get("drain_done_within_6s") is True,
        "cancel_idle": cancel.get("is_idle_post") is True,
        "cancel_reports_sdk_cancelled_error": cancel.get("drain_result", {}).get("exc")
        in ("AntigravityCancelledError", "CancelledError"),
        "cancel_agent_aexit_ok": cancel.get("agent_aexit_ok") is True,
    }
    return {
        "provider": "provider-substitute",
        "real_model_calls": 0,
        "control": control,
        "cancel": cancel,
        "verdict": verdict,
        "cancel_order_proven": all(verdict.values()),
    }


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-sdk-min-cancel3.json")
    result = asyncio.run(_main())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["cancel_order_proven"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
