# LG031-BOUNDARY-QA — PLAN

## Objective

Independently verify the LG-031 workspace-boundary fix (`fix/lg031-workspace-boundary@0814b80`)
against gate BOUNDARY-R1, without modifying product code. Report PASS/FAIL + limitations + commands +
exit codes + provider count (0 primary) + artifact paths + version hashes + formal-candidate verdict.

## Method

### Phase 1 — Static/structural audit (0 provider)
- Diff audit of the fix: `coordinator/graph.py`, `workspaces/manager.py`, `workspaces/provider.py`,
  tests. Confirm minimality, no authority widening, no monkeypatch.
- Confirm `selection_scratch_root` interface: back-compat (provider Protocol unaffected, callers use
  `getattr`) and `WorkspaceError` fallback semantics.
- Verify no reference to `data_dir` as write authority; scratch root is under `workspace_root`.

### Phase 2 — Real boundary proof (0 provider, real executor)
- Run existing `probes/lg031-workspace-boundary/proof_boundary.py` (real `AntigravityExecutor`,
  real `GraphWorkspaceProvider`/`WorktreeManager`, product default layout).
- Independent negative: real executor `_resolve_workspace` must reject out-of-root paths
  (a sibling worktree, the old save_dir scratch, `data_dir` itself).
- Re-verify the **original minimal repro** from `DEFECT-REPRO.md` (pre-fix scratch under save_dir)
  is now fixed and that the pre-fix path is still rejected by the real executor.

### Phase 3 — Product-default bootstrap path (0 provider)
- Build the real default runtime via `bootstrap`/`build_runtime` (real `GraphDispatcher`,
  real `GraphWorkspaceProvider`, `autonomous_pool=True`, decentralized on).
- Run the legal 3-node pool scenario offline with a real SDK session? -> Only with loopback fake
  upstream + real SDK 0.1.22. If the mature harness exists (harness snapshot / RUNTIME-AUTH probe),
  reuse it to prove: selector scratch inside root; selection phase has no write tools; selected node's
  workspace bound in execution; refs recorded; stopgate confirmed.
- If no mature fake harness is available offline within budget: focus on the original minimal repro
  (as instructed) and clearly mark the 3-node real-SDK pool end-to-end as NOT-RUN with reason, rather
  than expanding into full-product debugging.

### Phase 4 — Regression checks
- Targeted pytest: `tests/collaboration/test_lg031_pool_selection.py` and the boundary tests.
- `mypy` on changed modules / whole tree if cheap.
- Confirm no changes to `api/collaboration.py`, stopgate, lease fence, budget, diff handoff semantics.

## Deliverables
- `REPORT.md` (initial version before round 60, committed).
- Raw command outputs under `qa/evidence/`.
- STATUS updated each phase.

## Constraints honored
- Product read-only; no self-fix. Important source bugs -> REPORT to PM (do not fix).
- 0 primary provider generation. No outbound POST. No FakeExecutor-as-SDK.
- No rm/rmtree/reset/clean/overwrite; no push/deploy/publish; do not touch 8123 or other packages.
- Do not mark 032 done; do not sample cost.
