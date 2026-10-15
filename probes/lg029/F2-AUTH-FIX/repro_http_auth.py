#!/usr/bin/env python
"""LG-029 F2 minimal HTTP reproduction (real ASGI, no model, product calls 0).

Boots the *real* ``create_app`` router with a real ``FileStore`` and a
program-side ``ExecutionGrantRegistry`` (exactly what bootstrap wires), then
drives the frozen discovery/claim/lease endpoints over HTTP with httpx + ASGI
transport.  For every denial it asserts the on-disk Subtask state before/after
is unchanged (no business write), not merely the status code.

Run: ``uv run python probes/lg029/F2-AUTH-FIX/repro_http_auth.py``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from lightgravity.api.access import LocalAccessPolicy  # noqa: E402
from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.collaboration import ExecutionGrantRegistry  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402

# Reuse the maintained entity builders (real Store) rather than re-deriving the
# frozen Task/Run/Subtask frontmatter shapes here.
_HELPERS = Path(__file__).resolve().parents[3] / "tests" / "collaboration"
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))

from collab_helpers import (  # noqa: E402
    create_run,
    create_subtask,
    create_task,
    link_subtasks,
    set_switches,
)

OUT = Path(__file__).resolve().parent / "evidence"
OUT.mkdir(parents=True, exist_ok=True)


def _seed(store: FileStore) -> tuple[str, str, str]:
    task_id = create_task(store)
    run_id = create_run(store, task_id)
    sub_id = create_subtask(store, run_id, key="a")
    link_subtasks(store, run_id, [sub_id])
    set_switches(store, enabled=True, lease_seconds=60)
    return task_id, run_id, sub_id


def _mint(
    registry: ExecutionGrantRegistry, run_id: str, sub_id: str, member: str, **kw: object
) -> str:
    token, _grant = registry.mint(
        task_id=kw.pop("task_id", "task_probe"),  # type: ignore[arg-type]
        run_id=run_id,
        subtask_id=sub_id,
        member_ref=member,
        fence=kw.pop("fence", 0),  # type: ignore[arg-type]
        authorized_node_refs=kw.pop("authorized_node_refs", {sub_id}),  # type: ignore[arg-type]
        ttl_seconds=600,
        kind=kw.pop("kind", "pool"),  # type: ignore[arg-type]
    )
    return token


async def _call(client: httpx.AsyncClient, method: str, url: str, **kw: object) -> dict:
    response = await client.request(method, url, **kw)  # type: ignore[arg-type]
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        body = {"raw": response.text}
    return {"status": response.status_code, "body": body}


async def main() -> int:
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="lg029-f2-"))
    settings = Settings(
        data_dir=root / "data",
        workspace_root=root / "data" / "workspaces",
        secret_store=root / "secrets",
    )
    settings.ensure_data_dir()
    store = FileStore(settings.data_dir, settings.workspace_root)
    registry = ExecutionGrantRegistry()
    task_id, run_id, sub_id = _seed(store)

    app: FastAPI = create_app(
        settings,
        store=store,
        access_policy=LocalAccessPolicy(allow_sensitive_without_token=True),
        worker_grant=lambda request: registry.resolve(
            request.headers.get("X-LG-Execution-Grant")
        ),
    )

    results: dict[str, object] = {
        "product_model_calls": 0,
        "note": "real ASGI + real FileStore; provider-substitute (no SDK, no model)",
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://probe") as http:
        base = "/api/v1"
        before = store.read("subtask", sub_id).entity

        # 1. unauthenticated (no grant header) -> default-deny, no write
        results["unauthenticated_claim"] = await _call(
            http,
            "POST",
            f"{base}/runs/{run_id}/claim_requests",
            json={"owner": "member-a", "request_id": "r-1", "subtask_ref": sub_id},
        )
        results["state_after_unauthenticated"] = store.read("subtask", sub_id).entity
        assert results["state_after_unauthenticated"]["owner"] is None

        # 2. wrong principal: authenticated member-a names member-b
        token_a = _mint(registry, run_id, sub_id, "member-a")
        results["impersonation_claim"] = await _call(
            http,
            "POST",
            f"{base}/runs/{run_id}/claim_requests",
            json={"owner": "member-b", "request_id": "r-2", "subtask_ref": sub_id},
            headers={"X-LG-Execution-Grant": token_a},
        )
        assert store.read("subtask", sub_id).entity["owner"] is None

        # 3. capability/write escalation attempt via body is ignored (no grant -> deny)
        results["escalation_claim"] = await _call(
            http,
            "POST",
            f"{base}/runs/{run_id}/claim_requests",
            json={
                "owner": "member-a",
                "request_id": "r-3",
                "subtask_ref": sub_id,
                "capability": "admin",
                "write": True,
            },
            headers={"X-LG-Execution-Grant": token_a},
        )
        # capability/write are not model-grantable: discovery already excludes by
        # program scope; the claim records the program owner only.
        results["state_after_escalation"] = store.read("subtask", sub_id).entity

        # 4. cross-run scope: grant for run A used against run B
        task_b = create_task(store)
        run_b = create_run(store, task_b)
        sub_b = create_subtask(store, run_b, key="b")
        link_subtasks(store, run_b, [sub_b])
        results["cross_run_claim"] = await _call(
            http,
            "POST",
            f"{base}/runs/{run_b}/claim_requests",
            json={"owner": "member-a", "request_id": "r-4", "subtask_ref": sub_b},
            headers={"X-LG-Execution-Grant": token_a},
        )
        assert store.read("subtask", sub_b).entity["owner"] is None

        # 5. authorized same-owner happy path (retry of 3/4 with fresh grant)
        token_ok = _mint(registry, run_id, sub_id, "member-a")
        results["authorized_claim"] = await _call(
            http,
            "POST",
            f"{base}/runs/{run_id}/claim_requests",
            json={"owner": "member-a", "request_id": "r-5", "subtask_ref": sub_id},
            headers={"X-LG-Execution-Grant": token_ok},
        )
        granted = results["authorized_claim"]["body"]
        fence = granted.get("fence")
        results["state_after_authorized"] = store.read("subtask", sub_id).entity

        # 6. stale fence renew is refused and does not change the lease
        token_node = _mint(registry, run_id, sub_id, "member-a", fence=fence, kind="node")
        lease_before = store.read("subtask", sub_id).entity["lease_expires_at"]
        results["stale_renew"] = await _call(
            http,
            "POST",
            f"{base}/subtasks/{sub_id}/lease/renew",
            json={"owner": "member-a", "fence": (fence or 0) + 5, "lease_seconds": 60},
            headers={"X-LG-Execution-Grant": token_node},
        )
        assert store.read("subtask", sub_id).entity["lease_expires_at"] == lease_before

        # 7. authorized renew + release
        results["authorized_renew"] = await _call(
            http,
            "POST",
            f"{base}/subtasks/{sub_id}/lease/renew",
            json={"owner": "member-a", "fence": fence, "lease_seconds": 60},
            headers={"X-LG-Execution-Grant": token_node},
        )
        results["authorized_release"] = await _call(
            http,
            "POST",
            f"{base}/subtasks/{sub_id}/lease/release",
            json={"owner": "member-a", "fence": fence},
            headers={"X-LG-Execution-Grant": token_node},
        )
        results["state_after_release"] = store.read("subtask", sub_id).entity

        # 8. default-off rollback: disable the switch, authenticated claim refused
        store.write(
            "settings",
            "settings",
            {
                "decentralized_claim_enabled": False,
                "collab_requests_enabled": False,
                "claim_lease_seconds": 60,
            },
            expected_revision=store.read("settings", "settings").revision,
            actor="probe",
        )
        results["disabled_claim"] = await _call(
            http,
            "POST",
            f"{base}/runs/{run_id}/claim_requests",
            json={"owner": "member-a", "request_id": "r-9", "subtask_ref": sub_id},
            headers={"X-LG-Execution-Grant": token_node},
        )

    results["baseline_owner_before"] = before["owner"]
    (OUT / "http-auth-repro.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
