#!/usr/bin/env python3
"""LG-032 workspace-boundary fix — 0-fake proof (no model, no network).

Builds the REAL product default layout (``workspace_root = <data_dir>/workspaces``)
with a real ``AntigravityExecutor`` and a real ``GraphWorkspaceProvider`` (real
``WorktreeManager``), then asserts the selection scratch lands inside the
executor's authorized root and is accepted.  Also asserts a path outside the
root is still rejected (authority is not widened).  Exit 0 on PASS.

This is a provider-substitute proof of *the boundary*, not a formal 032 sample:
product real generation stays 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter import ResourceCompiler  # noqa: E402
from lightgravity.adapter.executor import AdapterConfigInvalid, AntigravityExecutor  # noqa: E402
from lightgravity.coordinator import DispatchContext, GraphDispatcher, RoleCatalog  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@e"}
    for cmd in (["git", "init", "-q"], ["git", "commit", "-q", "--allow-empty", "-m", "base"]):
        subprocess.run(cmd, cwd=path, check=True, env={**__import__("os").environ, **env},
                       capture_output=True)
    return path


def main() -> int:
    results: list[tuple[str, bool, object]] = []
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        data_dir = base / "bot-data"
        # PRODUCT DEFAULT layout: workspace_root is a SUBDIRECTORY of data_dir.
        workspace_root = data_dir / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        repo = _git_repo(workspace_root / "task-ws")

        store = FileStore(data_dir, workspace_root)
        executor = AntigravityExecutor(store, ResourceCompiler(store),
                                       workspace_root=workspace_root)
        dispatcher = GraphDispatcher(
            store, executor, catalog=TEAM,
            workspaces=GraphWorkspaceProvider(WorktreeManager(workspace_root)),
            autonomous_pool=True,
        )
        save_dir = data_dir / "native-sessions" / "task_proof"
        ctx = DispatchContext(
            task_id="task_proof", run_id="run_01PROOFBOUNDARY", attempt=1,
            objective="select a candidate", workspace_path=str(repo),
            save_dir=str(save_dir),
        )

        scratch = Path(dispatcher._selection_workspace(ctx, "slot_run_proof_0")).resolve()
        root_real = workspace_root.resolve()
        inside = scratch == root_real or root_real in scratch.parents
        results.append(("scratch_inside_authorized_root", inside, str(scratch)))

        try:
            resolved = executor._resolve_workspace(str(scratch))
            accepted = resolved == scratch
        except AdapterConfigInvalid as exc:
            accepted = False
            results.append(("executor_accepts_scratch_error", False, str(exc)))
        results.append(("executor_accepts_scratch", bool(accepted), str(scratch)))

        outside = base / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        try:
            executor._resolve_workspace(str(outside))
            rejected = False
        except AdapterConfigInvalid:
            rejected = True
        results.append(("out_of_root_still_rejected", rejected, str(outside)))

    ok = all(passed for _name, passed, _detail in results)
    for name, passed, detail in results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} {detail}")
    print(json.dumps({"ok": ok, "real_generation": 0,
                      "checks": [{"name": n, "passed": p} for n, p, _ in results]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
