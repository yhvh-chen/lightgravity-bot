---
title: "LG-040 R1-20261016 — API QA ACL ADDENDUM (independent owner)"
doc_type: report
category: qa
status: "addendum — one verified MAJOR API-slice defect; original REPORT.md preserved byte-for-byte"
updated: "2026-10-16"
---

# API QA ACL ADDENDUM — LG-040 R1-20261016

## 0. Relationship to the original REPORT

This file is an **addendum only**. It does **not** edit or rewrite
`REPORT.md` (still byte-identical: `sha256 dc22a683…602d8`). The original
**39/39 PASS** result for its own case set stands **limited to that case set**;
it did not assert that `revoke` suppresses `GET content` / `GET download`, so
this addendum does not retroactively falsify those 39 cases. It **does** change
the **API slice verdict** (see §5).

- Independent fresh QA owner. Root PM scope only. Owns only
  `probes/lg040/API-R1-20261016/**` (this addendum, `owncases/**`).
  No product/backlog/docs writes, no product fixes, no nested agents, no
  push/deploy/publish/reset/clean, no remote inference.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-r1-20261016`,
  branch `qa/lg040-api-r1-20261016`, HEAD `80dd0e7`. Product tree
  `backend/ frontend/ tests/` = `e1ec7b8988352c648d887e13617b752366a3dbd2`
  (unchanged, no product delta).

## 1. Method & isolation

- Real `FileStore` + real `create_app` + **real uvicorn TCP HTTP** on a chosen
  free loopback port (never 8123; ephemeral port this run — see raw JSON).
- OCR/vector target env vars **unset** (`LIGHTGRAVITY_OCR_BASE_URL/MODEL`,
  `LIGHTGRAVITY_VECTOR_BASE_URL/MODEL/TOKEN`). Zero external/LAN/model calls,
  zero product inference POST. Retries 0. No credentials read/logged/committed.
- A **machine stub** (`status="succeeded"`, `model="scripted"`, no network) is
  used **only** to seed a trusted machine derivative so the formal-edit endpoint
  can be exercised; it produces **no quality evidence**. Human formal content is
  then written through the real `POST /sources/{id}/formal` endpoint.
- Raw reads use `Cache-Control: no-store` and re-read over a fresh TCP request
  after the revoke; the addendum explicitly captures **before-revoke** and
  **after-revoke** actuals (not stale HTTP cache).
- Server is stopped in `finally` (SIGTERM/kill) and port release is asserted;
  cleanup case `ACL-cleanup port released` = PASS.

## 2. Case matrix (all REAL TCP, zero inference)

| Case | Expected (contract) | Actual | Result |
|---|---|---|---|
| ACL-1 query TaskA excludes TaskB | only task_a source | only task_a | PASS |
| ACL-2 scoped query never reaches TaskB | task_a (+global via include_global), never task_b | task_a + global; no task_b | PASS |
| ACL-3 hit resolves scope/version/hash/existence | hit matches file SoT | matches (formal, v1, hash match) | PASS |
| ACL-4 forged/stale candidate fail-closed | forged body never returned; `source_stale` | no forged hit; `source_stale` reported | PASS |
| ACL-5 revoked source: search hit cannot leak | before hit, after empty | before hit; after empty; revoke 200 | PASS |
| **ACL-5b revoke → content/download refused** | **pre 200/200; post content+download refused (404/409/410/423)** | **post content 200, download 200 (bytes served)** | **FAIL** |
| **ACL-5b2 revoked bytes actually served over TCP** | must be false for content and download | **content_served=true, download_served=true** | **FAIL** |
| ACL-5c archive retains search/open (intended) | archived source still searchable/openable | archive 200; searchable; content 200 | PASS |
| ACL-6 deleted source no cached snippet | before hit, after empty | before hit; after empty; delete 200 | PASS |
| ACL-7 unscoped browsing = only global, never task-scoped | global present; task_a excluded; all hits unscoped | global present; task_a excluded | PASS |
| ACL-8 worker/member grant on source API | not applicable (no worker principal) | no worker_grant/identity in sources/search/vector | PASS |
| ACL-9 unknown task_ref filter yields no hits | empty (filter narrows, not grants) | empty | PASS |
| ACL-10 vector disabled → honest, no leak, no inference | enabled=false, index_unavailable, hits empty | matches | PASS |
| ACL-cleanup port released | true | true | PASS |

Addendum: **12 PASS / 2 FAIL** — the two FAILs are the same verified defect
(happy-path assertion + machine-gate assertion on the actual bytes served).

## 3. CONFIRMED DEFECT — MAJOR (verified, not speculative)

**`revoke` does not suppress the source bytes: `GET /sources/{id}/content` and
`GET /sources/{id}/download` still return HTTP 200 with the content/original
after revoke.** Search correctly suppresses the revoked source, so the
revocation is only partially honored.

### Verdict basis (expected contract refusal, actual raw 200)

- docs/08 §6.6 (line 594): `archive`/`unarchive` 是可逆整理，**保留**来源、作用域/
  权限、检索与打开能力…只有 `revoke`/`delete` 使命中失效、**资料不可用**。
  (`archive` keeps open; only `revoke`/`delete` make the material unavailable.)
- docs/08 §4.3 endpoint row (line 233): `POST /sources/{id}/actions` … `revoke`
  **使资料不可用**并失效命中。
- Contrast confirmed in-product (1.9.0): `archive`/`unarchive` only toggle the
  additive `archived` flag and never touch `status`/index/retrieval/opening
  (`service.py` L601-L613). `revoke` sets `status=archived` (L618) and
  invalidates hits. So the `status=archived` marker is the revoke marker, and a
  revoked source is required to be **unavailable**, including view/download.

### Exact minimal repro (real TCP)

Requests (after creating a sourced + formal-seeded source `src_b`, scoped to a Task):

1. `GET /api/v1/sources/{src_b}/content`  → **200** (body contains the marker) — before revoke
2. `GET /api/v1/sources/{src_b}/download` → **200** (original bytes contain the marker) — before revoke
3. `POST /api/v1/sources/{src_b}/actions` body `{"action":"revoke"}` → **200**
   (`{"source_id":"…","status":"archived","revoked":true}`)
4. `GET /api/v1/search?q="<marker>"&task_ref=<task_b>` → 200, `hits=[]` (correctly suppressed)
5. `GET /api/v1/sources/{src_b}/content`  → **200 (BUG)** — expected refusal (404/409/410/423)
6. `GET /api/v1/sources/{src_b}/download` → **200 (BUG)** — expected refusal

Raw actuals (this run; full JSON `owncases/raw/acl_addendum_cases.json`):

- `before_content_status=200`, `before_download_status=200`
- `after_content_status=200`, `after_download_status=200`
- `content_serves_marker=true`, `download_serves_marker=true`
- `content_body_sha256=b491b882b67b24e268d0fce3744162838a68f293012ea784811ede4a51ac71d2`
- `download_body_sha256=557bb354ba5a637604797d0ed7eefaf739b58c59bf187bc0a6e0b94961ca86a8`
- `source_id` example (this run's raw JSON; IDs are per-run): `source_01M51N42YZS681N664VHDXRZ5T`
  (task-scoped source; a revoked sibling in the same run showed the same 200/200
  after revoke). Exact per-case IDs are in
  `owncases/raw/acl_addendum_cases.json`.

### Minimal root cause (path + line, real source)

- `backend/lightgravity/api/sources.py:307` `GET /sources/{source_id}/content`
  → `service.content_view(...)` (L315).
- `backend/lightgravity/api/sources.py:323` `GET /sources/{source_id}/download`
  → `service.download_view(...)` (L331).
- `backend/lightgravity/sources/service.py:417` `content_view` — reads
  `self._store.read_source(source_id)` (L423) but **never checks `record.status`**.
- `backend/lightgravity/sources/service.py:459` `download_view` — same (L462),
  **no `record.status` check**.
- `revoke` sets the marker at `backend/lightgravity/sources/service.py:618`
  (`"status": "archived"`).
- The search path **does** gate: `backend/lightgravity/sources/lexical/service.py:49`
  `_INACTIVE_STATUSES = ("archived",)` and L104-L105 return
  `(None, "archived")` → hit suppressed. This asymmetry is why search refuses
  but view/download serve.
- The source record itself is **not deleted** by `revoke` (original preserved,
  `status=archived`), so `read_source` succeeds and both views proceed.

**Severity: MAJOR** — expected-contract-refusal (docs/08 §6.6 L594 / §4.3 L233)
vs raw-actual **200** serving revoked bytes over real TCP. This is a fail-closed
expectation for a material-unavailability action. Not speculative: the statuses
were reproduced end-to-end over loopback TCP with no HTTP cache and with
before/after reads.

## 4. Scope notes (honest, non-blocking)

- **ACL-8**: the source/search/vector HTTP surface has **no** worker/member
  principal (`worker_grant`/`worker_identity` are wired only in
  `api/collaboration.py`). A "worker-grant source API" case is therefore **not
  applicable** to this contract; recorded as applicability, not a pass claim of
  member-level authz.
- **Cross-Task query scoping**: already built and passing in the pre-existing
  `harness_extended_tcp.py` case C13 (scope-local dedup) plus this addendum's
  ACL-1/2/7. Not re-overloaded.
- **ACL-7**: unscoped browsing by the single-user owner is **intended**; the
  assertion is that task-scoped material never appears unscoped. Recorded
  honestly as intended (not a leak).

## 5. Refined API-slice verdict

- Original REPORT 39/39 PASS: **stands limited to its own case set** (it did not
  assert revoke view/download suppression).
- With this addendum: **API slice verdict = FAIL**, on account of the confirmed
  **MAJOR** defect (`revoke` does not make the material unavailable via
  `GET content`/`GET download`).
- Whole-version verdict is **not** mine alone — this is the API slice only.

## 6. Counters & stop

- External network / LAN / model calls: **0** · product inference POST: **0** ·
  retries: **0** (non-cache 0; no replay of unknown side effects).
- Product code/test writes: **0**; product tree stays
  `e1ec7b8988352c648d887e13617b752366a3dbd2`.
- QA-owned files only under `probes/lg040/API-R1-20261016/owncases/**` (plus this
  addendum). `REPORT.md` unmodified.
- Server stop: confirmed in `finally` + port-release assertion PASS; **0**
  leftover QA servers.
- Env: `LIGHTGRAVITY_OCR_*` / `LIGHTGRAVITY_VECTOR_*` unset. Port 8123 **not**
  used (found already in use, excluded).
- Cost: pi unknown, **not 0**.

## 7. Disposition

Root PM dispatches a fix to the **other** owner (product code owner) after this
independent receipt. No product fix was made here.
