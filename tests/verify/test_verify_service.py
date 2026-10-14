"""Verification/acceptance service tests (LG-009).

Covers candidate preparation, the stop gate, version-bound idempotent
accept/reject, stale-decision invalidation, optimistic-concurrency conflicts
and preservation of unknown frontmatter/body.  All writes are real Store writes
under ``tmp_path``.
"""

from __future__ import annotations

import pytest

from lightgravity.contracts import AppError, ErrorCode, EventType
from lightgravity.store import FileStore
from lightgravity.verify import VerificationService

from verify_helpers import (
    make_verifying_task,
    set_requirements_revision,
)


def prepare(store: FileStore, task_id: str, request_id: str = "prep") -> None:
    result = VerificationService(store).verify_and_prepare(task_id, request_id=request_id)
    assert result.confirmed is True


def test_verify_prepares_candidate_and_binds_versions(store: FileStore) -> None:
    task_id, run_id, _members, _subtasks = make_verifying_task(
        store, evidence=("out/result.txt",)
    )
    service = VerificationService(store)
    result = service.verify_and_prepare(task_id, request_id="prep-1")

    assert result.confirmed is True
    assert result.phase == "awaiting_acceptance"
    task = store.read("task", task_id)
    assert task.entity["phase"] == "awaiting_acceptance"
    assert task.entity["deliverable_revision"] == 1
    acceptance = task.entity["acceptance"]
    assert acceptance["status"] == "awaiting"
    assert acceptance["requirements_revision"] == 1
    assert acceptance["deliverable_revision"] == 1
    assert acceptance["candidate_ref"] == run_id
    assert acceptance["candidate_plan_hash"] == "a" * 64
    assert store.read("run", run_id).entity["state"] == "awaiting_acceptance"
    events = [record.type for record in store.read_events(task_id)]
    assert EventType.DECISION_REQUESTED.value in events


def test_verify_is_idempotent_per_request_id(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)
    service = VerificationService(store)
    first = service.verify_and_prepare(task_id, request_id="same")
    revision = store.read("task", task_id).revision
    second = service.verify_and_prepare(task_id, request_id="same")

    assert second.to_dict() == first.to_dict()
    assert store.read("task", task_id).revision == revision


def test_verify_blocks_on_failing_machine_check(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(store, evidence=())
    result = VerificationService(store).verify_and_prepare(task_id, request_id="fail")

    assert result.confirmed is False
    assert result.phase == "verifying"
    assert any("evidence-present" in message for message in result.messages)
    assert store.read("task", task_id).entity["phase"] == "verifying"


def test_unregistered_authorized_check_is_reported_honestly(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(
        store, checks=("not-registered",)
    )
    result = VerificationService(store).verify_and_prepare(task_id, request_id="unknown")

    assert result.confirmed is True
    assert result.checks is not None
    assert result.checks["results"][0]["status"] == "unconfigured"


def test_verify_refuses_when_resources_not_stopped(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(
        store, run_state="executing"
    )
    result = VerificationService(store).verify_and_prepare(task_id, request_id="busy")

    assert result.confirmed is False
    assert store.read("task", task_id).entity["phase"] == "verifying"


def test_accept_binds_versions_and_replays_idempotently(store: FileStore) -> None:
    task_id, run_id, _members, _subtasks = make_verifying_task(store)
    service = VerificationService(store)
    prepare(store, task_id)

    accepted = service.decide(task_id, "accept", request_id="decision-1")
    assert accepted.confirmed is True
    assert accepted.phase == "completed"
    task = store.read("task", task_id)
    assert task.entity["status"] == "done"
    assert task.entity["acceptance"]["status"] == "accepted"
    assert task.entity["acceptance"]["requirements_revision"] == 1
    assert task.entity["acceptance"]["deliverable_revision"] == 1
    assert task.entity["acceptance"]["decision_ref"] == "decision-1"
    assert task.entity["active_run"] is None
    assert store.read("run", run_id).entity["state"] == "completed"
    events = [record.type for record in store.read_events(task_id)]
    assert EventType.DECISION_RESOLVED.value in events

    revision = task.revision
    same_request = service.decide(task_id, "accept", request_id="decision-1")
    assert same_request.confirmed is True
    assert store.read("task", task_id).revision == revision

    replay = service.decide(task_id, "accept", request_id="decision-2")
    assert replay.confirmed is True
    assert store.read("task", task_id).revision == revision


def test_reject_keeps_task_id_and_requests_repair(store: FileStore) -> None:
    task_id, run_id, _members, _subtasks = make_verifying_task(store)
    service = VerificationService(store)
    prepare(store, task_id)

    rejected = service.decide(task_id, "reject", request_id="reject-1", note="missing test")
    assert rejected.confirmed is True
    assert rejected.phase == "repairing"
    task = store.read("task", task_id)
    assert task.entity_id == task_id  # Task ID preserved
    assert task.entity["phase"] == "repairing"
    assert task.entity["status"] == "in-progress"
    assert task.entity["acceptance"]["status"] == "rejected"
    assert task.entity["acceptance"]["note"] == "missing test"
    assert task.entity["active_run"] is None
    assert store.read("run", run_id).entity["state"] == "failed"

    with pytest.raises(AppError) as excinfo:
        service.decide(task_id, "accept", request_id="after-reject")
    assert excinfo.value.code == ErrorCode.ILLEGAL_TRANSITION


def test_stale_requirements_invalidate_decision(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)
    service = VerificationService(store)
    prepare(store, task_id)

    set_requirements_revision(store, task_id, 2)
    with pytest.raises(AppError) as excinfo:
        service.decide(task_id, "accept", request_id="stale")
    assert excinfo.value.code == ErrorCode.ACCEPTANCE_STALE
    assert store.read("task", task_id).entity["acceptance"]["status"] == "awaiting"


def test_expected_versions_and_candidate_are_checked(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)
    service = VerificationService(store)
    prepare(store, task_id)

    with pytest.raises(AppError) as excinfo:
        service.decide(
            task_id, "accept", request_id="wrong-delivery", expected_deliverable_revision=99
        )
    assert excinfo.value.code == ErrorCode.ACCEPTANCE_STALE

    with pytest.raises(AppError) as excinfo:
        service.decide(
            task_id,
            "accept",
            request_id="wrong-candidate",
            target_run_id="run_somewhere_else",
        )
    assert excinfo.value.code == ErrorCode.ACCEPTANCE_STALE


def test_decision_revision_conflict(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(store)
    service = VerificationService(store)
    prepare(store, task_id)
    current = store.read("task", task_id).revision

    with pytest.raises(AppError) as excinfo:
        service.decide(task_id, "accept", request_id="conflict", expected_revision=current - 1)
    assert excinfo.value.code == ErrorCode.REVISION_CONFLICT
    assert store.read("task", task_id).entity["phase"] == "awaiting_acceptance"


def test_unknown_fields_and_body_are_preserved(store: FileStore) -> None:
    task_id, _run_id, _members, _subtasks = make_verifying_task(
        store, extra={"custom_field": "keep-me"}
    )
    service = VerificationService(store)
    prepare(store, task_id)
    service.decide(task_id, "accept", request_id="preserve")

    task = store.read("task", task_id)
    assert task.entity["custom_field"] == "keep-me"
    assert "body text preserved" in task.body


def test_request_repair_keeps_task_and_marks_run_terminal(store: FileStore) -> None:
    task_id, run_id, _members, _subtasks = make_verifying_task(store)
    result = VerificationService(store).request_repair(
        task_id, request_id="repair-1", note="checks failed"
    )

    assert result.confirmed is True
    assert result.phase == "repairing"
    task = store.read("task", task_id)
    assert task.entity["phase"] == "repairing"
    assert task.entity["active_run"] is None
    assert store.read("run", run_id).entity["state"] == "failed"
