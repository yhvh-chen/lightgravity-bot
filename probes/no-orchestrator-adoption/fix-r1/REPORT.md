# no-orchestrator-adoption fix-r1 — REPORT

- role: fix executor (equivalent fresh context for the `--no-session` original implementation);
  **not** an independent QA. A separate pi will re-verify.
- main repo: `/home/yhvh/code/lightgravity-bot`
- worktree: `/tmp/lightgravity-worktrees/no-orchestrator-fix-r1-20261015`
- branch: `experiment/no-orchestrator-fix-r1-20261015`
- base HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- candidate start = main working-tree candidate recorded in `fix-r1/PROGRESS.md` §4
- real SDK/DeepSeek/model calls made by this package: **0** (no network, no `.env`, credentials
  unset for every test subprocess). No new paid-model/token measurement; no fabricated cost.
- first-round QA artifacts (`qa-r1/**`, FAIL report, repro, logs) are **untouched**.
- original implementation `REPORT.md`/`PROGRESS.md` remain as history; this directory is the repair
  record.

## 1. Verdict of this repair (implementer self-check, not QA)

All three first-round findings are addressed with program-enforced, per-Run boundaries and dedicated
real-`ModelPlanner` regression tests. The **unmodified** first-round QA repro
`probes/no-orchestrator-adoption/qa-r1/repro_on_demand_budget.py` now exits `0` both in the fix
worktree and in the integrated main tree (it previously exited `1`). No default product path is
changed (still no model planner wired).

## 2. Per-finding fix

### QA-1 (major) — on-demand cap is instance-global, `PlanningRequest.max_calls` not enforced

Root cause: `ModelPlanner` used one process-global `self._calls` counter as the budget while the
dispatcher shares one instance across Runs; the request's `max_calls` was written to `plan.notes`
only.

Fix — the **program/control plane** now owns a per-Run budget, keyed by `run_id`:

- `backend/lightgravity/coordinator/graph.py:170` — `self._on_demand_calls: dict[str, int]` (one
  counter per Run, only for Runs that carry an explicit `PlanningRequest`).
- `backend/lightgravity/coordinator/graph.py:219-234` — when an on-demand proposal is requested:
  read the per-Run count; if `used >= planning_request.max_calls`, return a **clean failed**
  `DispatchOutcome` (`ModelProposalError`, summary contains `budget exhausted`) *before* calling the
  model; otherwise increment the counter **before** the call so a **failed attempt also counts**.
- `backend/lightgravity/coordinator/planner.py:356-379` — `ModelPlanner` no longer treats its
  instance counter as the per-Run budget. `max_calls` is now an **optional defensive
  instance-lifetime ceiling** (`None` default = no ceiling) for direct callers only; `calls` stays an
  observability counter. This makes a shared instance safe across Runs.
- Docs wording unified: `docs/01-design.md:148` and `docs/08-interface-contract.md:414` now state the
  single-Run cap is program-enforced (failed attempts counted, same-Run re-dispatch cannot open a new
  model loop, no cross-Run instance-global counter).

Actual boundary (not overstated): this bounds **on-demand model proposal calls per Run** — not the
Task's full token/cost budget. A single dispatch consults the model at most once; `max_calls` only
matters across repeated dispatches of the *same* Run. No global-counter reset was introduced, so
concurrent Runs with distinct `run_id`s each keep their own bound.

### QA-2 (minor/medium) — `trigger`/`requested_by` not validated; invalid trigger crashes dispatch

- `backend/lightgravity/coordinator/planning.py:59-88` — `__post_init__` now:
  - **normalizes** a valid trigger string to `PlanningTrigger` (`planning.py:63-73`; unknown strings
    and non-string values raise `ValueError`), so `to_dict()` / the audit note can never raise
    `AttributeError: 'str' object has no attribute 'value'`;
  - validates `requested_by` is a non-empty **printable** string `<= 200` chars and stores it stripped
    (`planning.py:78-83`);
  - keeps `reason` and `max_calls` strict.
- `backend/lightgravity/coordinator/graph.py:243-248` — the note-recording step is wrapped in
  `try/except` and converted to a clean `failed` outcome (`internal_error`), so a malformed internal
  request can never escape `dispatch` as a raw exception or hang the Run.

### QA-3 (info) — tests only covered an uncapped `CountingPlanner`

Added real-`ModelPlanner` fake-`propose` boundary tests (no model/SDK):

- `tests/coordinator/test_graph_dispatcher.py:482` — cross-Run shared instance: two Runs, each own
  `PlanningRequest`, both `succeeded` with `plan_source=model`, propose invoked exactly twice.
- `tests/coordinator/test_graph_dispatcher.py:511` — same-Run re-dispatch: first succeeds, second is
  a clean `failed`, model invoked exactly once (no hidden loop).
- `tests/coordinator/test_graph_dispatcher.py:533` — failed attempts consume `max_calls=2`: two
  failing dispatches call the model twice, the third is refused by the program before any call.
- `tests/coordinator/test_graph_dispatcher.py:563` — dispatcher wraps a recording exception into a
  clean `internal_error` outcome.
- `tests/coordinator/test_planning.py:47,56,62,69` — string-trigger normalization / invalid trigger /
  invalid-or-unprintable `requested_by` / strip.
- `tests/coordinator/test_planner.py:168,185` — optional instance ceiling still enforced when set;
  default has **no** instance ceiling across contexts.
- The pre-existing `test_injected_model_planner_is_on_demand_only` (uncapped stub) is kept: it still
  verifies the "no request → program plan" default and one proposal when requested.

## 3. Integrated files / hashes (main working tree, on base HEAD `9987d4f`)

Integration was exact-whitelist with a pre-copy check that every whitelist file in main matched its
recorded start hash (result: `ALL WHITELIST FILES MATCH START HASHES`); no conflict, no external
overwrite. Log: `fix-r1/logs/main-integration.log`.

| file | sha256 (main, after integration) |
|---|---|
| backend/lightgravity/coordinator/planning.py | `fc2f0035ff03608af46720ee00f5753e4052269511bfbc51a2a81c90d24aa098` |
| backend/lightgravity/coordinator/planner.py | `a2f12e765320625803c21e6789f5f9be633fd66027064e8a6f5e4fdd79b18d95` |
| backend/lightgravity/coordinator/graph.py | `adc0632410419f3a22117e7bebed40469da0d238206ad32aac522907cb531a00` |
| tests/coordinator/test_planning.py | `c71f46d709ed676bf59a24f1fa2f065c3d31543c58814505a9489dca41110553` |
| tests/coordinator/test_planner.py | `9a19c30218eb2ba020cd77c62aae7601e1b7dec3f828defea522b72d3d0ba5fd` |
| tests/coordinator/test_graph_dispatcher.py | `c6ecdd87e102c3903c13bf5436f274740c4481b8b3ed82d84b5ce9caab9f67d0` |
| docs/01-design.md | `eba2352f4b7b6fceee9b8af20e6940b97585208fbee27c246caf99442180c299` |
| docs/08-interface-contract.md | `554370ca768ee710b2356f7e099179d8c61df8f48c6b0cc9129dcba8c55b0a7b` |

Unchanged candidate files still match the recorded start hashes (`__init__.py`, `dispatcher.py`,
`graph_helpers.py`, `README.md`, `agent.md`, `docs/02`, `docs/03`, `docs/04`). `PROJECT.md` was not
touched (main-agent owner). No commit / stage / push / publish.

## 4. Tests (command / cwd / exit / log)

Worktree checks — `cwd=/tmp/lightgravity-worktrees/no-orchestrator-fix-r1-20261015`,
`PYTHONPATH=$PWD/backend`, main `.venv`, credential env vars unset:

| command | exit | result | log |
|---|---|---|---|
| `.venv/bin/python -m mypy` | 0 | Success: no issues found in 86 source files | `logs/wt-mypy.log` |
| `.venv/bin/python -m pytest tests/coordinator/test_planning.py tests/coordinator/test_planner.py tests/coordinator/test_graph_dispatcher.py -q` | 0 | 45 passed | `logs/wt-focused-pytest.log` |
| `.venv/bin/python -m pytest -q` | 0 | 413 passed, 4 skipped | `logs/wt-full-pytest.log` |
| `.venv/bin/python probes/.../qa-r1/repro_on_demand_budget.py` (unmodified copy) | 0 | **all checked behaviours match** | `logs/wt-original-qa-repro.log` |

Main checks — `cwd=/home/yhvh/code/lightgravity-bot`, `.venv` editable install, credentials unset:

| command | exit | result | log |
|---|---|---|---|
| `.venv/bin/python -m mypy` | 0 | Success: no issues found in 86 source files | `logs/main-mypy.log` |
| `.venv/bin/python -m pytest tests/coordinator/test_planning.py tests/coordinator/test_planner.py tests/coordinator/test_graph_dispatcher.py tests/contracts -q` | 0 | 52 passed | `logs/main-focused-pytest.log` |
| `.venv/bin/python -m pytest -q -rs` | 0 | 416 passed, 1 skipped | `logs/main-full-pytest.log` |
| `.venv/bin/python probes/.../qa-r1/repro_on_demand_budget.py` (unmodified) | 0 | **all checked behaviours match** | `logs/main-original-qa-repro.log` |

- The 4 worktree skips are the 3 `frontend/dist` skips (worktree has no built dist) plus the
  `LG020_REAL_DEEPSEEK` gate; main builds dist so the full run is 416 passed, 1 skipped. Base HEAD
  was 389/1; candidate was 397/1; this repair adds 19 cases (+19 = 416).
- `tests/contracts` 7 passed → `CONTRACT_VERSION` remains `1.5.0` (no wire/schema/API/event change).
- Test subprocesses ran with `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`,
  `ANTIGRAVITY_API_KEY`, `ANTHROPIC_API_KEY`, `LG020_REAL_DEEPSEEK` unset; `.env` was never read.

## 5. Semantics now implemented (single source of truth)

- `PlanningRequest.max_calls` = **per-Run** model-proposal budget. The dispatcher enforces it keyed by
  `run_id`; an attempt is counted before the call, so failed attempts count. Same Run re-dispatch
  cannot open a new model loop (returns a clean `failed` outcome). Cross-Run uses distinct counters,
  so one shared `ModelPlanner` is safe.
- `ModelPlanner.max_calls` = optional instance-lifetime ceiling for direct callers; default `None`.
  It is **not** the per-Run budget.
- Trigger is normalized/rejected at construction; `requested_by` must be a non-empty printable
  string; `reason` and `max_calls` stay strict. Dispatch never leaks an `AttributeError`.

## 6. Residual limitations (honest)

- **No real model backend** is wired. `ModelPlanner.propose` is only exercised by fake callables in
  tests. This repair does not add an SDK/DeepSeek path; 0 real model calls, no token/cost claim.
- The enforced cap is only the **on-demand proposal-call budget per Run**; it is not the Task's full
  token/cost budget, and no new budget field/endpoint is added.
- `_on_demand_calls` lives for the dispatcher process lifetime and is not persisted; on process
  restart the in-process `planning_request` seam is lost exactly as before (already disclosed).
- `ModelPlanner` still offers the opt-in instance ceiling for direct callers; the default is uncapped
  so it is not a per-Run cap. A caller that deliberately sets `max_calls` on a *shared* instance would
  re-introduce an instance-global limit — documented as not for dispatcher use.
- No user-facing trigger endpoint, no persistent planning request, no new SDK E2E; unchanged from the
  candidate disclaimers.
- This is an implementer self-check, **not** a version/full-product QA and not a claim that the
  product milestone acceptance passed. Independent re-verification is the next step.
