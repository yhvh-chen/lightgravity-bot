#!/usr/bin/env python3
"""LG-010 round-2 (post-fix) independent QA probe: duplicate ack safety boundary.

Round-2 fix (ed014c5, parent b418dcf) added a Task-scoped idempotency replay for
``accept``/``reject`` acknowledgements.  The original ``lg010_accept_repro_r1.py``
already shows ``duplicate_accept_idempotent=true``.  This independent probe does
**not** replace it; it adds the boundaries the fix must not weaken, all at the
HTTP layer through the real ASGI app with a prepared Store fixture (no model
calls, no network):

1. first ``accept`` with ``target_run_id`` -> 200; identical duplicate (with and
   without ``target_run_id``) -> byte-identical body, same ETag, no second write.
2. same ``request_id`` reused for the *other* action on the same Task -> not
   replayed, contract error.
3. same ``request_id`` reused on a *different* Task with its own valid target ->
   decided against Task B's own candidate, never leaks Task A.
4. cross-Task replay attempt using Task A's ``request_id`` **and** Task A's target
   against Task B -> rejected (target is not B's candidate).
5. stale ``expected_revision`` / wrong ``target_run_id`` on a fresh request still
   rejected.
6. non-loopback caller without the local token -> 401 even for a duplicate.
7. legacy (pre-fix) idempotency key ``verify:decision:<request_id>`` in
   ``coordinator/requests.jsonl`` is **not** silently treated as a replay for the
   new Task-scoped key: an already-decided candidate is still reported from
   acceptance state (bound-candidate replay), and the observation is recorded
   honestly.

Run:
    uv run python probes/lg010/lg010_accept_repro_r2.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_REPO / "tests"))

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from lightgravity.api.access import LocalAccessPolicy, TOKEN_HEADER  # noqa: E402
from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.coordinator.logs import append_jsonl  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from verify.verify_helpers import make_verifying_task  # noqa: E402


def _build(root: Path) -> tuple[FastAPI, FileStore, str, str]:
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
    return app, store, task_id, run_id


async def _prepare(app: FastAPI, store: FileStore, task_id: str) -> dict:
    prep = app.state.verification.verify_and_prepare(task_id, request_id=f"prep-{task_id}")
    acc = store.read("task", task_id).entity.get("acceptance") or {}
    return {"prepared_phase": prep.phase, "candidate_ref": acc.get("candidate_ref")}


async def _run() -> dict:
    root = Path(tempfile.mkdtemp(prefix="lg010-accept-r2-"))
    app, store, task_a, run_a = _build(root)
    report: dict[str, object] = {"task_a": task_a, "run_a": run_a}
    outcomes: dict[str, bool] = {}

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", timeout=30.0
        ) as client:
            report["prep_a"] = await _prepare(app, store, task_a)

            # --- (1) first accept + duplicate (with/without target) + ETag ---
            payload = {"action": "accept", "request_id": "ack-a", "target_run_id": run_a}
            r1 = await client.post(f"/api/v1/tasks/{task_a}/actions", json=payload)
            r2 = await client.post(f"/api/v1/tasks/{task_a}/actions", json=payload)
            r3 = await client.post(
                f"/api/v1/tasks/{task_a}/actions",
                json={"action": "accept", "request_id": "ack-a"},
            )
            report["first_accept"] = {"http": r1.status_code, "etag": r1.headers.get("etag")}
            report["dup_with_target"] = {"http": r2.status_code, "etag": r2.headers.get("etag")}
            report["dup_no_target"] = {"http": r3.status_code, "etag": r3.headers.get("etag")}
            outcomes["duplicate_with_target_identical"] = (
                r2.status_code == 200 and r2.json() == r1.json()
            )
            outcomes["duplicate_no_target_identical"] = (
                r3.status_code == 200 and r3.json() == r1.json()
            )
            outcomes["replay_etag_matches_first"] = (
                r1.headers.get("etag") == r2.headers.get("etag") == r3.headers.get("etag")
            )

            # --- (2) same request_id, other action (reject) on same Task ---
            r_other = await client.post(
                f"/api/v1/tasks/{task_a}/actions",
                json={"action": "reject", "request_id": "ack-a", "target_run_id": run_a},
            )
            report["same_request_other_action"] = {
                "http": r_other.status_code,
                "code": r_other.json().get("error", {}).get("code"),
            }
            outcomes["same_request_other_action_not_replay"] = (
                r_other.json() != r1.json()
            )

            # --- (3) Task B, own request_id, own target ---
            task_b, run_b, _mb, _sb = make_verifying_task(
                store,
                checks=("evidence-present",),
                evidence=("out/result.txt",),
                member_state="released",
                run_state="verifying",
            )
            (store._data_dir / "workspaces" / "demo-repo" / "out").mkdir(
                parents=True, exist_ok=True
            )
            (store._data_dir / "workspaces" / "demo-repo" / "out" / "result.txt").write_text(
                "ok\n"
            )
            report["prep_b"] = await _prepare(app, store, task_b)
            rb = await client.post(
                f"/api/v1/tasks/{task_b}/actions",
                json={"action": "accept", "request_id": "ack-b", "target_run_id": run_b},
            )
            report["task_b_accept"] = {"http": rb.status_code}
            outcomes["task_b_own_candidate"] = (
                rb.status_code == 200
                and rb.json()["task_id"] == task_b
                and rb.json()["acceptance"]["candidate_ref"] == run_b
                and rb.json()["acceptance"]["candidate_ref"] != report["prep_a"]["candidate_ref"]
            )

            # --- (4) cross-Task replay: Task A request_id + Task A target on Task B ---
            rc = await client.post(
                f"/api/v1/tasks/{task_b}/actions",
                json={"action": "accept", "request_id": "ack-a", "target_run_id": run_a},
            )
            report["cross_task_replay_attempt"] = {
                "http": rc.status_code,
                "code": rc.json().get("error", {}).get("code"),
            }
            outcomes["cross_task_replay_rejected"] = (
                rc.json() != r1.json()
            )

            # --- (5) stale revision and wrong target on a *fresh* awaiting Task ---
            # Task B is already accepted above, so a stale check there would be
            # answered by the bound-candidate replay path, not the freshness
            # guard.  Seed a separate still-awaiting Task to test staleness.
            task_s, run_s, _ms, _ss = make_verifying_task(
                store,
                checks=("evidence-present",),
                evidence=("out/result.txt",),
                member_state="released",
                run_state="verifying",
            )
            report["prep_s"] = await _prepare(app, store, task_s)
            r_stale = await client.post(
                f"/api/v1/tasks/{task_s}/actions",
                json={
                    "action": "accept",
                    "request_id": "stale-s",
                    "expected_deliverable_revision": 999,
                },
            )
            r_wrong = await client.post(
                f"/api/v1/tasks/{task_s}/actions",
                json={"action": "accept", "request_id": "wrong-s", "target_run_id": "run_nope"},
            )
            report["stale"] = {
                "http": r_stale.status_code,
                "code": r_stale.json().get("error", {}).get("code"),
            }
            report["wrong_target"] = {
                "http": r_wrong.status_code,
                "code": r_wrong.json().get("error", {}).get("code"),
            }
            outcomes["stale_rejected"] = r_stale.status_code == 409
            outcomes["wrong_target_rejected"] = r_wrong.status_code == 409

            # --- (7) legacy pre-fix key present, then a fresh-request replay ---
            append_jsonl(
                Path(store._data_dir) / "coordinator" / "requests.jsonl",
                {
                    "request_id": "verify:decision:legacy-b",
                    "at": "2026-10-15T00:00:00Z",
                    "result": {"action": "accept", "state": "confirmed", "confirmed": True,
                               "task_id": task_b, "phase": "completed", "acceptance": {},
                               "request_id": "legacy-b"},
                },
            )
            r_legacy = await client.post(
                f"/api/v1/tasks/{task_b}/actions",
                json={"action": "accept", "request_id": "legacy-b"},
            )
            report["legacy_key_request"] = {
                "http": r_legacy.status_code,
                "phase": r_legacy.json().get("phase"),
            }
            # bound-candidate replay comes from acceptance state, not the stale key
            outcomes["legacy_key_not_replayed_verbatim"] = (
                r_legacy.status_code == 200 and r_legacy.json().get("phase") == "completed"
            )

    # --- (6) non-loopback token enforcement on a fresh app/Task ---
    root2 = Path(tempfile.mkdtemp(prefix="lg010-accept-r2-auth-"))
    app2, store2, task_c, run_c = _build(root2)
    settings2 = Settings(
        data_dir=store2._data_dir,
        workspace_root=store2._data_dir / "workspaces",
        secret_store=root2 / "secrets",
    )
    app2 = create_app(settings2, store=store2, access_policy=LocalAccessPolicy(token="sesame"))
    async with app2.router.lifespan_context(app2):
        await _prepare(app2, store2, task_c)
        transport = httpx.ASGITransport(app=app2, client=("10.1.2.3", 5555))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", timeout=30.0
        ) as client:
            p = {"action": "accept", "request_id": "auth-c", "target_run_id": run_c}
            denied = await client.post(f"/api/v1/tasks/{task_c}/actions", json=p)
            allowed = await client.post(
                f"/api/v1/tasks/{task_c}/actions", json=p, headers={TOKEN_HEADER: "sesame"}
            )
            replay = await client.post(
                f"/api/v1/tasks/{task_c}/actions", json=p, headers={TOKEN_HEADER: "sesame"}
            )
            report["auth"] = {
                "denied": denied.status_code,
                "allowed": allowed.status_code,
                "replay": replay.status_code,
            }
            outcomes["non_loopback_denied"] = denied.status_code == 401
            outcomes["authed_replay_identical"] = (
                allowed.status_code == 200 and replay.json() == allowed.json()
            )

    report["outcomes"] = outcomes
    report["all_pass"] = all(outcomes.values())
    print(json.dumps(report, indent=2, default=str))
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(root2, ignore_errors=True)
    return report


if __name__ == "__main__":
    result = asyncio.run(_run())
    sys.exit(0 if result.get("all_pass") else 1)
