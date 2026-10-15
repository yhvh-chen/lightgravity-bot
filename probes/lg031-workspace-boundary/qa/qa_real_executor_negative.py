#!/usr/bin/env python3
"""LG031-BOUNDARY-QA — real-SDK-executor integration negative (0 provider).

Calls the REAL ``AntigravityExecutor.execute`` with a workspace path OUTSIDE the
authorized root and asserts it BLOCKS with the honest ``path_outside`` failure
(never silently runs, never widens authority, no model call / no upstream).

This complements the direct ``_resolve_workspace`` negative: it proves the
rejection happens on the real execution entry point, not only an internal helper.

0 provider (blocked before any model call).  Exit 0 iff all checks pass.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent
REPO = QA_DIR.parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "tests" / "coordinator"))
sys.path.insert(0, str(REPO / "tests" / "workspaces"))

from graph_helpers import build_environment  # noqa: E402

from lightgravity.adapter import (  # noqa: E402
    AntigravityExecutor,
    DirectoryArtifactSink,
    ExecuteRequest,
    InMemoryCredentialResolver,
    ResourceCompiler,
)
from lightgravity.store import FileStore  # noqa: E402

checks: list[tuple[str, bool, object]] = []


def record(name: str, passed: bool, detail: object = "") -> None:
    checks.append((name, bool(passed), detail))


async def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        data_dir = tmp / "bot-data"
        workspace_root = data_dir / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        store = FileStore(data_dir, workspace_root)
        # Compile a real executable environment so execution reaches the
        # workspace-boundary check (not an earlier reference_invalid).
        build_environment(store, tool_refs=("view-file",))
        executor = AntigravityExecutor(
            store,
            ResourceCompiler(store),
            credential_resolver=InMemoryCredentialResolver({"worker-default": "sk-fake-qa"}),
            artifacts=DirectoryArtifactSink(tmp / "artifacts"),
            allow_loopback_upstream=True,
            model_calls_cap=1,
            generation_budget=None,
        )

        outside = (data_dir / "native-sessions" / "task_qa" / ".lg-pool-selection").resolve()
        outside.mkdir(parents=True, exist_ok=True)
        req = ExecuteRequest(
            task_id="task_qa",
            run_id="run_qa",
            subtask_id="subtask_qa",
            objective="should be blocked",
            workspace_path=str(outside),
            connection_ref="primary",
            agent_ref="developer",
        )
        events: list[dict] = []

        async def emit(event: dict) -> None:
            events.append(event)

        result = await executor.execute(req, emit)
        record("real_execute_blocks_out_of_root", result.state == "blocked", result.state)
        code = result.failure.code if result.failure else None
        message = result.failure.message if result.failure else ""
        # The executor honestly blocks with an adapter config-invalid carrying the
        # exact "escapes the authorized root" reason (the workspace check runs
        # before any model call).
        record("real_execute_blocks_config_invalid", code == "config_invalid", code)
        record(
            "real_execute_message_escapes_authorized_root",
            "escapes the authorized root" in (message or ""),
            message,
        )
        record(
            "real_execute_emitted_blocked_event",
            any(e.get("type") == "adapter.execution_blocked" for e in events),
            [e.get("type") for e in events],
        )
        record("real_execute_no_session_started", not any(
            e.get("type") == "adapter.session_started" for e in events
        ))

    ok = all(p for _n, p, _d in checks)
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} {detail}")
    print(json.dumps({"ok": ok, "real_generation": 0,
                      "checks": [{"name": n, "passed": p} for n, p, _ in checks]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
