# LG-017 integration notes (shared contract proposal + call points)

Owner: pi-lg017. Base commit `141809d`. Frozen contract used: `docs/08`
`1.6.0` (additive-only; LG-017 adds no enum/transition/error changes).

This file lists the **new addititive fields** LG-017 reads/writes and the exact
call points the integration owner must wire. It is a proposal only: `docs/08`,
`README.md`, `PROJECT.md`, `PROGRESS.md` and `agent.md` are maintained by the
integration owner, not by this package.

## 1. What LG-017 implements (product runtime, not dev-flow QA)

`verify/review.py` + `verify/rework.py` add the runtime loop the product needs:

```
executing --(success)--> verifying
verifying --(independent review passed)--> awaiting_acceptance  (LG-009 gate)
verifying --(review rework, budget left)--> repairing -> new Run (re-recruit + re-verify)
verifying --(review rework, budget spent)--> waiting_user  (budget_exhausted)
verifying --(review unavailable)--> waiting_user  (no fake pass, no round spent)
```

* Reviewer is a separate role/context (`Reviewer` port) from the implementer;
  the default `ProgramReviewer` is deterministic and makes no model call.
* A finding is only valid when it cites **resolvable candidate-owned evidence**
  (`validate_findings`); a `rework` with no substantiated blocking finding
  degrades to `unavailable`.
* Program-validated, never model-judged: the orchestrator decides pass/rework/
  unavailable by program rules, so no model output can mark a Task done.
* `sdk_retries` / `review_rounds` / `repair_rounds_spent` are separate counters;
  the Task-lifetime ledger is never reset by a new Run.

## 2. New addititive Task frontmatter fields (proposal for docs/08 §6.1)

```yaml
rework:                       # additive; Task-lifetime QA/rework ledger
  review_rounds: 0            # independent reviews performed
  repair_rounds_spent: 0      # business rework rounds actually started (< budget.max_repair_rounds)
  sdk_retries: 0              # SDK/adapter retries (NOT business rounds)
  outcomes: [passed|rework|unavailable|rework_queued|budget_exhausted|...]
  last_findings: []           # last ReviewReport findings (structured, evidence-bound)
  last_candidate_ref: null
  history: []                 # append-only entries {at, outcome, candidate_ref, findings, prior_run_id, new_run_id}
review_findings: []           # additive; findings handed to the active repair Run
```

New optional budget key (additive):

```yaml
budget:
  max_repair_rounds: 1        # existing: bounds repair_rounds_spent across the Task
  max_review_rounds: 8        # optional additive: bounds review_rounds (default cap 8)
```

New addititive Run frontmatter field (proposal for docs/08 §6.2):

```yaml
review_findings: []           # additive; rework targets this Run was opened to fix
```

No new HTTP endpoint is required. `POST /tasks/{task_id}/actions` with
`action=reject` now returns an extra additive `rework` object
(`{queued, run_id, detail}`); existing fields/status codes are unchanged.

## 3. Exact call points for the integration owner

Everything below is already wired in this package except where marked.

1. `coordinator/service.py` (owned here, wired):
   * `Coordinator.set_rework(orchestrator)` / `coordinator.rework`;
   * lazy default `_resolved_rework()` builds a `ReworkOrchestrator` with a
     deterministic `ProgramReviewer` and the coordinator itself as `RunSpawner`;
   * `_auto_verify` runs review **before** `verify_and_prepare`, so acceptance
     only opens on a passing review;
   * `_process_rework` drains the bounded rework queue and dispatches the fresh
     Run (`repairing -> executing`), re-recruiting + re-verifying;
   * `spawn_repair_run` / `lookup_spawn_outcome` are the `RunSpawner` port.
2. `api/tasks.py` (owned here, wired): a human `reject` calls
   `_spawn_rework_after_reject` (queues a fresh Run) and adds `rework` to the
   response; duplicate rejects replay deterministically via the coordinator's
   rework-scoped idempotency key.
3. `api/app.py` (NOT touched — LG-019 owner): nothing is required. The default
   runtime already reviews via the coordinator. If the integration owner wants
   an explicit orchestrator (e.g. a model-backed reviewer), add:
   ```python
   from lightgravity.verify import ReworkOrchestrator, ProgramReviewer
   resolved_coordinator.set_rework(ReworkOrchestrator(
       broadcasting, reviewer=ProgramReviewer(),
       writer=..., spawner=resolved_coordinator,
   ))
   ```
   This is optional; without it the coordinator's lazy default is used.
4. `verify/router.py` (unchanged): still exposes only
   `GET /tasks/{id}/acceptance`; accept/reject stays in `api/tasks.py`.

## 4. Tests / evidence in this package

* `tests/verify/test_verify_review.py` — independent review, evidence-bound
  findings, unavailable-never-pass.
* `tests/verify/test_verify_rework.py` — bounded rounds, Task-lifetime ledger
  not reset by a new Run, spawn failure not spending a round, budget exhaustion.
* `tests/coordinator/test_rework_integration.py` — real coordinator worker loop:
  pass → acceptance; rework → fresh Run (attempt 2) → re-verify; budget stop;
  unavailable blocks acceptance. Old rejected candidate/evidence retained.

All are unit/local evidence (in-process fakes/temp stores). The real
SDK/DeepSeek end-to-end QA is a separate version gate (LG-021/022).
