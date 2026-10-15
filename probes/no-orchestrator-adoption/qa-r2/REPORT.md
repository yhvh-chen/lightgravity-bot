# no-orchestrator-adoption qa-r2 — independent QA REPORT

- role: independent QA r2 (fresh context; independent of the implementer and of the fix-r1 executor)
- cwd: `/home/yhvh/code/lightgravity-bot`
- HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- candidate: uncommitted working tree on top of HEAD (original change + qa-r1 FAIL + fix-r1 repair integrated)
- method: read actual source at the candidate (never trusted self-reports), wrote own negative/boundary
  repros, and re-ran the **unchanged** qa-r1 repro with output redirected here
- product real SDK/DeepSeek/model calls by this QA: **0** (no `.env` read; every subprocess ran with
  `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_API_KEY`/`ANTIGRAVITY_API_KEY`/
  `ANTHROPIC_API_KEY`/`LG020_REAL_DEEPSEEK` unset; verified `DEEPSEEK_API_KEY` absent in child)
- scope: **this change set only.** Not a full-product/version QA, not a new SDK E2E, and no
  token/cost saving claim.

## Verdict

**PASS** for the fix-r1 integration candidate (`qa-r2`). All three first-round findings are
independently reproduced as fixed, the default product path and the program control boundaries are
intact, and I found **no new regression** introduced by fix-r1. Residual limits are stated below and
are either pre-existing/not-required or explicitly out of scope.

This does **not** claim full-product QA, a real SDK E2E, or proven token/cost savings.

## Hash evidence — candidate did not change during review

| file | sha256 (start = end) |
|---|---|
| backend/lightgravity/coordinator/planning.py | `fc2f0035ff03608af46720ee00f5753e4052269511bfbc51a2a81c90d24aa098` |
| backend/lightgravity/coordinator/planner.py | `a2f12e765320625803c21e6789f5f9be633fd66027064e8a6f5e4fdd79b18d95` |
| backend/lightgravity/coordinator/graph.py | `adc0632410419f3a22117e7bebed40469da0d238206ad32aac522907cb531a00` |
| backend/lightgravity/coordinator/dispatcher.py | `aa7921b919e32ee7e0c739cb7f46c2c4397282d36df0c02ca7412a865ae6d088` |
| backend/lightgravity/coordinator/__init__.py | `517dc4690f233f060a648058e2dcc5e7cfa3cd7e222c009e8c5e4853e59dba87` |
| tests/coordinator/test_planning.py | `c71f46d709ed676bf59a24f1fa2f065c3d31543c58814505a9489dca41110553` |
| tests/coordinator/test_planner.py | `9a19c30218eb2ba020cd77c62aae7601e1b7dec3f828defea522b72d3d0ba5fd` |
| tests/coordinator/test_graph_dispatcher.py | `c6ecdd87e102c3903c13bf5436f274740c4481b8b3ed82d84b5ce9caab9f67d0` |
| tests/coordinator/graph_helpers.py | `4e82af1da63affe4e0cb2ac46a41521112293502c1669773bd3a0440a19f03cf` |
| docs/01-design.md | `eba2352f4b7b6fceee9b8af20e6940b97585208fbee27c246caf99442180c299` |
| docs/08-interface-contract.md | `554370ca768ee710b2356f7e099179d8c61df8f48c6b0cc9129dcba8c55b0a7b` |
| probes/.../qa-r1/repro_on_demand_budget.py (frozen) | `cdbf734522e20b7427afd135efbdcfafb4a8ef5c723373d29c08e5a8801d50c7` |

Post-review re-hash equals the QA-start table, and the frozen qa-r1 repro pre/post hash is
byte-identical (`logs/candidate-hashes.post.sha256`, `logs/repro-qa-r1.{pre,post}.sha256`).

## A. Default product path and retained boundaries — PASS

| check | result | independent evidence |
|---|---|---|
| bootstrap builds `GraphDispatcher` without `planner=` | PASS | read `api/bootstrap.py:305-311`; `repro_qa2.py` §H regex-checked the call and grepped all production modules for `ModelPlanner(` → none |
| default plan is the program minimal plan (`plan_source=rules`, no model) | PASS | `graph.py:206-237`; frozen repro §C `plan_source='rules'`; `test_default_dispatcher_has_no_model_planner` |
| injected planner without explicit request → 0 calls | PASS | `graph.py:214-237`; `test_injected_model_planner_is_on_demand_only` (`planner.calls == 0`); frozen repro default section |
| plan validation preserved (same `PlanValidator`) | PASS | candidate always calls `self._validator.validate(proposal, workspace_path=...)`; `planner.py` validator hunks unchanged |
| `plan`/`plan_hash`/`plan_source` snapshot written by program | PASS | `graph.py:254-261`; `repro_qa2.py` §I recomputed `plan_hash == stable_hash(run["plan"])` and checked source/notes |
| lease / file SoT / atomic write untouched | PASS | `git diff --name-only HEAD` does not include `coordinator/state.py`, `store/**`; only planner selection + tests/docs changed |
| dependency scheduling untouched | PASS | `coordinator/scheduler.py` not in diff; graph scheduling hunks unchanged |
| worker cannot write control state | PASS | diff adds no worker→controller writes; `_record_planning_request` only decorates the proposal notes |
| acceptance / stop-confirmation rules untouched | PASS | `graph.py` `_run_graph`/`_final_outcome`/cancel hunks unchanged; `tests/verify/test_verify_graph_integration.py` passed in full run |
| SDK internal delegation still off | PASS | `adapter/sdk_config.py:118 enable_subagents=False`; `capabilities.py:117 subagents=False`; `registry.py` `invoke-subagent`/`run-workflow` remain non-attaching; all untouched by diff |

## B. QA-1 fix (per-Run budget) — PASS

Source: the program owns `self._on_demand_calls: dict[str, int]` keyed by `run_id`
(`graph.py:170,219-234`); it checks `used >= planning_request.max_calls` **before** the model call and
increments **before** calling, so failed attempts count. `ModelPlanner.max_calls` default is now
`None` (opt-in instance ceiling only, `planner.py:356-379`).

Independently verified (`repro_qa2.py` §B/C/D/E, plus frozen repro):

| boundary | observed |
|---|---|
| shared **real default** `ModelPlanner(propose)` across Runs, each own request | 3 Runs × 1 proposal each, all `succeeded`, `plan_source=model`, `planner.calls==3` |
| `max_calls=2` with failing proposals on Run A | exactly 2 model attempts, 3rd dispatch refused by program ("budget exhausted") before any call |
| different Run B (same shared planner) after A exhausted | gets its own attempt (counter isolated; `calls` 2→3) |
| same-Run re-dispatch at cap | clean `failed` outcome `budget exhausted`, model invocations stay 1 (no hidden loop) |
| concurrency: 3 distinct Runs `asyncio.gather` on one shared `ModelPlanner` | all 3 succeeded, 3 distinct proposals, no starvation/cross-contamination |
| invalid plan after a call | consumes the attempt (failed-attempt counting); invalid plan never persisted (§F) |
| per-dispatch at most once vs per-Run bound | single `planner.plan` call site in `_dispatch_graph`; bound only across repeated dispatches of the same Run |
| opt-in direct-caller ceiling not confused with default | default `max_calls is None`; explicit `ModelPlanner(propose, max_calls=1)` still raises on the 2nd direct call (§G) — treated as intentional, not a default defect |

No cross-Run instance-global counter remains. The one observable instance counter (`calls`) is
documented observability only, not a budget.

## C. QA-2 fix (request validation, no raw-exception leak) — PASS

- `planning.py:59-88` (`__post_init__`): valid trigger strings are normalized to `PlanningTrigger`;
  unknown strings / non-strings raise `ValueError`; `requested_by` must be a non-empty printable
  string ≤ 200 chars and is stripped; `reason` non-empty string; `max_calls` a real `int >= 1`
  (`bool` rejected).
- Independent matrix (`repro_qa2.py` §A): rejected `trigger` ∈ {`not_a_trigger`, `""`, `"USER_REQUEST"`,
  `"user request"`, `123`, `None`, `object()`}; rejected `requested_by` ∈ {`""`, `"   "`, `123`,
  `None`, `"bad\nname"`, 201×`x`, `"\x00"`}; rejected `max_calls` ∈ {`True`, `False`, `0`, `-1`,
  `1.0`, `"1"`, `None`}; accepted valid values and stripped `requested_by`. All at **construction**.
- Recording exceptions do not escape: `graph.py:245-249` wraps `_record_planning_request` in
  `try/except Exception` → `_crash_failure`/`internal_error`. Verified twice:
  `test_dispatch_wraps_plan_request_recording_errors` (monkeypatched `AttributeError`) and an
  independent non-monkeypatched probe where the injected planner returned `None`
  (`logs/probe_none_proposal.stdout.log`): clean `failed internal_error`, no exception escaped.
- The original qa-r1 crash path is gone: plain-string `trigger="user_request"` now normalizes and the
  frozen repro §G prints "dispatch returned normally".

## D. QA-3 / test + tooling evidence — PASS

All commands `cwd=/home/yhvh/code/lightgravity-bot`, credentials filtered by
`logs/runenv.sh` (verified `DEEPSEEK_API_KEY` absent in child; `.env` never read).

| command | exit | result | log |
|---|---|---|---|
| `.venv/bin/python -m pytest tests/coordinator/test_planning.py tests/coordinator/test_planner.py tests/coordinator/test_graph_dispatcher.py -q` | 0 | 45 passed | `logs/focused-pytest.log` |
| `.venv/bin/python -m mypy` | 0 | Success: no issues found in 86 source files | `logs/mypy.log` |
| `.venv/bin/python -m pytest tests/contracts -q` | 0 | 7 passed (`CONTRACT_VERSION="1.5.0"`) | (stdout captured) |
| `.venv/bin/python -m pytest -q -rs` (full backend) | 0 | **416 passed, 1 skipped** | `logs/full-pytest.log` |
| `.venv/bin/python probes/.../qa-r1/repro_on_demand_budget.py` (unchanged) | 0 | all checked behaviours match | `logs/frozen-qa-r1-repro.stdout.log` |
| own `probes/.../qa-r2/repro_qa2.py` | 0 | all independent checks match | `logs/repro_qa2.stdout.log` |
| own `probes/.../qa-r2/repro_same_run_race.py` | 0 | no same-run race observed (1 proposal) | `logs/repro_same_run_race.stdout.log` |
| `probe_none_proposal` (custom planner returns `None`) | 0 | clean `failed internal_error` | `logs/probe_none_proposal.stdout.log` |

- The single skip is `tests/startup/test_real_deepseek_settings_path.py:54`:
  `set LG020_REAL_DEEPSEEK=1 with DEEPSEEK_API_KEY to run the real check` — intentionally not run
  (real-model gate; out of this QA's scope). No other skip.
- The 416/1 and 86-file results match the fix-r1 self-check, but were reproduced independently here,
  not copied.
- Real `ModelPlanner` coverage: `test_real_model_planner_budget_is_per_run_when_shared`,
  `test_real_model_planner_same_run_redispatch_does_not_loop`,
  `test_real_model_planner_failed_attempts_consume_run_budget`,
  `test_model_planner_default_has_no_instance_ceiling`, plus the frozen and own repros all exercise
  the real `ModelPlanner`/`GraphDispatcher`, not the old uncapped stub alone.

## E. Documentation consistency — PASS (one pending main-agent update)

- `docs/01` §3 diagram/§4 table/§7 step 2, `docs/08:414`, `docs/02`, `docs/03`, `docs/04`,
  `README.md`, `agent.md` now consistently state: default = program minimal model-free plan; model
  decomposition = bounded on-demand, not wired; candidate always program-validated; the **single-Run**
  cap is program-enforced per request (failed attempts counted, same-Run re-dispatch opens no new
  model loop), not a cross-Run instance counter. This matches the implemented code.
- No remaining "Planner is a mandatory per-delivery component" statements were found.
- **Non-blocking pending update (main-agent owned):** `PROJECT.md:58` (the 2026-10-15 decision entry)
  still says "ModelPlanner 默认调用上限收紧为 1"; the current code default is `None`, with the
  per-Run cap on `PlanningRequest`. Per the task, this is expected to be updated by the main agent
  after this QA and is not treated as a blocker. `qa-r1`/`fix-r1`/original `REPORT.md` are historical
  records and are not re-flagged for old wording.

## Residual limitations and scope of guarantees (honest)

1. **No real model backend.** `ModelPlanner.propose` is only exercised by fake/no-network callables.
   0 real model/SDK calls; no token/cost/platform claim. The enforced cap is the on-demand
   **proposal-call budget per Run**, not the Task's full token/cost budget.
2. **Not persisted.** `_on_demand_calls` and the `planning_request` seam live in-process for the
   dispatcher lifetime; on restart the in-process request and its consumed count are lost (same as
   before). `_on_demand_calls` is never pruned (one int per Run that carried a request) — negligible
   in practice, but a real non-persistent, non-bounded-lifetime structure.
3. **Opt-in instance ceiling remains.** A direct caller who sets `ModelPlanner(..., max_calls=N)` and
   then shares that instance across Runs re-introduces an instance-global limit; documented as
   direct-caller-only, not for dispatcher shared use. This is intentional, not a default defect.
4. **Budget-exhaustion failure code** is `validation_failed` (via `ModelProposalError`), not a
   dedicated `budget_exhausted` code. The outcome is a clean `failed`; no specific code was required.
5. **After a consumed attempt, no retry within the same Run** (including a proposal that parsed but
   failed plan validation). This follows directly from "failed attempts count"; with `max_calls=1` an
   invalid first proposal cannot be retried inside that Run.
6. **Concurrent same-`run_id` dispatch is unsupported** (one non-terminating Run per Task). A probe
   deliberately raced two dispatches of the same Run: the second was refused (`budget exhausted`) and
   only one proposal fired, because the counter check+increment happens synchronously before the
   first `await`. The dispatcher is asyncio single-thread and not claimed thread-safe.
7. **Historical / out-of-scope (pre-existing at HEAD, not introduced by this change).** An injected
   developer-controlled planner returning a structurally malformed `PlanProposal` whose `subtasks`
   elements are not `RawSubtask` can still leak a raw `AttributeError` from
   `_validator.validate` (`logs/probe_malformed_proposal.stdout.log`). This exists identically at HEAD
   (`git show HEAD:.../graph.py` catches only `PlanInvalid`), is not reachable from `ModelPlanner`
   model output (structurally parsed into `RawSubtask`), and is therefore reported separately rather
   than as a regression of this candidate. If defense-in-depth against a misbehaving injected planner
   is wanted, a later scoped change could catch non-`PlanInvalid` validator errors — not done here
   (read-only QA).

## Historical items (not attributed to this candidate)

- Untracked `probes/agensh-orchestration-r2/**` invalid `lease_path: -` YAML remains; pre-existing,
  out of scope, untouched.
- Real on-demand model backend, user-facing trigger endpoint, persistent planning requests, full
  Task-token billing, and full-product/browser/SDK E2E are not implemented and were explicitly not
  required here.

## Conclusion

The fix-r1 integration candidate satisfies acceptance items A–E for this change set. qa-r1 FAIL
findings QA-1/QA-2/QA-3 are all independently confirmed fixed; no new regression found.
**Verdict: PASS** (change-set scoped only; not a full-product/version QA, not an SDK E2E, no token
saving claim).
