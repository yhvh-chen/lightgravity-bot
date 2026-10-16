# REPORT — H-R1-INTEGRATION (LG-047 R1 repairs: F + G sequential integration)

**Type:** serial integration-before-independent-retest (NOT a version PASS, NOT a
new Task/Run, NOT the independent QA). **Owner:** H integration (`pi`).
**Base HEAD on entry:** `1d7095c` (root PM bind + R1 ledger-gap/R2-budget note).

> Related: [E-QA R1 FAIL](../E-QA/REPORT.md) (old candidate freeze, AUX only),
> [F-INTAKE-FIX-R1](../F-INTAKE-FIX-R1/REPORT.md),
> [G-DIALOGUE-FIX-R1](../G-DIALOGUE-FIX-R1/REPORT.md),
> [D-INTEGRATION](../D-INTEGRATION/REPORT.md).
> Durable raw logs: [`raw/`](raw/) (`mypy.log`, `pytest-full.log`, `smoke.log`).

## 1. Candidate / source tips / bindings

| Ref | SHA |
|---|---|
| Integration product HEAD (F+G+E merged) | `5a6ff2b` |
| E-QA R1 freeze (old candidate evidence, preserved as AUX) | `57809d4` |
| F native-intake repair branch tip | `fix/proto-material-intake-r1-20261016` @ `1821394` (code `09edad2`) |
| G dialogue/plan repair branch tip | `fix/proto-material-dialogue-r1-20261016` @ `8641010` |
| Pre-R1 candidate (D, LG-046) | `f7a32ac` |
| `HEAD:backend` tree | `1791679` |
| `HEAD:frontend` tree | `07618bb` = **byte-identical to `f7a32ac:frontend`** (B `552d839`, unchanged) |
| SDK / contract | `google-antigravity==0.1.22`; `contract_version` `1.12.0` (unchanged) |

## 2. Merge sequence (`--no-ff`, conservative)

1. `git merge --no-ff 57809d4` → `b2c312e` — E-QA R1 freeze/handoff (FAIL report +
   `seed_machine.py` + evidence). **Preserved, not renamed**; the report/seed are
   labelled **AUX-only** and are **never** treated as user-upload proof.
2. `git merge --no-ff 1821394` → `a639424` — F native text intake repair.
3. `git merge --no-ff 8641010` → `5a6ff2b` — G assistant-history + default-plan repair.

**No conflicts occurred.** F and G touch **disjoint** files (F: `backend/lightgravity/sources/**`,
`tests/sources/**`; G: `backend/lightgravity/coordinator/**`, `tests/coordinator/**`,
`tests/api/test_integration_wiring.py`, `tests/sources` untouched). Probe/report
paths are disjoint directories (`F-INTAKE-FIX-R1/`, `G-DIALOGUE-FIX-R1/`,
`E-QA/`). Therefore no conflict resolution was needed; **no product fixes** were
applied during integration, and no test was weakened.

## 3. Required checks (single completed runs, durable stdout)

| Check | Command | Result | EXIT | Log |
|---|---|---|---|---|
| Static types | `PYTHONPATH=backend mypy backend/lightgravity` | `Success: no issues found in 139 source files` | **0** | `raw/mypy.log` |
| **Full backend suite (F+G union, one run)** | `PYTHONPATH=backend pytest -q` | **930 passed, 2 skipped** | **0** | `raw/pytest-full.log` |
| Frontend `tsc`/build | **not re-run** — `HEAD:frontend` byte-identical to `f7a32ac:frontend` (B `552d839`); no frontend change | n/a | n/a | — |
| Combined zero-model API smoke | `smoke_combined_api.py` (see §4) | **8/8 checks OK** | **0** | `raw/smoke.log` |

`pytest` here is the **backend** test suite (`testpaths=["tests"]` under
`backend`); it is **not** a frontend suite. No new feature was added; the merged
candidate is exactly F ∪ G ∪ E over `1d7095c`.

## 4. Combined API zero-model smoke (actual factory default)

`probes/prototype-selected-material-20261016/H-R1-INTEGRATION/smoke_combined_api.py`
boots the **actual product factory** `lightgravity.api.app.create_app` (which
mounts `build_sources_router` itself) with the **real coordinator lifespan**;
only the **leaf executor is an in-process fake** (**fake-models, LOCAL ONLY, NOT
SDK/frontend-browser evidence**; **zero** real generation forwards —
`LIGHTGRAVITY_MAX_GENERATION_CALLS=0`). It asserts both repairs are wired
through the factory default, not a hand-assembled router:

- **F**: a real `POST /api/v1/sources` **`text/plain`** upload reaches terminal
  `extracted` (derivatives present) and `GET /sources/{id}/content?kind=auto`
  returns **200** with the exact body — produced by the native autopump, **no
  manual derivative seed**, **no OCR**.
- **G (default delivery plan)**: an ordinary generic Chat delivery with a
  selected source routes to a Task with a **program-derived acceptance criterion**
  + **authorized workspace**; phase advances past plan validation; the fake
  worker is dispatched with the **exact untrusted-wrapped selected body** and a
  real workspace boundary.
- **G (history + idempotency)**: a `direct` answered turn persists
  `assistant:<message_id>` **with `resolved_source_bindings` + `selected_context`**
  in the same conversation; a retried `message_id` adds **no duplicate row** and
  **no extra dispatch**.

Result JSON (see `raw/smoke.log`): `F_upload_status=extracted`,
`F_content_status=200`, `G_kind=task`, `G_derived_acceptance=true`,
`G_workspace_ref=true`, `G_phase_after_dispatch=waiting_user`,
`G_dispatched_requests=2`, `G_worker_got_body=true`, `G_workspace/body OK`,
`G_answer_kind=direct`, `G_assistant_persisted=true`, bindings present,
`G_duplicate_assistant_rows=1`, `G_extra_dispatch_on_retry=0`.

## 5. Documentation / contract updates (integration-owned)

- **docs/10**: qualified the old "省略字段 ⇒ 逐字节不变" claim to **optional
  request omission + existing response wire / model context** compatibility, and
  recorded the two **documented R1 bugfixes** (assistant-history persistence →
  legacy conversation row counts are **not** byte-identical; no-selection
  generic Chat delivery now produces a valid default rule plan). No rollback of
  the real fixes to satisfy old assertions.
- **docs/11**: added R1 current-facts — native plain/markdown success **without
  OCR**; **PDF/image unchanged, explicit OCR path**; selected reply + Sources
  **persisted** in history; deterministic file plan for generic Chat delivery;
  **`Sources` are NOT verified citations**.
- **README / PROJECT / PROGRESS / BACKLOG**: current-facts update (F+G merged
  candidate, `930 passed / 2 skipped`, `mypy` 139; LG-047 still in-progress, no
  version PASS; R2 budget 8, no claim the original 12-campaign was fully
  verified). `contract_version` stays `1.12.0` — **no fake version bump**.
- **backlog/tasks/LG-047.md**: fixed the D-report relative link to
  `../../probes/prototype-selected-material-20261016/D-INTEGRATION/REPORT.md`.

## 6. R1 ledger gap + R2 budget (recorded, not smoothed)

- R1 known real product request: **1** (Flow A answer via **auxiliary manual
  seed**), plus **one reserved** second-ledger entry orphaned by a harness
  `rm -rf` — the two ledgers do **not** reconcile to a single exact number
  (product-persistent 0/12 on the live instance; 1 reserved with no surviving
  durable proof). **Preserved as-is**; the original 12-call campaign is
  **not** claimed fully verified.
- **R2 replan**: fresh independent campaign with **≤8 new** product requests
  (all failures/worker/reviewer included), **retry 0**, pre-forward hard cap,
  ledger **never reset** across restarts, existing missing/corrupt campaign
  ledger ⇒ deny. R1 known request + failed samples kept **separate**.
- **No model calls** were made during this integration.

## 7. Stop state / boundary

- Merged `main` working tree: only the root-PM-authorized `backlog/tasks/LG-047.md`
  PM note was dirty on entry and is **preserved** (committed here with the
  integration); no `reset`/`stash`.
- Existing DeepSeek env only; **no native agents**; **no** product SDK/network/OCR/
  browser; **no** new deps; **no** push; **no** port `8123`; **no** new
  Task/Run/QA started by me; **no** broad new QA gate added per task.
- **LG-047 remains `in-progress`** — **no PASS, no done**.
- QA-R2: fresh independent persistent worktree
  `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-r2-20261016`
  on branch `qa/proto-material-r2-20261016` at the **new frozen candidate**;
  root PM dispatches a **different fresh pi** after this integration stops. QA
  must **not** reuse the old `start_run1.sh` `rm -rf` ledger pattern.
- **LG-041 stays blocked** (`todo`); all prior limits/out-of-scope unchanged.

## 8. Remaining gate (for QA-R2, not claimed here)

- Real SDK/DeepSeek end-to-end on the frozen candidate (≤8 new requests) with a
  real product lifespan harness (serve the product app directly so its lifespan
  runs — the R1 mounted-wrapper harness defect).
- Real browser 390/1024/1440 + Sources backlinks; negative/edge real error
  verification; artifact + reviewer + accept-after-stop.
- **`Sources` remain provided context, not span-verified citations.**
