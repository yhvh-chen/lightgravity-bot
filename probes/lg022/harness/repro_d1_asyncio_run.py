"""LG-022 defect D1 minimal reproduction (real product code, 0 model calls).

Root cause: ``lightgravity.verify.review.run_review_turn`` is a *sync* function
that calls ``asyncio.run(_turn())``.  The real coordinator calls the reviewer
from inside its running asyncio worker loop
(``Coordinator._run_loop`` -> ``_auto_verify`` -> ``ReworkOrchestrator.process``
-> ``ModelReviewer.review``), where ``asyncio.run`` raises
``RuntimeError: asyncio.run() cannot be called from a running event loop``.
The reviewer therefore always reports ``unavailable`` in the real runtime, so a
real independent review never completes and acceptance can never open through
the real path.

Contrast: the LG-017 probe (``probes/lg017/review_real_probe.py``) called
``run_review_turn`` from a *sync* entry point (no running loop), which is why it
reported ``passed``; that did not exercise the real coordinator call path.

This repro calls the actual product function through the same sync-into-async
shape used by the coordinator.  The failure happens before ``agent.chat``, so it
consumes **0** real DeepSeek generation calls.

Run:  uv run python probes/lg022/harness/repro_d1_asyncio_run.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

import lightgravity.coordinator  # noqa: F401,E402  (import order as the product)
from lightgravity.adapter.credentials import Secret  # noqa: E402
from lightgravity.verify.review import ReviewerSupport, run_review_turn  # noqa: E402


def main() -> int:
    support = ReviewerSupport(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com/v1",
        credential_ref="deepseek-api-key",
        backend="openai-compat",
    )
    resolver = lambda ref: Secret("dummy-not-used-before-the-failure")  # noqa: E731

    out: dict = {"scenario": "run_review_turn called from inside a running event loop"}

    async def coordinator_like_loop() -> dict:
        try:
            text, usage = run_review_turn(support, resolver, "review prompt", timeout_seconds=5)
            return {"raised": None, "text": text, "usage": usage}
        except Exception as exc:  # noqa: BLE001 - we want the exact failure here
            return {"raised": f"{type(exc).__name__}: {exc}"}

    result = asyncio.run(coordinator_like_loop())
    out["result"] = result
    raised = result.get("raised") or ""
    out["defect_d1_manifest"] = "asyncio.run" in raised and "running event loop" in raised
    print(json.dumps(out, indent=2, ensure_ascii=False))
    Path(REPO / "probes/lg022/evidence/repro-d1.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )
    return 0 if out["defect_d1_manifest"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
