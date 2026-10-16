---
title: "LG-040 REVOKE-FIX-R1-20261016 — implementation report (single owner)"
doc_type: report
category: engineering
status: "fix implemented + local verification PASS; awaiting independent retest"
updated: "2026-10-16"
---

# LG-040 REVOKE FIX R1 — REPORT

## 0. Scope & authority

- Sole implementation/rework owner for the CONFIRMED **MAJOR** API-slice QA
  finding in
  `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-r1-20261016/probes/lg040/API-R1-20261016/ACL-ADDENDUM.md`.
- Fresh implementer, distinct from independent API/browser/quality QA.
- Root PM only. No push/deploy/publish/reset/clean; no nested agents; no
  secrets read/logged/committed; existing DeepSeek env used by the harness,
  zero model calls.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-revoke-fix-r1-20261016`,
  branch `fix/lg040-revoke-r1-20261016`, base `dd4ca81` (product same
  `2f277fa`). Main and ongoing QA worktrees unchanged.

## 1. Defect (verified by QA, reproduced here over real TCP)

`revoke` set `status=archived` and invalidated search hits, but
`GET /sources/{id}/content` and `GET /sources/{id}/download` still returned
**200 with the original/machine bytes**. docs/08 §6.6 L594 / §4.3 L233: only
`revoke`/`delete` make material **unavailable**; reversible
`archive`/`unarchive` keeps it openable/searchable.

## 2. Fix

`backend/lightgravity/sources/service.py`:

- Added module constant `REVOKED_STATUS = "archived"` (the **revoke marker**,
  written only by `revoke`) and helper `_ensure_available(record)` that raises
  the **existing** `not_found` (`ErrorCode.NOT_FOUND`, HTTP 404) with
  `details={source_id, status, revoked:true}`.
- Gated, fail-closed, before any bytes are read or streamed:
  - `content_view` (covers `auto`/`formal`/`machine`),
  - `download_view` (covers `original`/`formal`/`machine`),
  - `source_actions("reprocess")` (processing rewrites `status` and could
    resurrect a revoked source),
  - `edit_formal` (writes + re-indexes; could recreate availability).
- Deliberately did **not** gate on the additive `archived: bool` flag, so
  reversible `archive`/`unarchive` remains searchable + openable.
- Preserved: original/machine/formal/history on disk (no deletion, no rollback
  of archive semantics), `revoke` idempotency, controlled writes/versioning/
  locks, per-source migration to `not_indexed`/`disabled` index.
- `GET /sources/{id}` metadata/status diagnosis view remains (a client can
  still observe `status=archived`).

`backend/lightgravity/api/sources.py` was **not** changed: the existing
`AppError` → HTTP mapping already yields 404 for `not_found`, and the
`EntityNotFound` handlers are untouched.

**Expected status code for independent retest: HTTP 404 `not_found`, with
`error.details.revoked=true`.** (No new error code/enum/endpoint/schema; no
public contract version change — this is an implementation alignment with the
already-frozen §6.6 semantics.)

## 3. Adjacent-path check (no resurrection)

| Path | Before fix | After fix |
|---|---|---|
| `POST actions {action:revoke}` | 200, status archived | 200, status archived (idempotent) |
| `POST actions {action:reprocess}` on revoked | 200 → rewrote status, **could resurrect** | 404 `not_found`, status unchanged |
| `POST /formal` on revoked | 200 → wrote + re-indexed, **could resurrect** | 404 `not_found`, status unchanged |
| `POST actions {action:archive/unarchive}` | openable/searchable | unchanged (openable/searchable) |
| alternate preview kinds (content/download) | served bytes | all kinds refused |

## 4. Verification evidence (all local, real, offline)

1. **Focused tests** `tests/sources/test_lg040_revoke_availability.py` — new,
   8 cases (before/after over fresh HTTP requests, all content/download kinds,
   archive/unarchive open+searchable, missing source, idempotent revoke,
   reprocess/formal no-resurrection, normal source unaffected).
   `PYTHONPATH=backend python -m pytest tests/sources/test_lg040_revoke_availability.py -q`
   → **8 passed**.
2. **Existing sources + api suites** (incl. updated
   `tests/sources/test_lg038_materials_flow.py`, whose revision test encoded the
   buggy 200-on-revoked-download behavior; now asserts refusal + on-disk
   preservation) → **219 passed, 1 skipped**.
3. **Full backend suite** → **862 passed, 5 skipped, 1 failed**. The single
   failure is `tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins`,
   a pre-existing timing/flaky concurrency race in the **collaboration**
   package (unrelated to sources/revoke; passes in isolation and on re-run).
4. **mypy** `python -m mypy` → **Success: no issues found in 138 source files**
   (exit 0).
5. **Real-TCP probe** `probes/lg040/REVOKE-FIX-R1-20261016/tcp_revoke_proof.py`
   (real uvicorn + FileStore + create_app; ephemeral loopback port; no 8123;
   OCR/vector env unset; zero model/LAN calls; server stopped in `finally`) →
   **14/14 PASS**, including:
   - BEFORE revoke: all content/download kinds 200 with the marker;
   - `revoke` 200, `status=archived`, `revoked=true`;
   - search hits `[]`;
   - AFTER revoke (fresh TCP, `Cache-Control: no-store`): all content/download
     kinds **404 `not_found` `revoked=true`, no marker served**;
   - original preserved on disk; idempotent revoke; reprocess/formal refused;
   - archive openable+searchable; unarchive restores; missing source 404.

## 5. Limits & honesty

- This is **not** independent QA; no self-pass claim. Independent retest is
  required on the final integrated candidate.
- The MAJOR finding is API-slice only; browser/quality slices were not assessed
  here.
- `not_found` (404) was chosen as the fail-closed refusal because it is the
  existing mapping already used for `delete`; the QA addendum's suggested
  404/409/410/423 set is satisfied. No over-broad refactor was performed.
- One flaky, unrelated collaboration test failed once in the full run; it does
  not touch sources/revoke and passes on re-run.
- Local cost: pi unknown, **not 0**.

## 6. Raw evidence

- `raw/tcp_revoke_proof.json` — machine-readable real-TCP case results.
- Commands + exits recorded in `STATUS.md`.
