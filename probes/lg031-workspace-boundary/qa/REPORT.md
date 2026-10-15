# LG031-BOUNDARY-QA — REPORT (independent QA)

- **Gate**: BOUNDARY-R1 (LG-031 workspace-boundary fix)
- **Verdict**: **PASS** (mechanism-fixed, real-SDK product-default-layout, 0 primary provider)
- **QA role**: independent (not the source implementer, not the fix owner)
- **Base under test**: `fix/lg031-workspace-boundary@0814b80` (`0814b80a02f22d7b65623dc7f286650ddffdc6ca`)
- **QA branch**: `qa/lg031-boundary`; **worktree**: `/home/yhvh/code/lightgravity-bot-worktrees/lg031-boundary`
- **merge-base(main, HEAD)**: `3def2941a3f147aded25ac509d3c91d1bd3bd245`
- **SDK**: pinned `google-antigravity==0.1.22` (`adapter/capabilities.py::SDK_PINNED_VERSION`, `uv.lock`)
- **Provider**: real DeepSeek configured in env, but this QA used **0 primary provider generation**.
  The real-SDK run used the **local fake OpenAI SSE upstream** (loopback only; no outbound POST).
- **Product read-only**: no product file changed by this QA. `git diff -- backend/ tests/` is empty.
- **Report version**: initial (written before round 60).

## Exact commit / hashes

| Item | Value |
|---|---|
| base commit | `0814b80a02f22d7b65623dc7f286650ddffdc6ca` |
| branch | `qa/lg031-boundary` |
| merge-base with main | `3def2941a3f147aded25ac509d3c91d1bd3bd245` |
| `backend/lightgravity/coordinator/graph.py` | `sha256:1aebbde175ab3832e491bdc41c324d6ee5dbc59713410dcaf1affcfe064245cf` |
| `backend/lightgravity/workspaces/manager.py` | `sha256:849417478888a7bc1187e79fe3af2155dd5fb135a49a84d8208da2eb54f91648` |
| `backend/lightgravity/workspaces/provider.py` | `sha256:c8d14b56c4d2c27d653172f6be8f65cc85abb1f4d3f033047acb26c621eb7934` |
| real-SDK probe evidence | `sha256:9655ca465e0eaf460036d0996a96731d46a0ae4d005cc0f7864637276633da66` |

The three product files above are the **entire** fix delta; `collaboration/` (grant/lease/fence/handoff)
and `adapter/` (executor/budget) are untouched (see below).

## Defect under test (from `probes/lg031-workspace-boundary/DEFECT-REPRO.md`)

Product default: `workspace_root = <data_dir>/workspaces` (a subdir of `data_dir`), while Task
`save_dir = <data_dir>/native-sessions/<task>` (outside that root). Pre-fix the candidate-pool
**selection scratch** was created under `save_dir`, which the real `AntigravityExecutor` honestly
rejects (`escapes the authorized root`). Every arm-B Run under product defaults failed at selection.

## Gate BOUNDARY-R1 — item-by-item

| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | Real default bootstrap/`create_app` + legal 3-node pool scenario | **PASS** | `qa/evidence/qa_default_bootstrap_probe.txt`; real `Settings.from_env` + `build_runtime` wired, no wiring warning |
| 2 | Selector scratch truly inside SDK authorized root | **PASS** | `qa/evidence/qa_boundary_probe.txt`, `qa/evidence/product-default-two-phase-sdk.json` (`scratch_inside_root=true`) |
| 3 | No write tools before selection; after selection real SDK binds selected node's workspace | **PASS** | `product-default-two-phase-sdk.json`: `selection_phase_has_no_product_write_tool=true`, beta (non-first) selected, each artifact in its own worktree, `writer_collision_into_wrong_node=false` |
| 4 | All refs enter stopgate / SDK confirmed-closed / not-stopped held | **PASS** | `product-default-two-phase-sdk.json` `stop_confirmation={confirmed:true, sessions_stopped:4/4, proxy_stopped:true, unknown_sessions:[]}` |
| 5 | Out-of-root really rejected | **PASS** | `qa_boundary_probe.txt` (`data_dir` itself, sibling worktrees root outside, arbitrary outside, pre-fix save_dir scratch all rejected) |
| 6 | Real SDK 0.1.22 + loopback fake upstream, not FakeExecutor-as-SDK | **PASS** | `real_sdk_version="0.1.22"`; harness uses real `AntigravityExecutor`; provider = local fake SSE; no outbound POST |
| 7 | No root widening / no `data_dir` as write authority / no monkeypatch of executor root or stopgate | **PASS** | fix delta is 3 files; only relative path resolution changed; `git diff` shows no stopgate/executor edits |
| 8 | New `workspaceprovider` interface compat; residual recovery/leasefence/budget/diffhandoff impact | **PASS (with one low note)** | see "Interface & residual scope" below |
| 9 | Independent negative: real `SdkExecutor` rejects out-of-bound; product-normal-bootstrap re-verify of original minimal repro | **PASS** | `qa_boundary_probe.txt` checks 1–3; `qa_default_bootstrap_probe` reproduces product default layout |
| 10 | Small-scope pytest/mypy for the change | **PASS** | see "Commands" below |

## Interface & residual scope (item 8)

The fix adds:
- `WorktreeManager.selection_scratch_root(run_id) -> Path` (calls `_authorize`, cannot escape root).
- `GraphWorkspaceProvider.selection_scratch_root(run_id) -> Path | None` (returns `None` when no manager;
  swallows `WorkspaceError`).
- `GraphDispatcher._selection_scratch_root(context)` using `getattr(provider, "selection_scratch_root", None)`;
  falls back to `context.workspace_path` when absent.

Compatibility: `WorkspaceProvider` Protocol is unchanged (the new method is optional, looked up via
`getattr`), so old providers without it keep working (verified: `4_no_method_provider_falls_back`).
`None` never becomes a new root.

**Low-severity interface note (non-blocking):** `GraphDispatcher._selection_scratch_root` itself has no
`try/except`; it relies on the provider swallowing its own `WorkspaceError`. The shipped
`GraphWorkspaceProvider` does swallow it, so this is **not reachable product behaviour** for the current
provider set. Recorded so a future provider that lets `WorkspaceError` escape does not turn a benign
fallback into a Run crash. Probe check `4c_dispatcher_does_not_swallow_raw_provider_error=true` documents it.

Residual recovery scope / lease fence / budget / diff handoff: **not touched** — the fix delta contains
no changes to `backend/lightgravity/collaboration/**` (grant/lease/fence/handoff) or
`backend/lightgravity/adapter/**` (executor/budget). Selection grant is still revoked after phase 1 and the
pool grant never acts as an execution identity (unchanged code path at `coordinator/graph.py:1000+`).

## Commands (real exit codes)

All saved raw under `probes/lg031-workspace-boundary/qa/evidence/`.

| Command | Result | Exit |
|---|---|---|
| `uv run --frozen python probes/lg031-workspace-boundary/proof_boundary.py` (owner proof) | ok=true | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_boundary_probe.py` (independent negative) | all checks pass | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_default_bootstrap_probe.py` | all checks pass | 0 |
| `uv run --frozen python probes/lg031-workspace-boundary/qa/qa_product_default_two_phase_sdk.py` | ok=true, failed_gates=[] | 0 |
| `uv run --frozen pytest tests/collaboration/test_lg031_pool_selection.py -q -p no:randomly` | 13 passed | 0 |
| `uv run --frozen pytest tests/collaboration tests/coordinator tests/workspaces tests/adapter -q -p no:randomly` | 329 passed | 0 |
| `uv run --frozen mypy backend/lightgravity/coordinator/graph.py backend/lightgravity/workspaces/` | Success, 5 files | 0 |

## Provider / cost / budget

- Primary provider generation: **0**. The real-SDK probe used a local fake SSE upstream over loopback
  (no outbound POST). No cost sampling performed. This QA does **not** mark LG-032 done.
- LG-032 formal attempts remain **0**; total 192 / each 48 unchanged.

## Limitations / honest non-claims

1. The real-SDK product-default-layout run is a **provider-substitute** (local fake upstream), not a
   real-DeepSeek end-to-end sample. It proves the **boundary/lifecycle mechanism**, not model quality.
2. The full default `CoordinatorWorkerLoop` async loop against a real model was **not** run here
   (would consume real provider budget and belongs to LG-032 formal sampling). Item 1 was verified
   structurally (real `build_runtime` + real executor wired + exact bootstrap wiring asserted).
3. The RUNTIME-AUTH-INTEGRATION probe as-shipped did **not** reproduce the defect (its `save_dir` is
   `None`, so the pre-fix fallback used `workspace_path`, inside the root). This QA therefore added a
   product-default-`save_dir` variant (`qa_product_default_two_phase_sdk.py`) that exercises the actual
   defect path end-to-end. The baseline probe still passes (`two-phase-sdk-baseline.json`).
4. One low-severity interface note (item 8 above); no blocking defect found.

## Verdict

**BOUNDARY-R1: PASS.** The fix roots the selection scratch inside the executor-authorized root without
widening authority, keeps selection write-free, binds the selected node's real worktree in execution,
records all sessions and confirms stop, and is compatible with the existing provider seam. Product tree
unchanged by this QA. **Suggested for LG-031 done pending LG-032** (the real-SDK multi-worker engineering
evidence at 86 legacy generations remains valid; the path change is covered here by the
product-normal-bootstrap fake proof). This QA does **not** itself merge to main or write task status.
