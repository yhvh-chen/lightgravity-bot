"""QA-r2 independent boundary/negative repro for the no-orchestrator-adoption fix.

Read-only w.r.t. production code and existing tests.  Complements the frozen
qa-r1 repro with: validation matrix, cross-Run isolation with different budgets,
concurrency, failed-attempt accounting, invalid-plan non-persistence and the
opt-in direct-caller instance ceiling.  No network, no SDK, no credentials.

Exit code 0 only when every check matches the documented per-Run contract.
"""

from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))

from lightgravity.coordinator import (  # noqa: E402
    DispatchContext,
    GraphDispatcher,
    ModelPlanner,
    ModelProposalError,
    PlanProposal,
    PlanningRequest,
    PlanningTrigger,
    RoleCatalog,
)
from lightgravity.coordinator.planner import stable_hash  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from graph_helpers import FakeGraphExecutor, build_environment, make_dispatch_setup  # noqa: E402

CATALOG = RoleCatalog({"implementation": ["developer"], "verification": ["developer"]})
FAILURES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{label}: {detail}")


def no_sink(_event: dict[str, object]) -> None:
    return None


def single_node_propose(calls: list[str]):
    async def propose(context: DispatchContext) -> dict[str, object]:
        calls.append(context.run_id)
        await asyncio.sleep(0)  # yield so concurrent dispatches can interleave
        return {
            "subtasks": [
                {
                    "key": "deliver",
                    "objective": "implement the feature",
                    "capability": "implementation",
                    "acceptance": ["the feature works"],
                    "write": True,
                }
            ]
        }

    return propose


async def new_dispatcher(tmp: Path, planner, tag: str):
    store = FileStore(tmp / f"data-{tag}", tmp / f"ws-{tag}")
    build_environment(store)
    executor = FakeGraphExecutor()
    dispatcher = GraphDispatcher(store, executor, catalog=CATALOG, planner=planner)
    return store, executor, dispatcher


# ---------------------------------------------------------------- A. validation matrix
def check_request_validation() -> None:
    print("== A. PlanningRequest construction validation (stable failures) ==")
    # valid normalization
    r = PlanningRequest(trigger="user_request", reason="x")  # type: ignore[arg-type]
    check(r.trigger is PlanningTrigger.USER_REQUEST, "plain str trigger normalized")
    check(r.to_dict()["trigger"] == "user_request", "to_dict uses enum value")

    invalid_triggers = ["not_a_trigger", "", "USER_REQUEST", "user request", 123, None, object()]
    for bad in invalid_triggers:
        try:
            PlanningRequest(trigger=bad, reason="x")  # type: ignore[arg-type]
            check(False, f"reject trigger={bad!r}", "accepted")
        except ValueError:
            check(True, f"reject trigger={bad!r}")

    for bad in ["", "   ", 123, None, "bad\nname", "x" * 201, "\x00"]:
        try:
            PlanningRequest(  # type: ignore[arg-type]
                trigger=PlanningTrigger.USER_REQUEST, reason="x", requested_by=bad
            )
            check(False, f"reject requested_by={bad!r}", "accepted")
        except ValueError:
            check(True, f"reject requested_by={bad!r}")

    # bool must not pass as int
    for bad in [True, False, 0, -1, 1.0, "1", None]:
        try:
            PlanningRequest(
                trigger=PlanningTrigger.USER_REQUEST, reason="x", max_calls=bad  # type: ignore[arg-type]
            )
            check(False, f"reject max_calls={bad!r}", "accepted")
        except ValueError:
            check(True, f"reject max_calls={bad!r}")

    # valid int
    r2 = PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason="x", max_calls=7)
    check(r2.max_calls == 7, "valid int max_calls accepted")
    r3 = PlanningRequest(
        trigger=PlanningTrigger.USER_REQUEST, reason="x", requested_by="  user  "
    )
    check(r3.requested_by == "user", "requested_by stripped")


# ---------------------------------------------------------------- B/C. budget semantics
async def check_budget_semantics(tmp: Path) -> None:
    print("== B. per-Run budget: cross-Run isolation with different max_calls ==")
    calls: list[str] = []
    planner = ModelPlanner(single_node_propose(calls))  # default: no instance ceiling
    store, _exec, dispatcher = await new_dispatcher(tmp, planner, "B")

    # Run A: max_calls=2, two failed attempts consume it, third refused.
    def boom(_context: DispatchContext) -> dict[str, object]:
        raise RuntimeError("backend down")

    fail_planner = ModelPlanner(boom)
    fstore, _fexec, fdisp = await new_dispatcher(tmp, fail_planner, "Bfail")
    req_a = PlanningRequest(trigger=PlanningTrigger.BLOCKED, reason="a", max_calls=2)
    _ta, _ra, ctrl_a, ctx_a = make_dispatch_setup(fstore, planning_request=req_a)
    a1 = await fdisp.dispatch(ctx_a, ctrl_a, no_sink)
    a2 = await fdisp.dispatch(ctx_a, ctrl_a, no_sink)
    a3 = await fdisp.dispatch(ctx_a, ctrl_a, no_sink)
    check(a1.state == "failed" and a2.state == "failed", "Run A first two attempts failed")
    check(a3.state == "failed" and "budget exhausted" in (a3.summary or ""),
          "Run A third attempt refused by program", a3.summary)
    check(fail_planner.calls == 2, "Run A consumed exactly max_calls=2", str(fail_planner.calls))

    # Run B (different run id, same shared fail planner): gets its own 2 attempts.
    req_b = PlanningRequest(trigger=PlanningTrigger.BLOCKED, reason="b", max_calls=2)
    _tb, _rb, ctrl_b, ctx_b = make_dispatch_setup(fstore, planning_request=req_b)
    b1 = await fdisp.dispatch(ctx_b, ctrl_b, no_sink)
    check(b1.state == "failed", "Run B first attempt runs despite Run A exhaustion")
    check(fail_planner.calls == 3, "cross-Run counter is isolated", str(fail_planner.calls))

    # Run C with its own max_calls=1 succeeds via the shared successful planner.
    res: list[tuple[str, str]] = []
    for index in (1, 2, 3):
        request = PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason=f"run {index}", max_calls=1
        )
        task_id, run_id, controller, context = make_dispatch_setup(store, planning_request=request)
        outcome = await dispatcher.dispatch(context, controller, no_sink)
        run = store.read("run", run_id).entity
        res.append((outcome.state, run.get("plan_source", "")))
        check(outcome.state == "succeeded", f"successful Run {index} succeeded", outcome.summary)
        check(run.get("plan_source") == "model", f"successful Run {index} used model plan")
    check(len(calls) == 3, "three distinct Runs each got one proposal", str(len(calls)))

    print("== C. default ModelPlanner instance has no global ceiling ==")
    check(planner.max_calls is None, "default ModelPlanner.max_calls is None")
    check(planner.calls == 3, "observability counter accumulates across Runs")

    print("== D. same-Run re-dispatch cannot exceed max_calls ==")
    req_d = PlanningRequest(trigger=PlanningTrigger.REPAIR_CAP, reason="d", max_calls=1)
    dstore, _de, ddisp = await new_dispatcher(tmp, ModelPlanner(single_node_propose([])), "D")
    _td, _rd, cd, cxd = make_dispatch_setup(dstore, planning_request=req_d)
    d1 = await ddisp.dispatch(cxd, cd, no_sink)
    d2 = await ddisp.dispatch(cxd, cd, no_sink)
    check(d1.state == "succeeded", "same-Run first dispatch succeeded", d1.summary)
    check(d2.state == "failed" and "budget exhausted" in (d2.summary or ""),
          "same-Run re-dispatch refused before model call", d2.summary)


# ---------------------------------------------------------------- E. concurrency
async def check_concurrency(tmp: Path) -> None:
    print("== E. concurrent distinct Runs sharing one ModelPlanner ==")
    calls: list[str] = []
    planner = ModelPlanner(single_node_propose(calls))
    store, _exec, dispatcher = await new_dispatcher(tmp, planner, "E")

    setups = []
    for index in (1, 2, 3):
        req = PlanningRequest(trigger=PlanningTrigger.AMBIGUOUS_REQUIREMENT, reason=f"c{index}")
        setups.append(make_dispatch_setup(store, planning_request=req))

    results = await asyncio.gather(
        *(dispatcher.dispatch(ctx, ctrl, no_sink) for (_t, _r, ctrl, ctx) in setups)
    )
    check(all(o.state == "succeeded" for o in results),
          "all concurrent on-demand Runs succeeded", str([o.summary for o in results]))
    check(len(calls) == 3 and len(set(calls)) == 3,
          "each concurrent Run got exactly one distinct proposal", str(calls))
    # None of the concurrent runs were starved by a shared counter.
    sources = [store.read("run", r).entity.get("plan_source") for (_t, r, _c, _x) in setups]
    check(all(s == "model" for s in sources), "all concurrent runs used model plan", str(sources))


# ---------------------------------------------------------------- F. invalid plans
async def check_invalid_plans(tmp: Path) -> None:
    print("== F. invalid model plans never persist; no fake success ==")
    bad_variants = {
        "bad_key": [
            {"key": "BAD KEY", "objective": "x", "capability": "implementation",
             "acceptance": ["a"], "write": True}
        ],
        "duplicate_key": [
            {"key": "deliver", "objective": "x", "capability": "implementation",
             "acceptance": ["a"], "write": True},
            {"key": "deliver", "objective": "y", "capability": "implementation",
             "acceptance": ["a"], "write": True},
        ],
        "cycle": [
            {"key": "a", "objective": "x", "capability": "implementation",
             "acceptance": ["a"], "write": True, "depends_on": ["b"]},
            {"key": "b", "objective": "y", "capability": "implementation",
             "acceptance": ["a"], "write": True, "depends_on": ["a"]},
        ],
        "unknown_capability": [
            {"key": "deliver", "objective": "x", "capability": "nope",
             "acceptance": ["a"], "write": True}
        ],
        "no_acceptance": [
            {"key": "deliver", "objective": "x", "capability": "implementation",
             "acceptance": [], "write": True}
        ],
    }
    for name, subtasks in bad_variants.items():
        def propose(_c: DispatchContext, subtasks=subtasks) -> dict[str, object]:
            return {"subtasks": subtasks}

        store, _e, disp = await new_dispatcher(tmp, ModelPlanner(propose), f"F-{name}")
        req = PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason=name)
        _t, run_id, ctrl, ctx = make_dispatch_setup(store, planning_request=req)
        outcome = await disp.dispatch(ctx, ctrl, no_sink)
        run = store.read("run", run_id).entity
        check(outcome.state == "failed", f"invalid plan '{name}' failed", outcome.summary)
        check("plan" not in run and "plan_hash" not in run,
              f"invalid plan '{name}' did not persist a snapshot")


# ---------------------------------------------------------------- G. opt-in ceiling
async def check_direct_caller_ceiling(tmp: Path) -> None:
    print("== G. opt-in direct-caller instance ceiling still enforced ==")
    calls: list[str] = []
    planner = ModelPlanner(single_node_propose(calls), max_calls=1)
    check(planner.max_calls == 1, "explicit ceiling recorded")
    ctx = DispatchContext(
        task_id="t", run_id="r", attempt=1, objective="x", acceptance_criteria=("a",)
    )
    first = await planner.plan(ctx)
    check(isinstance(first, PlanProposal), "first direct call succeeds")
    try:
        await planner.plan(ctx)
        check(False, "second direct call exceeds ceiling", "no error")
    except ModelProposalError as exc:
        check("ceiling" in str(exc), "second direct call raises ceiling error", str(exc))


# ---------------------------------------------------------------- H. default assembly
def check_default_assembly() -> None:
    print("== H. default product assembly wires no model planner ==")
    bootstrap = (REPO / "backend/lightgravity/api/bootstrap.py").read_text()
    match = re.search(r"dispatcher = GraphDispatcher\((.*?)\)\n", bootstrap, re.S)
    check(match is not None, "bootstrap GraphDispatcher call located")
    if match:
        check("planner" not in match.group(1), "bootstrap does not pass planner=",
              match.group(1).strip().replace("\n", " "))
    # No production module constructs a ModelPlanner.
    hits = []
    for path in (REPO / "backend/lightgravity").rglob("*.py"):
        text = path.read_text()
        if "ModelPlanner(" in text:
            hits.append(str(path.relative_to(REPO)))
    check(hits == [], "no production ModelPlanner construction", str(hits))


# ---------------------------------------------------------------- I. plan snapshot
async def check_plan_snapshot(tmp: Path) -> None:
    print("== I. on-demand plan snapshot is complete, hashed and self-consistent ==")
    calls: list[str] = []
    planner = ModelPlanner(single_node_propose(calls))
    store, _e, disp = await new_dispatcher(tmp, planner, "I")
    req = PlanningRequest(
        trigger=PlanningTrigger.USER_REQUEST,
        reason="audit me",
        requested_by="qa",
        max_calls=1,
    )
    _t, run_id, ctrl, ctx = make_dispatch_setup(store, planning_request=req)
    outcome = await disp.dispatch(ctx, ctrl, no_sink)
    run = store.read("run", run_id).entity
    check(outcome.state == "succeeded", "snapshot run succeeded", outcome.summary)
    plan_dict = run.get("plan")
    check(isinstance(plan_dict, dict), "plan snapshot persisted")
    if isinstance(plan_dict, dict):
        check(run.get("plan_source") == plan_dict.get("source") == "model",
              "plan_source matches snapshot")
        # recompute hash from validated snapshot content via stable_hash
        expect = stable_hash(plan_dict)
        check(run.get("plan_hash") == expect, "plan_hash equals stable_hash(plan)",
              f"{run.get('plan_hash')} vs {expect}")
        notes = " ".join(plan_dict.get("notes", []))
        check("trigger=user_request" in notes, "trigger recorded in notes")
        check("audit me" in notes, "reason recorded in notes")
        check("requested_by=qa" in notes, "requested_by recorded in notes")
        check("max_calls=1" in notes, "max_calls recorded in notes")


async def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        check_request_validation()
        await check_budget_semantics(tmp / "budget")
        await check_concurrency(tmp / "conc")
        await check_invalid_plans(tmp / "invalid")
        await check_direct_caller_ceiling(tmp / "ceiling")
        check_default_assembly()
        await check_plan_snapshot(tmp / "snap")

    print("\n== VERDICT ==")
    if FAILURES:
        for item in FAILURES:
            print(f"  CONTRADICTION: {item}")
        return 1
    print("  all independent checks match the documented per-Run contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
