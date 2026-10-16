---
title: "LG-040 QUALITY-R1-20261016 — PARTIAL/FINAL REPORT (English-primary slice)"
doc_type: report
category: qa
status: "INCOMPLETE slice — executed within frozen budget; not a full LG-040 PASS claim"
updated: "2026-10-16"
---

# REPORT — LG-040 QUALITY-R1-20261016 (independent QUALITY QA slice)

## 0. Continuation provenance (honest)

- This is an **explicit continuation** of an independent LG-040 QUALITY QA run, **not an automatic
  replay**. The original wrapper exited `143` (max-rounds, 868 s) with last message `Now run phase2`.
- On resume: **no live writer/proxy process** was found (`run_phase1/phase2`, `counting_proxy`,
  ports 18140/18141 all absent); the product tree on `qa/lg040-quality-r1-20261016` is still
  `backend/ frontend/ tests/ == 2f277fa`. No side effects were replayed.
- **Phase 1 was already fully executed and persisted** (OCR×2 + 10 embedding POST, vector build,
  queries, lexical contrast, `phase1/analysis.json`). Phase 2 was **also already executed and
  persisted** (`evidence/phase2.json`: PNG image embed, cache DELETE+rebuild×4, Q3′, Q1″). The
  wrapper died **after** phase-2 network work, **before** phase-2 scoring and the final report.
- Therefore this continuation **only added offline scoring + this report** — it issued
  **0 new model requests, 0 network POST, 0 health/models GET**.

## 1. Candidate under test

- Product candidate = **`main@2f277fa`** (`2f277faf39364232f01c7a02f5a44db3d8b27301`).
- QA branch `qa/lg040-quality-r1-20261016`; owned writes only `probes/lg040/QUALITY-R1-20261016/**`.
- Product tree `backend/ frontend/ tests/` unchanged (`== 2f277fa`); QA wrote **no product/test code**.
- Endpoint (used only during the already-executed phase): `http://192.168.8.12:11434`, models
  `qwen3.8-27b` (OCR) and `embeddinggemma-2-Q8_0` (embedding, dim 768, cache_version 1).

## 2. Model-call counters (durable, actual — not 0)

From the two counting-proxy ledgers (`evidence/phase1/proxy_ledger.jsonl`,
`evidence/proxy_ledger.jsonl`), all `forwarded: true`, retries 0:

| Kind | phase 1 | phase 2 | used | cap | remaining |
|---|---|---|---|---|---|
| OCR POST (`/v1/chat/completions`) | 2 | 0 | **2** | 2 | **0 (exhausted)** |
| embedding POST (`/v1/embeddings`) | 10 (1× HTTP 500) | 7 | **17** | 18 | **1** |
| health/models GET | 2 (separate earlier attempt, see note) | 0 | **2** | 2 | 0 |
| **inference POST total** | 12 | 7 | **19** | ≤20 | 1 |

- No 429/cap-rejection rows in either ledger. No ASR, no worker, no DeepSeek product generation.
- **Unknown in-flight risk**: the wrapper exited after phase-2 wrote its evidence file; the last
  ledger row is phase 2's `Q1_rebuilt` embedding. No request was in flight at resume. Retry 0 held.
- Cost: pi **unknown, not 0** (prior wrapper used DeepSeek; this continuation issued 0 model calls).
- Note on GET budget: the ledger proxy counts `health_get`, but the phase-1 harness comment records
  the 2 GETs as consumed by an **earlier attempt outside this ledger**; the ledger itself holds only
  POST rows. GET usage is therefore reported as **≤2 consumed / 0 issued in this continuation**.

## 3. Frozen inputs / truth (fixed before any POST)

- Corpus frozen in commit `3ed3259` before any call: D1 NIST SP 811 SI-units text
  (`fa74a73e…`), D2 tesseract `phototest.gold.txt` (`76ef157b…`), D3 tesseract `phototest.tif`
  (`d2241a1e…`), D4 real-human Wikimedia audio ≤10 s (`1eede9d1…`), plus the mixed NIST+scan PDF
  (`0f728601…`). No new downloads, no synthetic quality, no post-hoc label expansion.
- Labels/gates/metrics frozen in `frozen/LABELS.json`. Q1 text→D1, Q2 text→D2, Q3 image→D3,
  Q4 audio→D4 (indicative), QN negative.
- **Product API defect independently under separate fix (out of QA scope):** a whole-source
  `revoke`/content/`download` MAJOR is being fixed under a different implementation. This QA did
  **not** modify product and did **not** call a full-version pass. The frozen-candidate quality data
  below remains valid; the affected seam will need its own retest.

## 4. OCR quality (2 pages, mixed born-digital + scan PDF, `qwen3.8-27b`)

| Page | input_sha256 | got_chars | truth_chars | edit_distance | CER |
|---|---|---|---|---|---|
| 1 (native NIST page) | `265f187a…` | 2272 | 600 | 1674 | **2.79** |
| 2 (real scan) | `1aebdc63…` | 284 | 284 | 0 | **0.00** |

- Page 1 `cer 2.79` is a real, disclosed **quality defect**: on a dense native typeset page the
  model emitted 2272 chars against a 600-char truth excerpt, i.e. **gross over-generation
  (hallucinated/extraneous content)** relative to the frozen human text. Page 2 real-scan is exact.
- OCR path itself is mechanically sound (normal product `ProcessingEngine`/`IntakeService`
  reprocess action, 2/2 succeeded, `machine.v1.md` + paginated derivative present).

## 5. Retrieval ranking — vector vs lexical (frozen query battery)

### Phase 1 (index D1,D2,MIX,D4; TIFF image **failed to embed**)

| Q | positive | vector order (top) | R@1 | MRR | gate |
|---|---|---|---|---|---|
| Q1 | D1 | **D1**, MIX, D2, D4 | 1.0 | 1.0 | G1 |
| Q2 | D2 | **D2**, MIX, D1, D4 | 1.0 | 1.0 | G1 |
| Q3 | D3 | D2, MIX, D1, D4 (D3 **absent**) | 0.0 | 0.0 | G2 |
| Q4 | D4 | **D4**, D2, MIX, D1 | 1.0 | 1.0 | G3 (indicative) |
| QN | none | D1, D2, MIX, D4 | — | — | G4 |

- Lexical `GET /search` contrast recorded (`lexical_queries.json`): Q2 lexical neutral-noun
  mismatch produced sparse lexical hits while vector ranked D2 top-1 → **vector adds recall over
  lexical** on this battery.

### Phase 2 (PNG image embedded; cache DELETE + rebuild; 5-doc index incl. image vector)

| Q | positive | rebuilt vector order (top) | R@1 | gate |
|---|---|---|---|---|
| Q3′ image | D3 | D2, **D3**, MIX, D1, D4 (rank **2**) | 0.0 | G2 FAIL |
| Q1″ text | D1 | **D1**, MIX, D2, D4, D3 | 1.0 | reproducibility PASS |

- Cache delete + rebuild is a **real reproduction** (5/5 indexed, `not_indexed=[]`,
  `rebuild_wall_s=10.355`, `cache_version=1`), not a fake.
- **Independent cosine recomputation** from raw wire vectors (not trusted from the service)
  reproduces the service order **exactly** for Q3′ and Q1″ (`phase2_analysis.json`). Phase 1
  independent recompute also reproduced Q1/Q2/Q4/QN orders.
- **PNG vs TIFF**: phase-1 TIFF image embed failed (`vector_backend_failed`, HTTP 500
  `05_embedding_POST.json`); the PNG image **did** embed and entered the index. So the image-vector
  path works, but only for PNG here.

## 6. Gate summary (frozen definitions)

| Gate | Result | Basis |
|---|---|---|
| **G1 text** | **PASS** | Q1,Q2 vector top-1 correct, Recall@1 = 1.0 |
| **G2 image** | **FAIL** | Q3 vector top-1 ≠ D3; rebuilt image ranked **2** |
| **G3 audio (indicative)** | **PASS (indicative)** | Q4 top-1 = D4; real audio is **mixed-language, no ASR**, so this is indicative only, not proof of English audio retrieval |
| **G4 negative (informational)** | 4 false hits in top-5 | No abstention (expected per docs/09 §7); recorded as quality metric, **not** an ACL bug |
| Cache delete+rebuild reproduction | PASS | 5/5 indexed after delete |
| OCR page-2 (real scan) CER | PASS (0.00) | exact |
| OCR page-1 (dense native) CER | **FAIL/defect** | CER 2.79, over-generation |

## 7. Required-case PASS/FAIL/UNVERIFIED (English-primary slice)

- **PASS**: English text vector retrieval (G1) + lexical contrast; real PNG image intake →
  image vector embed; cache delete/rebuild reproduction + post-rebuild reproducibility; OCR of a
  real scan page.
- **FAIL (important quality defect)**: image retrieval top-1 (G2) — the true image source is
  ranked 2 behind a text doc; and OCR CER on a dense native typeset page (2.79).
- **UNVERIFIED (not executed — out of budget/scope, honestly declared)**:
  - TIFF → image vector embedding (failed HTTP 500; only PNG verified) — **real image-embedding
    limitation, not hidden**.
  - Browser real-upload/UI/E2E seam (BROWSER owner; the independently-fixed revoke/download MAJOR
    seam needs its own retest).
  - English **audio** retrieval as an English claim (Q4 is mixed-language, no ASR).
  - Concurrency/idempotency/cancel/restart/corrupt-index/unavailable-backend ACL behavior (API owner).
- **Weak-path mechanics are not counted as quality** (no over-claim). Chinese R5 image rank-7 stays
  a historical, disclosed limitation (not a standalone blocker).

## 8. Process / budget honesty

- Prior wrapper terminated at max-rounds (exit 143) **after** both phases had performed and persisted
  their network work; side effects are bounded to the two ledgers above (all `forwarded`, 0 retries).
  No unknown request was replayed; the unused 1 embedding slot was **not** spent (no planned need).
- **No physical ledger reset**; caps persisted before every forward (`counting_proxy.py` rejects
  over-cap with 429 before any upstream connection). No helper that resets the ledger per run.
- No nested agents, no push/deploy/publish/reset/clean, no product writes, no browser/API worktree or
  port 8123 touched. Browser + browser-closure wrappers already EXITED; model slot free.
- **All owned server/proxy processes confirmed stopped** (ports 18140/18141 and the QA app port are
  not listening; no `run_*`/`counting_proxy` process alive).
- Cost: pi unknown, **not 0**; this continuation issued 0 model calls. **Not a full-version PASS.**

## 9. Raw evidence paths

- `evidence/phase1/proxy_ledger.jsonl`, `evidence/proxy_ledger.jsonl` (all POSTs)
- `evidence/phase1/raw_responses/01..12_*.json` (OCR + embedding bodies, full raw vectors + usage)
- `evidence/raw_responses/01..07_embedding_POST.json` (phase-2 rebuild/query bodies)
- `evidence/phase1/{analysis,ocr_cer,ocr_mixed,ocr_machine_content,vector_build,vector_queries,lexical_queries,vector_status_after_build,models}.json`
- `evidence/phase2.json` (PNG intake, cache delete, rebuild, Q3′/Q1″, status_after)
- `evidence/phase2_analysis.json` (offline phase-2 scoring + independent recompute)
- `frozen/LABELS.json` (frozen pre-POST truth/labels/gates)
- Product cache: `/tmp/lg040-quality-r1-20261016/data/sources-index/**/vectors.jsonl`

## 10. Verdict

- This **QUALITY slice is INCOMPLETE**, not a full LG-040 PASS. English text retrieval, cache
  reproduction and scan OCR pass; **image retrieval top-1 (G2) FAILs** and **dense-native OCR CER is
  a defect**. Full LG-040 acceptance also requires the browser and API lines plus the revoke/download
  seam retest, which this slice did not cover.
