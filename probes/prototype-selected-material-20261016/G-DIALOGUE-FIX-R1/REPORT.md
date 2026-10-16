# G-DIALOGUE-FIX-R1 — FINAL report

- Branch: `fix/proto-material-dialogue-r1-20261016`
- Owner (G): `coordinator/**`, `tests/coordinator/**`, existing `tests/api/test_integration_wiring.py` (only the lines G changed), own probe.
- Continuation base HEAD: `1d7095c` (pm bind QA). Product candidate `f7a32ac`.
- F source owner stopped at `22459d6` — **F source files/tests untouched by G** (verified: `git status` shows only owned files).
- Status: **COMPLETE (coherent, tested candidate)**; single honest candidate.

## Changed files

Code (all under `backend/lightgravity/coordinator/`):
- `service.py` (+~112): persist the assistant reply (and its additive selected-source bindings/snapshot) into the same conversation SoT the user message used; default Chat-delivery provisioning of an acceptance criterion + authorized workspace; new `_persist_assistant_reply`, `_ensure_default_workspace`.
- `planner.py` (+~44): `default_acceptance_criteria(objective)` — derive a deterministic, checkable acceptance criterion when a Task declares none; RuleBasedPlanner uses it only for the derived default and adds **no** verify node in that case.
- `dispatcher.py` (+~19): extract `DispatchContext.worker_instructions()` (appends the untrusted-wrapped selected body) reused by both dispatchers.
- `graph.py` (+~5): graph path uses `context.worker_instructions()` so the worker gets the same exact selected body.

Tests:
- NEW `tests/coordinator/test_g047_dialogue_delivery_r1.py` (8 tests, the R1 evidence).
- `tests/coordinator/test_planner.py`, `test_idempotency.py`, `test_service.py`: updated for derived default + persisted assistant row (documented below).
- `tests/api/test_integration_wiring.py`: updated history-length assertions.

Probe: this file.

## Mechanism

1. **Assistant-history repair.** For every `direct`/`bounded_read` turn (global + Task), the program persists one assistant row with a deterministic id `assistant:<message_id>` into the *same* store the user message used (`GlobalConversationLog` / task message log). Idempotent: a retried `message_id` reuses the stored result and never appends a second assistant row. The row carries the reply `content` and, when a selection was present, the additive `resolved_source_bindings` (in `data`) and the `selected_context` snapshot. No new DB, no second source of truth, no raw path/secret (bindings are stable locators only).
2. **Default Chat delivery plan.** An ordinary Chat delivery ("create a Markdown file …") names no acceptance criteria and no workspace. `create_task(default_delivery=True)` now derives a checkable criterion (`default_acceptance_criteria`) and provisions a Task-scoped workspace `tasks/<task_id>` **inside** the configured authorized root (`Store.resolve_path` enforces containment; directory created for the executor). The RuleBasedPlanner then emits the prototype's minimal single `deliver` node that the **unchanged** `PlanValidator` accepts. Explicit `/tasks` callers are unchanged.
3. **Source-context worker request.** `DispatchContext.worker_instructions()` appends the persisted selected body (already untrusted-wrapped) to the Task instructions; both single-slot and graph dispatchers use it, so the worker receives the exact same body the chat reply used.
4. **Source-bound trigger unchanged.** `_trigger_binding`/`_bind_selected_trigger`/`_run_selected_snapshot` are untouched; a selected delivery still freezes its own `{message_id, snapshot}` and a no-selection delivery carries `snapshot: null` (no cross-message inheritance).

New public/program fields: **none announced** beyond the already-documented additive `selected_trigger` (Task/Run) and message `selected_context`; the assistant row reuses the existing `data.resolved_source_bindings` shape documented in docs/10 §4. No new endpoint/error code/enum/migration. Frontend `selected_sources` wire unchanged. No new model tools.

## Compatibility / history impact (explicit)

- Preserved: old request schema, no-selection model prompt/content, auth, classifier, controls/reviewer/accept/stop. The plan validator is **not** waived: arbitrary proposals missing acceptance or a write workspace are still rejected (`test_validator_still_requires_acceptance_and_workspace`).
- **Intentional R1 history bugfix:** the baseline persisted *only* direct user messages, so reopening a conversation never showed the assistant's answer (nor its Sources). R1 persists assistant replies for **all** Task/global direct+bounded-read answers — including the **no-selection** case. This means legacy conversation histories are **not** byte-identical: `GET .../messages` now returns an extra `assistant:<id>` row.
- Old assertions changed accordingly:
  - `tests/coordinator/test_service.py::test_global_and_task_messages_are_persisted` — expects `["msg-g1","assistant:msg-g1"]`.
  - `tests/coordinator/test_idempotency.py::test_global_message_id_is_idempotent` — expects the user row + exactly one assistant row (no duplicate on retry). `test_task_message_id_is_idempotent` — a follow-up (append) note still yields only the user row.
  - `tests/api/test_integration_wiring.py::test_global_conversation_roundtrip_and_source_limits` — history length 2 after replay.
  - `tests/coordinator/test_planner.py::test_rule_planner_single_node_derives_acceptance_without_declared` replaces the old "single node without acceptance" (which asserted the validator *rejected* it).
- No-selection assistant row attaches only the ordinary bounded-tools list, never source bindings/snapshot.
- **Do NOT claim legacy history byte-identical.** Repairing the missing assistant-message history is accepted by RootPM as part of the prototype.

## Exact checks run (durable stdout, this worktree)

Run with `PYTHONPATH=backend` (the worktree `.venv` is a symlink to the main repo venv whose editable `.pth` points at the **main** repo; `PYTHONPATH=backend` is required to test this worktree's source).

| Check | Command | Result |
|---|---|---|
| New R1 tests | `pytest tests/coordinator/test_g047_dialogue_delivery_r1.py -q` | `8 passed` EXIT 0 |
| Coordinator + API wiring | `pytest tests/coordinator tests/api/test_integration_wiring.py -q` | `125 passed` EXIT 0 |
| LG-043 selected material | `pytest tests/sources/test_lg043_selected_material.py -q` | `42 passed` EXIT 0 |
| Full backend suite | `pytest -q` | `914 passed, 5 skipped` EXIT 0 |
| Static types | `mypy backend/lightgravity` | `Success: no issues found in 139 source files` EXIT 0 |

## Runtime evidence: units vs real

- All R1 tests are **local units**: the executor is an in-process `FakeExecutor` (explicitly **not** real SDK/model evidence); no network/credential/browser; no port 8123.
- The delivery test drives the real coordinator/graph/services/store with the fake executor and asserts the worker `ExecuteRequest` carries the exact original selected `BRIEF_BODY` (untrusted-wrapped) and a real workspace directory inside the boundary.
- **SDK/real-model end-to-end remains pending** and belongs to the H run after F/G merge. No user-upload proof is claimed (source fixture is seeded via the program path; F's plaintext-intake fix is separate, post-merge).

## Known limits

- No real SDK/model call was made; deliverable quality is unverified here.
- If a global Chat delivery prompt itself contains a decision keyword (e.g. "approved"), the deterministic classifier routes it as `decision`; docs/11 Flow B sends that phrasing as a **Task** message, which bypasses classification. The R1 global test uses a decision-keyword-free delivery phrasing.
- Assistant persistence changes legacy history row counts (documented above; intentional).
- H (single real run after F/G) still owed by RootPM's process.

## Stop state

- Worktree HEAD before commit: `1d7095c`. Branch `fix/proto-material-dialogue-r1-20261016`.
- F source owner tip: `22459d6` (untouched).
- Staging is **explicitly scoped** to owned code/tests/probe; `.venv` symlink, root `REPORT.md` and other files are NOT staged.
