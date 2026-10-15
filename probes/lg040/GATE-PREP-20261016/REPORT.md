---
title: "LG-040 GATE-PREP — REPORT (independent evidence audit of r2 smoke)"
doc_type: report
category: probe
status: "complete — offline audit done; 1 honest caveat + boundary clarifications; no service/POST/status change"
updated: "2026-10-16"
---

# REPORT — LG-040 GATE-PREP-20261016

## 0. One-line result

Independent **offline** audit of the `materials-retry-20261016-r2` smoke evidence reproduces its
headline numbers exactly (**3/3 GET 200; 2/2 POST; OCR Z1 CER 0.0423 ≤ 0.15 PASS; embedding 768-dim
finite nonzero L2=1.0; ASR 0 POST**), confirms the freeze/provenance claims hold, confirms product
code was **not** modified, and flags **one honest methodological caveat** (self-declared PLAN freeze
time cannot be proven from git alone) plus the pre-existing scope limits (mixed-PDF class, real ASR,
real retrieval quality unmeasured). This is **QA preparation**, not the LG-040 version verdict.

## 1. Scope & authority compliance

- Independent pi auditor/QA-prep owner; **no nested agents**; root did **not** code-review.
- **Offline only**: 0 network, 0 POST, 0 service calls, 0 new live testing, 0 credential values read.
- Product code **read-only** (verified byte-identical between audit base and smoke commit for `backend/`).
- No task status changes, no docs/contracts changes, no push/deploy/publish, no merge to main.
- Sole owned writes: `probes/lg040/GATE-PREP-20261016/**`.
- Did **not** read the parallel quality executor's partial results as final; that executor writes
  only `probes/materials-quality-20261016-r3/**` (different branch/owner) — no conflict, no dependency.

## 2. Claim-vs-record audit (smoke package @ `b3b7b4f`)

Source: `probes/materials-retry-20261016-r2/{REPORT,PLAN,STATUS}.md`, `evidence/*.json`, `http/*`.

| Claim | Record checked | Verdict |
|---|---|---|
| Stage A **3 GET 200** (`/health`,`/v1/models`,`/props`) | `http/stageA_results.json`: all `http_status=200`, `retries=0`, `num_connects=1`; raw bodies present | **CONFIRMED** |
| Service is llama.cpp **router**, not Ollama | `http/props.raw.json`: `role=router`, `build_info=b11641-843e7dcc1`, `model_alias=llama-server` | **CONFIRMED** |
| **Budget frozen before POST** (2 POST cap) | `PLAN.md` header + declared counters; reached exactly 2/2, 0 retries | **CONFIRMED with caveat** (see §5) |
| POST budget **2/2** exactly | REPORT §6; OCR 1 + embedding 1; no ASR POST | **CONFIRMED** |
| Real **Z1 provenance**: PD scan + human level-3 truth | `truth_manifest.json` records PD license + ProofreadPage level-3 pairing; `truth/LG035-ZH-Z1.p10.txt` present | **CONFIRMED** |
| Fixture **hash** matches manifest | `sha256sum` = `5c73b9d0…e64f` == OCR input `input_sha256`/PLAN/manifest | **CONFIRMED** |
| OCR **CER 0.0423**, threshold **0.15** PASS | Recomputed offline (§3) from recorded hypothesis vs human truth | **CONFIRMED (independently reproduced)** |
| Product `OpenAICompatOcrBackend` **unmodified** | `git diff db01cd6 b3b7b4f -- backend/` = empty; commit touches only `probes/materials-retry-20261016-r2/**` (14 files) | **CONFIRMED** |
| Embedding **768-dim, finite, nonzero, L2=1.0**; **not a quality claim** | `evidence/embedding_result.json`: `dim=768`, `finite=true`, `nonzero=true`, `l2_norm=1.0`; REPORT §5 explicitly defers Recall@k | **CONFIRMED** |
| **ASR 0 POST**; LG-041 locked | No audio/transcription call in evidence scripts; REPORT §3 documents declared-but-unusable audio | **CONFIRMED** |
| No credential values in package | Grep for `sk-`/`api_key`/`Bearer`/`token=` → none; raw bodies non-sensitive | **CONFIRMED** |
| Task statuses / contracts unchanged | Commit touches no `backlog/`, `docs/`, `backend/`; LG-040/041 remain `todo` | **CONFIRMED** |

## 3. Independent offline CER recompute (no network)

Method (same as `SCORING-PROTOCOL.md` §1): `NFKC` normalize then strip whitespace; Levenshtein over
Unicode code points; `CER = edit_distance / len(norm_truth)`; timestamp threshold 0.15 pre-registered.

```
truth_chars(norm) = 189
hyp_chars(norm)   = 193
edit_distance     = 8
CER               = 0.0423
threshold 0.15 -> PASS
```

Result **reproduces the recorded `ocr_cer.json` exactly** (189/193/8/0.0423/PASS). This validates the
arithmetic and the truth pairing; it does **not** upgrade the smoke to a quality battery.

## 4. What the smoke does and does not establish

- **Establishes** (mechanism/real single-call): a real OCR adapter call on one real PD Chinese page
  at CER well under the pre-registered gate; a real embedding call returning a finite normalized
  vector; endpoint reachability as of the r2 run.
- **Does NOT establish** (must not be read as done): full OCR quality battery (Z2 table, low-quality,
  multi-page mixed, born-digital+scan mixed class — **missing/blocked**); real retrieval quality
  (no Recall@k / ranking / negative controls — **unmeasured**); ASR (0 POST; **unusable backend**);
  product end-to-end through Chat/Files; permission/revoke/rebuild behaviour on real data.
- **Therefore** the smoke does **NOT** close LG-035/037, does **NOT** unlock LG-040/041. See
  `QA-PLAN.md` for the exact LG-040 acceptance matrix.

## 5. Honest discrepancies / caveats

1. **Freeze-time caveat (minor, methodological).** "Frozen before any POST" is a **self-declared**
   property of `PLAN.md`. PLAN and the POST artifacts landed in the **same commit** (`b3b7b4f`), so
   git alone cannot independently prove the wall-clock freeze preceded the first POST. Consistency
   evidence: the declared 2/2 cap was reached exactly with 0 retries and the PLAN contains no
   post-hoc threshold relaxation. **Recorded as caveat, not as falsification.** A future gate should
   freeze the plan in a **separate commit** before the first inference call to make this auditable.
2. **"ASR 0 and 041 locked"** — confirmed, but note `embeddinggemma-2-Q8_0` **declares** an `audio`
   input modality while remaining embeddings-only; this is a declared-but-unusable path, not an ASR
   capability. LG-039's negative conclusion stands (independent evidence, not re-run here).
3. **Z2 table gate not exercised.** The TRUTH-PREP Z2 binary is `binary_ready` (sha1 verified) but the
   table structure/segment gate remains unrun. Class coverage gap carried into the acceptance matrix.
4. **Mixed born-digital + scan class** remains **missing/BLOCKED** (no licensed paired truth obtained).

No implementer evidence was modified. No discrepancy was found in the recorded numbers themselves.

## 6. Offline-runnable vs needs-service split (summary)

- **Offline / already-persisted (testable now, no POST):** mechanism JSON/HTTP tests under
  `tests/sources/**` on real `FileStore` + real `create_app` + real HTTP (no model); upload/attribution/
  archive/reprocess/revoke/rebuild-permission semantics with stand-in backends; lexical index
  rebuild/invalidations; vector cache delete/rebuild/model-switch with stand-in vectors; the
  TRUTH-PREP CER scorer; the r2 raw evidence re-scoring.
- **Needs service (future, authorization-gated, POST):** real OCR quality battery (Z1/Z2/mixed/
  multi-page), real embedding/vector retrieval quality (Recall@k/ranking/negative vs lexical
  baseline), real cross-modal (image/audio → vector) search, real ASR (LG-041 only).
- Detailed matrix + minimal future-gate call budget proposal: `QA-PLAN.md`.

## 7. Deliverables & evidence index (this package)

- `STATUS.md` — authority/scope, first-5-rounds plan, counters.
- `REPORT.md` — this audit.
- `QA-PLAN.md` — LG-040 acceptance matrix (named dependencies 035/036/037/038/022), boundary/blocker
  list, offline-vs-service split, and a **proposal-only** minimal future-gate call budget.
- `evidence/cer_recompute.md` — offline CER recompute record (command + result + hashes).
- Base `main` @ `db01cd6`, audit worktree `qa/lg040-gate-prep-20261016`.

## 8. Non-claims

This report does **not** claim LG-040 passed, does not close LG-035/037, does not unlock LG-041, does
not change any task status, and does not modify product code, contracts, or shared docs. Costs of
future real runs are **unknown where unmeasured**.
