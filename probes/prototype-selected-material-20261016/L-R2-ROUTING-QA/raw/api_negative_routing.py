#!/usr/bin/env python3
"""L-R2-ROUTING-QA API negative-routing probe (independent, component/API ONLY).

Through the **public global messages API** on the real ``create_app`` wiring,
assert that ordinary/non-command messages do NOT create a Task (no implicit
write authorization) and that genuine commands keep their route. The fixture
uses the default ``UnavailableExecutor`` (no SDK), so this is **component/API
evidence only**.

Cases (each a distinct global message, no selected source needed for routing):
  * "How do I create a file?"           -> direct answer, NO task created
  * "Who approved the budget?"          -> direct answer, NO task created
  * 'Create a file with the text "approve" inside' -> task created (delivery)
  * "Create acceptance.md"              -> task created (delivery)
  * "Create approved-budget.md"         -> task created (delivery)
  * "Please approve the current candidate." -> decision, NO task created
  * "cancel the running task"           -> no target -> clarify, NO task created
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import httpx

from lightgravity.api.access import LocalAccessPolicy
from lightgravity.api.app import create_app
from lightgravity.config import Settings

CASES = [
    ("ordinary_how_create_file", "How do I create a file?", "no_task"),
    ("ordinary_who_approved_budget", "Who approved the budget?", "no_task"),
    ("ordinary_what_can_you_do", "What can you do?", "no_task"),
    ("quoted_approve_literal", 'Create a file with the text "approve" inside', "task"),
    ("filename_acceptance_md", "Create acceptance.md", "task"),
    ("filename_approved_budget_md", "Create approved-budget.md", "task"),
    ("genuine_approve", "Please approve the current candidate.", "no_task"),
    ("genuine_cancel_no_target", "cancel the running task", "no_task"),
]


async def _run(root: Path) -> dict[str, object]:
    settings = Settings(
        data_dir=root / "data",
        workspace_root=root / "data" / "workspaces",
        secret_store=root / "secrets",
    )
    app = create_app(settings, access_policy=LocalAccessPolicy(allow_sensitive_without_token=True))
    rows = []
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i, (label, text, expect) in enumerate(CASES):
                r = await client.post(
                    "/api/v1/conversations/global/messages",
                    json={"message_id": f"qa-neg-{i}", "content": text},
                )
                body = r.json()
                kind = body.get("kind")
                created = kind == "task"
                ok = (expect == "task") == created
                rows.append(
                    {
                        "label": label,
                        "text": text,
                        "expected": expect,
                        "status": r.status_code,
                        "kind": kind,
                        "intent": (body.get("data") or {}).get("intent"),
                        "task_id": body.get("task_id"),
                        "creates_task": created,
                        "ok": ok,
                    }
                )
    return {
        "probe": "L-R2-ROUTING-QA/api_negative_routing",
        "evidence_boundary": "component/API ONLY; default UnavailableExecutor, no SDK",
        "cases": rows,
        "passed": all(row["ok"] for row in rows),
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="l-r2-neg-") as tmp:
        report = asyncio.run(_run(Path(tmp)))
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
