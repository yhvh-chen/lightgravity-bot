"""LG-243 reviewer/review execution history (deterministic doubles, no model calls).

The reviewer turn is injected as a fake, so this is unit evidence.  These tests
prove the actual resolved reviewer connection (not a current Settings default)
and the validated candidate-bound verdict are persisted on the reviewed Run,
while legacy/missing/unknown facts stay unknown.
"""

from __future__ import annotations

import json

from lightgravity.adapter import ConnectionPin
from lightgravity.adapter.credentials import InMemoryCredentialResolver
from lightgravity.coordinator.state import StateWriter
from lightgravity.execution_evidence import (
    build_execution_view,
    merge_execution_evidence,
    worker_connection_snapshot,
)
from lightgravity.store import FileStore
from lightgravity.verify.review import (
    REVIEW_PASSED,
    REVIEW_UNAVAILABLE,
    ModelReviewer,
    ReviewerSupport,
    UnavailableReviewer,
)
from lightgravity.verify.rework import (
    REWORK_OPENED,
    REWORK_UNAVAILABLE,
    ReworkOrchestrator,
)

from verify_helpers import make_verifying_task, write_workspace_file


def _support(*, connection_id: str = "reviewer-conn", name: str = "Reviewer Display") -> ReviewerSupport:
    return ReviewerSupport(
        model="reviewer-model",
        base_url="https://api.deepseek.com/v1",
        credential_ref="reviewer-key",
        backend="openai-compat",
        connection_id=connection_id,
        name=name,
        role="reviewer",
    )


def _worker_pin() -> ConnectionPin:
    return ConnectionPin(
        connection_id="worker-conn",
        role="worker",
        revision=3,
        content_hash="worker-hash",
        backend="openai-compat",
        model="worker-model",
        base_url="https://api.deepseek.com/v1",
        credential_ref="worker-key",
        credential_version="cred-v1",
        config_hash="worker-config",
    )


def _seed_worker_history(store: FileStore, run_id: str) -> None:
    StateWriter(store, actor="test").write_run(
        run_id,
        {
            "execution_evidence": merge_execution_evidence(
                None, worker=worker_connection_snapshot(_worker_pin(), name="Worker Display")
            )
        },
    )


def _assert_no_admin_or_secret_keys(value: object, path: str = "evidence") -> None:
    forbidden = {
        "credential_ref",
        "credential_value",
        "credential_version",
        "base_url",
        "config_hash",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden, f"{path}.{key} must not be persisted/exposed"
            _assert_no_admin_or_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_admin_or_secret_keys(item, f"{path}[{index}]")


def test_model_review_persists_actual_reviewer_and_candidate_binding(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    _seed_worker_history(store, run_id)

    reviewer = ModelReviewer(
        _support(),
        InMemoryCredentialResolver({"reviewer-key": "sk-test-value"}).resolve,
        turn=lambda _prompt: (
            json.dumps({"outcome": "passed", "reason": "meets criteria", "findings": []}),
            {"prompt_tokens": 120, "completion_tokens": 30},
        ),
    )
    result = ReworkOrchestrator(store, reviewer=reviewer).process(task_id, request_id="r1")
    assert result.state == REWORK_OPENED

    run = store.read("run", run_id).entity
    evidence = run["execution_evidence"]
    _assert_no_admin_or_secret_keys(evidence)

    # Worker history written at planning is preserved, not replaced by the review.
    assert evidence["worker"]["connection_id"] == "worker-conn"
    assert evidence["worker"]["name"] == "Worker Display"
    assert evidence["worker"]["stage"] == "planned"
    assert evidence["worker"]["evidence_kind"] == "frozen_run_connection"

    reviewer_snapshot = evidence["reviewer"]
    assert reviewer_snapshot["connection_id"] == "reviewer-conn"
    assert reviewer_snapshot["name"] == "Reviewer Display"
    assert reviewer_snapshot["provider"] == "openai-compat"
    assert reviewer_snapshot["model"] == "reviewer-model"
    assert reviewer_snapshot["status"] == "recorded"
    assert reviewer_snapshot["stage"] == "review_execution"
    assert reviewer_snapshot["evidence_kind"] == "resolved_reviewer_support"

    review = evidence["review"]
    assert review["outcome"] == "passed"
    assert review["reviewer_kind"] == "model"
    assert review["candidate_ref"] == run_id
    assert review["candidate_binding"] == {
        "run_id": run_id,
        "candidate_ref": run_id,
        "requirements_revision": 1,
        "plan_hash": "a" * 64,
    }
    assert review["model_calls"] == 1
    assert review["usage"] == {"prompt_tokens": 120, "completion_tokens": 30}

    view = build_execution_view(task_id, run)
    assert view["worker"]["connection_id"] == "worker-conn"
    assert view["reviewer"]["connection_id"] == "reviewer-conn"
    assert view["review"]["outcome"] == "passed"
    assert view["connections_distinct"] is True
    assert view["missing"] == []

    # A later reviewer object/default cannot rewrite this Run's persisted history.
    replacement = ModelReviewer(
        _support(connection_id="other-reviewer", name="Other Reviewer"),
        InMemoryCredentialResolver({"reviewer-key": "sk-test-value"}).resolve,
        turn=lambda _prompt: (json.dumps({"outcome": "passed", "findings": []}), {}),
    )
    assert replacement.support.connection_id == "other-reviewer"
    assert store.read("run", run_id).entity["execution_evidence"] == evidence
    assert build_execution_view(task_id, store.read("run", run_id).entity) == view


def test_unavailable_review_is_recorded_honestly_not_as_passed(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    _seed_worker_history(store, run_id)

    result = ReworkOrchestrator(store, reviewer=UnavailableReviewer()).process(
        task_id, request_id="r1"
    )
    assert result.state == REWORK_UNAVAILABLE

    evidence = store.read("run", run_id).entity["execution_evidence"]
    _assert_no_admin_or_secret_keys(evidence)
    assert evidence["reviewer"]["status"] == "unavailable"
    assert evidence["reviewer"]["stage"] == "review_execution"
    assert evidence["reviewer"]["reason"]
    assert evidence["review"]["outcome"] == REVIEW_UNAVAILABLE
    assert evidence["review"]["reviewer_kind"] == "unavailable"

    view = build_execution_view(task_id, store.read("run", run_id).entity)
    assert view["review"]["outcome"] != REVIEW_PASSED
    assert view["reviewer"]["status"] == "unavailable"


def test_unresolvable_model_reviewer_is_recorded_as_configured_but_unavailable(
    store: FileStore,
) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    write_workspace_file(store, "ws/out/result.txt")
    _seed_worker_history(store, run_id)

    reviewer = ModelReviewer(
        _support(),
        InMemoryCredentialResolver({}).resolve,
        turn=lambda _prompt: (json.dumps({"outcome": "passed", "findings": []}), {}),
    )
    result = ReworkOrchestrator(store, reviewer=reviewer).process(task_id, request_id="r1")
    assert result.state == REWORK_UNAVAILABLE

    evidence = store.read("run", run_id).entity["execution_evidence"]
    assert evidence["reviewer"]["connection_id"] == "reviewer-conn"
    assert evidence["reviewer"]["status"] == "unavailable"
    assert evidence["reviewer"]["reason"]
    assert evidence["review"]["outcome"] == REVIEW_UNAVAILABLE
    assert evidence["review"]["model_calls"] == 0


def test_legacy_run_has_truthful_worker_fallback_and_unknown_reviewer(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    StateWriter(store, actor="test").write_run(
        run_id,
        {
            "connection_pin": {
                "connection_id": "legacy-worker",
                "role": "worker",
                "revision": 1,
                "content_hash": "h",
                "backend": "openai-compat",
                "model": "legacy-model",
                "base_url": "https://api.deepseek.com/v1",
                "credential_ref": "legacy-key",
                "credential_version": "v1",
                "config_hash": "c",
            }
        },
    )

    view = build_execution_view(task_id, store.read("run", run_id).entity)
    _assert_no_admin_or_secret_keys(view)
    assert view["worker"]["connection_id"] == "legacy-worker"
    assert view["worker"]["name"] is None
    assert view["worker"]["status"] == "recorded"
    assert view["worker"]["source"] == "run_connection_pin"
    assert view["worker"]["stage"] == "planned"
    assert view["worker"]["evidence_kind"] == "frozen_run_connection"
    assert view["reviewer"]["status"] == "unknown"
    assert view["reviewer"]["source"] == "missing"
    assert view["review"] is None
    assert "reviewer_history" in view["missing"]
    assert "review" in view["missing"]
    assert view["connections_distinct"] is None


def test_projection_strips_unknown_or_tampered_evidence_keys(store: FileStore) -> None:
    task_id, run_id, _, _ = make_verifying_task(store)
    StateWriter(store, actor="test").write_run(
        run_id,
        {
            "execution_evidence": {
                "schema": "lightgravity.execution-evidence/v1",
                "worker": {
                    "connection_id": "w",
                    "name": "W",
                    "provider": "openai-compat",
                    "model": "wm",
                    "status": "recorded",
                    "source": "run_default_pin",
                    "stage": "planned",
                    "evidence_kind": "frozen_run_connection",
                    "credential_ref": "should-not-leak",
                    "base_url": "https://secret.internal/v1",
                },
                "reviewer": {
                    "connection_id": "r",
                    "name": "R",
                    "provider": "openai-compat",
                    "model": "rm",
                    "status": "recorded",
                    "source": "resolved_reviewer_support",
                    "stage": "review_execution",
                    "evidence_kind": "resolved_reviewer_support",
                    "credential_version": "should-not-leak",
                },
                "review": {
                    "outcome": "passed",
                    "reviewer_kind": "model",
                    "candidate_binding": {
                        "run_id": run_id,
                        "candidate_ref": run_id,
                        "requirements_revision": 1,
                        "plan_hash": "p",
                    },
                    "findings": [],
                    "usage": {"prompt_tokens": 1, "secret_header": "should-not-leak"},
                    "model_calls": 1,
                    "reviewed_at": "2026-10-18T00:00:00.000Z",
                    "reason": "",
                },
                "unexpected_admin_blob": {"credential_ref": "should-not-leak"},
            }
        },
    )
    view = build_execution_view(task_id, store.read("run", run_id).entity)
    _assert_no_admin_or_secret_keys(view)
    assert "unexpected_admin_blob" not in view
    assert view["review"]["usage"] == {"prompt_tokens": 1}
