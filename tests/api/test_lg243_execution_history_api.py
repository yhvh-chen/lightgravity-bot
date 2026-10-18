"""LG-243 member-readable execution history API (unit/HTTP evidence).

Seeds real Store entities under the test app, then asserts the new projection is
safe, historical and task-scoped.  It also pins the compatibility rule: existing
public ``run.connection_pin`` fields are unchanged.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI

from lightgravity.adapter import ConnectionPin
from lightgravity.coordinator.state import StateWriter
from lightgravity.execution_evidence import (
    connection_snapshot,
    merge_execution_evidence,
    review_snapshot,
    reviewer_connection_snapshot,
    worker_connection_snapshot,
)
from lightgravity.store import new_id
from lightgravity.verify.candidate import Candidate


def _task(store: Any) -> str:
    task_id = new_id("task")
    store.create(
        "task",
        task_id,
        {
            "title": "LG243 task",
            "objective": "show real execution history",
            "acceptance_criteria": ["it works"],
            "status": "in-progress",
            "phase": "awaiting_acceptance",
            "requirements_revision": 2,
            "project_ref": None,
            "repository_ref": None,
            "workspace_ref": "ws",
            "agent_ref": "developer",
            "depends_on": [],
            "active_run": None,
            "last_run": None,
            "deliverable_revision": 1,
            "queue": {
                "state": "not_queued",
                "order": None,
                "queued_at": None,
                "owner": None,
                "lease_expires_at": None,
            },
            "acceptance": {"status": "pending"},
            "budget": {"max_workers": 3, "max_parallel": 2},
            "archived": False,
        },
        actor="test",
        request_id=f"req-{task_id}",
        body="# Task\n",
    )
    return task_id


def _run(store: Any, task_id: str, *, evidence: dict[str, Any] | None) -> str:
    run_id = new_id("run")
    store.create(
        "run",
        run_id,
        {
            "task_ref": task_id,
            "attempt": 1,
            "state": "awaiting_acceptance",
            "plan_ref": "PLAN.md",
            "plan": None,
            "plan_hash": "p" * 64,
            "plan_source": "rules",
            "team_refs": [],
            "subtask_refs": [],
            "session_refs": [],
            "cleanup": {"status": "done"},
            "ended_at": None,
            "fail_reason": None,
            # Existing public field content stays exactly as stored.
            "connection_pin": {
                "connection_id": "worker-conn",
                "role": "worker",
                "revision": 4,
                "content_hash": "worker-hash",
                "backend": "openai-compat",
                "model": "worker-model",
                "base_url": "https://api.deepseek.com/v1",
                "credential_ref": "worker-key",
                "credential_version": "cred-v1",
                "config_hash": "worker-config",
            },
            **({"execution_evidence": evidence} if evidence is not None else {}),
        },
        actor="test",
        request_id=f"req-{run_id}",
        body=f"# Run {run_id}\n",
    )
    StateWriter(store, actor="test").write_task(task_id, {"active_run": run_id})
    return run_id


def _evidence(task_id: str, run_id: str) -> dict[str, Any]:
    worker_pin = ConnectionPin(
        connection_id="worker-conn",
        role="worker",
        revision=4,
        content_hash="worker-hash",
        backend="openai-compat",
        model="worker-model",
        base_url="https://api.deepseek.com/v1",
        credential_ref="worker-key",
        credential_version="cred-v1",
        config_hash="worker-config",
    )
    support = type(
        "Support",
        (),
        {
            "connection_id": "reviewer-conn",
            "name": "Reviewer Display",
            "backend": "openai-compat",
            "model": "reviewer-model",
            "role": "reviewer",
        },
    )()
    candidate = Candidate(
        task_id=task_id,
        run_id=run_id,
        run_state="awaiting_acceptance",
        attempt=1,
        plan_hash="p" * 64,
        requirements_revision=2,
        deliverable_revision=1,
        workspace_ref="ws",
        workspace_path=None,
        member_refs=(),
        subtask_refs=(),
        artifact_refs=(),
        diff_ref=None,
        session_refs=(),
        check_records=(),
    )
    report = type(
        "Report",
        (),
        {
            "outcome": "passed",
            "reviewer_kind": "model",
            "candidate_ref": run_id,
            "findings": (),
            "unsubstantiated": (),
            "model_calls": 1,
            "usage": {"prompt_tokens": 10},
            "reason": "",
        },
    )()
    return merge_execution_evidence(
        None,
        worker=worker_connection_snapshot(worker_pin, name="Worker Display"),
        reviewer=reviewer_connection_snapshot(support),
        review=review_snapshot(report, candidate),
    )


def _assert_safe(value: Any) -> None:
    forbidden = {
        "credential_ref",
        "credential_value",
        "credential_version",
        "base_url",
        "config_hash",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden, key
            _assert_safe(item)
    elif isinstance(value, list):
        for item in value:
            _assert_safe(item)


async def test_task_execution_is_safe_task_scoped_and_historical(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    store = app.state.context.store
    task_id = _task(store)
    run_id = _run(store, task_id, evidence=_evidence(task_id, run_id="pending"))
    # Rebuild evidence now that the real run id exists.
    evidence = _evidence(task_id, run_id)
    StateWriter(store, actor="test").write_run(run_id, {"execution_evidence": evidence})

    detail = (await api.get(f"/api/v1/tasks/{task_id}")).json()
    assert detail["execution"]["reviewer"]["connection_id"] == "reviewer-conn"
    # Compatibility: the existing public run pin is unchanged in the response.
    pin = detail["run"]["connection_pin"]
    assert pin["connection_id"] == "worker-conn"
    assert pin["base_url"] == "https://api.deepseek.com/v1"
    assert pin["credential_ref"] == "worker-key"
    assert pin["credential_version"] == "cred-v1"
    assert pin["config_hash"] == "worker-config"

    response = await api.get(f"/api/v1/tasks/{task_id}/execution")
    assert response.status_code == 200
    execution = response.json()
    _assert_safe(execution)
    assert execution["task_id"] == task_id
    assert execution["run"]["id"] == run_id
    assert execution["worker"] == {
        "role": "worker",
        "connection_id": "worker-conn",
        "name": "Worker Display",
        "provider": "openai-compat",
        "model": "worker-model",
        "status": "recorded",
        "source": "run_default_pin",
        "stage": "planned",
        "evidence_kind": "frozen_run_connection",
        "captured_at": execution["worker"]["captured_at"],
        "reason": None,
    }
    assert execution["reviewer"]["connection_id"] == "reviewer-conn"
    assert execution["reviewer"]["stage"] == "review_execution"
    assert execution["review"]["outcome"] == "passed"
    assert execution["review"]["candidate_binding"] == {
        "run_id": run_id,
        "candidate_ref": run_id,
        "requirements_revision": 2,
        "plan_hash": "p" * 64,
    }
    assert execution["connections_distinct"] is True

    # Changing the current reviewer default after the Run must not rewrite history.
    connections = app.state.context.connections
    connections.create_connection(
        "reviewer-b",
        title="Reviewer B",
        model="other-reviewer-model",
        base_url="https://api.deepseek.com/v1",
        credential_ref="other-key",
        actor="test",
        request_id="req-reviewer-b",
    )
    current = connections.get_settings()
    connections.update_settings(
        expected_revision=current["revision"],
        actor="test",
        default_reviewer_connection_ref="reviewer-b",
    )
    after = (await api.get(f"/api/v1/tasks/{task_id}/execution")).json()
    assert after == execution

    # A Run belonging to another Task is not readable through this Task.
    other_task = _task(store)
    other_run = _run(store, other_task, evidence=None)
    foreign = await api.get(
        f"/api/v1/tasks/{task_id}/execution", params={"run_id": other_run}
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"


async def test_legacy_run_endpoint_reports_unknown_reviewer(
    app: FastAPI, api: httpx.AsyncClient
) -> None:
    store = app.state.context.store
    task_id = _task(store)
    run_id = _run(store, task_id, evidence=None)

    body = (await api.get(f"/api/v1/tasks/{task_id}/execution")).json()
    _assert_safe(body)
    assert body["worker"]["source"] == "run_connection_pin"
    assert body["worker"]["status"] == "recorded"
    assert body["worker"]["stage"] == "planned"
    assert body["worker"]["name"] is None
    assert body["reviewer"]["status"] == "unknown"
    assert body["review"] is None
    assert "reviewer_history" in body["missing"]
    assert "review" in body["missing"]
    assert body["run"]["id"] == run_id
