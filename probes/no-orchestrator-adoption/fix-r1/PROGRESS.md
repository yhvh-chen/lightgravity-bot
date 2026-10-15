# no-orchestrator-adoption fix-r1 — PROGRESS / plan

- role: fix executor (equivalent fresh context for the `--no-session` original implementation)
- main repo: `/home/yhvh/code/lightgravity-bot`
- worktree: `/tmp/lightgravity-worktrees/no-orchestrator-fix-r1-20261015`
- branch: `experiment/no-orchestrator-fix-r1-20261015`
- base HEAD: `9987d4f643b3ad02618d0c45fa35f8eb6ae84eef`
- date: 2026-10-15
- this is **not** an independent QA; it is implementer-side repair + self-check. A separate pi will
  re-verify.

## 1. Inputs / problem statement (from qa-r1, read-only)

First-round independent QA is `FAIL` on acceptance #2. The default product path is unaffected
(no model planner is wired); the defects are in the newly delivered on-demand planning interface.

- **QA-1 (major, blocking #2)** — `ModelPlanner` keeps a *process-global* `self._calls` counter and
  the dispatcher shares one instance across Runs. `PlanningRequest.max_calls` is validated and
  written to `plan.notes` but never enforced. A shared planner's 2nd qualifying Run (and same-Run
  re-dispatch) fails `budget exhausted`. Fix must be per-Run/request isolation; same-Run repeated
  dispatch must not open a new model loop; the cap is enforced by the program; failed attempts
  count; **do not** "reset the global counter", which would lose concurrency bounds.
- **QA-2 (minor/medium, #2)** — `PlanningRequest.__post_init__` validates only `reason`/`max_calls`.
  `trigger="user_request"` (plain str) is accepted, then `request.trigger.value` in
  `_record_planning_request` raises `AttributeError` that escapes `dispatch`; `requested_by=""` /
  `requested_by=123` are accepted. Malformed input must not let a Run escape as a raw exception.
- **QA-3 (info, #4)** — new tests only use an uncapped `CountingPlanner`; no test exercises the real
  `ModelPlanner` across Runs, over-limit, failed retry, or invalid trigger/requester.

Repro preserved read-only: `probes/no-orchestrator-adoption/qa-r1/**` (script + logs + FAIL report).
The original `REPORT.md`/`PROGRESS.md` of the implementation stay as history; this directory holds the
repair record.

## 2. Fix plan

- **QA-1**: make `PlanningRequest.max_calls` the single authoritative **per-Run** proposal budget and
  enforce it in `GraphDispatcher` (program/control plane), keyed by `run_id`, incremented **before**
  the proposal call so failed attempts count. A Run already at its cap is not allowed to consult the
  model again (clean `failed` outcome, no hidden loop). `ModelPlanner` no longer treats its
  instance-lifetime counter as the per-Run budget; the optional `max_calls` becomes an explicit,
  documented defensive instance ceiling only (`None` default = no ceiling) so shared instances work
  across Runs. No global-counter reset.
- **QA-2**: `PlanningRequest.__post_init__` normalizes a valid trigger string to `PlanningTrigger`
  (rejects unknown strings / non-str) and validates `requested_by` is a non-empty printable string;
  `reason`/`max_calls` stay strict. The dispatcher also wraps the note-recording step so any
  unexpected error becomes a clean `failed` outcome (defense in depth).
- **QA-3**: add real-`ModelPlanner` boundary tests: cross-Run shared instance, same-Run re-dispatch
  (no new loop), failed attempts consuming budget / numeric `max_calls`, over-limit, invalid
  trigger and requester, and a planner-crash path. Update `test_planner.py` semantics comment.
- **Docs**: only precise wording sync where the cap location/semantics is stated (planner docstrings,
  `docs/08`, `docs/01`); no unrelated design changes. `PROJECT.md` is main-agent-owned and is **not**
  touched.

## 3. Writable ownership (technical code)

`backend/lightgravity/coordinator/{planning.py,planner.py,graph.py,dispatcher.py,__init__.py}` and
directly related `tests/coordinator/*` (`test_planning.py`, `test_graph_dispatcher.py`,
`test_planner.py`, `graph_helpers.py`). Minimal doc wording sync in `docs/01`, `docs/08` (and the
candidate README/agent.md/docs if their candidate text is already in the whitelist). No other files.

## 4. Candidate hash at work start (main working tree, base HEAD above)

| file | sha256 |
|---|---|
| backend/lightgravity/coordinator/__init__.py | `517dc4690f233f060a648058e2dcc5e7cfa3cd7e222c009e8c5e4853e59dba87` |
| backend/lightgravity/coordinator/dispatcher.py | `aa7921b919e32ee7e0c739cb7f46c2c4397282d36df0c02ca7412a865ae6d088` |
| backend/lightgravity/coordinator/graph.py | `b53c85b2f47be3f2b2869439555dd98c72004c96b79acd9f558902fbaed4bebb` |
| backend/lightgravity/coordinator/planner.py | `f9e6b38b80fdb6fd0de6a96c046d5aa4830efd804f43f3e41f777214892bd7d9` |
| backend/lightgravity/coordinator/planning.py | `6071802e6df3dfef459dbc0c0a0dc69e71d390eb4ff25a417f5f83be25d80c50` |
| tests/coordinator/graph_helpers.py | `4e82af1da63affe4e0cb2ac46a41521112293502c1669773bd3a0440a19f03cf` |
| tests/coordinator/test_graph_dispatcher.py | `85aaf60bd5b51d14281055905e4f4a354f1ac7a29559b0d0a22eea66425b85cc` |
| tests/coordinator/test_planning.py | `3eca801d3538be054fab11f9bfeb1580e2a0c68f0cfd602eddca251a98ea3cf2` |
| tests/coordinator/test_planner.py | `978854b31e7d97fd694159e6fe8f248dea6c12b537a602869da16393ba9bfa9c` |

Docs/README/agent.md candidate hashes are recorded at integration time by the same method.

## 5. Work log

- [x] inputs read (agent.md, PROJECT.md, README.md, probes REPORT/PROGRESS, qa-r1 REPORT + repro + logs)
- [x] candidate hashes recorded
- [x] worktree + branch created from base HEAD; candidate overlaid by exact whitelist
- [x] code fix (planning/planner/graph)
- [x] tests added/updated
- [x] worktree checks (mypy + focused + full pytest)
- [x] precise whitelist integration back to main + main checks
- [x] `fix-r1/REPORT.md` written

(Return code and raw evidence in `fix-r1/REPORT.md` and `fix-r1/logs/`.)
