# no-orchestrator-adoption — independent QA r1 REPORT

- owner: independent QA (`qa-r1`), not the implementer
- cwd: `/home/yhvh/code/lightgravity-bot`
- HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- candidate: **uncommitted working tree** on top of HEAD (implementer self-check package
  `probes/no-orchestrator-adoption/REPORT.md` was read but **not trusted**)
- product real SDK/DeepSeek calls by this QA: **0** (no network paid test, no `.env` read,
  subprocesses ran with `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`/token vars unset)
- scope: this change set only. **Not** a full-product version QA and **not** a new SDK E2E.

## Verdict

**FAIL (on acceptance item 2; default product path unaffected).**

The default architecture change is real and honest — bootstrap wires no model planner, the
program produces a model-free minimal plan, and all program control boundaries survive. But
the **new on-demand planning contract makes a per-Run bounded-call promise it does not keep**:
the effective cap is a process-global counter on the injected `ModelPlanner` instance, and the
per-request `PlanningRequest.max_calls` is only written to `notes`. That is exactly the failure
mode acceptance item 2 forbids ("调用和重试有界，按同一个 Run/Task 预算 … 不能只把限制写入 notes
而不落实 … 不能把实例全局计数误作每 Run"), and it is reproducible. A second, smaller validation
gap also crashes the dispatcher. Since the real model backend is not wired, no **default**
product path is broken today; these are latent defects in the newly delivered interface.

## Findings (only regressions introduced/exposed by this candidate)

### QA-1 — MAJOR / blocking for acceptance #2: on-demand planning cap is instance-global, not per Run/request

- code paths:
  - `backend/lightgravity/coordinator/planner.py:348-365` — `ModelPlanner.__init__` stores one
    `self._max_calls` and `plan()` guards on `self._calls` (single per-instance counter).
  - `backend/lightgravity/coordinator/planning.py:48-63` — `PlanningRequest.max_calls` is the
    documented per-request budget; it is validated (`__post_init__`) and exposed via `to_dict`.
  - `backend/lightgravity/coordinator/graph.py:204-218` — the dispatcher holds **one** injected
    planner (`self._planner`, `graph.py:147`) and, on every on-demand Run, calls the same
    instance; `graph.py:289-303` records `max_calls` into `plan.notes` but never enforces it.
- input / repro (`probes/no-orchestrator-adoption/qa-r1/repro_on_demand_budget.py`, section A):
  1. `ModelPlanner(propose)` (default `max_calls=1`) injected into one `GraphDispatcher`;
  2. Run #1 with `PlanningRequest(trigger=USER_REQUEST, reason=...)` → succeeds, `source=model`;
  3. Run #2 with its **own fresh** `PlanningRequest` → fails.
- observed:
  `run#2 outcome=failed (plan_on_demand failed: model planner call budget exhausted)` while
  `propose_invocations=1`. Same root cause on same-Run re-dispatch (section B).
- expected: each Run that carries an explicit `PlanningRequest` gets its own bounded proposal
  ("每个 Run 最多一次", "same Task/Run budget and call cap"); the budget must be scoped per
  Run/request, not consumed once for the whole process.
- impact: any future wiring of a real model backend / shared dispatcher breaks on the second
  qualifying Run with an opaque budget error. `PlanningRequest.max_calls` is dead weight — the
  advertised limit is not the limit actually applied.
- note: `tests/coordinator/test_planner.py:166-175` deliberately locks in the instance-global
  cap, while the new dispatcher wiring assumes per-Run scope; the two were not reconciled.

### QA-2 — MINOR/MEDIUM / acceptance #2: request contract does not validate `trigger`/`requested_by`; invalid trigger crashes dispatch unhandled

- code paths:
  - `backend/lightgravity/coordinator/planning.py:44-56` — `__post_init__` validates only
    `reason` and `max_calls`; `trigger` type and `requested_by` are unchecked.
  - `backend/lightgravity/coordinator/graph.py:218` calls `_record_planning_request` **outside**
    the planner `try/except`; `graph.py:301` does `request.trigger.value`.
- repro (`logs/repro_trigger_type.log`, `logs/repro_request_validation.log`):
  - `PlanningRequest(trigger="user_request", reason="x")` is accepted at construction, then
    `dispatch(...)` raises `AttributeError: 'str' object has no attribute 'value'`
    (unhandled — escapes `dispatch`, not a clean `DispatchOutcome`).
  - `requested_by=""` and `requested_by=123` are accepted and written into the plan note.
- expected: validate requestor/trigger at construction (or fail cleanly); acceptance #2 lists
  "trigger/reason/请求方/预算" as required validations.
- impact: a malformed internal request can abort a Run with an internal exception instead of a
  recorded `failed` outcome; audit note can contain a non-string/non-identifier requestor.

### QA-3 — INFO / acceptance #4: new tests do not cover the real budget or invalid-trigger boundaries

- `tests/coordinator/test_graph_dispatcher.py:395-455` (`test_injected_model_planner_is_on_demand_only`)
  uses `CountingPlanner` (uncapped) shared across two Runs, so it passes while the real
  `ModelPlanner` would fail QA-1. No new test exercises `ModelPlanner` across Runs, over-limit,
  or invalid `trigger`/`requested_by`.
- The `397 passed, 1 skipped` self-check **is reproducible** (see commands); it simply does not
  cover these boundaries. This is a coverage/soundness gap, not a product regression.

## Confirmed retained behaviour (no defect)

| check | result | evidence |
|---|---|---|
| default bootstrap builds no model planner | PASS | `api/bootstrap.py:305-311` has no `planner=`; `GraphDispatcher(planner=None)` → `graph.py:147`, `planner` property `None` |
| injected planner NOT called without explicit request; program plan used | PASS | `test_default_dispatcher_has_no_model_planner`, `test_injected_model_planner_is_on_demand_only`; `plan_source=rules` |
| on-demand candidate passes the same `PlanValidator`; invalid → no snapshot | PASS | `graph.py:219-222`; repro section E: `failed/config_invalid`, `plan` absent |
| program rules still reach `verifying → awaiting_acceptance` (verify step retained) | PASS | `tests/verify/test_verify_graph_integration.py:34-55` (no planner injected) |
| plan/plan_hash/plan_source snapshot written by program | PASS | `graph.py:224-230` |
| file SoT / atomic lease / worker cannot write control state | PASS (untouched) | diff does not modify `coordinator/state.py`, `scheduler.py`, `verify/**`; only planner selection + docs + tests |
| SDK internal delegation off | PASS | `adapter/sdk_config.py:118` `enable_subagents=False`; `capabilities.py:117` `subagents=False` |
| no public schema/API/event change; contract version | PASS | `planning_request` is internal `DispatchContext` only (no api/contracts refs); `CONTRACT_VERSION="1.5.0"`; `tests/contracts` 7 passed |
| docs do not claim a resident LLM impl or an implemented real on-demand backend | PASS | README/agent.md/PROJECT.md/docs/08 all say model backend 未接线/未实现；report says 0 real calls |
| docs/report bounded-cap wording accurate | FAIL | see QA-1: "每个 Run 最多一次" / "at most once per request" overstate the instance-global implementation |

## Commands / exit codes / raw logs

All with `cwd=/home/yhvh/code/lightgravity-bot`, credentials filtered from the subprocess env.

| command (abridged) | exit | result | log |
|---|---|---|---|
| `python -m pytest tests/coordinator/test_planning.py tests/coordinator/test_graph_dispatcher.py -q` | 0 | 18 passed | `logs/focused-pytest.log` |
| `python -m mypy` | 0 | Success: no issues found in 86 source files | `logs/mypy.log` |
| `python -m pytest -q` (full backend) | 0 | **397 passed, 1 skipped** | `logs/full-pytest.log` |
| `python -m pytest -q -rs` (skip reason) | 0 | skip = `tests/startup/test_real_deepseek_settings_path.py:54` gated `LG020_REAL_DEEPSEEK=1` + `DEEPSEEK_API_KEY` | captured in log above |
| `python probes/no-orchestrator-adoption/qa-r1/repro_on_demand_budget.py` | 1 (by design) | QA-1 and QA-2 triggered | `logs/repro_on_demand_budget.log` |
| inline `trigger`/`requested_by` check | 0 | QA-2 accepted / crash shown | `logs/repro_trigger_type.log`, `logs/repro_request_validation.log` |

Reproducible script: `probes/no-orchestrator-adoption/qa-r1/repro_on_demand_budget.py`
(no network, no credentials, no production-code writes; exits non-zero when the contract is
violated). Complement with `logs/repro_trigger_type.log` / `logs/repro_request_validation.log`.

## Non-package / known historical items (NOT attributed to this candidate)

- Historical untracked `probes/agensh-orchestration-r2/**` still contains `lease_path: -`
  (invalid YAML) in 12 files; **no tracked file contains it** (`git ls-files` check). Pre-existing,
  out of scope, kept untouched.
- Real on-demand model backend, user-facing trigger endpoint, persistent planning requests and
  the full-product / browser / SDK E2E are **not implemented** — explicitly not required by this
  QA and correctly disclaimed by the docs.

## Suggested fix direction (for a separate repair task, not done here)

1. Scope the planning budget to the Run/request: e.g. enforce `PlanningRequest.max_calls` in the
   dispatcher per explicit request (fail/record cleanly when exceeded) and stop treating
   `ModelPlanner._calls` (instance-global) as the per-Run cap. Reconcile with
   `tests/coordinator/test_planner.py::test_model_planner_rejects_malformed_and_caps_calls`.
2. Validate `PlanningRequest.trigger`/`requested_by` in `__post_init__` (and/or guard
   `_record_planning_request`) so a malformed request yields a recorded failure, not an unhandled
   `AttributeError`.
3. Add real `ModelPlanner` boundary tests: two Runs sharing one instance, over-limit behaviour,
   and invalid trigger/requestor.
