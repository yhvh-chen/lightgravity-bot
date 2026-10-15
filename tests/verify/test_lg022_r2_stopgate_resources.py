"""LG-022 R2: the stop gate must confirm real session/reviewer resources.

The R1 independent re-verification found a deadlock: a successful real Run
records non-empty ``session_refs`` but the success path never wrote
``cleanup=done``, so ``StoreResourceStopper`` was always ``unconfirmed`` and the
Task could not reach ``awaiting_acceptance``.  These tests pin the fix:

* a real adapter stop fact (sessions provably closed + proxy stopped) releases
  the gate even while ``cleanup`` is still ``pending`` -- without deleting the
  refs or fabricating ``cleanup=done``;
* an unknown / still-active session keeps the gate unconfirmed and preserves the
  refs;
* the independent reviewer resource must also show a confirmed stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lightgravity.store import FileStore
from lightgravity.verify import StopReport, StoreResourceStopper

from verify_helpers import create_member, create_run, create_task


@dataclass
class _FakeConfirmer:
    """A stand-in for the adapter's real ``confirm_stopped`` port."""

    confirmed: bool
    problems: tuple[str, ...] = ()
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def confirm_stopped(
        self, run_id: str, session_refs: tuple[str, ...]
    ) -> Any:
        self.calls.append((run_id, session_refs))
        return _Confirmation(self.confirmed, self.problems)


@dataclass(frozen=True)
class _Confirmation:
    confirmed: bool
    problems: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"confirmed": self.confirmed, "problems": list(self.problems)}


def test_real_session_stop_releases_gate_without_cleanup_done(store: FileStore) -> None:
    task_id = create_task(store, queue_state="claimed", queue_owner="coordinator:1")
    run_id = create_run(store, task_id, session_refs=("sess_a", "sess_b"), cleanup="pending")
    member_id = create_member(store, run_id, state="ready")
    store.write(
        "run",
        run_id,
        {"team_refs": [member_id]},
        expected_revision=store.read("run", run_id).revision,
        actor="test",
    )

    confirmer = _FakeConfirmer(confirmed=True)
    report = StoreResourceStopper(store, session_confirmer=confirmer).stop(task_id, run_id)

    assert report.confirmed is True
    assert report.sessions_stopped is True
    assert report.session_confirmation is not None
    assert confirmer.calls == [(run_id, ("sess_a", "sess_b"))]
    # The refs are preserved (never deleted to sneak past the gate).
    assert store.read("run", run_id).entity["session_refs"] == ["sess_a", "sess_b"]
    assert store.read("run", run_id).entity["cleanup"] == {"status": "pending"}
    assert store.read("member", member_id).entity["state"] == "released"


def test_unknown_session_stop_keeps_gate_unconfirmed(store: FileStore) -> None:
    task_id = create_task(store, queue_state="claimed", queue_owner="coordinator:1")
    run_id = create_run(store, task_id, session_refs=("sess_a",), cleanup="pending")

    confirmer = _FakeConfirmer(confirmed=False, problems=("session still active",))
    report = StoreResourceStopper(store, session_confirmer=confirmer).stop(task_id, run_id)

    assert report.confirmed is False
    assert report.sessions_stopped is False
    assert any("not confirmed closed" in problem for problem in report.problems)
    assert store.read("run", run_id).entity["session_refs"] == ["sess_a"]


def test_cleanup_failure_keeps_gate_unconfirmed(store: FileStore) -> None:
    task_id = create_task(store)
    run_id = create_run(store, task_id, session_refs=("sess_a",), cleanup="failed")
    # No confirmer: a failed close must never be read as stopped.
    report = StoreResourceStopper(store).stop(task_id, run_id)

    assert report.confirmed is False
    assert report.sessions_stopped is False
    assert store.read("run", run_id).entity["session_refs"] == ["sess_a"]


def test_reviewer_resource_must_also_be_confirmed(store: FileStore) -> None:
    task_id = create_task(store)
    run_id = create_run(store, task_id, session_refs=(), cleanup="done")
    # A pending reviewer resource (its real teardown not confirmed) holds the gate.
    store.write(
        "run",
        run_id,
        {"reviewer_cleanup": {"status": "pending", "confirmed": False}},
        expected_revision=store.read("run", run_id).revision,
        actor="test",
    )
    report = StoreResourceStopper(store).stop(task_id, run_id)
    assert report.confirmed is False
    assert any("reviewer resource not confirmed stopped" in p for p in report.problems)

    # A confirmed reviewer stop releases it.
    store.write(
        "run",
        run_id,
        {"reviewer_cleanup": {"status": "done", "confirmed": True}},
        expected_revision=store.read("run", run_id).revision,
        actor="test",
    )
    report = StoreResourceStopper(store).stop(task_id, run_id)
    assert report.confirmed is True
    assert isinstance(report, StopReport)
