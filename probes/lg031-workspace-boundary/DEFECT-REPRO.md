# LG-032 workspace-boundary defect — minimal repro & impact (owner: pi-lg032)

## Defect (product)

The autonomous claim **selection** phase (LG-031 POOL-FIX, contract 1.11.0)
creates its SDK scratch workspace under the Task `save_dir`:

    <data_dir>/native-sessions/<task_id>/.lg-pool-selection/<run_id>/<slot>

(`GraphDispatcher._selection_workspace`, `coordinator/graph.py`), while the real
`AntigravityExecutor` only authorizes `Settings.workspace_root`.  The product
**default** sets that root to `<data_dir>/workspaces` (`config.py:48`), a
*subdirectory* of `data_dir`.  The scratch therefore never lies inside the
authorized root, so the real executor honestly rejects it:

    AdapterConfigInvalid: workspace '.../native-sessions/.../.lg-pool-selection/...'
    escapes the authorized root '...'

and the selection session blocks -> the Run fails.  Reachable under the normal
default bootstrap, so it is a real product defect, not a harness misconfiguration.

## Minimal repro (offline, no model/network)

```python
# workspace_root = <data_dir>/workspaces  (product default layout)
provider = GraphWorkspaceProvider(WorktreeManager(workspace_root))
dispatcher = GraphDispatcher(store, real_AntigravityExecutor, workspaces=provider,
                             autonomous_pool=True)
ctx = DispatchContext(..., workspace_path=<repo>, save_dir=<data_dir>/native-sessions/<task>)
scratch = dispatcher._selection_workspace(ctx, "slot")
real_executor._resolve_workspace(scratch)   # -> raises "escapes the authorized root"
```

Pinned offline by `tests/collaboration/test_lg031_pool_selection.py::
test_selection_scratch_lives_inside_authorized_root` (pre-fix: scratch under
save_dir, rejected) and `::test_selection_scratch_out_of_root_still_rejected`.

## Impact

- Trigger: `decentralized_claim_enabled=true` + `autonomous_pool=true` + a real
  executor (workspace-boundary enforcement active).
- Affected: F1 candidate-pool autonomous selection is unusable under product
  defaults — every arm-B Run fails at selection.
- Not affected: the deterministic single-node path (arm A), which creates no
  selection scratch; grant/lease/fence/budget/stopgate logic; `max_parallel`.
- Not caught before: the existing LG-031 pool test uses `PoolWorkerSim`, a fake
  executor with no workspace-root enforcement.

## Fix (minimal, no authority widening)

Root the selection scratch under the Run's own **authorized** worktree area
(`<workspace_root>/.lg-worktrees/<run_id>/.lg-pool-selection/<slot>`), the same
isolation seam real write nodes already use:

- `WorktreeManager.selection_scratch_root(run_id)` returns the authorized Run
  worktree directory (via `_authorize`, so it cannot escape the root).
- `GraphWorkspaceProvider.selection_scratch_root(run_id)` exposes it; returns
  `None` (never a new root) if there is no manager.
- `GraphDispatcher._selection_workspace` uses it; falls back to the shared
  workspace path when no provider is wired.

No new root, no permission widening, no widening to sibling worktrees; the
selection phase still carries no write tools; default remains off.
