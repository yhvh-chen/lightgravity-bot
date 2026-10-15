# no-orchestrator-adoption qa-r2 — PROGRESS

- role: independent QA r2 (fresh context, independent of implementer and fix-r1 executor)
- cwd: `/home/yhvh/code/lightgravity-bot`
- HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- candidate: uncommitted working tree on top of HEAD (candidate + qa-r1 FAIL + fix-r1 repair already integrated)
- real SDK/DeepSeek/model calls by this QA: **0** (credentials filtered from every subprocess; `.env` never read)
- writable scope: this directory only (`probes/no-orchestrator-adoption/qa-r2/**`)
- read-only scope: everything else, including production code, existing tests, `qa-r1/**`, `fix-r1/**`, `PROJECT.md`, docs

## Candidate hashes captured at QA start (sha256)

| file | sha256 |
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
| README.md | `ba370f2de94af7d9a062fa753e3f9a98b0dbff9146aec3236337f4bcc951e82a` |
| agent.md | `5d0a26d412959f53ae4cb2f67e5459f8b13e4c292ecc6aade18884d30ea80790` |
| PROJECT.md | `93e21dd6d8d26846aaba3a027f751b100d690a421d6e8608384e701bf5738f91` |
| probes/.../qa-r1/repro_on_demand_budget.py (frozen, must stay unchanged) | `cdbf734522e20b7427afd135efbdcfafb4a8ef5c723373d29c08e5a8801d50c7` |

These coordinator/test hashes match the fix-r1 integration table — the fix-r1 candidate is present
in main. QA-r2 will re-hash at the end to detect any change during review.

## Plan

1. independently read `planning.py` / `planner.py` / `graph.py` diff vs HEAD, plus first-round repro.
2. verify A (default product path + preserved boundaries) from source, not self-report.
3. verify B (per-Run budget) with own negative/boundary repros (concurrency, exception, repeat, cross-Run).
4. verify C (trigger/requested_by validation, no raw exception leak) with own repros.
5. re-run the frozen qa-r1 repro unchanged (output redirected to qa-r2/logs).
6. focused tests + mypy + one full backend run with credentials filtered; record cwd/exit/log/skips.
7. docs consistency (current spec vs new semantics).
8. write REPORT.md with PASS/FAIL, item-by-item, residual limits.

## Status (all complete)

- [x] candidate hash + read-only scope registered
- [x] source review (planning.py / planner.py / graph.py / dispatcher.py / tests / docs)
- [x] independent boundary+negative repro (`repro_qa2.py`, exit 0)
- [x] same-Run concurrency residual probe (`repro_same_run_race.py`, exit 0)
- [x] frozen qa-r1 repro re-run unchanged (exit 0), output redirected to `logs/`
- [x] focused 45 passed / mypy 86 files / full 416 passed 1 skipped / contracts 7 passed
- [x] docs consistency checked
- [x] `REPORT.md` written -> **PASS**
- [x] candidate hashes unchanged during review (`logs/candidate-hashes.post.sha256`)

## Result summary

- Verdict: **PASS** for the fix-r1 integration candidate (scope = this change set only).
- qa-r1 findings QA-1/QA-2/QA-3 all independently reproduced as fixed; default program path and
  control boundaries intact.
- No new regression introduced by fix-r1.
- Residual limits (not defects): no real model backend; in-process non-persisted per-Run counters;
  budget is proposal-call not full Task token; opt-in direct-caller instance ceiling remains;
  concurrent same-run dispatch unsupported (probe showed no race because increment is synchronous).
- Historical/out-of-scope (pre-existing at HEAD, not this change): a custom injected planner
  returning a structurally malformed `PlanProposal` can still leak a raw `AttributeError` from
  `_validator.validate`; unreachable from `ModelPlanner` model output (structurally parsed).
- Doc note (non-blocking, main-agent owned): `PROJECT.md:58` still says "ModelPlanner 默认调用上限
  收紧为 1"; current default is `None` with the per-Run cap on `PlanningRequest`.
