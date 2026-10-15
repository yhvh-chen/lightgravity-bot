# LG-017 docs/08 change proposal (for the integration owner)

Status: **proposal only** — does not edit `docs/08`. Frozen base: `docs/08`
`1.6.0`. All changes are **additive** and change no `state`/`phase` enum,
transition direction, error code or endpoint semantics (MINOR bump).

## §6.1 Task — additive fields

```yaml
rework:                       # QA/rework ledger, Task-lifetime
  review_rounds: 0
  repair_rounds_spent: 0
  sdk_retries: 0
  outcomes: []
  last_findings: []
  last_candidate_ref: null
  history: []
review_findings: []           # findings for the active repair Run (additive)
budget:
  max_repair_rounds: 1        # existing
  max_review_rounds: 8        # additive optional
```

Semantics:
* `repair_rounds_spent` is bounded by `budget.max_repair_rounds` **across the
  whole Task lifetime**; a new Run never resets it.
* `sdk_retries` counts SDK/adapter retries only; it is not a business round.
* Reaching the budget writes `budget_exhausted` and moves to `waiting_user`; it
  is never treated as completion.
* `review_rounds` bounds independent reviews (`max_review_rounds`, default 8).

## §6.2 Run — additive field

```yaml
review_findings: []           # rework targets this Run was opened to fix
attempt: N                    # rework Runs increment the prior Run's attempt
```

## §4.3 — reject response additive field

`POST /tasks/{task_id}/actions` with `action=reject` may include an additive
`rework` object: `{queued: bool, run_id: str|null, detail: str}`. No new
endpoint; existing response fields, status codes and idempotency semantics are
unchanged (a duplicate reject replays the first result including `rework`).

## §9 — behavior clarification

* Machine checks (LG-009) gate the candidate; the independent reviewer (LG-017)
  runs **before** acceptance opens. `verifying -> awaiting_acceptance` requires
  a passing review.
* A blocking review with budget left goes `verifying -> repairing` and opens a
  **new** Run (the only frozen exit is `repairing -> executing`); the rejected
  candidate/evidence are retained.
* No usable independent reviewer yields `unavailable`: the Task parks at
  `waiting_user`, no round is spent, and acceptance never opens (no fake pass).
* Findings are program-validated against resolvable candidate-owned evidence; a
  model reviewer cannot mark a Task done.
