# LG-017 implementation status

Owner: pi-lg017 (DeepSeek, this worktree). Base commit: `141809d`.

## Goal
Product-runtime independent candidate QA + bounded business rework closed loop
(NOT dev-flow per-task QA). Reviewer context/role separated from implementer,
structured findings bound to real candidate-version evidence, program-validated
(not model-judged) done, rework rounds counted separately from SDK retries,
Task-total budget not resettable across Runs, reject keeps old candidate and
opens a new Run that re-recruits + re-verifies, stale/duplicate ack idempotency
preserved, no fake pass when no reviewer is available.

## File owners (this package)
- `backend/lightgravity/verify/**` (new `review.py`, `rework.py`; extend `service.py`)
- `backend/lightgravity/coordinator/service.py` (shared assembly point)
- `backend/lightgravity/api/tasks.py` (action wiring)
- `tests/verify/**` + new `tests/rework/**`
- `probes/lg017/**`
- Do NOT touch graph.py/scheduler.py/dispatcher.py/adapter; do NOT touch api/app.py / frontend.

## Checklist
- [x] Read AGENTS/agent/PROJECT/BACKLOG/docs06/docs08(1.6.0)/relevant tasks + skills
- [ ] Implement reviewer port + program-driven default reviewer (verify/review.py)
- [ ] Implement bounded rework orchestrator + Task-total budget ledger (verify/rework.py)
- [ ] Wire orchestrator into coordinator auto-verify + api accept/reject reject path
- [ ] Tests: candidate binding, wrong-evidence reject, rounds/total budget, reject new Run,
      stale/duplicate ack, review-not-finished blocks accept, reviewer unavailable no fake pass
- [ ] backend type check + local test run
- [ ] INTEGRATION.md with schema/call points + docs08 proposal
- [ ] Local precise commit; record evidence/limits/cost

## Progress log
- 2026-10-16: context read done; architecture confirmed (LG-009 verify seam + LG-006/008 dispatcher + LG-016 recovery). docs08 frozen at 1.6.0 on main (my base is ancestor); additive-only.
- 2026-10-16: Implemented verify/review.py (independent reviewer port + ProgramReviewer +
  validate_findings + resolve_candidate_evidence) and verify/rework.py (ReworkOrchestrator,
  ReworkLedger persisted in Task frontmatter, RunSpawner/SpawnOutcome, bounded rounds).
- 2026-10-16: Wired coordinator: ReworkReviewer port, set_rework, lazy default ProgramReviewer
  orchestrator, spawn_repair_run (queues fresh Run), _auto_verify now reviews before acceptance,
  Run attempt increments, review findings carried into repair context instructions.
- 2026-10-16: Wired api/tasks.py reject -> spawn rework run; adds {"rework": ...} to response.
- 2026-10-16: mypy clean (93 files).
- Next: tests (tests/verify/test_verify_review.py, test_verify_rework.py), local run, INTEGRATION.md.
- 2026-10-16: Tests added & green: tests/verify/test_verify_review.py (7), test_verify_rework.py (8),
  tests/coordinator/test_rework_integration.py (4, real worker loop). Full suite: 502 passed, 4 skipped.
  mypy clean (93 files).
- 2026-10-16: Wrote probes/lg017/INTEGRATION.md (schema + exact call points) and DOCS08-PROPOSAL.md.
- Note: docs08 1.6.0 frozen base; additive-only. api/app.py NOT touched (LG-019 owner);
  coordinator lazy default wires review so the default runtime is a real closed loop.
- Real-model cargo: 0 calls this package (all local/in-process fakes; real SDK E2E is LG-021/022).

## Delivered
- Commit `99174d8` on `dev/lg017`; working tree clean; base `141809d`.
- Final verification at commit: `uv run pytest -q` -> 502 passed, 4 skipped;
  `uv run mypy` -> Success (93 files).
- Real model calls this package: 0 (unknown=0, not fabricated). All evidence is
  local/in-process fakes; real SDK/DeepSeek E2E remains LG-021/022.
- Limits: model-backed reviewer is a port (default is deterministic program
  reviewer); multi-worker isolation and browser paths not covered here.
