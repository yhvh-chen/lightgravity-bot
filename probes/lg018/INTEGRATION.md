# LG-018 integration notes (assembly point owned by the integration owner)

LG-018 ships a new, self-contained backend package
`backend/lightgravity/workspaces/` plus a small additive seam in
`coordinator/graph.py` (`GraphDispatcher(..., workspaces=...)`).  Per the batch
instruction I do **not** edit shared assembly files (`coordinator/service.py`,
`verify/**`, `api/tasks.py` owned by LG-017; `api/app.py`/frontend owned by
LG-019).  The one real assembly point that must be wired by the integration
owner is `backend/lightgravity/api/bootstrap.py` (shared integration file).

Without this wiring the isolation code is inert (the dispatcher keeps its
current, conservative `max_parallel=1` single-writer behavior).  This file
specifies the exact call site so parallelism is only enabled after real
isolation is proven.

## 1. Required change (single, additive)

In `build_runtime` (`api/bootstrap.py`), where the `GraphDispatcher` is built,
construct a real `WorktreeManager` over the authorized workspace root and pass a
`GraphWorkspaceProvider`:

```python
from ..workspaces import GraphWorkspaceProvider, WorktreeManager

# inside the `if options.wire_real_executor:` block, before GraphDispatcher(...):
workspace_manager = WorktreeManager(settings.workspace_root)
workspace_provider = GraphWorkspaceProvider(workspace_manager)

dispatcher = GraphDispatcher(
    store,
    executor,
    catalog=catalog,
    compiler=compiler,
    connections=connection_pins,
    workspaces=workspace_provider,   # <-- additive seam (LG-018)
)
```

No other production file needs a change for basic wiring.  `settings.workspace_root`
already exists (`LIGHTGRAVITY_WORKSPACE_ROOT`, default `<data_dir>/workspaces`).

## 2. Field/semantic contract already honored (no new wire fields)

- The manager writes nothing into `TASK.md`/`RUN.md`; it only creates real git
  worktrees under `<workspace_root>/.lg-worktrees/<run_id>/<node_key>/` and a
  `workspace.json` metadata file that freezes the **base commit** and each
  node's branch.  The `.lg-worktrees` directory must stay inside the authorized
  workspace root so the adapter's `_resolve_workspace` containment check passes.
- A write node's `ExecuteRequest.workspace_path` becomes its isolated worktree
  path (see `GraphDispatcher._build_request`).  Read-only nodes and non-git
  workspaces keep the shared path, so there is no silent semantic change.
- `config_hash`/`reuse_identity` are unaffected: `CompiledAgentConfig.config_hash`
  does not include `workspace_path`, so the LG-016 anti-replay guard still holds.
- **`max_parallel` stays conservative by default.**  Only raise it (to 2) once
  this wiring is present *and* the real-git evidence in
  `probes/lg018/reports/LG-018-report.md` is reviewed.  A non-git or
  unauthorized workspace yields `None` from the provider, and the dispatcher
  then serializes the write nodes — it never fakes parallelism.

## 3. Additional optional wiring (integration owner's decision)

- **Candidate integration on acceptance-adjacent flows**: `WorktreeSession.integrate(...)`
  merges node branches on a dedicated integration branch/worktree and returns
  `conflicted=True` (with real conflicting paths) instead of auto-resolving.
  The Run should pause (keep lock + worktrees) and surface the conflict to the
  user.  This is deliberately *not* wired into `verify/**` (LG-017 owner).
- **Cleanup**: call `session.cleanup(confirmed_stop=True, delivered_branches=[...])`
  only after a **confirmed** stop *and* after the candidate was actually
  delivered/accepted.  A merged-but-undelivered candidate is retained.

## 4. Boundaries / limitations (do not overstate)

- This is **write isolation**, not a security sandbox.  A worktree shares the
  repository object store and the host process; it does not confine a hostile
  process.  The adapter's loopback proxy and tool policy remain the credential
  boundary (docs/08 §8.1).
- Git subprocesses run with `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL`/`SYSTEM`
  isolated, `core.hooksPath` redirected to an empty dir, and an allow-listed
  child environment (inherited secret env vars are not forwarded).  This bounds
  *git*, not the executor's own model/tool subprocesses.
- Path operations reject lexical `..` escapes, symlink escapes and `.git`
  components, all under `realpath` containment against the authorized root.

## 5. Test entry points

- `tests/workspaces/test_worktree_manager.py` — real-git isolation, parallel
  writes, non-conflicting/conflicting integration, dirty-HEAD preservation,
  stop/lock semantics, recovery retention.
- `tests/workspaces/test_graph_isolation.py` — real dispatcher wiring: two write
  nodes get distinct worktrees and run concurrently (peak 2); without the
  provider they are conservatively serialized.
- `tests/workspaces/test_boundaries.py` — hooks not executed, secret env not
  forwarded, `.git`/symlink escape rejection.

Run: `uv run pytest tests/workspaces -q`.
