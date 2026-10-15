#!/usr/bin/env python3
"""LG-032 R1 gate 2b — same-Runtime concurrent claim race + identity boundaries.

Two workers of the SAME member in the SAME ``GraphDispatcher`` (distinct
program-frozen lease owners) concurrently request the SAME ready node.  The
fenced collaboration authority must grant exactly one (fence 1); the loser gets a
bounded, definite refusal and can still claim a remaining legal node.  Because
the pool path scopes a candidate to the assignee member, a genuine *cross-member*
same-node race is not produced by the frozen recruiter; this probe therefore
uses the real ``GraphDispatcher._claim_for_worker_pool`` seam (the same code the
product pool slot calls) with distinct frozen owners — exactly the surface the
task asks about — and separately checks the identity/scope boundaries.

Real ``FileStore`` + real ``flock``; no SDK, no network, no model.
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
sys.path.insert(0, str(REPO / "tests" / "collaboration"))

from lightgravity.adapter import ExecutionRef, ExecutorResult  # noqa: E402
from lightgravity.collaboration import (  # noqa: E402
    ClaimPolicy,
    CollaborationService,
    ExecutionGrantRegistry,
)
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402

from collab_helpers import create_run, create_subtask, create_task, link_subtasks, set_switches  # noqa: E402
from graph_helpers import build_environment, make_dispatch_setup  # noqa: E402

TEAM = RoleCatalog({"implementation": ["developer"]})


class _NoopExecutor:
    name = "noop"
    version = "0"

    def capabilities(self):  # noqa: ANN201
        from lightgravity.adapter import adapter_capabilities

        return adapter_capabilities()

    async def execute(self, request, emit):  # noqa: ANN001, ANN201
        return ExecutorResult(state="succeeded", summary="noop", stop_confirmed=True)

    def confirm_stopped(self, run_id, session_refs):  # noqa: ANN001, ANN201
        from lightgravity.adapter import StopConfirmation

        return StopConfirmation(run_id=run_id, confirmed=True, sessions_total=0)

    async def cancel(self, ref):  # noqa: ANN001, ANN201
        from lightgravity.adapter import CancelResult

        return CancelResult(confirmed=True, state="cancelled", reason="noop")


class _Slot:
    def __init__(self, member_id: str) -> None:
        self.subtask_id = f"slot-{member_id}"
        self.member_id = member_id


async def run(work: Path, out: Path) -> dict[str, Any]:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    ws = work / "ws"
    ws.mkdir(parents=True)
    store = FileStore(work / "data", ws)
    build_environment(store)

    task_id = create_task(store)
    run_id = create_run(store, task_id)
    member_a = "member-a"
    alpha = create_subtask(
        store, run_id, key="alpha", write=True, capability="implementation",
        assignee_member_ref=member_a, objective="Write alpha", config_hash="h-alpha",
    )
    beta = create_subtask(
        store, run_id, key="beta", write=True, capability="implementation",
        assignee_member_ref=member_a, objective="Write beta", config_hash="h-beta",
    )
    gamma = create_subtask(
        store, run_id, key="gamma", write=True, capability="implementation",
        assignee_member_ref=member_a, objective="Write gamma", config_hash="h-gamma",
    )
    delta = create_subtask(
        store, run_id, key="delta", write=True, capability="implementation",
        assignee_member_ref="member-OTHER", objective="Write delta", config_hash="h-delta",
    )
    link_subtasks(store, run_id, [alpha, beta, gamma, delta])
    set_switches(store, enabled=True, lease_seconds=300)

    collab = CollaborationService(
        store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
    )
    dispatcher = GraphDispatcher(
        store,
        _NoopExecutor(),
        catalog=TEAM,
        collaboration=collab,
        grant_registry=ExecutionGrantRegistry(),
        autonomous_pool=True,
    )
    _task_id, _run_id2, controller, context = make_dispatch_setup(
        store=store, budget={"max_collab_requests": 8}
    )
    # Point the dispatch context at the run/member we built.
    context = context.__class__(
        task_id=task_id,
        run_id=run_id,
        attempt=1,
        objective="race",
        acceptance_criteria=(),
        instructions="# t\n",
        workspace_path=str(ws),
        budget={"max_collab_requests": 8},
    )
    bindings = {
        alpha: {"node_ref": alpha, "key": "alpha", "capability": "implementation",
                "objective": "Write alpha", "write": True, "workspace_path": str(ws),
                "member_ref": member_a},
        beta: {"node_ref": beta, "key": "beta", "capability": "implementation",
               "objective": "Write beta", "write": True, "workspace_path": str(ws),
               "member_ref": member_a},
        gamma: {"node_ref": gamma, "key": "gamma", "capability": "implementation",
                "objective": "Write gamma", "write": True, "workspace_path": str(ws),
                "member_ref": member_a},
    }
    pool = (alpha, beta, gamma)
    slot = _Slot(member_a)

    def dispatcher_for(owner: str) -> GraphDispatcher:
        return GraphDispatcher(
            store,
            _NoopExecutor(),
            catalog=TEAM,
            collaboration=collab,
            grant_registry=ExecutionGrantRegistry(),
            autonomous_pool=True,
            owner=owner,
        )

    d_a = dispatcher_for("graph-dispatcher:race-a")
    d_b = dispatcher_for("graph-dispatcher:race-b")

    # Concurrent claim of the SAME node (alpha) by two frozen owners.
    res_a, res_b = await asyncio.gather(
        asyncio.to_thread(
            d_a._claim_for_worker_pool,  # noqa: SLF001
            slot, context, alpha, "req-a", pool_refs=pool, bindings=bindings,
        ),
        asyncio.to_thread(
            d_b._claim_for_worker_pool,  # noqa: SLF001
            slot, context, alpha, "req-b", pool_refs=pool, bindings=bindings,
        ),
    )
    winners = [r for r in (res_a, res_b) if r.get("granted")]
    alpha_entity = store.read("subtask", alpha).entity

    # The loser then claims the remaining legal node (beta).
    loser_dispatcher = d_a if not res_a.get("granted") else d_b
    loser_claim = await asyncio.to_thread(
        loser_dispatcher._claim_for_worker_pool,  # noqa: SLF001
        slot, context, beta, "req-loser", pool_refs=pool, bindings=bindings,
    )

    # Single-dispatcher race: the SAME Runtime (one dispatcher, one shared
    # ``self._owner``) receives two concurrent claims for the same node from two
    # DIFFERENT member refs.  The frozen lease owner is the worker instance, so
    # the second must be idempotent ``already_owned`` (no new fence, no double
    # write), never a second real grant.
    single = dispatcher_for("graph-dispatcher:single")
    s_a, s_b = await asyncio.gather(
        asyncio.to_thread(
            single._claim_for_worker_pool,  # noqa: SLF001
            slot, context, gamma, "req-s1", pool_refs=pool, bindings=bindings,
        ),
        asyncio.to_thread(
            single._claim_for_worker_pool,  # noqa: SLF001
            slot, context, gamma, "req-s2", pool_refs=pool, bindings=bindings,
        ),
    )
    alpha_after = store.read("subtask", gamma).entity
    single_race = {
        "both_granted": bool(s_a.get("granted")) and bool(s_b.get("granted")),
        "reasons": sorted([s_a.get("reason"), s_b.get("reason")]),
        "fences": sorted([s_a.get("fence") or 0, s_b.get("fence") or 0]),
        "final_fence": alpha_after.get("fence"),
        # A double real grant would bump the fence twice; one grant + one
        # idempotent replay keeps a single fence increment.
        "single_fence_increment": alpha_after.get("fence") == 1,
    }

    # Out-of-pool / cross-node scope refusal (a node not in the frozen pool).
    outside = await asyncio.to_thread(
        d_a._claim_for_worker_pool,  # noqa: SLF001
        slot, context, "subtask_nonexistent", "req-out", pool_refs=pool, bindings=bindings,
    )
    # Cross-member impersonation: a worker for member-a tries to claim a node
    # assigned to member-OTHER.  The live re-validation must refuse it (the node
    # is not in member-a's legal candidate set), so a worker can never widen its
    # authority by naming another member's node.
    cross = await asyncio.to_thread(
        d_a._claim_for_worker_pool,  # noqa: SLF001
        slot, context, delta, "req-cross", pool_refs=pool, bindings=bindings,
    )

    result = {
        "probe": "lg032-r1/gate2b-race",
        "product_real_generation": 0,
        "race_same_node": {
            "granted_count": len(winners),
            "one_winner": len(winners) == 1,
            "fence": alpha_entity.get("fence"),
            "owners": sorted(
                r.get("binding", {}).get("member_ref") for r in (res_a, res_b) if r.get("granted")
            ),
            "loser_reasons": sorted(
                r.get("reason") for r in (res_a, res_b) if not r.get("granted")
            ),
            "receipts_redacted": all(
                "token" not in json.dumps(r).lower() for r in (res_a, res_b)
            ),
            "res_a": res_a,
            "res_b": res_b,
        },
        "loser_claims_remaining": {
            "granted": loser_claim.get("granted"),
            "binding_key": (loser_claim.get("binding") or {}).get("key"),
            "fence": loser_claim.get("fence"),
        },
        "single_dispatcher_race": single_race,
        "out_of_pool_refused": {
            "granted": outside.get("granted"),
            "reason": outside.get("reason"),
        },
        "cross_member_node_refused": {
            "granted": cross.get("granted"),
            "reason": cross.get("reason"),
            "other_member_node_state": store.read("subtask", delta).entity.get("state"),
            "other_member_node_owner": store.read("subtask", delta).entity.get("owner"),
        },
        "alpha_owner": alpha_entity.get("owner"),
        "beta_owner": store.read("subtask", beta).entity.get("owner"),
    }
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
                "one_winner": res["race_same_node"]["one_winner"],
                "fence": res["race_same_node"]["fence"],
                "loser_reasons": res["race_same_node"]["loser_reasons"],
                "loser_claims_remaining": res["loser_claims_remaining"],
                "out_of_pool_refused": res["out_of_pool_refused"],
                "receipts_redacted": res["race_same_node"]["receipts_redacted"],
                "single_dispatcher_race": res["single_dispatcher_race"],
                "cross_member_node_refused": res["cross_member_node_refused"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
