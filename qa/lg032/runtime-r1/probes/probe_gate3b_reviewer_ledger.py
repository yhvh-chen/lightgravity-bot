#!/usr/bin/env python3
"""LG-032 R1 gate 3b — selection + execution + reviewer share ONE ledger.

Gate 3 requires the selection + execution + reviewer proxies to share a single
physical persistent ledger so a Task's cumulative real-generation budget does not
reset per role, and an over-limit request is refused *before* forwarding.

Product facts this probe independently confirms:
* ``AntigravityExecutor`` receives the process-global ``GenerationCounter``;
* ``run_review_turn`` builds its own ``LocalAuthProxy`` WITHOUT passing a budget,
  and ``LocalAuthProxy`` defaults the budget to ``_default_generation_counter()``
  — the SAME process-global counter — so the reviewer consumes the same ledger;
* ``api/bootstrap.create_app`` calls ``configure_generation_ledger(data_dir)`` so
  that shared counter is persisted under the controlled data root.

The probe wires the *same* physical data root into ``configure_generation_ledger``
and the worker executor, exhausts the ledger with a worker session, then runs a
real reviewer turn against the same fake upstream.  Because the reviewer proxy
consults the shared ledger, its over-limit request must be **refused before
forwarding** (0 upstream requests for the reviewer).

The reviewer's proxy only authorizes a public upstream host, so this probe
substitutes ``lightgravity.verify.review.LocalAuthProxy`` with a loopback-allowing
subclass in the QA harness ONLY (product source untouched), clearly labelled.

Provider-substitute; product real generation 0.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_upstream import UpstreamServer  # noqa: E402

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.adapter.execution import ExecuteRequest  # noqa: E402
from lightgravity.adapter.proxy import (  # noqa: E402
    LocalAuthProxy,
    configure_generation_ledger,
    global_generation_counter,
)
from lightgravity.store import FileStore  # noqa: E402

from graph_helpers import build_environment  # noqa: E402

_FAKE_SECRET = "sk-fake-upstream-not-real"


class _LoopbackAuthProxy(LocalAuthProxy):
    """QA harness only: allow the local fake upstream for the reviewer turn.

    The product reviewer proxy authorizes only public hosts; this subclass only
    widens the *upstream host policy* so the probe can observe the ledger
    behaviour locally.  It deliberately does not pass ``generation_budget``, so
    it inherits the same default (process-global) ledger as the product.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["allow_loopback_upstream"] = True
        super().__init__(**kwargs)


async def run(work: Path, out: Path) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    ws = work / "ws"
    ws.mkdir(parents=True)
    store = FileStore(work / "data", ws)
    build_environment(store)
    upstream = UpstreamServer(select_non_first=False)
    result: dict[str, Any] = {
        "probe": "lg032-r1/gate3b-reviewer-ledger",
        "provider": "local-fake-openai-sse-loopback",
        "provider_substitute": True,
        "product_real_generation": 0,
        "started_at": time.time(),
        "reviewer_proxy_substituted": True,
    }
    try:
        # The product startup call: one physical ledger under the data root.
        counter = configure_generation_ledger(work / "data", limit=1)
        ledger_path = str(work / "data" / "generation" / "generation.jsonl")

        worker = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=InMemoryCredentialResolver({"worker-default": _FAKE_SECRET}),
            artifacts=DirectoryArtifactSink(work / "artifacts"),
            allow_loopback_upstream=True,
            model_calls_cap=1,
            generation_budget=counter,
        )
        cur = int(store.read("connection", "primary").entity.get("revision", 0))
        store.write(
            "connection",
            "primary",
            {
                "backend": "openai-compat",
                "model": "fake-model",
                "credential_ref": "worker-default",
                "base_url": upstream.base_url,
            },
            expected_revision=cur,
            actor="qa-r1",
        )
        before = len(upstream.records)
        wres = await worker.execute(
            ExecuteRequest(
                task_id="task_x",
                run_id="run_x",
                subtask_id="subtask_x",
                attempt=1,
                objective="Write out/x.txt",
                workspace_path=str(ws),
                allowed_tools=("view-file",),
                connection_ref="primary",
                agent_ref="developer",
                skill_refs=("implementation",),
                budget={},
            ),
            lambda e: None,
        )
        worker_forwarded = len(upstream.records) - before
        snapshot_after_worker = global_generation_counter().count

        # Reviewer turn: real SDK, same fake upstream, shared default ledger.
        import lightgravity.adapter.proxy as proxy_mod
        import lightgravity.coordinator  # noqa: F401  (import order: avoid cycle)
        from lightgravity.verify.review import ReviewerSupport, run_review_turn

        # ``run_review_turn`` imports ``LocalAuthProxy`` from this module at call
        # time, so patching it here routes the reviewer proxy through the
        # loopback-allowing subclass (QA harness only).
        original = proxy_mod.LocalAuthProxy
        proxy_mod.LocalAuthProxy = _LoopbackAuthProxy
        reviewer_refusal: str | None = None
        text = None
        usage: dict[str, Any] = {}
        try:
            before_r = len(upstream.records)
            try:
                text, usage = run_review_turn(
                    ReviewerSupport(
                        model="fake-model",
                        base_url=upstream.base_url,
                        credential_ref="worker-default",
                    ),
                    lambda ref: InMemoryCredentialResolver(
                        {"worker-default": _FAKE_SECRET}
                    ).resolve(ref),
                    "Review the candidate.",
                    timeout_seconds=20,
                    max_model_calls=3,
                )
            except Exception as exc:  # noqa: BLE001 - the shared-ledger refusal
                reviewer_refusal = f"{type(exc).__name__}: {str(exc)[:160]}"
            reviewer_forwarded = len(upstream.records) - before_r
        finally:
            proxy_mod.LocalAuthProxy = original

        result.update(
            {
                "ledger_limit": 1,
                "ledger_path": ledger_path,
                "count_after_worker": snapshot_after_worker,
                "worker_state": wres.state,
                "worker_failure_code": getattr(wres.failure, "code", None),
                "worker_forwarded": worker_forwarded,
                "reviewer_forwarded": reviewer_forwarded,
                "reviewer_text": (text or "")[:120],
                "reviewer_usage": usage,
                "reviewer_refusal": reviewer_refusal,
                "reviewer_shares_shared_ledger": reviewer_forwarded == 0
                and "budget exhausted" in (reviewer_refusal or ""),
            }
        )
    finally:
        upstream.close()
        result["finished_at"] = time.time()
        result["elapsed_seconds"] = round(result["finished_at"] - result["started_at"], 3)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = asyncio.run(run(Path(a.work), Path(a.out)))
    print(
        json.dumps(
            {
                k: res.get(k)
                for k in (
                    "count_after_worker",
                    "worker_forwarded",
                    "reviewer_forwarded",
                    "reviewer_shares_shared_ledger",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
