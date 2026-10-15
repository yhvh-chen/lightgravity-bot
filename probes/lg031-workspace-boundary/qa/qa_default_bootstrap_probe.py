#!/usr/bin/env python3
"""LG031-BOUNDARY-QA default-bootstrap structural boundary probe.

Verifies the **product default bootstrap** layout and wiring:

 1. ``Settings.from_env`` with only ``LIGHTGRAVITY_DATA_DIR`` set yields the
    product default layout ``workspace_root = <data_dir>/workspaces`` (a SUBDIR
    of data_dir); Task ``save_dir = <data_dir>/native-sessions/<task>`` is
    OUTSIDE that root.
 2. Real ``build_runtime(StartupOptions)`` (the default ``create_app`` assembly
    path) wires the real executor with no "executor could not be wired" warning.
 3. A ``GraphDispatcher`` assembled with the SAME wiring ``api/bootstrap.py``
    uses (``GraphWorkspaceProvider(WorktreeManager(settings.workspace_root))``,
    ``autonomous_pool`` on) resolves the selection scratch INSIDE the authorized
    ``workspace_root`` and the real executor accepts it -- while the pre-fix
    save_dir location is still rejected.  The wiring line in bootstrap.py is
    read from source and asserted to match, so this does not silently diverge.

0 provider (no model call); real assembly + real executor boundary.  Exit 0 iff
all checks pass.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent
REPO = QA_DIR.parents[2]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter import ResourceCompiler  # noqa: E402
from lightgravity.adapter.executor import AntigravityExecutor  # noqa: E402
from lightgravity.api.bootstrap import StartupOptions, build_runtime  # noqa: E402
from lightgravity.config import Settings  # noqa: E402
from lightgravity.coordinator import (  # noqa: E402
    DispatchContext,
    GraphDispatcher,
    RoleCatalog,
)
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402

checks: list[tuple[str, bool, object]] = []
TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


def record(name: str, passed: bool, detail: object = "") -> None:
    checks.append((name, bool(passed), detail))


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td) / "bot-data"
        env = {"LIGHTGRAVITY_DATA_DIR": str(data_dir)}
        settings = Settings.from_env(env)
        record(
            "1_default_workspace_root_is_subdir_of_data_dir",
            settings.workspace_root == data_dir / "workspaces",
            str(settings.workspace_root),
        )
        record(
            "1_default_workspace_root_inside_data_dir",
            data_dir in settings.workspace_root.parents,
            str(settings.workspace_root),
        )
        record(
            "1_default_save_dir_layout_outside_root",
            not (settings.workspace_root == data_dir / "native-sessions"
                 or settings.workspace_root in (data_dir / "native-sessions").parents),
            f"save_dir under {data_dir / 'native-sessions'} vs root {settings.workspace_root}",
        )

        settings.ensure_data_dir()
        repo = settings.workspace_root / "task-bootstrap"
        repo.mkdir(parents=True, exist_ok=True)
        genv = {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@e",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@e",
        }
        for cmd in (["git", "init", "-q"], ["git", "commit", "-q", "--allow-empty", "-m", "base"]):
            subprocess.run(cmd, cwd=repo, check=True, env={**os.environ, **genv}, capture_output=True)

        runtime = build_runtime(
            StartupOptions(settings=settings, serve_frontend=False, tester=True)
        )
        record("2_default_bootstrap_executor_wired", bool(runtime.executor_wired), runtime.warnings[:2])
        record(
            "2_no_executor_wiring_warning",
            not any("executor could not be wired" in w for w in runtime.warnings),
            runtime.warnings[:3],
        )

        # Assert bootstrap.py wires exactly this seam (no silent divergence).
        bootstrap_src = (REPO / "backend" / "lightgravity" / "api" / "bootstrap.py").read_text()
        record(
            "2_bootstrap_wires_graph_workspace_provider",
            "GraphWorkspaceProvider(WorktreeManager(settings.workspace_root))" in bootstrap_src,
            "",
        )
        record(
            "2_bootstrap_enables_autonomous_pool_with_decentralized",
            re.search(r"autonomous_pool\s*=\s*decentralized", bootstrap_src) is not None,
            "",
        )

        # Assemble the dispatcher with the SAME wiring bootstrap uses.
        store = FileStore(settings.data_dir, settings.workspace_root)
        executor = AntigravityExecutor(
            store, ResourceCompiler(store), workspace_root=settings.workspace_root
        )
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            workspaces=GraphWorkspaceProvider(WorktreeManager(settings.workspace_root)),
            autonomous_pool=True,
        )
        ctx = DispatchContext(
            task_id="task_bootstrap_qa",
            run_id="run_01BOOTSTRAPQA",
            attempt=1,
            objective="select",
            workspace_path=str(repo),
            save_dir=str(data_dir / "native-sessions" / "task_bootstrap_qa"),
        )
        scratch = Path(dispatcher._selection_workspace(ctx, "slot_0")).resolve()  # noqa: SLF001
        root_real = settings.workspace_root.resolve()
        record(
            "2_bootstrap_scratch_inside_authorized_root",
            scratch == root_real or root_real in scratch.parents,
            str(scratch),
        )
        try:
            accepted = executor._resolve_workspace(str(scratch)) == scratch  # noqa: SLF001
            record("3_real_executor_accepts_bootstrap_scratch", accepted, str(scratch))
        except Exception as exc:  # noqa: BLE001
            record("3_real_executor_accepts_bootstrap_scratch", False, str(exc))

        old = (data_dir / "native-sessions" / "task_bootstrap_qa" / ".lg-pool-selection").resolve()
        old.mkdir(parents=True, exist_ok=True)
        try:
            executor._resolve_workspace(str(old))  # noqa: SLF001
            record("3_prefix_save_dir_still_rejected", False, "NOT rejected")
        except Exception:  # noqa: BLE001
            record("3_prefix_save_dir_still_rejected", True, str(old))

    ok = all(p for _n, p, _d in checks)
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} {detail}")
    print(json.dumps({"ok": ok, "real_generation": 0,
                      "checks": [{"name": n, "passed": p} for n, p, _ in checks]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
