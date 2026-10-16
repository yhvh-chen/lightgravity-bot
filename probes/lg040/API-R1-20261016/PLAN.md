---
title: "LG-040 R1-20261016 — API QA plan (independent owner)"
doc_type: plan
category: qa
status: "owner case matrix — frozen before execution"
updated: "2026-10-16"
---

# API QA PLAN — LG-040 R1-20261016

## Candidate (bound)

- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-r1-20261016`
- Branch `qa/lg040-api-r1-20261016`, HEAD `dd4ca81`
- Product tree `backend/ frontend/ tests/` byte-identical to `main@2f277fa`
  (verified by `git ls-tree` object hash `e1ec7b89…`, empty product diff).
- Any product delta during QA = defect/stop, not silent adaptation.

## Method

- Real `FileStore` + real `create_app` + **real uvicorn TCP HTTP** (loopback, this
  worktree only, chosen free port, never 8123). ASGI/TestClient adds mechanical
  coverage only and is labelled as such.
- OCR/vector target env **unset** (`LIGHTGRAVITY_OCR_BASE_URL/MODEL`,
  `LIGHTGRAVITY_VECTOR_BASE_URL/MODEL`) so no accidental inference; stubs only for
  controlled mechanical faults, explicitly labelled, never quality evidence.
- Zero external LAN/model calls. Zero product inference. No ASR/no DeepSeek
  product generation. No retries. Credentials never logged/committed.

## Case matrix (expected / actual / provenance)

| # | Case | Path | Expected |
|---|---|---|---|
| C1 | Auth: loopback no-token allowed (non-sensitive) | `GET /health` | 200 |
| C2 | Auth: non-loopback without token denied | `GET /sources` (forge client host) | 401 unauthorized |
| C3 | Auth: non-loopback with correct token allowed | `X-LG-Token` | 200 |
| C4 | Auth: non-loopback with wrong token denied | `X-LG-Token=bad` | 401 |
| C5 | Sensitive write denied without injected token | `POST /settings/connections` | 401 |
| C6 | Scope: global inline source → inbox ref, NO Task/Run | `POST /sources` | 201, tasks empty |
| C7 | ACL: unknown task_ref refused | `POST /sources` scope | 422 reference_invalid |
| C8 | ACL: project_ref refused w/o registry | `POST /sources` scope | 422 reference_invalid |
| C9 | Path escape refused | `POST /sources path=../` | 403 path_outside_workspace |
| C10 | Symlink escape refused | `POST /sources` symlink | 403 |
| C11 | request_id idempotent replay (same payload) | `POST /sources` | 200 created=false dedup |
| C12 | request_id conflict (diff payload) | `POST /sources` | 409 source_conflict |
| C13 | Scope-local dedup not merged across tasks | `POST /sources` two tasks | distinct ids |
| C14 | Intake creates NO delivery Task/Run | `POST /sources` + `GET /tasks` | no task |
| C15 | Inbox message creates NO Task | `POST /inbox/messages` | no task |
| C16 | Concurrent intake N distinct sources persisted | real HTTP parallel | N unique, all readable |
| C17 | Machine/formal content views distinct kinds | `GET /sources/{id}/content` | machine vs formal |
| C18 | Formal edit bumps revision, preserves machine | `POST /sources/{id}/formal` | new rev |
| C19 | Archive (reversible) keeps status/index/retrieval | `POST actions=archive` | archived flag only |
| C20 | Unarchive reverses | `POST actions=unarchive` | archived=false |
| C21 | Revoke makes unavailable + invalidates index hits | `POST actions=revoke` | status archived, hit gone |
| C22 | Delete requires confirmation | `POST actions=delete` unconfirmed | 409 |
| C23 | Delete confirmed removes original, invalidates hits | `POST actions=delete` confirmed | deleted |
| C24 | Cancel requires confirmation; idempotent | `POST intake jobs cancel` | 409 then cancelled |
| C25 | Running job not auto-replayed → recovery_required | retry running job | 409 illegal_transition |
| C26 | Failed job can retry | retry failed job | queued |
| C27 | Restart marks running job recovery_required | recover() | recovery_required |
| C28 | Reprocess → new machine derivative, formal preserved | `POST actions=reprocess` | machine new, formal same |
| C29 | Stale index on new version | `record_version` | lexical=stale |
| C30 | Corrupt/torn receipt JSONL repaired on restart | reopen store | repaired, no bogus |
| C31 | State rebuildable from authoritative files only | drop caches | source+receipt intact |
| C32 | Vector backend unavailable → lexical fallback, no crash | vector/status + search | unavailable truthful |

## Pass rules

- Each case ⇒ PASS/FAIL/UNVERIFIED. Uncovered ⇒ UNVERIFIED, never pass.
- Severity BLOCKER/MAJOR/MINOR with minimal repro (path + line + actual state).
- Verdict is only the **API slice**: PASS / FAIL / INCOMPLETE.
