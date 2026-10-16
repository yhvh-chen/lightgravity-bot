#!/usr/bin/env python3
"""LG-047 R1-integration combined API zero-model smoke (LOCAL ONLY).

Purpose
-------
Prove that the merged R1 repairs (F native-text intake + G assistant-history /
default-delivery-plan) are both wired through the **actual product factory
default** ``create_app`` (which itself mounts ``build_sources_router``), with the
real coordinator lifespan, and **no** real model / SDK / network / OCR / browser.

Scope (LOCAL, fake leaf executor):
  * F: a real ``POST /api/v1/sources`` plain-text (``text/plain``) upload is
    auto-pumped by the native UTF-8 extractor and becomes a **readable body**
    (``GET /sources/{id}/content``) with **no manual derivative seed** and no
    OCR.  This is the exact R1 main-flow defect.
  * G: an ordinary generic Chat delivery request routes to a Task whose default
    plan (derived acceptance criterion + authorized workspace) passes the
    unchanged ``PlanValidator`` and dispatches to the (fake) worker; the
    assistant answer is **persisted to history** together with its
    ``resolved_source_bindings``; a retried ``message_id`` is idempotent (no
    duplicate row, no second dispatch).

This is explicitly **not** SDK/real-model evidence.  The leaf executor is an
in-process fake; the file is labelled ``fake-models`` and makes **zero** product
generation forwards.  Do not interpret any of this as a version-QA PASS.

Run:
    PYTHONPATH=backend python probes/prototype-selected-material-20261016/H-R1-INTEGRATION/smoke_combined_api.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from graph_helpers import build_environment  # noqa: E402
from lightgravity.adapter import (  # noqa: E402
    AdapterCapabilities,
    CancelResult,
    ExecutionRef,
    ExecutorResult,
    adapter_capabilities,
)
from lightgravity.api.app import create_app  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.coordinator import GraphDispatcher  # noqa: E402
from lightgravity.coordinator.recruiter import RoleCatalog  # noqa: E402
from lightgravity.store import new_id  # noqa: E402

BRIEF_BODY = (
    "PROJECT ORION-71 — sample brief. Project code name ORION-71. "
    "Programme owner Halden Reyes. Primary launch date 2027-03-14. "
    "Total approved budget 418,250 EUR."
)
DELIVERY_PROMPT = (
    "Create a Markdown file summary with these exact fixture facts: project code "
    "name ORION-71, programme owner Halden Reyes, primary launch date 2027-03-14, "
    "total budget 418,250 EUR."
)
ONE_AGENT = RoleCatalog(
    {"implementation": ["developer"], "verification": ["developer"]}
)


class FakeExecutor:
    """In-process fake leaf executor (fake-models; NOT SDK evidence)."""

    name = "fake-smoke"
    version = "0"

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def capabilities(self) -> AdapterCapabilities:
        return adapter_capabilities()

    async def execute(self, request: Any, emit: Any) -> ExecutorResult:
        self.requests.append(request)
        return ExecutorResult(
            state="succeeded",
            summary="fake:succeeded",
            artifact_refs=(f"artifact_{request.subtask_id}",),
            execution_ref=ExecutionRef(
                execution_id=f"exec_{request.subtask_id}",
                task_id=request.task_id,
                run_id=request.run_id,
                subtask_id=request.subtask_id,
            ),
            stop_confirmed=True,
        )

    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult:
        return CancelResult(confirmed=True, state="cancelled")


def _build() -> tuple[FastAPI, FakeExecutor, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="lg047-h-smoke-"))
    settings = Settings(
        data_dir=tmp / "data",
        workspace_root=tmp / "data" / "workspaces",
        secret_store=tmp / "secrets",
    )
    settings.ensure_data_dir()
    # Seed the deterministic resource environment into the SAME store the app
    # will use (create_app is given the store explicitly so both share it).
    from lightgravity.store import FileStore

    store = FileStore(settings.data_dir, settings.workspace_root)
    build_environment(store)
    executor = FakeExecutor()
    dispatcher = GraphDispatcher(store, executor, catalog=ONE_AGENT)
    # ACTUAL product factory default: create_app mounts build_sources_router and
    # keeps the real coordinator lifespan; only the leaf executor is fake.
    app = create_app(settings, store=store, dispatcher=dispatcher, executor=executor)
    return app, executor, tmp


async def _wait_for_dispatch(client: httpx.AsyncClient, task_id: str, timeout: float) -> str:
    deadline = asyncio.get_event_loop().time() + timeout
    phase = "?"
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"/api/v1/tasks/{task_id}")
        phase = r.json().get("phase", "?")
        if phase not in {"planning", "queued", "running", "verifying", "repairing"}:
            return phase
        await asyncio.sleep(0.15)
    return phase


async def main() -> int:
    report: dict[str, Any] = {"kind": "fake-models", "sdk": False}
    app, executor, tmp = _build()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            # ---- F: real native UTF-8 upload -> readable body (no seed, no OCR)
            upload = await client.post(
                "/api/v1/sources",
                json={
                    "request_id": new_id("req"),
                    "filename": "brief.txt",
                    "content_base64": base64.b64encode(BRIEF_BODY.encode()).decode(),
                    "media_type": "text/plain",
                },
                headers={"X-Request-Id": new_id("req")},
            )
            assert upload.status_code in (200, 201), upload.text
            src = upload.json()
            source_id = src["source"]["source_id"]
            report["F_upload_status"] = src["source"]["status"]
            report["F_upload_derivatives"] = len(src["source"].get("derivatives", []))

            content = await client.get(
                f"/api/v1/sources/{source_id}/content", params={"kind": "auto"}
            )
            report["F_content_status"] = content.status_code
            assert content.status_code == 200, content.text
            report["F_body_has_ORION71"] = "ORION-71" in content.text

            # ---- G: generic Chat delivery + selected source -> valid plan, dispatch
            msg_id = "h-smoke-deliver"
            payload = {
                "message_id": msg_id,
                "content": DELIVERY_PROMPT,
                "selected_sources": [{"source_id": source_id}],
            }
            first = await client.post(
                "/api/v1/conversations/global/messages",
                json=payload,
                headers={"X-Request-Id": new_id("req")},
            )
            assert first.status_code == 200, first.text
            first_body = first.json()
            report["G_kind"] = first_body.get("kind")
            task_id = str(first_body.get("task_id"))
            report["G_task_id"] = task_id
            assert report["G_kind"] == "task", first_body

            task = (await client.get(f"/api/v1/tasks/{task_id}")).json()
            report["G_derived_acceptance"] = bool(task.get("acceptance_criteria"))
            report["G_workspace_ref"] = bool(task.get("workspace_ref"))

            phase = await _wait_for_dispatch(client, task_id, timeout=20.0)
            report["G_phase_after_dispatch"] = phase
            report["G_dispatched_requests"] = len(executor.requests)
            report["G_worker_got_body"] = bool(
                executor.requests and BRIEF_BODY in executor.requests[0].instructions
            )
            report["G_worker_has_workspace"] = bool(
                executor.requests and executor.requests[0].workspace_path
            )

            # ---- G: direct answered turn persists assistant + bindings (history)
            ans_id = "h-smoke-answer"
            answer_payload = {
                "message_id": ans_id,
                "content": "Summarize the selected brief.",
                "selected_sources": [{"source_id": source_id}],
            }
            ans = await client.post(
                "/api/v1/conversations/global/messages",
                json=answer_payload,
                headers={"X-Request-Id": new_id("req")},
            )
            assert ans.status_code == 200, ans.text
            report["G_answer_kind"] = ans.json().get("kind")
            history = (
                await client.get("/api/v1/conversations/global/messages")
            ).json()["items"]
            ids = [row["message_id"] for row in history]
            report["G_history_ids"] = ids
            assistant = next(
                (r["message"] for r in history if r["message_id"] == f"assistant:{ans_id}"),
                None,
            )
            report["G_assistant_persisted"] = assistant is not None
            if assistant is not None:
                bindings = assistant.get("data", {}).get("resolved_source_bindings", [])
                report["G_assistant_bindings"] = [b["source_id"] for b in bindings]
                report["G_assistant_has_selected_context"] = "selected_context" in assistant

            # ---- G: idempotency — retry the answered turn, no dup row/dispatch
            exec_before = len(executor.requests)
            again = await client.post(
                "/api/v1/conversations/global/messages",
                json=answer_payload,
                headers={"X-Request-Id": new_id("req")},
            )
            report["G_retry_status"] = again.status_code
            history2 = (
                await client.get("/api/v1/conversations/global/messages")
            ).json()["items"]
            report["G_history_count_after_retry"] = len(history2)
            report["G_duplicate_assistant_rows"] = sum(
                1 for r in history2 if r["message_id"] == f"assistant:{ans_id}"
            )
            report["G_extra_dispatch_on_retry"] = len(executor.requests) - exec_before

    report["tmp_dir"] = str(tmp)
    print(json.dumps(report, indent=2))

    checks = {
        "F readable native body": report["F_content_status"] == 200
        and report.get("F_body_has_ORION71"),
        "F terminal extracted/done": report["F_upload_status"] in {"extracted", "done"},
        "G routed to task": report["G_kind"] == "task",
        "G derived acceptance+workspace": report["G_derived_acceptance"]
        and report["G_workspace_ref"],
        "G plan validated (phase advanced)": report["G_phase_after_dispatch"]
        not in {"failed", "?"},
        "G worker dispatched with exact body+workspace": report["G_dispatched_requests"] >= 1
        and report["G_worker_got_body"]
        and report["G_worker_has_workspace"],
        "G assistant persisted with bindings": report["G_assistant_persisted"]
        and bool(report.get("G_assistant_bindings")),
        "G idempotent retry (no dup row, no re-dispatch)": report[
            "G_duplicate_assistant_rows"
        ]
        == 1
        and report["G_extra_dispatch_on_retry"] == 0,
    }
    print("\n=== CHECKS ===")
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    os.environ.setdefault("LIGHTGRAVITY_MAX_GENERATION_CALLS", "0")
    raise SystemExit(asyncio.run(main()))
