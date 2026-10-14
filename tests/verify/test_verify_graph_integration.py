"""Integration test: an LG-008 graph candidate flows into LG-009 acceptance.

Reuses the coordinator's in-process graph helpers (unit evidence only; the real
SDK/DeepSeek end-to-end path is LG-010).  Exercises the real frontmatter handoff
produced by ``GraphDispatcher`` instead of a hand-built Run.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coordinator"))

from graph_helpers import (  # noqa: E402  (path set above)
    FakeGraphExecutor,
    build_environment,
    make_dispatch_setup,
)

from lightgravity.contracts import TaskPhase  # noqa: E402
from lightgravity.coordinator import GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify import VerificationService  # noqa: E402

TWO_AGENT = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


def no_sink(_event: dict[str, object]) -> None:
    return None


async def test_graph_candidate_reaches_acceptance_and_completes(store: FileStore) -> None:
    build_environment(store)
    dispatcher = GraphDispatcher(store, FakeGraphExecutor(), catalog=TWO_AGENT)
    task_id, run_id, controller, context = make_dispatch_setup(
        store, acceptance=("the feature works",)
    )
    writer = StateWriter(store, actor="test")
    # The optional Task ``checks`` list is the machine-check authorization.
    writer.write_task(task_id, {"checks": ["evidence-present"]})

    outcome = await dispatcher.dispatch(context, controller, no_sink)
    assert outcome.state == "succeeded"

    # The coordinator writes these on a successful dispatch (docs/08 §6.2/§6.3).
    writer.transition_run(run_id, "verifying", task_ref=task_id)
    writer.transition_task(task_id, TaskPhase.VERIFYING, run_ref=run_id)

    service = VerificationService(store)
    prepared = service.verify_and_prepare(task_id, request_id="integration-prepare")
    assert prepared.confirmed is True
    task = store.read("task", task_id)
    assert task.entity["phase"] == "awaiting_acceptance"
    assert task.entity["deliverable_revision"] == 1
    assert task.entity["acceptance"]["candidate_ref"] == run_id
    assert task.entity["acceptance"]["evidence_refs"]

    accepted = service.decide(task_id, "accept", request_id="integration-accept")
    assert accepted.confirmed is True
    assert store.read("task", task_id).entity["status"] == "done"
