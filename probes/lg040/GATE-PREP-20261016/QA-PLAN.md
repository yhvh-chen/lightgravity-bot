---
title: "LG-040 QA-PLAN — acceptance matrix (offline preparation)"
doc_type: plan
category: qa
status: "prepared — for the already-NAMED LG-040 concentrated source/retrieval-version QA; proposal only, no POST authorization implied"
updated: "2026-10-16"
---

# LG-040 QA-PLAN — acceptance matrix (GATE-PREP)

> **Nature.** This is **offline preparation** for the **already-named** LG-040 concentrated
> source/retrieval-version QA (docs/06 §6.2; task `backlog/tasks/LG-040.md`). It **reuses existing
> QA plans** (`probes/lg022/QA-PLAN.md`, `qa/lg022-stream/PLAN.md`,
> `probes/lg035/{QUALITY-PLAN*,TRUTH-PREP/protocol/SCORING-PROTOCOL}.md`,
> `probes/lg037/PLAN.md`, `probes/lg038/*`, `probes/lg036/*`) and **does not invent extra scope**.
> It is **not** the LG-040 verdict and **not** a new required independent gate for a single smoke.
> Any future real run needs its **own** authorization; the budget below is a **proposal**, not a grant.

## 0. Separation of evidence tiers (do not conflate)

| Tier | Meaning | Evidence today |
|---|---|---|
| **S** smoke | one/few real calls proving reachability + a shallow real result | r2: 3 GET, 2 POST (OCR Z1 CER 0.0423 PASS; embedding 768-dim) |
| **M** implementation-mechanism | real `FileStore`+real `create_app`+real HTTP with **stand-in** backends; no model | `tests/sources/**` (lexical, ocr, vectors, lg038 flow, archive semantics, intake jobs, durability) |
| **F** full real quality | frozen samples/truth + authorized real service; quality metrics (CER/Recall@k/…) | **not yet run** (blocked/unmeasured) |

LG-040 acceptance requires **M (offline)** + **F (real, authorized)** coverage. **S does not close
LG-040.**

## 1. Dependency map for LG-040 (named: 035/036/037/038/022)

| Dep | Status now | What LG-040 must verify from it | Gap carried in |
|---|---|---|---|
| **LG-022** | `done` (门内) | 首版排序门：run lifecycle / accept / stop / persistent ledger already independently QA'd. LG-040 **does not** re-run LG-022's full suite — reuse its QA evidence as the ordering gate. | None new; re-verify only the **integration seam** (sources/search under the real coordinator path if a task is created). |
| **LG-035** | `in-progress` | real image/PDF OCR quality + machine/formal layering; `content`/`download` read-only; reprocess-not-overwrite-formal. | **F missing:** Z2 table gate, mixed born-digital+scan class, low-quality/multi-page battery. **M present** (`tests/sources/ocr/**`). |
| **LG-036** | `done` (待 QA) | lexical index build + source back-check + invalidation on delete/revoke/move/formal-edit; rebuild-from-files reproduces query; corrupt/processing shown honestly; no external DB. | **M present** (`tests/sources/lexical/**`, real `create_app` + real HTTP); **F missing** on real corpora. |
| **LG-037** | `in-progress` | optional vector path honesty; model/dim/fragment-hash/cache-version recorded; model-switch rebuild; media-direct embedding; **vector-unavailable ⇒ lexical + original still usable**. | **M present** with stand-in vectors; **F missing:** real Recall@k/ranking/negative vs lexical baseline. |
| **LG-038** | `done` (待 QA) | Chat intake + Files browse/archive/reprocess/formal/download on **one** source state; no duplicate entry; link-not-fetched honesty; global upload does **not** create a delivery Task. | **M+UI smoke present** (`tests/sources/test_lg038_materials_flow.py`, `frontend/tests/lg038-materials.test.tsx`, `probes/lg038` browser fixture). |

## 2. Acceptance matrix (what to run, tier, blocker)

Legend: **[M]** offline/persisted, runnable without service; **[F]** needs authorized real service + POST;
**[S]** already covered by smoke only.

| # | Acceptance dimension | Tier | Concretely checks | Current blocker |
|---|---|---|---|---|
| A1 | Chat real upload/drag → receipt; link recorded-not-fetched | M + F | `POST /sources` idempotent by `request_id`; per-file receipt states; `origin.fetched=false` ≠ indexed | **F** needs real UI/browser upload |
| A2 | Attribution / scope (Task/Project/inbox; global upload no Task) | M | scope resolution; inbox fallback; no delivery Task/Run created | none (M runnable) |
| A3 | OCR image/PDF quality (clear/low/multi-page/**table**/**mixed**) | F | per-class CER vs frozen truth (`SCORING-PROTOCOL` §2) | **F**: Z2 table + **mixed born-digital+scan missing/BLOCKED**; endpoint authorized-run needed |
| A4 | Machine vs formal layering; reprocess ≠ overwrite formal | M | `derivatives/` vs `formal/` separation; reprocess new version | none |
| A5 | Lexical search + source back-check (existence/permission/version/hash) | M | `GET /search` 200; stale/revoked ⇒ `source_stale`; honest `index_unavailable` | none |
| A6 | Invalidation: delete/revoke/move/formal-edit ⇒ old hits fail | M | `source.invalidated`; no dangling hits | none |
| A7 | Index rebuild from files reproduces query; corrupt/processing honest | M | delete cache → rebuild → same query; corrupt index path | none |
| A8 | Optional vector path honesty (`status`/`search`/`rebuild`) | M | disabled default; unavailable ⇒ `lexical_fallback=true`, `hits=[]`; no separate vector DB | none |
| A9 | Vector **retrieval quality** (Recall@k/ranking/negative vs lexical) | F | pre-registered Chinese query set + relevance truth | **F unmeasured** (`LG037_RUN_REAL_VECTOR=1` gated; endpoint run needed) |
| A10 | Cross-modal direct embedding (image/audio → vector, not faked as text) | F | media `input[].content[]`; vector ≠ transcription | **F**: real image/audio embedding; ASR blocked |
| A11 | Model-switch ⇒ rebuild; incompatible vectors not mixed | M | model/version change triggers rebuild | none |
| A12 | Permissions: query + hit-source both authorized; cross-Task no leak | M | scope narrowing; cross-Task query returns no foreign hits | none |
| A13 | Async/idempotency/cancel/restart; side-effect-unknown not auto-replayed | M | `request_id` conflict; cancel needs confirmed stop; recovery | none |
| A14 | Vector backend unavailable ⇒ lexical + original view still available | M | degradation | none |
| A15 | Resource cost of intake/rebuild/query recorded | M/F | timing/call counts; unknown where unmeasured | none |
| A16 | **Chinese ASR** | — | **out of LG-040 hard scope** | LG-041 locked (LG-039 negative); not a blocker for this version |

## 3. Offline (persisted) vs needs-service split

- **Runnable offline now, no POST, no install:** A2, A4, A5, A6, A7, A8, A11, A12, A13, A14 (all [M]);
  plus the TRUTH-PREP scorer and re-scoring r2 raw evidence (already done in REPORT §3).
  These live in `tests/sources/**` and reuse the existing prior QA harnesses.
- **Needs authorized service + POST (future gate):** A1 (browser), A3 (OCR battery incl. Z2/mixed),
  A9 (vector retrieval quality), A10 (cross-modal). A15 partially.
- **Explicitly not in this version's hard gate:** A16 real Chinese ASR (LG-041).

## 4. Precise missing / boundary items (vs latest docs & product test evidence)

1. **Missing real fixtures:** Z2 table page (binary `binary_ready`, gate unrun); **mixed
   born-digital+scan** paired sample (**BLOCKED**, no licensed paired truth); low-quality/multi-page
   real battery; frozen **Chinese query set + relevance truth** for retrieval (defined in
   `probes/lg037/PLAN.md`, not yet run).
2. **Missing real metrics:** real OCR per-class CER (only Z1 smoke exists); real Recall@k / MRR /
   ranking / negative-hit counts vs lexical baseline (none).
3. **Missing cross-modal evidence:** real image→vector and audio→vector direct-embed (stand-in only);
   real ASR (blocked).
4. **Chat/Files:** mechanism + UI smoke exist; **real browser upload / deep-link / cross-view same
   state** not re-run in this audit.
5. **Revoke vs archive:** `revoke` (unusable + hits invalidated, `status=archived`) vs reversible
   `archive`/`unarchive` (keeps search/open/permission) — mechanism tested; real-data confirmation pending.
6. **Permissions:** scope/permission mechanisms tested; real multi-Task isolation on real corpus pending.
7. **Rebuild:** cache delete/rebuild + model-switch rebuild tested with stand-ins; real vector rebuild
   pending (needs service).
8. **Corrupt index / vector-unavailable degradation:** mechanism tested; real corruption injection pending.

## 5. Minimal future LG-040 gate call budget (PROPOSAL ONLY — no POST authorized here)

Proposal shape (final numbers are the PM/user's call; **unknown where unmeasured**):

- **GET (read-only reachability + status):** ≤ 4 (health, models, vector/status, one search) before freeze.
- **POST (real inference) — one frozen plan, separate commit before first call:**
  - OCR: Z1 re-run 1 + Z2 table 1 + one mixed/low-quality 1 + one multi-page page 1 ≈ **≤ 8**.
  - Embedding/vector retrieval: 1 embed-per-query over a frozen small set (e.g. ≤ 20 queries, batched
    where supported) ≈ **≤ 20 POST** total for the quality set, plus **1 rebuild trigger**.
  - Cross-modal: 1 image + (audio only if LG-041 ever unlocks) ≈ **≤ 2**.
  - **Retries 0; concurrency 1; per-call timeout per existing plans (cold bound frozen).**
- **Total proposal ceiling:** ≈ **≤ 3 GET + ≤ 30 POST**, all under the **single persistent generation
  ledger** where the product path is used; offline [M] suite = 0 real model calls.
- **Mandatory conditions:** freeze plan in one commit **before** first POST (addresses REPORT §5 caveat);
  pre-register thresholds; separate commits for plan vs results; honest fail on unreachable endpoint.

## 6. What this prep explicitly does NOT do

- Does **not** run the gate, **does not** emit a pass/fail verdict, **does not** close LG-035/037,
  **does not** unlock LG-041, **does not** assume POST authorization.
- Does **not** duplicate a broad full suite (no full pytest re-run here; reuse existing [M] evidence).
- Does **not** read the parallel quality executor's `probes/materials-quality-20261016-r3/**` as final
  and does **not** require it to wait for this prep.
- **37 done / 2 in-progress / 2 todo are not closed by the r2 smoke.** "Existing 37 done, 2 in-progress,
  2 todo do NOT close from smoke" (docs/06 §6.1 final CLI read).
