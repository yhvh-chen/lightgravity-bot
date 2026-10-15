#!/usr/bin/env python3
"""LG031-BOUNDARY-QA independent boundary probe (0 provider, real executor).

This is the INDEPENDENT QA probe (not the fix owner's proof).  It re-verifies:

 1. ORIGINAL MINIMAL REPRO (from probes/lg031-workspace-boundary/DEFECT-REPRO.md):
    product default layout ``workspace_root = <data_dir>/workspaces`` with a Task
    ``save_dir = <data_dir>/native-sessions/<task>`` OUTSIDE the root.  Pre-fix the
    selection scratch landed under save_dir and the real executor rejected it.
    Now the scratch must land inside the authorized root and be accepted.

 2. The PRE-FIX scratch location (under save_dir) is STILL honestly rejected by
    the real executor (the fix relocated the scratch; it did not widen authority).

 3. Authority is NOT widened: sibling worktrees, ``data_dir`` itself, and an
    arbitrary outside dir are all rejected by the real executor.

 4. Interface back-compat: a provider WITHOUT ``selection_scratch_root`` (the old
    Protocol shape) still works (falls back, never crashes); the real provider
    returns ``None`` (never a new root) when there is no manager; a provider whose
    method raises ``WorkspaceError`` returns ``None``.

Exit 0 iff every check passes.  real generation = 0, no network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

from lightgravity.adapter import ResourceCompiler  # noqa: E402
from lightgravity.adapter.executor import AdapterConfigInvalid, AntigravityExecutor  # noqa: E402
from lightgravity.coordinator import (  # noqa: E402
    DispatchContext,
    GraphDispatcher,
    RoleCatalog,
)
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.workspaces import GraphWorkspaceProvider, WorktreeManager  # noqa: E402
from lightgravity.workspaces.manager import WorkspaceError  # noqa: E402

TEAM = RoleCatalog({"implementation": ["developer"], "verification": ["verifier"]})


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
    }
    for cmd in (["git", "init", "-q"], ["git", "commit", "-q", "--allow-empty", "-m", "base"]):
        subprocess.run(
            cmd, cwd=path, check=True, env={**os.environ, **env}, capture_output=True
        )
    return path


class _NoScratchProvider:
    """Old Protocol shape: no ``selection_scratch_root`` at all."""

    def isolate(self, **kwargs):  # noqa: ANN003
        return None

    def release(self, *, run_id: str, confirmed_stop: bool):  # noqa: ANN001
        return []


class _RaisingProvider:
    """Provider mirroring ``GraphWorkspaceProvider``: swallows its own
    ``WorkspaceError`` and returns ``None`` (the shipped contract)."""

    def __init__(self, store: FileStore) -> None:
        self._store = store

    def selection_scratch_root(self, run_id: str) -> Path | None:
        try:
            raise WorkspaceError("simulated unauthorized run root")
        except WorkspaceError:
            return None

    def isolate(self, **kwargs):  # noqa: ANN003
        return None

    def release(self, *, run_id: str, confirmed_stop: bool):  # noqa: ANN001
        return []


class _RawRaisingProvider:
    """Provider that does NOT swallow ``WorkspaceError`` (robustness probe)."""

    def selection_scratch_root(self, run_id: str) -> Path:
        raise WorkspaceError("simulated unauthorized run root")

    def isolate(self, **kwargs):  # noqa: ANN003
        return None

    def release(self, *, run_id: str, confirmed_stop: bool):  # noqa: ANN001
        return []


def main() -> int:
    checks: list[tuple[str, bool, object]] = []

    def record(name: str, passed: bool, detail: object = "") -> None:
        checks.append((name, bool(passed), detail))

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        data_dir = base / "bot-data"
        # PRODUCT DEFAULT: workspace_root is a SUBDIRECTORY of data_dir.
        workspace_root = data_dir / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)
        repo = _git_repo(workspace_root / "task-ws")
        store = FileStore(data_dir, workspace_root)
        executor = AntigravityExecutor(
            store, ResourceCompiler(store), workspace_root=workspace_root
        )
        provider = GraphWorkspaceProvider(WorktreeManager(workspace_root))
        dispatcher = GraphDispatcher(
            store,
            executor,
            catalog=TEAM,
            workspaces=provider,
            autonomous_pool=True,
        )
        # Product default save_dir: OUTSIDE workspace_root.
        save_dir = data_dir / "native-sessions" / "task_qa_boundary"
        ctx = DispatchContext(
            task_id="task_qa_boundary",
            run_id="run_01QABOUNDARY",
            attempt=1,
            objective="select a candidate",
            workspace_path=str(repo),
            save_dir=str(save_dir),
        )

        scratch = Path(dispatcher._selection_workspace(ctx, "slot_qa_0")).resolve()
        root_real = workspace_root.resolve()
        record(
            "1_scratch_inside_authorized_root",
            scratch == root_real or root_real in scratch.parents,
            str(scratch),
        )
        record(
            "1_scratch_not_under_save_dir",
            not (scratch == save_dir.resolve() or save_dir.resolve() in scratch.parents),
            str(save_dir),
        )
        try:
            resolved = executor._resolve_workspace(str(scratch))
            record("1_real_executor_accepts_scratch", resolved == scratch, str(resolved))
        except AdapterConfigInvalid as exc:
            record("1_real_executor_accepts_scratch", False, str(exc))

        # 2. Pre-fix location (under save_dir) must STILL be rejected.
        old_scratch = (save_dir / ".lg-pool-selection" / "run_01QABOUNDARY" / "slot_qa_0").resolve()
        old_scratch.mkdir(parents=True, exist_ok=True)
        try:
            executor._resolve_workspace(str(old_scratch))
            record("2_prefix_scratch_still_rejected", False, "NOT rejected")
        except AdapterConfigInvalid:
            record("2_prefix_scratch_still_rejected", True, str(old_scratch))

        # 3. Authority not widened.  NOTE: a path under
        # ``workspace_root/.lg-worktrees/<other_run>/`` IS inside the authorized
        # root and is correctly accepted by the real executor -- that is the
        # existing isolation seam, not a widening.  The negatives are paths
        # OUTSIDE the authorized root: data_dir itself, a sibling worktrees root
        # outside, and an arbitrary outside dir.
        for label, candidate in (
            ("3_data_dir_itself_rejected", data_dir),
            ("3_sibling_worktrees_root_outside_rejected", data_dir / "other-worktrees" / "run" / "n"),
            ("3_arbitrary_outside_rejected", base / "outside" / "x"),
        ):
            candidate = Path(candidate)
            candidate.mkdir(parents=True, exist_ok=True)
            try:
                executor._resolve_workspace(str(candidate.resolve()))
                record(label, False, "NOT rejected")
            except AdapterConfigInvalid:
                record(label, True, str(candidate))

        # 4. Interface back-compat.
        d_none = GraphDispatcher(store, executor, catalog=TEAM, workspaces=_NoScratchProvider(), autonomous_pool=True)
        scratch_none = d_none._selection_workspace(ctx, "slot_x")
        record("4_no_method_provider_falls_back", scratch_none == str(repo), scratch_none)
        record("4_no_method_scratch_root_is_none", d_none._selection_scratch_root(ctx) is None)

        d_raise = GraphDispatcher(store, executor, catalog=TEAM, workspaces=_RaisingProvider(store), autonomous_pool=True)
        record("4_raising_provider_root_is_none", d_raise._selection_scratch_root(ctx) is None)
        record("4_raising_provider_falls_back", d_raise._selection_workspace(ctx, "slot_y") == str(repo))

        # 4c. Robustness observation (non-gating): a provider whose method
        # raises (does not swallow WorkspaceError) makes the dispatcher raise,
        # i.e. _selection_scratch_root has no try/except of its own.  The
        # shipped GraphWorkspaceProvider swallows WorkspaceError so this is not
        # reachable product behaviour; recorded only as an interface note.
        d_raw = GraphDispatcher(store, executor, catalog=TEAM, workspaces=_RawRaisingProvider(), autonomous_pool=True)
        try:
            d_raw._selection_scratch_root(ctx)
            raw_raised = False
        except Exception:  # noqa: BLE001
            raw_raised = True
        record("4c_dispatcher_does_not_swallow_raw_provider_error", raw_raised, raw_raised)

        # 4b. Real provider returns None (never a new root) when no manager.
        provider_none = GraphWorkspaceProvider.__new__(GraphWorkspaceProvider)
        provider_none._manager = None  # type: ignore[attr-defined]
        provider_none._sessions = {}  # type: ignore[attr-defined]
        record(
            "4_real_provider_no_manager_returns_none",
            provider_none.selection_scratch_root("run_x") is None,
        )

    ok = all(passed for _n, passed, _d in checks)
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} {detail}")
    print(
        json.dumps(
            {
                "ok": ok,
                "real_generation": 0,
                "provider": "none(real-executor boundary only)",
                "checks": [{"name": n, "passed": p} for n, p, _ in checks],
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
