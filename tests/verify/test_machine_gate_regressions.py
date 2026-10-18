"""LG244: recorded real checks bind the candidate before review and acceptance."""
from __future__ import annotations

import pytest

from lightgravity.contracts import AppError
from lightgravity.coordinator.state import StateWriter
from lightgravity.verify import VerificationService
from lightgravity.verify.checks import CheckOutcome, CheckRegistration, default_check_registry
from verify_helpers import make_verifying_task, write_workspace_file


def test_get_never_runs_or_fabricates_check_results(store):
    task_id, run_id, _, _ = make_verifying_task(store)
    calls = []
    registry = default_check_registry()
    registry.register(CheckRegistration("evidence-present", lambda context: (
        calls.append(context.run_id) or CheckOutcome(True)
    )))
    service = VerificationService(store, registry=registry)
    assert service.acceptance(task_id).checks["status"] == "not_run"
    assert not service.acceptance(task_id).checks["satisfied"]
    assert calls == []
    assert service.check_before_review(task_id)
    recorded = store.read("run", run_id).entity["machine_checks"]
    assert recorded["binding"]["requirements_revision"] == 1
    assert service.acceptance(task_id).checks["status"] == "passed"
    assert calls == [run_id]


@pytest.mark.parametrize("mode", ["failed", "error", "unconfigured", "skipped"])
def test_nonpassing_check_cannot_open_acceptance(store, mode):
    task_id, run_id, _, _ = make_verifying_task(store, checks=("gate",))
    registry = default_check_registry()
    if mode != "unconfigured":
        def handler(context):
            if mode == "error":
                raise RuntimeError("local fixture failure")
            return CheckOutcome(mode == "skipped", skipped=mode == "skipped")
        registry.register(CheckRegistration("gate", handler))
    service = VerificationService(store, registry=registry)
    assert not service.check_before_review(task_id)
    assert not service.verify_and_prepare(task_id).confirmed
    assert store.read("run", run_id).entity["machine_checks"]["results"][0]["status"] == mode
    assert store.read("task", task_id).entity["phase"] == "verifying"


@pytest.mark.parametrize("mutation", ["missing_record", "requirements", "plan", "evidence", "bytes", "unknown_status", "missing_result"])
def test_direct_accept_rejects_missing_or_stale_checks(store, mutation):
    task_id, run_id, _, subtasks = make_verifying_task(
        store, checks=("evidence-present", "artifacts-in-workspace"), evidence=("out/result.txt",)
    )
    artifact = write_workspace_file(store, "ws/out/result.txt")
    service = VerificationService(store)
    assert service.check_before_review(task_id)
    assert service.verify_and_prepare(task_id).confirmed
    writer = StateWriter(store, actor="regression")
    if mutation == "missing_record":
        writer.write_run(run_id, {"machine_checks": None})
    elif mutation == "requirements":
        writer.write_task(task_id, {"requirements_revision": 2})
    elif mutation == "plan":
        writer.write_run(run_id, {"plan_hash": "b" * 64})
    elif mutation == "evidence":
        writer.write_subtask(subtasks[0], {"acceptance": {"status": "passed", "criteria": [], "evidence_refs": []}})
    elif mutation == "bytes":
        artifact.write_text("changed candidate")
    else:
        report = store.read("run", run_id).entity["machine_checks"]
        if mutation == "missing_result":
            report["results"] = []
        else:
            report["results"][0]["status"] = "unknown"
        writer.write_run(run_id, {"machine_checks": report})
    assert not service.acceptance(task_id).checks["satisfied"]
    with pytest.raises(AppError):
        service.decide(task_id, "accept", request_id="bypass")
    assert store.read("task", task_id).entity["phase"] == "awaiting_acceptance"


def test_legacy_no_check_task_is_not_reported_as_passed_but_keeps_compatibility(store):
    task_id, _, _, _ = make_verifying_task(store, checks=None)
    service = VerificationService(store)
    assert service.verify_and_prepare(task_id).confirmed
    report = service.acceptance(task_id).checks
    assert report["status"] == "not_configured"
    assert not report["satisfied"]
    assert service.decide(task_id, "accept", request_id="legacy").confirmed


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_machine_checks_run_and_persist_before_reviewer(store, asynchronous):
    from types import SimpleNamespace
    from lightgravity.coordinator import Coordinator
    task_id, run_id, _, _ = make_verifying_task(store)
    service = VerificationService(store)
    calls = []

    class Reviewer:
        def process(self, task_id, **kwargs):
            assert store.read("run", run_id).entity["machine_checks"]["satisfied"]
            calls.append(task_id)
            return SimpleNamespace(state="unavailable")

    coordinator = Coordinator(store, verification=service, rework=Reviewer())
    if asynchronous:
        await coordinator._auto_verify_async(task_id, run_id)
    else:
        coordinator._auto_verify(task_id, run_id)
    assert calls == [task_id]
    writer = StateWriter(store, actor="regression")
    writer.write_task(task_id, {"checks": ["unregistered"]})
    if asynchronous:
        await coordinator._auto_verify_async(task_id, run_id)
    else:
        coordinator._auto_verify(task_id, run_id)
    assert calls == [task_id]
    assert not store.read("run", run_id).entity["machine_checks"]["satisfied"]


@pytest.mark.parametrize("authorization", [[], ["evidence-present"]])
def test_default_policy_missing_authorization_does_not_execute_or_accept(store, authorization):
    task_id, run_id, _, _ = make_verifying_task(store)
    writer = StateWriter(store, actor="regression")
    writer.write_task(task_id, {"machine_check_policy": "default_delivery_v1", "checks": authorization})
    service = VerificationService(store)
    assert not service.check_before_review(task_id)
    report = store.read("run", run_id).entity["machine_checks"]
    assert [item["check_id"] for item in report["results"]] == authorization
    assert not service.verify_and_prepare(task_id).confirmed
    # A manually forged awaiting phase still cannot bypass the direct decision gate.
    writer.transition_task(task_id, "awaiting_acceptance", extra={"acceptance": {
        "status": "awaiting", "requirements_revision": 1, "deliverable_revision": 0,
        "candidate_ref": run_id, "candidate_plan_hash": "a" * 64,
        "evidence_refs": [], "decided_at": None, "decision_ref": None,
    }})
    with pytest.raises(AppError):
        service.decide(task_id, "accept", request_id="missing-auth")
