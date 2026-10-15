"""Independent QA repro: on-demand planning budget semantics.

Read-only w.r.t. production code.  Exercises the *real* ``ModelPlanner`` and
``GraphDispatcher`` (no test stub) for the acceptance-criterion-2 checks:

  A. different Runs sharing ONE ModelPlanner instance, each with its own
     explicit ``PlanningRequest``;
  B. same Run re-dispatch (no hidden loop);
  C. explicit request with NO injected planner;
  D. empty reason rejected at construction;
  E. invalid proposal -> plan validation failure, no snapshot write;
  F. over-limit / repeated on-demand.

No network, no SDK, no credentials.  Exit code is non-zero when the observed
behaviour contradicts the documented per-Run bounded contract.
"""

from __future__ import annotations

import asyncio
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
    PlanningRequest,
    PlanningTrigger,
    RoleCatalog,
)
from lightgravity.store import FileStore  # noqa: E402
from graph_helpers import FakeGraphExecutor, build_environment, make_dispatch_setup  # noqa: E402

CATALOG = RoleCatalog({"implementation": ["developer"], "verification": ["developer"]})


def no_sink(_event: dict[str, object]) -> None:
    return None


def make_model_planner() -> ModelPlanner:
    calls: list[str] = []

    def propose(context: DispatchContext) -> dict[str, object]:
        calls.append(context.run_id)
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

    planner = ModelPlanner(propose)  # default max_calls == 1
    planner._qa_calls = calls  # type: ignore[attr-defined]
    return planner


async def run_one(store: FileStore, dispatcher: GraphDispatcher, request: PlanningRequest | None):
    _task, run_id, controller, context = make_dispatch_setup(
        store, planning_request=request
    )
    outcome = await dispatcher.dispatch(context, controller, no_sink)
    run = store.read("run", run_id).entity
    return outcome, run_id, run


async def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = FileStore(root / "data", root / "ws")
        build_environment(store)
        executor = FakeGraphExecutor()
        planner = make_model_planner()
        dispatcher = GraphDispatcher(store, executor, catalog=CATALOG, planner=planner)

        print("== A. different Runs sharing one ModelPlanner instance ==")
        for index in (1, 2):
            request = PlanningRequest(
                trigger=PlanningTrigger.USER_REQUEST,
                reason=f"explicit decomposition for run {index}",
            )
            outcome, run_id, run = await run_one(store, dispatcher, request)
            print(
                f"  run#{index} id={run_id} outcome={outcome.state} "
                f"plan_source={run.get('plan_source')!r} "
                f"model_calls_so_far={planner.calls} propose_invocations={len(planner._qa_calls)}"  # type: ignore[attr-defined]
            )
            if index == 1 and outcome.state != "succeeded":
                problems.append(f"A: first on-demand run failed: {outcome.summary}")
            if index == 2 and outcome.state != "succeeded":
                problems.append(
                    "A: SECOND run with a fresh explicit PlanningRequest failed "
                    f"({outcome.state}: {outcome.summary}) while sharing the dispatcher's "
                    "single ModelPlanner instance.  The documented contract is "
                    "'bounded per Run/Task request', not one global call for the whole process."
                )

        print("== B. same Run re-dispatch uses no hidden planning loop ==")
        # A fresh dispatcher so the shared counter from A does not interfere.
        store_b = FileStore(Path(tmp) / "datab", Path(tmp) / "wsb")
        build_environment(store_b)
        planner_b = make_model_planner()
        dispatcher_b = GraphDispatcher(
            store_b, FakeGraphExecutor(), catalog=CATALOG, planner=planner_b
        )
        request_b = PlanningRequest(
            trigger=PlanningTrigger.BLOCKED, reason="needs decomposition"
        )
        _t, run_b, controller_b, context_b = make_dispatch_setup(
            store_b, planning_request=request_b
        )
        outcome_b1 = await dispatcher_b.dispatch(context_b, controller_b, no_sink)
        print(f"  first dispatch outcome={outcome_b1.state} calls={planner_b.calls}")
        # Re-dispatch the exact same context/controller.
        try:
            outcome_b2 = await dispatcher_b.dispatch(context_b, controller_b, no_sink)
            print(f"  re-dispatch outcome={outcome_b2.state} calls={planner_b.calls}")
        except Exception as exc:  # noqa: BLE001
            print(f"  re-dispatch raised {type(exc).__name__}: {exc} calls={planner_b.calls}")
        # B is supporting evidence for the SAME root cause as A: the second
        # planning phase of one Run cannot get a bounded per-Run proposal because
        # the shared ModelPlanner already consumed its single process-global call.
        # (Re-dispatch of a finished Run may also be unsupported; do not count it
        # as a separate regression beyond the shared-counter defect.)
        if planner_b.calls != 2:
            print(
                f"  note: same-Run re-dispatch left planner.calls={planner_b.calls}; "
                "the second planning phase hit the shared instance budget, same root cause as A."
            )

        print("== C. explicit request with NO injected planner ==")
        store_c = FileStore(Path(tmp) / "datac", Path(tmp) / "wsc")
        build_environment(store_c)
        dispatcher_c = GraphDispatcher(store_c, FakeGraphExecutor(), catalog=CATALOG)
        request_c = PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason="user asked for decomposition"
        )
        outcome_c, run_c_id, run_c = await run_one(store_c, dispatcher_c, request_c)
        print(
            f"  outcome={outcome_c.state} plan_source={run_c.get('plan_source')!r} "
            f"planner={dispatcher_c.planner!r}"
        )
        if outcome_c.state != "succeeded" or run_c.get("plan_source") != "rules":
            problems.append("C: explicit request without an injected planner did not fall back to rules")

        print("== D. empty reason is rejected at construction ==")
        try:
            PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason="   ")
            problems.append("D: empty reason was accepted")
        except ValueError as exc:
            print(f"  rejected as expected: {exc}")

        print("== E. invalid model proposal -> plan validation failure, no snapshot ==")
        store_e = FileStore(Path(tmp) / "datae", Path(tmp) / "wse")
        build_environment(store_e)

        def bad_propose(_context: DispatchContext) -> dict[str, object]:
            return {"subtasks": [{"key": "BAD KEY", "objective": "x", "capability": "implementation", "acceptance": ["a"], "write": True}]}

        bad_planner = ModelPlanner(bad_propose)
        dispatcher_e = GraphDispatcher(
            store_e, FakeGraphExecutor(), catalog=CATALOG, planner=bad_planner
        )
        request_e = PlanningRequest(trigger=PlanningTrigger.USER_REQUEST, reason="bad plan")
        _te, run_e_id, controller_e, context_e = make_dispatch_setup(
            store_e, planning_request=request_e
        )
        outcome_e = await dispatcher_e.dispatch(context_e, controller_e, no_sink)
        run_e = store_e.read("run", run_e_id).entity
        print(
            f"  outcome={outcome_e.state} code={outcome_e.failure_code} "
            f"plan_present={'plan' in run_e}"
        )
        if outcome_e.state != "failed" or "plan" in run_e:
            problems.append("E: invalid on-demand proposal did not fail cleanly without a snapshot")

        print("== F. PlanningRequest.max_calls is recorded but not enforced ==")
        request_f = PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason="budget check", max_calls=5
        )
        store_f = FileStore(Path(tmp) / "dataf", Path(tmp) / "wsf")
        build_environment(store_f)
        planner_f = make_model_planner()
        dispatcher_f = GraphDispatcher(
            store_f, FakeGraphExecutor(), catalog=CATALOG, planner=planner_f
        )
        outcome_f, _id_f, run_f = await run_one(store_f, dispatcher_f, request_f)
        note = " ".join(run_f.get("plan", {}).get("notes", []))
        print(
            f"  outcome={outcome_f.state} max_calls_in_note={'max_calls=5' in note} "
            f"model_planner_own_cap={planner_f._max_calls}"  # type: ignore[attr-defined]
        )

        print("== G. invalid trigger type is not validated and crashes the dispatcher ==")
        store_g = FileStore(Path(tmp) / "datag", Path(tmp) / "wsg")
        build_environment(store_g)
        planner_g = make_model_planner()
        dispatcher_g = GraphDispatcher(
            store_g, FakeGraphExecutor(), catalog=CATALOG, planner=planner_g
        )
        request_g = PlanningRequest(trigger="user_request", reason="plain str")  # type: ignore[arg-type]
        _tg, _rg, controller_g, context_g = make_dispatch_setup(
            store_g, planning_request=request_g
        )
        try:
            await dispatcher_g.dispatch(context_g, controller_g, no_sink)
            print("  dispatch returned normally (unexpected)")
        except Exception as exc:  # noqa: BLE001
            print(f"  dispatch raised {type(exc).__name__}: {exc}")
            problems.append(
                "G: a plain-string trigger is accepted at construction and then raises an "
                f"unhandled {type(exc).__name__} out of dispatch (the request contract must "
                "validate the trigger type/requester, not crash the run)."
            )

    print("\n== VERDICT ==")
    if problems:
        for item in problems:
            print(f"  CONTRADICTION: {item}")
        return 1
    print("  all checked behaviours match the documented contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
