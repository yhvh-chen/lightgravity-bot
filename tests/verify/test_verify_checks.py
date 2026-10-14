"""Unit tests for the machine-check registry (LG-009).

Only program-registered + Task-authorized checks run; unconfigured/erroring
checks are reported truthfully and never treated as passed.  The default
``evidence-present`` check refuses a worker summary as evidence.
"""

from __future__ import annotations

from pathlib import Path

from lightgravity.store import FileStore
from lightgravity.verify import (
    CheckContext,
    CheckOutcome,
    CheckRegistration,
    CheckRegistry,
    default_check_registry,
    run_checks,
)

from verify_helpers import make_candidate, write_workspace_file


def make_context(store: FileStore, candidate) -> CheckContext:
    return CheckContext(
        task_id=candidate.task_id,
        run_id=candidate.run_id,
        candidate=candidate,
        store=store,
        workspace_path=candidate.workspace_path,
    )


def test_unregistered_authorized_check_is_unconfigured_and_not_run(store: FileStore) -> None:
    registry = CheckRegistry()
    report = run_checks(registry, ["missing-check"], make_context(store, make_candidate()))
    assert [result.status for result in report.results] == ["unconfigured"]
    assert report.satisfied  # unconfigured does not block, but is never "passed"


def test_unauthorized_registered_check_does_not_run(store: FileStore) -> None:
    calls: list[str] = []

    def handler(_context: CheckContext) -> CheckOutcome:
        calls.append("ran")
        return CheckOutcome(passed=True)

    registry = CheckRegistry()
    registry.register(CheckRegistration("some-check", handler))
    report = run_checks(registry, [], make_context(store, make_candidate()))
    assert calls == []
    assert report.results == ()
    assert report.registered == ("some-check",)


def test_handler_crash_is_error_not_pass(store: FileStore) -> None:
    def boom(_context: CheckContext) -> CheckOutcome:
        raise RuntimeError("check exploded")

    registry = CheckRegistry()
    registry.register(CheckRegistration("boom", boom))
    report = run_checks(registry, ["boom"], make_context(store, make_candidate()))
    assert [result.status for result in report.results] == ["error"]
    assert report.satisfied is False


def test_evidence_present_requires_real_evidence(store: FileStore) -> None:
    registry = default_check_registry()
    without = run_checks(
        registry, ["evidence-present"], make_context(store, make_candidate())
    )
    assert without.satisfied is False
    assert without.failed_ids == ("evidence-present",)

    with_evidence = run_checks(
        registry,
        ["evidence-present"],
        make_context(store, make_candidate(artifact_refs=("out/result.txt",))),
    )
    assert with_evidence.satisfied is True


def test_artifacts_in_workspace_checks_real_files(store: FileStore, tmp_path: Path) -> None:
    registry = default_check_registry()
    write_workspace_file(store, "ws/out/result.txt", "done\n")
    workspace_path = str(store.resolve_path("ws", write=False))

    present = run_checks(
        registry,
        ["artifacts-in-workspace"],
        make_context(
            store,
            make_candidate(
                artifact_refs=("out/result.txt",),
                workspace_path=workspace_path,
            ),
        ),
    )
    assert present.satisfied is True

    missing = run_checks(
        registry,
        ["artifacts-in-workspace"],
        make_context(
            store,
            make_candidate(
                artifact_refs=("out/missing.txt",),
                workspace_path=workspace_path,
            ),
        ),
    )
    assert missing.satisfied is False

    escaping = run_checks(
        registry,
        ["artifacts-in-workspace"],
        make_context(
            store,
            make_candidate(
                artifact_refs=("../escape.txt",),
                workspace_path=workspace_path,
            ),
        ),
    )
    assert escaping.satisfied is False
