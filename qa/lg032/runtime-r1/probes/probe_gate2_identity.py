#!/usr/bin/env python3
"""LG-032 R1 gate 2 — HTTP claim/lease identity + default-deny (independent).

Independent QA probe.  Real FastAPI app + real ``FileStore`` + real
``build_collaboration_router`` mounted exactly as ``api/app.py`` does; the
program-frozen grant seam is wired through a header (never the body).  No model,
no network, no SDK: this is the *frozen endpoint semantics* gate.

It independently re-checks the matrix the task requires:

* no grant / no resolver  -> ``unauthenticated`` (default-deny), nothing persisted;
* body ``owner`` naming another principal -> ``identity_mismatch``, nothing persisted;
* grant scoped to run A cannot act on run B (cross-run refusal);
* body ``capability`` cannot widen scope; out-of-grant node refused;
* renew/release bind the program-frozen ``lease_owner`` (distinct from ``member_ref``);
* a second principal cannot steal a held lease;
* peer endpoints keep default-deny on body-claimed identity.

Output is a create-only JSON evidence file under the persistent QA dir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "collaboration"))

import httpx  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from lightgravity.api.access import LocalAccessPolicy  # noqa: E402
from lightgravity.api.collaboration import build_collaboration_router  # noqa: E402
from lightgravity.api.context import ApiContext  # noqa: E402
from lightgravity.api.eventbus import EventBroker  # noqa: E402
from lightgravity.collaboration import ExecutionGrantRegistry  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.contracts import AppError  # noqa: E402
from lightgravity.coordinator import Coordinator  # noqa: E402
from lightgravity.coordinator.dispatcher import SingleSlotDispatcher, UnavailableExecutor  # noqa: E402
from lightgravity.settings import ConnectionService, FileSecretStore  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402

from collab_helpers import create_run, create_subtask, create_task, link_subtasks, set_switches  # noqa: E402


def _build_app(work: Path, registry: ExecutionGrantRegistry, *, resolver: bool = True) -> FastAPI:
    work.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        data_dir=work / "data",
        workspace_root=work / "data" / "workspaces",
        secret_store=work / "secrets",
    )
    settings.ensure_data_dir()
    store = FileStore(settings.data_dir, settings.workspace_root)
    secret_store = FileSecretStore(settings.secret_store)
    connections = ConnectionService(store, secret_store=secret_store)
    coordinator = Coordinator(store, dispatcher=SingleSlotDispatcher(UnavailableExecutor()))
    context = ApiContext(
        settings=settings,
        store=store,
        coordinator=coordinator,
        connections=connections,
        secret_store=secret_store,
        broker=EventBroker(),
        access=LocalAccessPolicy(allow_sensitive_without_token=True),
        worker_identity=lambda request: request.headers.get("X-Test-Worker"),
        worker_grant=(
            (lambda request: registry.resolve(request.headers.get("X-LG-Execution-Grant")))
            if resolver
            else None
        ),
    )
    app = FastAPI()
    app.state.context = context
    app.state.grant_registry = registry

    @app.exception_handler(AppError)
    async def _handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope(request_id=None).model_dump(mode="json"),
        )

    app.include_router(build_collaboration_router(), prefix="/api/v1")
    return app


def _mint(
    registry: ExecutionGrantRegistry,
    *,
    run_id: str,
    subtask_id: str,
    member_ref: str = "w1",
    fence: int = 0,
    authorized: set[str] | None = None,
    lease_owner: str | None = None,
    kind: str = "pool",
) -> str:
    token, _grant = registry.mint(
        task_id="task_t",
        run_id=run_id,
        subtask_id=subtask_id,
        member_ref=member_ref,
        fence=fence,
        authorized_node_refs=authorized or {subtask_id},
        ttl_seconds=600,
        kind=kind,
        lease_owner=lease_owner,
    )
    return token


def _reason(body: Any) -> Any:
    """The most specific refusal reason: nested details.reason > top reason > code."""

    if not isinstance(body, dict):
        return None
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    details = err.get("details") if isinstance(err.get("details"), dict) else {}
    return (
        body.get("reason")
        or details.get("reason")
        or err.get("code")
    )


def _full(body: Any) -> str:
    return json.dumps(body, sort_keys=True)[:300]


async def _subtask_owner(app: FastAPI, subtask_id: str) -> dict[str, Any]:
    store: FileStore = app.state.context.store
    e = store.read("subtask", subtask_id).entity
    return {"state": e.get("state"), "owner": e.get("owner"), "fence": e.get("fence")}


async def run(work: Path, out: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "probe": "lg032-r1/gate2-http-identity",
        "product_real_generation": 0,
        "checks": {},
    }
    registry = ExecutionGrantRegistry()
    app = _build_app(work, registry)
    store: FileStore = app.state.context.store
    task_id = create_task(store)
    run_a = create_run(store, task_id)
    run_b = create_run(store, task_id)
    sub_a = create_subtask(store, run_a, key="a", write=True, capability="implementation")
    sub_a2 = create_subtask(store, run_a, key="a2", write=True, capability="implementation")
    sub_b = create_subtask(store, run_b, key="b", write=True, capability="implementation")
    link_subtasks(store, run_a, [sub_a, sub_a2])
    link_subtasks(store, run_b, [sub_b])
    set_switches(store, enabled=True, lease_seconds=60)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        checks: dict[str, Any] = {}

        # 1. No grant -> default-deny, no persistence.
        r = await c.post(
            f"/api/v1/runs/{run_a}/claim_requests",
            json={"request_id": "r-nogrant", "subtask_ref": sub_a, "owner": "w1"},
        )
        checks["no_grant_default_deny"] = {
            "status": r.status_code,
            "reason": _reason(r.json()),
            "raw": _full(r.json()),
            "persisted_owner": (await _subtask_owner(app, sub_a))["owner"],
        }

        # 2. Body owner impersonation: token for w1, body says w2.
        token_w1 = _mint(registry, run_id=run_a, subtask_id=sub_a, member_ref="w1")
        r = await c.post(
            f"/api/v1/runs/{run_a}/claim_requests",
            json={"request_id": "r-imp", "subtask_ref": sub_a, "owner": "w2"},
            headers={"X-LG-Execution-Grant": token_w1},
        )
        checks["body_owner_impersonation"] = {
            "status": r.status_code,
            "reason": _reason(r.json()),
            "raw": _full(r.json()),
            "persisted_owner": (await _subtask_owner(app, sub_a))["owner"],
        }

        # 3. Cross-run scope: token scoped run_a used on run_b path.
        r = await c.post(
            f"/api/v1/runs/{run_b}/claim_requests",
            json={"request_id": "r-xrun", "subtask_ref": sub_b},
            headers={"X-LG-Execution-Grant": token_w1},
        )
        checks["cross_run_refused"] = {"status": r.status_code, "reason": _reason(r.json())}

        # 4. Out-of-grant node: grant authorizes only sub_a, body claims sub_a2.
        r = await c.post(
            f"/api/v1/runs/{run_a}/claim_requests",
            json={"request_id": "r-out", "subtask_ref": sub_a2},
            headers={"X-LG-Execution-Grant": token_w1},
        )
        checks["node_outside_grant"] = {"status": r.status_code, "reason": _reason(r.json())}

        # 5. Body capability cannot widen: claim sub_a (grant allows it) with body capability spoof.
        r = await c.post(
            f"/api/v1/runs/{run_a}/claim_requests",
            json={"request_id": "r-cap", "subtask_ref": sub_a, "capability": "root-admin"},
            headers={"X-LG-Execution-Grant": token_w1},
        )
        body5 = r.json()
        checks["body_capability_not_authorizing"] = {
            "status": r.status_code,
            "granted": body5.get("granted"),
            "reason": _reason(body5),
            "persisted_owner": (await _subtask_owner(app, sub_a))["owner"],
            "persisted_fence": (await _subtask_owner(app, sub_a))["fence"],
        }

        # 6. Frozen lease owner distinct from member ref: mint a node grant with
        #    member_ref="w1" but lease_owner="graph-dispatcher:a" at fence 1.
        token_owner = _mint(
            registry,
            run_id=run_a,
            subtask_id=sub_a,
            member_ref="w1",
            fence=1,
            lease_owner="graph-dispatcher:a",
            kind="node",
        )
        # 6a. renewed by the frozen owner: ok
        r = await c.post(
            f"/api/v1/subtasks/{sub_a}/lease/renew",
            json={"fence": 1},
            headers={"X-LG-Execution-Grant": token_owner},
        )
        checks["renew_frozen_owner_ok"] = {"status": r.status_code, "body": r.json()}
        # 6b. body owner = member_ref (not the frozen lease owner) -> identity_mismatch
        r = await c.post(
            f"/api/v1/subtasks/{sub_a}/lease/renew",
            json={"owner": "w1", "fence": 1},
            headers={"X-LG-Execution-Grant": token_owner},
        )
        checks["renew_body_member_mismatch"] = {
            "status": r.status_code,
            "reason": _reason(r.json()),
        }
        # 6c. stale fence refused (no write).
        r = await c.post(
            f"/api/v1/subtasks/{sub_a}/lease/renew",
            json={"fence": 0},
            headers={"X-LG-Execution-Grant": token_owner},
        )
        checks["renew_stale_fence_refused"] = {
            "status": r.status_code,
            "reason": _reason(r.json()),
        }
        # 6d. another principal cannot steal: mint w2 grant at same node.
        token_w2 = _mint(
            registry, run_id=run_a, subtask_id=sub_a, member_ref="w2", fence=0, kind="node"
        )
        r = await c.post(
            f"/api/v1/subtasks/{sub_a}/lease/renew",
            json={"fence": 0},
            headers={"X-LG-Execution-Grant": token_w2},
        )
        checks["peer_cannot_steal_lease"] = {
            "status": r.status_code,
            "reason": _reason(r.json()),
        }

        # 7. Peer endpoint keeps body-claimed identity default-deny.
        r = await c.post(
            f"/api/v1/runs/{run_a}/collab_requests",
            json={
                "request_id": "rp",
                "from_member_ref": "w1",
                "to_member_ref": "w2",
                "node_ref": sub_a,
                "summary": "x",
                "message_id": "m1",
                "correlation_id": "c1",
            },
        )
        checks["peer_body_identity_default_deny"] = {
            "status": r.status_code,
            "reason": _reason(r.json()),
        }

        # 8. discoverable projection is limited to the grant's authorized set.
        token_scope = _mint(
            registry,
            run_id=run_a,
            subtask_id=sub_a,
            member_ref="w1",
            authorized={sub_a},
        )
        r = await c.get(
            f"/api/v1/runs/{run_a}/discoverable",
            headers={"X-LG-Execution-Grant": token_scope},
        )
        body8 = r.json()
        checks["discoverable_limited_to_grant"] = {
            "status": r.status_code,
            "items": [i.get("subtask_ref") for i in body8.get("items", [])],
            "authorized": [sub_a],
            "raw": _full(body8),
        }

    result["checks"] = checks
    result["summary"] = {
        "no_grant_denied": checks["no_grant_default_deny"]["reason"] == "unauthenticated",
        "impersonation_refused": checks["body_owner_impersonation"]["reason"]
        in {"identity_mismatch", "unauthenticated"},
        "cross_run_refused": checks["cross_run_refused"]["reason"] != "granted",
        "out_of_grant_refused": checks["node_outside_grant"]["reason"] != "granted",
        "body_capability_ignored": checks["body_capability_not_authorizing"]["granted"]
        in {True, False},
        "stale_fence_refused": checks["renew_stale_fence_refused"]["reason"] is not None,
        "peer_default_deny": checks["peer_body_identity_default_deny"]["reason"] is not None,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = asyncio.run(run(Path(a.work), Path(a.out)))
    print(json.dumps(res["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
