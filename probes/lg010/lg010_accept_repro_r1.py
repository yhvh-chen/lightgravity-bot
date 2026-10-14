#!/usr/bin/env python3
"""LG-010 round-2 model-free probe: version-bound accept / duplicate ack.

The real end-to-end run (``lg010_e2e_r1.py``) showed that a first accept with
``target_run_id`` succeeds but a *duplicate* accept with the same request_id and
the same ``target_run_id`` is answered ``409 illegal_transition`` instead of an
idempotent replay.  This probe reproduces that at the HTTP layer with a prepared
Store fixture (no model calls, no network) and also checks the stale-revision
and cross-run binding paths.

It uses the product router through an in-process ASGI client; the Task fixture is
built with the same Store helpers the product/integration tests use, because the
independent QA is model-call capped and cannot create an awaiting_acceptance Task
another way.  No product code is modified.

Run:
    uv run python probes/lg010/lg010_accept_repro_r1.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_REPO / "tests"))

import httpx  # noqa: E402

from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify.service import VerificationService  # noqa: E402
from verify.verify_helpers import make_verifying_task  # noqa: E402


async def _run() -> dict:
    root = Path(tempfile.mkdtemp(prefix="lg010-accept-r1-"))
    data_dir = root / "bot-data"
    workspace_root = data_dir / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "demo-repo").mkdir(parents=True, exist_ok=True)

    store = FileStore(data_dir, workspace_root)
    task_id, run_id, _members, _subtasks = make_verifying_task(
        store,
        checks=("evidence-present",),
        evidence=("out/result.txt",),
        member_state="released",
        run_state="verifying",
    )
    (workspace_root / "demo-repo" / "out").mkdir(parents=True, exist_ok=True)
    (workspace_root / "demo-repo" / "out" / "result.txt").write_text("ok\n")

    settings = Settings(
        data_dir=data_dir, workspace_root=workspace_root, secret_store=root / "secrets"
    )
    app = create_app(settings, store=store)
    report: dict[str, object] = {"task_id": task_id, "run_id": run_id}

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", timeout=30.0
        ) as client:
            prep = app.state.verification.verify_and_prepare(
                task_id, request_id="prep-accept"
            )
            report["prepared_phase"] = prep.phase
            report["prepared_checks"] = prep.checks

            task = store.read("task", task_id).entity
            acc = task.get("acceptance") or {}
            req_rev = acc.get("requirements_revision")
            del_rev = acc.get("deliverable_revision")
            candidate_ref = acc.get("candidate_ref")
            report["candidate_ref"] = candidate_ref

            base = {
                "action": "accept",
                "request_id": "dup-accept",
                "expected_requirements_revision": req_rev,
                "expected_deliverable_revision": del_rev,
                "target_run_id": candidate_ref,
            }

            # Stale revision must be rejected and must not decide.
            stale = dict(base, request_id="stale-accept", expected_deliverable_revision=999)
            r = await client.post(f"/api/v1/tasks/{task_id}/actions", json=stale)
            report["stale_accept"] = {"http": r.status_code, "body": r.json()}

            # Wrong run binding must be rejected.
            cross = dict(base, request_id="cross-run-accept", target_run_id="run_other")
            r = await client.post(f"/api/v1/tasks/{task_id}/actions", json=cross)
            report["cross_run_accept"] = {"http": r.status_code, "body": r.json()}

            # First real accept.
            r1 = await client.post(f"/api/v1/tasks/{task_id}/actions", json=base)
            report["first_accept"] = {"http": r1.status_code, "body": r1.json()}

            # Duplicate ack, identical request_id + target_run_id.
            r2 = await client.post(f"/api/v1/tasks/{task_id}/actions", json=base)
            report["duplicate_accept_same_request"] = {
                "http": r2.status_code,
                "body": r2.json(),
            }
            report["duplicate_accept_idempotent"] = (
                r2.status_code == r1.status_code and r2.json() == r1.json()
            )

            # Duplicate without target_run_id (router regression test shape).
            no_target = {k: v for k, v in base.items() if k != "target_run_id"}
            r3 = await client.post(f"/api/v1/tasks/{task_id}/actions", json=no_target)
            report["duplicate_accept_no_target"] = {
                "http": r3.status_code,
                "body": r3.json(),
            }

    report["final_phase"] = store.read("task", task_id).entity.get("phase")
    print(json.dumps(report, indent=2, default=str))
    import shutil

    shutil.rmtree(root, ignore_errors=True)
    return report


if __name__ == "__main__":
    asyncio.run(_run())
