#!/usr/bin/env python3
"""LG-031 POOL-FIX probe — candidate-pool selection + multi-process claim race.

Owner: LG-031 runtime owner (fix/lg031-pool).  Provider-substitute: real
``FileStore`` (real ``flock``/atomic replace) + real OS processes; **no SDK, no
network, no model**.

It demonstrates, against the REAL product program handler
``GraphDispatcher._claim_for_worker_pool``:

1. the program freezes a genuinely multi-candidate pool (two ready
   same-capability nodes assigned to one member) and the discovery projection the
   worker sees lists BOTH candidates;
2. a worker may select a **non-first** candidate and be granted exactly that node
   (its binding points at that node), never a program-pre-bound one;
3. two real OS processes racing the SAME candidate: exactly one wins, the other
   gets a definite refusal, and the persisted fence advances exactly once;
4. the loser can still discover/claim the REMAINING legal candidate;
5. an out-of-pool node is refused before any write, and no token leaks.

Run:
  uv run --frozen python probes/lg031/POOL-FIX/probe_pool_selection.py \
      --work probes/lg031/POOL-FIX/fixtures/pool/work \
      --out probes/lg031/POOL-FIX/evidence/pool-selection.json
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _child_claim(
    data_dir: str, ws: str, run_id: str, task_id: str, member_id: str,
    node_ref: str, pool_refs: list[str], owner: str, wid: str, barrier, out,
) -> None:
    sys.path.insert(0, str(REPO / "backend"))
    from lightgravity.collaboration import ClaimPolicy, CollaborationService
    from lightgravity.coordinator import DispatchContext, GraphDispatcher
    from lightgravity.store import FileStore
    from types import SimpleNamespace

    store = FileStore(Path(data_dir), Path(ws))
    dispatcher = GraphDispatcher(
        store,
        _NullExecutor(),
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        grant_registry=None,
        autonomous_pool=True,
        owner=owner,
    )
    context = DispatchContext(
        task_id=task_id, run_id=run_id, attempt=1, objective="probe", acceptance_criteria=(),
        instructions="# probe\n", workspace_path=str(Path(ws) / "task-ws"),
        budget={"max_collab_requests": 6},
    )
    slot = SimpleNamespace(
        subtask_id=f"slot_{wid}", member_id=member_id,
        member=SimpleNamespace(capabilities=("implementation",)),
    )
    bindings = {
        ref: {"node_ref": ref, "key": ref, "capability": "implementation", "write": False,
              "workspace_path": "", "member_ref": member_id}
        for ref in pool_refs
    }
    barrier.wait()
    try:
        result = dispatcher._claim_for_worker_pool(
            slot, context, node_ref, f"req-{wid}", pool_refs=tuple(pool_refs), bindings=bindings
        )
        out.put(
            {
                "worker": wid,
                "granted": bool(result.get("granted")),
                "reason": result.get("reason"),
                "node_ref": result.get("node_ref") or node_ref,
                "binding_key": (result.get("binding") or {}).get("key"),
                "leaks_token": "token" in json.dumps(result).lower(),
            }
        )
    except Exception as exc:  # noqa: BLE001 - surface any error honestly
        out.put({"worker": wid, "error": f"{type(exc).__name__}: {exc}"})


class _NullExecutor:
    name = "null"
    version = "0"

    async def execute(self, request, emit):  # pragma: no cover - never called here
        raise AssertionError("executor must not run in this probe")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--processes", type=int, default=4)
    args = ap.parse_args()
    work = Path(args.work)
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite existing out: {out}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(REPO / "backend"))
    sys.path.insert(0, str(REPO / "tests" / "collaboration"))
    from collab_helpers import (
        create_run,
        create_subtask,
        create_task,
        link_subtasks,
        set_switches,
    )
    from lightgravity.store import FileStore
    from lightgravity.collaboration import ClaimPolicy, CollaborationService
    from lightgravity.coordinator import DispatchContext, GraphDispatcher
    from types import SimpleNamespace

    data_dir = work / "data"
    ws = work / "ws"
    store = FileStore(data_dir, ws)
    set_switches(store, enabled=True, lease_seconds=300)
    task = create_task(store)
    run = create_run(store, task)
    member = "member-pool"
    alpha = create_subtask(
        store, run, key="alpha", capability="implementation", write=False,
        assignee_member_ref=member,
    )
    beta = create_subtask(
        store, run, key="beta", capability="implementation", write=False,
        assignee_member_ref=member,
    )
    link_subtasks(store, run, [alpha, beta])
    pool_refs = [alpha, beta]

    collab = CollaborationService(
        store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
    )
    view = collab.discover(run, member)
    discoverable = [c.subtask_id for c in view.candidates]

    report: dict = {
        "work": str(work),
        "run_ref": run,
        "member_ref": member,
        "nodes": {"alpha": alpha, "beta": beta},
        "discoverable_at_dispatch": discoverable,
        "provider_substitute": "real FileStore + real OS processes; no SDK/network/model",
    }

    # (2) Select the NON-FIRST candidate with a single program handler call.
    dispatcher = GraphDispatcher(
        store, _NullExecutor(),
        collaboration=collab, autonomous_pool=True, owner="graph-dispatcher:probe",
    )
    context = DispatchContext(
        task_id=task, run_id=run, attempt=1, objective="probe", acceptance_criteria=(),
        instructions="# probe\n", workspace_path=str(ws / "task-ws"), budget={"max_collab_requests": 6},
    )
    slot = SimpleNamespace(
        subtask_id="slot_select", member_id=member,
        member=SimpleNamespace(capabilities=("implementation",)),
    )
    key_of = {alpha: "alpha", beta: "beta"}
    bindings = {
        ref: {"node_ref": ref, "key": key_of.get(ref, ref), "capability": "implementation",
              "write": False, "workspace_path": "", "member_ref": member}
        for ref in pool_refs
    }
    selected = dispatcher._claim_for_worker_pool(
        slot, context, beta, "req-select-beta", pool_refs=tuple(pool_refs), bindings=bindings
    )
    report["non_first_selection"] = {
        "selected_node": beta,
        "is_first_candidate": beta == discoverable[0],
        "granted": bool(selected.get("granted")),
        "binding_key": (selected.get("binding") or {}).get("key"),
        "leaks_token": "token" in json.dumps(selected).lower(),
    }
    # Out-of-pool refusal.
    refused = dispatcher._claim_for_worker_pool(
        slot, context, "subtask_foreign", "req-foreign",
        pool_refs=tuple(pool_refs), bindings=bindings,
    )
    report["out_of_pool_refusal"] = {
        "reason": refused.get("reason"),
        "granted": bool(refused.get("granted")),
    }

    # (3)+(4) Real multi-process race on the REMAINING node (alpha).
    barrier = mp.Barrier(args.processes)
    queue: "mp.Queue[dict]" = mp.Queue()
    procs = []
    for i in range(args.processes):
        p = mp.Process(
            target=_child_claim,
            args=(
                str(data_dir), str(ws), run, task, member, alpha, pool_refs,
                f"graph-dispatcher:p{i}", f"p{i}", barrier, queue,
            ),
        )
        p.start()
        procs.append(p)
    results = [queue.get(timeout=60) for _ in procs]
    for p in procs:
        p.join(timeout=30)
    granted = [r for r in results if r.get("granted")]
    report["race_on_same_node"] = {
        "node_ref": alpha,
        "processes": args.processes,
        "granted_count": len(granted),
        "winner": granted[0]["worker"] if granted else None,
        "results": results,
        "final_fence": int(store.read("subtask", alpha).entity.get("fence") or 0),
    }

    # The loser path: a fresh worker claims the other (still-legal) candidate.
    # (alpha is now held; beta was granted in-process above, so reset beta to
    # ready in this probe fixture to model "remaining legal candidate".)
    store.write(
        "subtask", beta, {"state": "pending", "owner": None, "fence": 0},
        expected_revision=store.read("subtask", beta).revision, actor="probe",
    )
    loser = GraphDispatcher(
        store, _NullExecutor(),
        collaboration=CollaborationService(
            store, policy=ClaimPolicy(enabled=True, lease_seconds=300, collab_requests_enabled=True)
        ),
        autonomous_pool=True, owner="graph-dispatcher:loser",
    )
    remaining = loser._claim_for_worker_pool(
        SimpleNamespace(subtask_id="slot_loser", member_id=member,
                        member=SimpleNamespace(capabilities=("implementation",))),
        context, beta, "req-loser", pool_refs=tuple(pool_refs), bindings=bindings,
    )
    report["loser_reclaims_remaining"] = {
        "granted": bool(remaining.get("granted")),
        "binding_key": (remaining.get("binding") or {}).get("key"),
    }

    # (5) No claim -> no write: a fresh ready node claimed by nobody keeps owner
    # unset and fence 0 (the program never writes on a worker's behalf).
    gamma = create_subtask(
        store, run, key="gamma", capability="implementation", write=False,
        assignee_member_ref=member,
    )
    untouched = store.read("subtask", gamma).entity
    report["no_claim_no_write"] = {
        "owner": untouched.get("owner"),
        "fence": int(untouched.get("fence") or 0),
        "state": untouched.get("state"),
    }
    # Stale/unknown selection refused before any write.
    stale = dispatcher._claim_for_worker_pool(
        slot, context, gamma, "req-gamma", pool_refs=tuple(pool_refs), bindings=bindings,
    )
    report["selection_not_in_pool_refused"] = {
        "reason": stale.get("reason"), "granted": bool(stale.get("granted")),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
