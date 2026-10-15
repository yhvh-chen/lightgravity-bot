# LG031-BOUNDARY-QA — STATUS (independent QA, qa/lg031-boundary)

- **Role**: independent QA (NOT source implementer). Product read-only, no self-fix.
- **Worktree**: `/home/yhvh/code/lightgravity-bot-worktrees/lg031-boundary`
- **Branch**: `qa/lg031-boundary`
- **Base**: `fix/lg031-workspace-boundary@0814b80` (`0814b80a02f22d7b65623dc7f286650ddffdc6ca`)
- **merge-base(main, HEAD)**: `3def2941a3f147aded25ac509d3c91d1bd3bd245`
- **Provider**: real DeepSeek via env, real provider=0 primary; loopback/fake upstream allowed. No nested proxy.
- **Scope owner**: `qa/lg031-workspace-boundary/**` only.
- **Preservation**: all raw/worktree/failures kept. No rm/rmtree/reset/clean/overwrite. No push/deploy/publish.
- **Budget**: wall 600s; max round 130; noncache 160k; idle 150; retry 0. No cost sampling. Do not mark 032 done.
- **032 formal attempts**: 0; total 192/each 48 unchanged.

## Gate BOUNDARY-R1 (must verify)

1. Real default `bootstrap`/`create_app` + `CoordinatorWorkerLoop` legal 3-node pool scenario.
2. Selector scratch now truly inside SDK authorized root.
3. No write tools before selection; after selection real SDK execution binds the workspace of the
   selected node.
4. All refs enter stopgate / SDK confirmed-closed / not-stopped held.
5. Out-of-root really rejected.
6. Use real SDK 0.1.22 + loopback fake upstream (not FakeExecutor pretending to be SDK). No outbound POST.
7. Fix must NOT widen root to other worktrees, must not treat data_dir as write authority, must not
   monkeypatch executor root / stopgate.
8. Check `workspaceprovider` new interface for compat issues; residual recovery scope / leasefence /
   budget / diffhandoff impact.
9. Independent negative: real `SdkExecutor` rejects out-of-bound; product-normal-bootstrap re-verify of
   original minimal repro. If an existing R1 full chain is reusable, cite it without needless re-run.
10. Small-scope pytest/mypy for the change. Single command may exceed 90s but results must be saved
    stepwise (no handoff lost).

## Round log

- R0: oriented; read agent.md, LG-031/LG-032 gates, DEFECT-REPRO.md, RUNTIME/AUTH integration notes,
  fix branch diff; created QA worktree. Wrote STATUS/PLAN.
- R1-R8: static/structural audit; ran owner proof + independent boundary negative probe; found & filed
  low interface note (dispatcher does not swallow raw provider WorkspaceError).
- R9-R16: real-SDK loopback two-phase run with product-default save_dir (reuses RUNTIME-AUTH harness).
  First attempt FAIL on an over-strict gate B (skill-discovery tools); refined to assert no *write*
  tool, re-ran PASS. Baseline RUNTIME-AUTH probe re-run PASS.
- R17-R20: default-bootstrap structural probe PASS; targeted mypy + affected pytest PASS; REPORT v1 written.

## Results summary

Gate BOUNDARY-R1: **PASS** (0 primary provider). Full detail in `REPORT.md`.
See `qa/evidence/` for raw outputs. Product tree unchanged by QA (`git diff -- backend/ tests/` empty).

