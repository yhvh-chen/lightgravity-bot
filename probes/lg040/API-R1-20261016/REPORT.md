---
title: "LG-040 R1-20261016 — API QA REPORT (independent owner)"
doc_type: report
category: qa
status: "API slice result recorded — independent; not a whole-version verdict"
updated: "2026-10-16"
---

# API QA REPORT — LG-040 R1-20261016

## 0. Identity & authority

- Independent fresh QA owner (NOT an implementer). Root PM scope only.
- Owns **only** `probes/lg040/API-R1-20261016/**`. No product/backlog/docs writes;
  no product fixes; no nested agents; no push/deploy/publish/reset/clean.
- Whole-version verdict is **not** mine alone — this is the **API slice only**.

## 1. Candidate (bound)

- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-r1-20261016`
- Branch `qa/lg040-api-r1-20261016`, HEAD (pre-QA) `dd4ca81`
- Product tree `backend/ frontend/ tests/` **byte-identical to `main@2f277fa`** at
  QA start and after QA: `git ls-tree -r HEAD backend frontend tests | hash-object`
  = `e1ec7b8988352c648d887e13617b752366a3dbd2` for both. Empty product diff. No
  product delta occurred.

## 2. Method & isolation

- Real `FileStore` + real `create_app` + **real uvicorn TCP HTTP** on loopback,
  chosen free ports (51937/37659/44443/51289 — never 8123), isolated tmp data dirs.
  ASGI transport used only for the non-loopback auth cases (no real non-loopback
  peer exists locally) — **labelled ASGI**.
- OCR/vector target env **unset** (`LIGHTGRAVITY_OCR_BASE_URL/MODEL`,
  `LIGHTGRAVITY_VECTOR_BASE_URL/MODEL/TOKEN`) → no accidental inference possible.
- Scripted in-process OCR backend used **only** for controlled mechanical faults
  (machine/formal/reprocess/version-stale). Explicitly a stub: **no quality
  evidence**, zero network calls.
- Zero external LAN/model calls. Zero product inference. No ASR/no DeepSeek
  product generation. Retries 0. Credentials never read/logged/committed.
- Server processes stopped in `finally` + SIGTERM/kill; port release confirmed.
  No leftover harness/uvicorn processes from this QA (verified via `pgrep`).

## 3. Raw evidence (all under `probes/lg040/API-R1-20261016/raw/`)

| File | Content |
|---|---|
| `01_product_sources_tests.txt` | existing `tests/sources/**` run: **147 passed, 1 skipped** |
| `02_api_cases.json` | 22 real-TCP/ASGI-auth cases — **22/22 PASS** |
| `03_mechanical_cases.json` | 7 mechanical service-layer cases — **7/7 PASS** |
| `04_extended_cases.json` | 10 extended real-TCP/service cases — **10/10 PASS** |
| `server-*.log` | uvicorn stdout (empty at warning level) |

Commands used `PYTHONPATH=backend`, `.venv` provisioned from the locked
`uv.lock` offline (`uv sync --frozen --all-groups --offline`); no dependency
subscription/provider change.

## 4. Case matrix — expected / actual / provenance

### 4.1 Real TCP + auth (02)
| Case | Expected | Actual | Result |
|---|---|---|---|
| C1 loopback health no-token | 200 | 200 | PASS |
| C2 non-loopback no token (ASGI) | 401 | 401 unauthorized | PASS |
| C3 non-loopback correct token (ASGI) | 200 | 200 | PASS |
| C4 non-loopback wrong token (ASGI) | 401 | 401 | PASS |
| C5 sensitive write w/o injected token | 401 | 401 unauthorized | PASS |
| C6 global inline → inbox ref, no Task | 201 global scope | 201 global scope | PASS |
| C7 unknown task_ref refused | 422 reference_invalid | 422 reference_invalid | PASS |
| C9 path escape refused | 403 path_outside_workspace | 403 path_outside_workspace | PASS |
| C11 request_id idempotent replay | 200 created=false dedup | 200 created=false dedup | PASS |
| C12 request_id conflict diff payload | 409 source_conflict | 409 source_conflict | PASS |
| C14 intake creates NO delivery Task | tasks [] | tasks [] | PASS |
| C16 concurrent intake 10 distinct | 10 unique 201 | 10 unique 201, listed 11 | PASS |
| C17 machine view absent w/o OCR | 404 not_found | 404 not_found | PASS |
| C17b auto view absent | 404 | 404 | PASS |
| C17c invalid kind | 422 | 422 | PASS |
| C18 formal edit w/o machine seed | 404 (no fabrication) | 404 not_found | PASS |
| C19 archive reversible | 200 archived=true | 200 archived=true | PASS |
| C20 unarchive | 200 archived=false | 200 archived=false | PASS |
| C21 revoke | 200 revoked, status archived, index not_indexed | matches | PASS |
| C22 delete unconfirmed | 409 cancellation_unconfirmed | 409 cancellation_unconfirmed | PASS |
| C23 delete confirmed | 200 deleted then 404 | 200 deleted then 404 | PASS |
| C32 vector status w/o env | 200 truthful disabled | 200 enabled=false, configured=false | PASS |

### 4.2 Mechanical service layer (03) — real FileStore, scripted OCR stub
| Case | Expected | Actual | Result |
|---|---|---|---|
| C-M1 machine derivative | succeeded, text present | succeeded, md has text | PASS |
| C-M2 formal seeded from machine | formal present | formal present | PASS |
| C-M3 reprocess non-destructive | machine new, formal kept | SECOND PASS / HELLO WORLD kept | PASS |
| C-M4 record_version | v+1, lexical=stale | v2, lexical=stale | PASS |
| C-M5 torn receipt repaired on restart | repaired, no bogus | repaired, entries intact | PASS |
| C-M6 state rebuildable from files only | source+receipt+original | all intact | PASS |
| C-M7 vector backend disabled w/o env | UnavailableEmbeddingBackend | UnavailableEmbeddingBackend | PASS |

### 4.3 Extended TCP/service (04)
| Case | Expected | Actual | Result |
|---|---|---|---|
| C8 project_ref refused w/o registry | 422 reference_invalid | 422 reference_invalid | PASS |
| C10 symlink escape refused | 403 path_outside_workspace | 403 path_outside_workspace | PASS |
| C13 scope-local dedup not merged | distinct across tasks, dedup within | matches | PASS |
| C15 inbox msg creates NO Task/Run | 201, tasks unchanged | 201, task_created=false | PASS |
| C24 cancel confirm + idempotent | 409 → cancelled → cancelled | matches | PASS |
| C25 running job not auto-replayed | recovery_required | recovery_required | PASS |
| C26 failed job can retry | queued | queued | PASS |
| C27 restart marks running recovery_required | recovery_required | recovery_required | PASS |
| C28 reprocess w/o OCR | no fabricated derivative | status=failed (honest) | PASS |
| C-ext unsupported action refused | 422/400 | 422 | PASS |

## 5. Result

- Independent cases: **39/39 PASS** (22 + 7 + 10). Existing `tests/sources/**`:
  147 passed, 1 skipped.
- No BLOCKER / MAJOR / MINOR defects found in the API slice.
- **API slice verdict: PASS** (limited to the scope below — not a whole-version
  verdict).

## 6. Remaining gaps / UNVERIFIED (honest disclosure)

- **UNVERIFIED — real OCR/vector quality**: not API scope and no inference was
  performed by design (target env unset). The `tests/sources/vectors/
  test_real_quality.py` real-quality probe is **skipped** (requires explicit
  authorization + reachable endpoint). Quality belongs to the QUALITY owner.
- **UNVERIFIED — real non-loopback peer**: auth for non-loopback is exercised via
  **ASGI-transport with a forged client host**, not a physical second host. This
  is mechanical coverage of `LocalAccessPolicy`; no real network peer was used.
- **UNVERIFIED — cross-Task permission on an owned Task with a real member
  identity** (worker_identity/worker_grant resolution) beyond the task_ref
  reference checks: out of this API slice's exercised paths.
- Browser E2E and quality statistics are other owners' paths (parallel), not
  covered here.

## 7. Counters

- External network / LAN / model calls: **0** · product inference POST: **0** ·
  retries: **0**.
- Product code/test writes: **0**; product tree stays `2f277fa`.
- QA-owned files only under `probes/lg040/API-R1-20261016/`.
- Process stop: all QA servers stopped and confirmed; **0** leftover.
- Cost: pi unknown, **not 0**.
