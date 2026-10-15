# qa-r1 — independent QA of "no-orchestrator default / retire old approach"

- role: independent QA executor (owner `qa-r1`), **not** the implementer
- repo/cwd: `/home/yhvh/code/lightgravity-bot`
- HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- candidate: **uncommitted working-tree** implementation on top of HEAD (not HEAD itself)
- authorize: this QA is limited to this change set; NOT a full-product version QA / SDK E2E
- scope: verify default program planning, bounded on-demand planning contract, retained
  control boundaries, doc honesty, schema/plan_hash compatibility, test truthfulness.
- constraints honoured: code read-only; writes only under this `qa-r1/` dir; no `.env` read,
  no env/secret printing; subprocesses filter `DEEPSEEK_API_KEY`/credential vars; no real
  product SDK/model calls, no network paid test, no new deps.

## Candidate file hashes (sha256, as inspected)

Tracked (modified vs HEAD):

| file | sha256 |
|---|---|
| `PROJECT.md` | `931fd83fa84fed8233ec8654630f011963c5cd78ac1188752ec2ef2c616bcf98` |
| `README.md` | `ba370f2de94af7d9a062fa753e3f9a98b0dbff9146aec3236337f4bcc951e82a` |
| `agent.md` | `5d0a26d412959f53ae4cb2f67e5459f8b13e4c292ecc6aade18884d30ea80790` |
| `backend/lightgravity/coordinator/__init__.py` | `517dc4690f233f060a648058e2dcc5e7cfa3cd7e222c009e8c5e4853e59dba87` |
| `backend/lightgravity/coordinator/dispatcher.py` | `aa7921b919e32ee7e0c739cb7f46c2c4397282d36df0c02ca7412a865ae6d088` |
| `backend/lightgravity/coordinator/graph.py` | `b53c85b2f47be3f2b2869439555dd98c72004c96b79acd9f558902fbaed4bebb` |
| `backend/lightgravity/coordinator/planner.py` | `f9e6b38b80fdb6fd0de6a96c046d5aa4830efd804f43f3e41f777214892bd7d9` |
| `docs/01-design.md` | `eef96dc3c650adde9a90e2bc22aa3ab735e0d88284b2385a70a57f3bc5e8321a` |
| `docs/02-task-and-sdk-resources.md` | `e59e193e8b38d78505bc8c1987f44de76bba47c475fa8ef03296713549b8c4a8` |
| `docs/03-sdk-capability-audit.md` | `3dfe99b28d1baab0d49ebedef6e36558116f04a988ac506e8622a5138426dfe6` |
| `docs/04-bot-behavior.md` | `2c1c7a937701217adb8ae592e4333d6cae58de7c15c481658e2638389fa69253` |
| `docs/08-interface-contract.md` | `b7d88433d921c3461dd948ac43cf2a030985e0af92ab202a10e1c2f438fb3b41` |
| `tests/coordinator/graph_helpers.py` | `4e82af1da63affe4e0cb2ac46a41521112293502c1669773bd3a0440a19f03cf` |
| `tests/coordinator/test_graph_dispatcher.py` | `85aaf60bd5b51d14281055905e4f4a354f1ac7a29559b0d0a22eea66425b85cc` |

Untracked (new source):

| file | sha256 |
|---|---|
| `backend/lightgravity/coordinator/planning.py` | `6071802e6df3dfef459dbc0c0a0dc69e71d390eb4ff25a417f5f83be25d80c50` |
| `tests/coordinator/test_planning.py` | `3eca801d3538be054fab11f9bfeb1580e2a0c68f0cfd602eddca251a98ea3cf2` |

Other untracked `probes/agensh-orchestration*` dirs kept untouched (out of scope).

## Plan (acceptance 1–5)

1. default bootstrap→GraphDispatcher no model planning; injected planner not called w/o request;
   retained program plan/validate/snapshot/schedule/file-SoT/lease/verify/acceptance/stop;
   worker no control write; SDK subagents off.
2. on-demand request validates trigger/reason/requester/budget; same PlanValidator; bounded calls
   & retries under one Run/Task budget (watch instance-global counter vs per-Run); repeated dispatch,
   same-Run retry, different Runs sharing instance, no-planner explicit request, error/invalid/empty
   reason/over-limit behaviors.
3. docs/report honesty; schema/API compat & plan_hash; program path still reaches
   verifying→awaiting_acceptance.
4. new test truthfulness; reproduce "397 passed" & skip reason; run tests/mypy.
5. only report regressions introduced/exposed by this change; old known issues separately labelled.

## Status log

- [x] registered scope + hashes
- [x] inspect diff + real default assembly (bootstrap has no `planner=`; SDK subagents off)
- [x] run focused (18 passed) + full (397 passed, 1 skipped) backend tests / mypy (86 files, ok)
- [x] independent repro scripts (`repro_on_demand_budget.py`, plus inline trigger/requested_by checks)
- [x] final REPORT.md — verdict: **FAIL on acceptance item 2** (default product path unaffected)

## Findings (short)

- **QA-1 major/blocking (acceptance #2)**: on-demand planning cap is the `ModelPlanner`
  **instance-global** `_calls`, not per Run/request. A second Run (or same-Run re-dispatch)
  sharing the dispatcher's planner fails with `model planner call budget exhausted`.
  `PlanningRequest.max_calls` is validated and written into `plan.notes` but never enforced.
- **QA-2 minor/medium (acceptance #2)**: `PlanningRequest` does not validate `trigger` type
  or `requested_by`; a plain-string trigger is accepted then raises an unhandled
  `AttributeError` out of `dispatch`.
- **QA-3 info (acceptance #4)**: new tests use an uncapped `CountingPlanner`, so the real
  `ModelPlanner` budget / invalid-trigger boundaries are not covered. `397 passed` is
  reproducible; the 1 skip is the gated real-DeepSeek test.

See `REPORT.md` and `logs/` for commands, exit codes and raw output.
