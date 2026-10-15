"""QA-r2 residual-boundary probe: concurrent dispatch of the SAME Run.

The product contract permits at most one non-terminating Run per Task, so
concurrent same-``run_id`` dispatch is not a supported operation.  This probe
records what actually happens to the per-Run budget counter in that case so the
limitation can be stated honestly (it is *not* a supported-path defect).
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


async def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        store = FileStore(root / "data", root / "ws")
        build_environment(store)
        calls: list[str] = []

        async def propose(context: DispatchContext) -> dict[str, object]:
            calls.append(context.run_id)
            await asyncio.sleep(0.05)  # widen the window deliberately
            return {
                "subtasks": [
                    {
                        "key": "deliver",
                        "objective": "x",
                        "capability": "implementation",
                        "acceptance": ["a"],
                        "write": True,
                    }
                ]
            }

        planner = ModelPlanner(propose)
        dispatcher = GraphDispatcher(
            store, FakeGraphExecutor(), catalog=CATALOG, planner=planner
        )
        request = PlanningRequest(
            trigger=PlanningTrigger.USER_REQUEST, reason="same-run race", max_calls=1
        )
        _t, _run, controller, context = make_dispatch_setup(store, planning_request=request)

        results = await asyncio.gather(
            dispatcher.dispatch(context, controller, no_sink),
            dispatcher.dispatch(context, controller, no_sink),
            return_exceptions=True,
        )
        print("concurrent same-run dispatch results:")
        for index, result in enumerate(results):
            if isinstance(result, BaseException):
                print(f"  #{index}: raised {type(result).__name__}: {result}")
            else:
                print(f"  #{index}: state={result.state} summary={result.summary!r}")
        print(f"model_propose_invocations={len(calls)} (max_calls=1)")
        if len(calls) > 1:
            print(
                "RESIDUAL: concurrent dispatch of the SAME run_id is not serialized; "
                "the per-Run budget counter check is not atomic across awaits, so a "
                "same-run concurrent caller can exceed max_calls. This is an "
                "unsupported operation (one non-terminating Run per Task)."
            )
            return 2
        print("no same-run race observed")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
