"""LG-030 real default-app HTTP chain self-check (probe, not a test).

Drives the **default** ``create_app()`` (collaboration router already mounted)
with a real ``FileStore`` over loopback ASGI transport, exercising:

* accept of a controlled peer request with a real sha256-hashed evidence ref;
* idempotent replay of the same ``request_id``;
* definite ``budget_exhausted`` on the next request (Task budget ceiling);
* read-only ``GET /runs/{run_id}/collab_requests`` projection.

Run: ``uv run python probes/lg030/http_protocol_check.py``
Expected output (2026-10-16, base `61fad69`):
``POST 200 requested True`` / ``REPLAY True`` / ``BUDGET rejected budget_exhausted`` /
``GET 200 ['c1', 'c2']``
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from pathlib import Path

import httpx

from lightgravity.api.app import create_app
from lightgravity.config import Settings
from lightgravity.store import new_id


async def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        settings = Settings(
            data_dir=Path(d) / "data",
            workspace_root=Path(d) / "data" / "ws",
            secret_store=Path(d) / "sec",
        )
        settings.ensure_data_dir()
        app = create_app(settings)
        store = app.state.context.store
        # Program-authenticated worker identity seam (LG-030/LG-031): the
        # authenticated member ref comes from the caller's execution identity,
        # never from the request body.  The real coordinator injection is LG-031;
        # here it is a header to exercise the default-deny boundary.
        app.state.context.worker_identity = lambda request: request.headers.get("X-Test-Worker")

        task = new_id("task")
        store.create(
            "task",
            task,
            {
                "title": "t",
                "status": "in-progress",
                "phase": "executing",
                "requirements_revision": 1,
                "project_ref": None,
                "repository_ref": None,
                "workspace_ref": "ws",
                "agent_ref": "coordinator",
                "depends_on": [],
                "active_run": None,
                "deliverable_revision": 0,
                "queue": {
                    "state": "not_queued",
                    "order": None,
                    "queued_at": None,
                    "owner": None,
                    "lease_expires_at": None,
                },
                "acceptance": {
                    "status": "pending",
                    "requirements_revision": None,
                    "deliverable_revision": None,
                    "evidence_refs": [],
                    "decided_at": None,
                    "decision_ref": None,
                },
                "budget": {"max_workers": 2, "max_collab_requests": 1},
                "archived": False,
            },
            actor="t",
            request_id="r-task",
            body="#\n",
        )
        run = new_id("run")
        store.create(
            "run",
            run,
            {
                "task_ref": task,
                "attempt": 1,
                "state": "executing",
                "plan_ref": "PLAN.md",
                "plan_source": "rules",
                "team_refs": ["member-a", "member-b"],
                "subtask_refs": [],
                "session_refs": [],
                "cleanup": {"status": "pending"},
                "ended_at": None,
                "fail_reason": None,
            },
            actor="t",
            request_id="r-run",
            body="#\n",
        )
        sub = new_id("subtask")
        store.create(
            "subtask",
            sub,
            {
                "run_ref": run,
                "state": "pending",
                "depends_on": [],
                "assignee_member_ref": None,
                "upstream_artifact_refs": [],
                "objective": "o",
                "capability": "implementation",
                "key": "a",
                "write": False,
                "config_hash": "h",
                "owner": None,
                "lease_expires_at": None,
                "fail_reason": None,
                "blocked_by": [],
                "acceptance": {"status": "pending", "criteria": [], "evidence_refs": []},
            },
            actor="t",
            request_id="r-sub",
            body="#\n",
        )
        cur = store.read("run", run)
        store.write("run", run, {"subtask_refs": [sub]}, expected_revision=cur.revision, actor="t")
        store.create(
            "settings",
            "settings",
            {
                "title": "S",
                "enabled": True,
                "default_coordinator_connection_ref": None,
                "default_worker_connection_ref": None,
                "decentralized_claim_enabled": False,
                "collab_requests_enabled": True,
                "claim_lease_seconds": 60,
            },
            actor="t",
            request_id="r-set",
            body="#\n",
        )

        root = Path(d) / "data" / "tasks" / task / "artifacts" / run
        root.mkdir(parents=True, exist_ok=True)
        art = root / "diff.patch"
        art.write_text("+x\n")
        digest = hashlib.sha256(art.read_bytes()).hexdigest()
        ref = f"evidence:{run}/diff.patch@sha256:{digest}"

        transport = httpx.ASGITransport(app=app)
        auth = {"X-Test-Worker": "member-a"}
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            payload = {
                "request_id": "c1",
                "from_member_ref": "member-a",
                "to_member_ref": "member-b",
                "node_ref": sub,
                "mode": "review",
                "summary": "review please",
                "message_id": "msg_01J00000000000000000000AA",
                "correlation_id": "corr_01J00000000000000000000AA",
                "handoff_refs": [ref],
            }
            # Unauthenticated body-supplied identity must be refused (default-deny).
            denied = await c.post(f"/api/v1/runs/{run}/collab_requests", json=payload)
            print("DENY", denied.json()["state"], denied.json()["reason"])
            r = await c.post(f"/api/v1/runs/{run}/collab_requests", json=payload, headers=auth)
            print("POST", r.status_code, r.json()["state"], r.json()["produced_refs"] == [ref])
            r2 = await c.post(
                f"/api/v1/runs/{run}/collab_requests", json=payload, headers=auth
            )
            print("REPLAY", r2.json()["idempotent_replay"])
            r3 = await c.post(
                f"/api/v1/runs/{run}/collab_requests",
                json={**payload, "request_id": "c2"},
                headers=auth,
            )
            print("BUDGET", r3.json()["state"], r3.json()["reason"])
            g = await c.get(f"/api/v1/runs/{run}/collab_requests")
            print("GET", g.status_code, [i["request_id"] for i in g.json()["items"]])


if __name__ == "__main__":
    asyncio.run(main())
