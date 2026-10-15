"""Minimal real-SDK cancel probe, v2 — control vs cancel + stop-reason evidence.

Adds, on top of v1:
  * a **control** scenario with NO cancel: confirm the turn does *not* become
    idle within the same idle window (so the cancel transition is not a
    pre-existing idle);
  * the SDK's own ``_last_turn_stop_reason`` after cancel (expect CANCELLED);
  * whether the upstream observed the client socket go away (best effort).

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
    response = None
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

        # Begin draining the stream and leave the drain pending mid-stream.
        drain = asyncio.ensure_future(_drain_pending(response))
        deadline = time.monotonic() + 8.0
        while not upstream.gate.opened.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        out["stream_opened"] = upstream.gate.opened.is_set()
        out["is_idle_pre"] = conversation.is_idle

        drain.cancel()
        try:
            await drain
        except BaseException:  # noqa: BLE001
            pass

        if do_cancel:
            await conversation.cancel()

        idle_ok = None
        try:
            await asyncio.wait_for(conversation.wait_for_idle(), timeout=6.0)
            idle_ok = True
        except asyncio.TimeoutError:
            idle_ok = False
        out["idle_within_6s"] = idle_ok
        out["is_idle_post"] = conversation.is_idle
        if do_cancel:
            reason = conversation._last_turn_stop_reason
            out["last_turn_stop_reason"] = getattr(reason, "name", str(reason))
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


async def _drain_pending(response) -> None:
    try:
        async for _chunk in response.chunks:
            pass
    except BaseException:  # noqa: BLE001
        pass


async def _main() -> dict:
    control = await _scenario(do_cancel=False)
    cancel = await _scenario(do_cancel=True)
    verdict = {
        "control_not_idle_within_window": control.get("idle_within_6s") is False,
        "cancel_idle_within_window": cancel.get("idle_within_6s") is True,
        "cancel_stop_reason_cancelled": cancel.get("last_turn_stop_reason") == "CANCELLED",
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
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-sdk-min-cancel2.json")
    result = asyncio.run(_main())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["cancel_order_proven"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
