"""Dependency graph, Subtask lease and artifact handoff (LG-008)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lightgravity.coordinator.scheduler import (
    ArtifactHandoff,
    DependencyGraph,
    GraphError,
    GraphNode,
    SubtaskClaimer,
    encode_handoffs,
    parse_handoff_ref,
)
from lightgravity.coordinator.state import StateWriter
from lightgravity.store import FileStore, new_id

from graph_helpers import make_dispatch_setup


def test_dependency_graph_order_and_readiness() -> None:
    graph = DependencyGraph(
        (
            GraphNode(key="a"),
            GraphNode(key="b", depends_on=("a",)),
            GraphNode(key="c", depends_on=("b",)),
        )
    )
    assert graph.topological_order() == ("a", "b", "c")
    assert graph.ready(set(), set()) == ("a",)
    assert graph.ready({"a"}, set()) == ("b",)
    assert graph.ready({"a", "b"}, set()) == ("c",)
    assert graph.unresolved({"a"}, set()) == ("b", "c")
    assert graph.blocked_by("c", {"b"}) == ("b",)


def test_dependency_graph_rejects_duplicates_unknown_and_cycles() -> None:
    with pytest.raises(GraphError):
        DependencyGraph((GraphNode(key="a"), GraphNode(key="a")))
    with pytest.raises(GraphError):
        DependencyGraph((GraphNode(key="a", depends_on=("missing",)),))
    with pytest.raises(GraphError):
        DependencyGraph(
            (GraphNode(key="a", depends_on=("b",)), GraphNode(key="b", depends_on=("a",)))
        )


def _make_subtask(store: FileStore) -> tuple[str, str, str]:
    task_id, run_id, controller, _context = make_dispatch_setup(store)
    subtask_id = new_id("subtask")
    controller.create_subtask(
        subtask_id,
        {
            "run_ref": run_id,
            "state": "pending",
            "depends_on": [],
            "assignee_member_ref": None,
            "upstream_artifact_refs": [],
            "acceptance": {"status": "pending", "criteria": ["ok"], "evidence_refs": []},
        },
        body="# Subtask\n",
    )
    return task_id, run_id, subtask_id


def test_subtask_claim_is_idempotent_and_lease_guarded(store: FileStore) -> None:
    task_id, run_id, subtask_id = _make_subtask(store)
    writer = StateWriter(store, actor="test")
    claimer = SubtaskClaimer(writer, task_id=task_id, run_id=run_id)

    first = claimer.claim(subtask_id, "owner-a", lease_seconds=30)
    assert first.acquired is True and first.state == "acquired"
    persisted = store.read("subtask", subtask_id).entity
    assert persisted["state"] == "running"
    assert persisted["owner"] == "owner-a"
    assert persisted["lease_expires_at"]

    again = claimer.claim(subtask_id, "owner-a", lease_seconds=30)
    assert again.acquired is True and again.state == "already_owned"

    other = claimer.claim(subtask_id, "owner-b", lease_seconds=30)
    assert other.acquired is False and other.state == "held_by_other"
    assert other.owner == "owner-a"

    assert claimer.renew(subtask_id, "owner-b", lease_seconds=30) is False
    assert claimer.renew(subtask_id, "owner-a", lease_seconds=30) is True
    claimer.release(subtask_id, "owner-a")
    assert store.read("subtask", subtask_id).entity["owner"] is None

    claimed_after_release = claimer.claim(subtask_id, "owner-b", lease_seconds=30)
    assert claimed_after_release.acquired is True


def test_subtask_claim_expires_and_terminal_is_refused(store: FileStore) -> None:
    task_id, run_id, subtask_id = _make_subtask(store)
    writer = StateWriter(store, actor="test")
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    claimer = SubtaskClaimer(writer, task_id=task_id, run_id=run_id, clock=lambda: now[0])

    assert claimer.claim(subtask_id, "owner-a", lease_seconds=10).acquired is True
    assert claimer.claim(subtask_id, "owner-b", lease_seconds=10).state == "held_by_other"
    now[0] = now[0] + timedelta(seconds=11)
    reclaimed = claimer.claim(subtask_id, "owner-b", lease_seconds=10)
    assert reclaimed.acquired is True
    assert reclaimed.state == "expired_reclaimed"

    writer.write_subtask(subtask_id, {"state": "passed"})
    terminal = claimer.claim(subtask_id, "owner-c", lease_seconds=10)
    assert terminal.acquired is False
    assert terminal.state == "terminal"


def test_artifact_handoff_encodes_producer_hash() -> None:
    handoff = ArtifactHandoff(
        subtask_ref="subtask_01J0000000000000000000001",
        revision=3,
        content_hash="deadbeef",
        artifacts=("artifact_a", "artifact_b"),
    )
    refs = handoff.encoded_refs()
    assert refs == (
        "subtask_01J0000000000000000000001@deadbeef:artifact_a",
        "subtask_01J0000000000000000000001@deadbeef:artifact_b",
    )
    for ref in refs:
        assert parse_handoff_ref(ref) == (
            "subtask_01J0000000000000000000001",
            "deadbeef",
            ref.split(":", 1)[1],
        )
    second = ArtifactHandoff("subtask_01J0000000000000000000002", 1, "cafe", ("artifact_c",))
    combined = encode_handoffs([handoff, second])
    assert combined[:2] == refs
    assert combined[2] == "subtask_01J0000000000000000000002@cafe:artifact_c"
