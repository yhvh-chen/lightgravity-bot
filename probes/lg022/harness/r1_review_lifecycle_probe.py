"""LG-022 R1 probe: D1 fix + D2 review lifecycle (deterministic, 0 model calls).

Runs the *real* product functions (``_run_coro_sync`` from the D1 fix and the
``ReviewLifecycle``) with deterministic doubles and writes raw evidence to
``probes/lg022/evidence/r1-review-lifecycle.json``.  No network, no SDK call, no
DeepSeek generation request is made (product real-model budget for this package
is 0).

Run:  uv run python probes/lg022/harness/r1_review_lifecycle_probe.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

import lightgravity.coordinator  # noqa: F401,E402  (import order as the product)
from lightgravity.verify.review import _run_coro_sync  # noqa: E402
from lightgravity.verify.review_lifecycle import (  # noqa: E402
    ReviewLifecycle,
    ReviewStopped,
    run_review_off_loop,
)


def d1_fix() -> dict:
    async def work() -> str:
        await asyncio.sleep(0.001)
        return "ok"

    async def coordinator_like_loop() -> dict:
        started = time.monotonic()
        value = _run_coro_sync(work())  # the old code raised RuntimeError here
        return {"raised": None, "value": value, "elapsed": round(time.monotonic() - started, 4)}

    return asyncio.run(coordinator_like_loop())


def d2_served_during_review() -> dict:
    release = threading.Event()

    def runner(stop_event: threading.Event):  # noqa: ARG001 - double ignores it
        release.wait(timeout=5.0)
        return "reviewed"

    async def main() -> dict:
        lifecycle = ReviewLifecycle(stop_timeout_seconds=2.0)
        loop = asyncio.get_running_loop()
        future = run_review_off_loop(loop, lifecycle, "task_x", "run_x", runner)
        ticks = 0
        status_served = time.monotonic()
        while not future.done() and ticks < 100:
            await asyncio.sleep(0.005)  # the loop keeps serving other work
            ticks += 1
        served_latency = round(time.monotonic() - status_served, 4)
        release.set()
        result = await future
        return {
            "result": result,
            "loop_scheduled_ticks_while_review_running": ticks,
            "loop_served_latency": served_latency,
            "loop_not_blocked": ticks > 0,
        }

    return asyncio.run(main())


def d2_stop_confirmed_and_unknown() -> dict:
    # confirmed: runner observes the stop
    def stopping_runner(stop_event: threading.Event):
        stop_event.wait(timeout=5.0)
        raise ReviewStopped("task_c", "run_c")

    release = threading.Event()

    def stuck_runner(stop_event: threading.Event):  # noqa: ARG001
        release.wait(timeout=5.0)
        return "late"

    async def main() -> dict:
        lifecycle = ReviewLifecycle(stop_timeout_seconds=3.0)
        loop = asyncio.get_running_loop()
        f1 = run_review_off_loop(loop, lifecycle, "task_c", "run_c", stopping_runner)
        for _ in range(200):
            if lifecycle.is_reviewing("task_c", "run_c"):
                break
            await asyncio.sleep(0.005)
        stop1 = await lifecycle.request_stop_async("task_c", "run_c")
        try:
            await f1
        except ReviewStopped:
            pass

        lifecycle2 = ReviewLifecycle(stop_timeout_seconds=0.2)
        f2 = run_review_off_loop(loop, lifecycle2, "task_u", "run_u", stuck_runner)
        for _ in range(200):
            if lifecycle2.is_reviewing("task_u", "run_u"):
                break
            await asyncio.sleep(0.005)
        stop2 = await lifecycle2.request_stop_async("task_u", "run_u")
        slot_retained = lifecycle2.is_reviewing("task_u", "run_u")
        release.set()
        await f2
        return {
            "confirmed_stop": stop1.to_dict(),
            "unknown_stop": stop2.to_dict(),
            "unknown_keeps_slot": slot_retained,
        }

    return asyncio.run(main())


def main() -> int:
    out = {
        "probe": "lg022-r1-review-lifecycle",
        "evidence_kind": "deterministic-double",
        "real_model_calls": 0,
        "d1_running_loop": d1_fix(),
        "d2_served_during_review": d2_served_during_review(),
        "d2_stop": d2_stop_confirmed_and_unknown(),
    }
    target = REPO / "probes/lg022/evidence/r1-review-lifecycle.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    ok = (
        out["d1_running_loop"]["raised"] is None
        and out["d2_served_during_review"]["loop_not_blocked"]
        and out["d2_stop"]["confirmed_stop"]["confirmed"] is True
        and out["d2_stop"]["unknown_stop"]["confirmed"] is False
        and out["d2_stop"]["unknown_keeps_slot"] is True
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
