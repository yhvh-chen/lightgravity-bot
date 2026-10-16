---
title: "LG-040 REVOKE-FIX-R1-20261016 — status"
doc_type: status
category: engineering
status: "DONE (local verification PASS) — awaiting independent retest"
updated: "2026-10-16"
---

# STATUS — LG-040 REVOKE FIX R1

Round-based progress (STATUS first 3 rounds, REPORT by 20, final commit by 45):

- **R1** read AGENTS/agent.md + QA ACL-ADDENDUM; confirmed defect and root cause.
- **R2** created isolated worktree/branch from `dd4ca81`; implemented fail-closed
  gate in `sources/service.py` for `content_view`/`download_view`/`reprocess`/
  `edit_formal`; added focused tests; updated the test that encoded the bug.
- **R3** verification: focused tests, sources+api suites, full backend suite,
  mypy, real-TCP probe; wrote REPORT + docs implementation note; committed.

## Commands + exits (from worktree root, venv reused, no install)

```
PYTHONPATH=$PWD/backend python -m pytest tests/sources/test_lg040_revoke_availability.py -q
  -> 8 passed                                            (exit 0)
PYTHONPATH=$PWD/backend python -m pytest tests/sources tests/api -q
  -> 219 passed, 1 skipped                               (exit 0)
PYTHONPATH=$PWD/backend python -m pytest -q
  -> 862 passed, 5 skipped, 1 failed                     (exit 1)
     failure: tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins
     (pre-existing flaky parallel race; passes on isolated re-run; unrelated to sources/revoke)
PYTHONPATH=$PWD/backend python -m mypy
  -> Success: no issues found in 138 source files        (exit 0)
PYTHONPATH=$PWD/backend python probes/lg040/REVOKE-FIX-R1-20261016/tcp_revoke_proof.py
  -> 14/14 PASS                                           (exit 0)
```

## Expected status code for independent retest

`GET /sources/{revoked}/content` and `GET /sources/{revoked}/download`
(all kinds) → **HTTP 404**, `error.code = "not_found"`,
`error.details.revoked = true`; original/formal/machine bytes/history remain on
disk; `archive`/`unarchive` unchanged (openable + searchable).

## Counters / stop

- External network / LAN / model calls: 0 · retries: 0 · product inference: 0.
- OCR/vector env unset; port 8123 not used; no orphan processes (server stopped,
  port release asserted).
- Files owned by this task only:
  `backend/lightgravity/sources/service.py`,
  `tests/sources/test_lg040_revoke_availability.py`,
  `tests/sources/test_lg038_materials_flow.py`,
  `docs/08-interface-contract.md` (narrow note, no version change),
  `probes/lg040/REVOKE-FIX-R1-20261016/**`.
- `api/sources.py` not needed / unchanged. No public schema version change.
- Cost: pi unknown, **not 0**. Raw source failure history preserved.
