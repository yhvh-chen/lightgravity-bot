# LG-047 E-QA R1 — FREEZE / HANDOFF REPORT (verdict: FAIL)

> Owner: independent QA executor (NOT any A/B/C/D author, NOT the F repair owner).
> Root PM authorized this FREEZE of the `oldcandidate` E-QA run. This report is a
> READ-ONLY freeze of the *actual persisted* evidence; it makes **no product
> changes**, makes **no new model / SDK / browser / API call** (product calls
> **0 NEW**), and does **not** replay or re-seed anything.

## 0. Freeze scope and authorization

- Authorized by PM HANDOFF/FREEZE (`prototype-E-freeze-r1-20261016.txt`).
- Stopped **only** the exact predecessor wrapper and its owned descendants;
  did **not** broad-pkill, did **not** touch port 8123, the F backend-repair
  worktree, or any other worker.
- F repair worktree `proto-material-intake-fix-r1-20261016` was read-only
  (I only read its `DIAGNOSIS.md`). No product file was modified here.

## 1. Candidate / bindings (all preserved, unchanged)

QA worktree: `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-20261016`
Branch: `qa/proto-material-20261016`

| Binding | Value |
|---|---|
| HEAD (this freeze) | `217b536b94703ab476f2eb6d5c2bbe75c1fe5f4e` |
| `HEAD:backend` | `69d02e7af1554f89594290d739e457535c358345` |
| `HEAD:frontend` | `07618bb29bed372f47422b584070101196ce86bc` |
| Sealed candidate | `f7a32ac` (LG-046) |
| Contract version (live health) | `1.12.0`; SDK pinned `0.1.22` |

- `git diff --stat f7a32ac -- backend frontend tests examples docs` → only
  `docs/11` differs (PM-owned on `main`); **no backend/frontend product change**.
- The uncommitted E edits are **harness-only** (`flow_a_api.py`, `launch_app.py`)
  plus new E files (`flow_b_delivery.py`, `seed_machine.py`, evidence). No product
  source was touched.

## 2. Process stop (precise, owned-only)

| PID | What | Action | Result |
|---|---|---|---|
| `3774453` | **old wrapper** = `lightgravity-pi-bounded.py … prototype-E-independent-qa-20261016.txt` (EXACT predecessor; not this freeze wrapper) | `kill -TERM 3774453` | GONE |
| `3774454` | its child `pi` model process | died with parent | GONE |
| `3802202` | bash running `flow_b_delivery.py` (owned) | orphaned, then TERM via 3802204 | GONE |
| `3802204/3802206/3802209` | `timeout … flow_b_delivery.py` tree (owned) | `kill -TERM 3802204` | GONE |
| `3801618/3801623` | E `launch_app.py` product server (owned, port 35983) | `kill -TERM 3801618` | GONE; port 35983 released |

Untouched and verified alive: F worker `3801489` (separate worktree
`proto-material-intake-fix-r1-20261016`), port 8123 server `3320745`, gateways
8009/8080. This freeze wrapper is `3802940`.

No SDK sessions or proxies remained after stop; no unknown-side-effect process
was observed. Post-stop `ss` shows **no listener on 35983**; no E harness process
remains.

## 3. Campaign ledger — ACTUAL counts (not from stale STATUS)

Two independent ledgers, both inspected directly:

1. **Product persistent generation ledger** (`PersistentGenerationLedger`,
   root `/tmp/lg047-qa/run1`, file `generation.jsonl`; read via live evidence
   route `GET /_lg047_generation`): **count 0**, limit 12, remaining 12,
   `persistent:true`, `corrupt:false`. The `run1/generation/` dir on disk is
   **empty** → the restart-reset instance wrote no product call.
2. **E second ledger** `evidence/run1-product-ledger.jsonl` → **1 reserved**
   entry `{count:1, kind:"reserved", pid:3791237, reserve_id:"3791237-…-1"}`.
   That reservation came from a **prior** run1 instance that `start_run1.sh`
   then `rm -rf`'d, so it is **not** visible to the current product counter.

`flow_b.json` captured `ledger_before=1`, `ledger_after=1` on the OLD mounted
instance (task `…KQN0`), i.e. **no new product forward**. `flow_negative.json`
captured `count 0 → 0` (unchanged; all negatives were refused pre-forward).

**Honest summary of product calls:**

- Confirmed completed real product SDK calls (Flow A chat answer): **1**
  (Flow A used one real DeepSeek answer — see §4.2). This is internal to the
  campaign cap of 12.
- **NEW product calls during this freeze: 0.**
- **Remaining (this campaign, 12 cap): ≥ 11**, exact product-persistent value
  is **0/12 on the current run1 instance** and **1 reserved on the discarded
  instance** — the two ledgers do **not reconcile to a single exact number**
  because of the harness `rm -rf` restart. This discrepancy is recorded, not
  smoothed: the exact current product-persistent count is **0**, with a
  **1-call reservation that has no surviving durable proof**.
- Development pi calls are separate and out of scope.

## 4. Actual findings by required case (verdict FAIL)

### 4.1 Real upload plaintext → no readable body (MAIN-FLOW **FAIL**)

- `flow_a_prep.json` / `flow_b.json`: upload of `text/plain` returns **201**,
  `source.status="received"`, `derivatives=[]`, `index.lexical="not_indexed"`,
  receipt `detail="original persisted; extraction not started (LG-035)"`,
  `error_code=null`.
- `GET /sources/{id}/content` → **404 not_found** "no machine content exists".
- Explicit `reprocess` is **unsupported** for `text/plain`
  (`unsupported media type for OCR: text/plain`) — F `DIAGNOSIS.md` Finding 1/5,
  reproduced independently by F via the real `build_source_service`.
- **Verdict: required main flow (upload → selectable body → real answer) FAILS.**
  This is a genuine **product defect**, not a QA artifact.

### 4.2 Flow A real answer (partial; **no full PASS**)

- `flow_a_real.json`: after a **manual** `harness/seed_machine.py` used the
  product `ContentStore.write_machine` to materialize a machine derivative, one
  real DeepSeek answer was obtained. `fact_check` **all required facts present**
  (ORION-71, Halden Reyes, 2027-03-14, 418,250, PRJ-ORION-71, CB-8842) and
  **all decoy facts absent** (ORION-99, etc.). `resolved_source_bindings`
  matched the selected `content_hash`/`source_version`.
- **Auxiliary-only:** the manual seed is **NOT** the upload main path; it is a
  clearly-labelled auxiliary proof that a *seeded* existing body → real answer is
  possible. It does **not** satisfy the required main flow.
- **History finding (MAJOR, for repair):** the response history
  (`history.sample`, `count=1`) contains **only the user message**
  (`qa-flowA-q1`). **No assistant message and no assistant-side
  `selected_sources` persist.** The assistant sources were asserted only from
  the live HTTP response body (`answer.body.data.resolved_source_bindings`), not
  from persisted history. Claim "response history + Sources persist" therefore
  **fails as a persist case**; do not claim it.

### 4.3 Flow B delivery (worker queued → **did not run the product flow**)

Actual persisted state in `/tmp/lg047-qa/run1` (last, post-fix harness instance,
port 35983):

- Task `task_01M51YSDMCR807MQWHNPSRE3Y8` → Run `run_01M51YSDQDS7BG05YJGRQW80J4`.
- Events: `task.created → queue.enqueued → run.created → queue.claimed →
  error.recorded → task.phase_changed → error.recorded`.
- `RUN.md`: `state: failed`, `fail_reason: plan failed program validation`.
- `error.recorded` detail:
  `mode=plan_validation, code=config_invalid`, problems:
  `["subtask 'deliver' has no acceptance criteria",
    "write subtask 'deliver' has no authorized workspace boundary"]`.
- **No product SDK call** (generation ledger empty; 0 forwards).
- Artifacts: `candidate_ref=null`, no workspace → no deliverable.

**Harness-lifespan caveat (recorded precisely):** the *earlier* mounted-wrapper
harness (`FastAPI.mount("/", app)`) did **not** run the product lifespan, so the
resident coordinator/queue worker was absent → a queued task would simply never
be processed (harness defect, not a product SDK failure). The **uncommitted**
`launch_app.py` fix (insert evidence routes directly on the product app so its
lifespan runs) was exercised in the last instance: the coordinator **did** claim
the run, and the failure became **plan validation** (product-behavior gap for the
generic-chat "create a file" delivery intent: templated subtask lacks acceptance
criteria + workspace boundary). Both observations are real:
**harness defect (old instance)** and **product plan-validation gap (fixed
instance)**. No new attempt was made (freeze: 0 new calls).

**History finding for Flow B:** run1 conversation has **only the user message**
(`qa-flowB-deliver`), no assistant reply persisted — consistent with the worker
never producing a candidate.

### 4.4 Zero-call negatives (setup vs product error ordering)

From `flow_negative.json` (all pre-forward, ledger **0 → 0**, unchanged):

| Case | Got | docs/11 expected |
|---|---|---|
| N1 over-limit (4 selected) | 422 `validation_failed` "at most 3" | ✓ acceptable |
| N2 stale ref | 422 `reference_invalid` "does not resolve" | **409 `source_stale`** — mismatch |
| N3 revoked | 404 `not_found` "revoked and unavailable" | ✓ 404 |
| N4 cross-Task | 422 `reference_invalid` "scoped to another Task" | ✓ 422 |
| N5 no readable body | 422 `reference_invalid` "does not resolve" | **404/503** — mismatch |

- **N2/N5** return `422 reference_invalid` instead of the frozen docs/11
  `409 source_stale` / `404|503`. Whether this is a **wrong test setup**
  (the stale/no-body fixture resolves to "does not resolve") or a **product
  error-ordering bug** cannot be separated from this evidence alone; the exact
  scope is: *stale vs unresolvable vs body-missing are collapsed to a single
  422 `reference_invalid` on the selected-source resolution path.* F owns this
  fix. Recorded, not re-tested.

## 5. Harness defects (QA-side, not product)

1. **Mounted-wrapper lifespan** (fixed in uncommitted `launch_app.py`): must
   serve the product app directly so its lifespan runs. (F `DIAGNOSIS.md`
   Finding 2; independently visible in my harness.)
2. **`start_run1.sh` does `rm -rf`** the run1 data dir on restart → the
   product persistent generation ledger is **reset to 0**, disconnecting the
   E second-ledger reservation (1) from the product counter. For R2 reuse the
   campaign must **not** wipe the ledger root, so the 12-cap reservation is
   continuous (same campaign, no auto-extend).

## 6. UNVERIFIED / unknown (no fabrication)

- Flow B end-to-end (single real SDK worker artifact + real reviewer +
  accept-after-stop): **UNVERIFIED** — worker never delivered; no artifact hash,
  no review record, no SDK usage to report.
- Real-browser UI picker / Sources / backlink / responsive geometry: **not
  exercised in this freeze** (no browser call).
- Truncation 12000 metadata/UI, 390/1024/1440 responsiveness: **UNVERIFIED**.
- Exact reconciliation of the two generation ledgers: **UNKNOWN** (harness
  restart reset); recorded above.
- Any assistant-side persisted sources: **absent** in the two inspected
  histories (see §4.2/§4.3).

## 7. Verdict

**FAIL.** The required main flow (real upload of plain text → selectable body →
real answer → Sources/history persist) does **not** pass: the upload produces no
readable body and explicit reprocess refuses plain text. The delivery flow
produced no artifact and no SDK call. A single real SDK answer was obtained only
via an **auxiliary manual seed**, and even then the assistant reply/sources did
**not** persist to history. Negatives N2/N5 do not match the frozen contract.

## 8. Handoff for R2 (same campaign, cap 12, no auto-extend)

- **Reuse** data dir `/tmp/lg047-qa` (do **not** `rm -rf`): product ledger root
  `/tmp/lg047-qa/run1` (file `generation.jsonl`) + E second ledger
  `probes/…/E-QA/evidence/run1-product-ledger.jsonl`.
- **Guard paths:** product `LIGHTGRAVITY_MAX_GENERATION_CALLS=12` rooted at the
  isolated data dir (pre-forward in `LocalAuthProxy.begin_call`); second guard
  `harness/campaign_guard.py` (`evidence/ledger/history.jsonl`).
- **Current counts:** product-persistent **0/12** on the live instance;
  E second-ledger **1 reserved** (orphaned). Treat remaining as **≥ 11**;
  reconcile before R2 by NOT wiping the ledger.
- **Repairs owed (F/owner):** (a) native model-free UTF-8 text extraction +
  minimal upload pump; (b) stale/no-body error codes (N2/N5); (c) plan-validation
  for generic-chat file-delivery intent (acceptance criteria + workspace
  boundary); (d) assistant reply/sources persistence in history.
- **Frozen artifacts (do not replay):** `evidence/flow_a_prep.json`,
  `evidence/flow_a_real.json`, `evidence/flow_negative.json`,
  `evidence/run1-product-ledger.jsonl`, `/tmp/lg047-qa/flow_b.json`,
  `/tmp/lg047-qa/run1/**` (task/run/events/sources), `/tmp/lg047-qa/run1-ready.json`.

## 9. Checklist

- [x] Old wrapper `3774453` TERM'd by exact PID; `pi` child + owned server +
      flow_b tree confirmed stopped; 8123/F-worker/other workers untouched.
- [x] Product calls **0 NEW**; no model/API/browser/test/fixture-seed/new-harness.
- [x] Both ledgers read from actual persistence; count/remaining/unknowns frozen.
- [x] Candidate hashes/versions preserved; **no product change**.
- [x] Report + STATUS updated with actual counters; raw evidence preserved
      (redacted; no secrets copied).
- [x] No Task-047 status changed; root owns that.
