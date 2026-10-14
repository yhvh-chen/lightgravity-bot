# verify — machine verification & human acceptance (LG-009)

Owner: LG-009 / LG-017 (`docs/08` §11). This package runs the machine checks a
Task authorizes, refuses to hand a candidate to human acceptance until every
executor/session is confirmed stopped and the team/execution slot are released,
and applies version-bound, idempotent accept/reject decisions. It never merges,
pushes or deploys, and workers never write control state.

## Module map

| Module | Responsibility |
|---|---|
| `candidate.py` | Read a Run's delivery snapshot (evidence, versions, plan hash) from the Store. |
| `checks.py` | In-process check registry + `evidence-present` / `artifacts-in-workspace`; Markdown never supplies code. |
| `stopgate.py` | Confirm Run/session stop and release members + the Task execution slot; never fakes a release. |
| `service.py` | `VerificationService`: `verify_and_prepare`, `decide`, `request_repair`, `acceptance`. |
| `router.py` | Independent `build_router(service)` for LG-012 / the integration owner. |

## Minimal wiring for the integration owner (LG-012 / LG-010)

1. **Mount the router** (do not edit `api/app.py` here):
   `app.include_router(build_router(service), prefix=API_PREFIX)`.
   The router itself converts `AppError` to the frozen error envelope, so it does
   not depend on app-level handlers.
2. **Trigger verification from the coordinator** after a dispatcher returns
   `succeeded` and the Task/Run are in `verifying`:
   `service.verify_and_prepare(task_id, request_id=<coordinator request id>)`.
   On a failing check, the caller may call
   `service.request_repair(task_id, request_id=..., note=...)`; new-Run creation
   stays with the coordinator.
3. **Authorize checks** by adding the optional Task frontmatter field
   `checks: [<registered-check-id>, ...]`. Only registered + authorized checks
   run; an authorized-but-unregistered id is reported `unconfigured` and is
   never run. If no `checks` field is present, no machine check runs (nothing is
   fabricated as passed).
4. **Decisions** use `POST /tasks/{task_id}/actions` with
   `{"action": "accept"|"reject", "request_id": ..., "expected_revision": ...}`
   (docs/08 §4.3). They are idempotent per `request_id` and stale when the
   requirements/deliverable/candidate version no longer matches.

## Interface notes needing shared registration (contract MINOR)

The service adds **additive** fields only; it does not change any frozen enum,
error code, endpoint or transition:

- Task frontmatter: optional `checks` (authorized registered check ids).
- `acceptance` mapping: `candidate_ref`, `candidate_plan_hash`, `check_records`,
  optional `note` (the frozen `requirements_revision` / `deliverable_revision`
  binding is unchanged).

## Test boundary

`tests/verify/**` uses only temporary data (`tmp_path`). The graph integration
test uses the coordinator's in-process fake executor as unit evidence; the real
SDK/DeepSeek end-to-end path is LG-010.
