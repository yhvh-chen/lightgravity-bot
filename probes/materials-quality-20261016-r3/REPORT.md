---
title: "Materials Quality R3 — REPORT (LG-035 OCR + LG-037 retrieval, real quality)"
doc_type: report
category: probe
status: "complete — real service reachable; OCR Z2 table FAIL; retrieval vector vs lexical measured; ASR untouched"
updated: "2026-10-16"
---

# REPORT — materials-quality-20261016-r3

## 0. One-line result

Authorized endpoint **`http://192.168.8.12:11434` reachable** (1/1 GET `/health` HTTP 200).
On the frozen budget (**16/18 POST**, 0 retries, concurrency 1) the product paths produced:
**LG-035 OCR of real Z2 PDF page 2 → FAIL** (table structure collapsed, segment CER 0.328 >
0.25) while Z1 printed-page OCR already **PASSED** in the prior smoke (r2, CER 0.0423 ≤ 0.15);
**LG-037 retrieval → vector Recall@5 1.0 / MRR 1.0 vs lexical Recall@5 0.7 / MRR 0.8, BUT
vector negative controls leaked 5/5 (no relevance threshold) vs lexical 0/5.** Valid real
evidence for **both** tasks; **no task marked done**, **ASR POST = 0**, LG-041 locked.

## 1. Authority & scope compliance

- Single pi executor (no nested agents). No push/deploy/publish/merge/cherry-pick/reset/clean.
- Writes confined to `probes/materials-quality-20261016-r3/**`. Product/backend/tests/contracts/
  task files **read-only**; **no product code edited** (verified in §7).
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-quality-20261016-r3`,
  branch `test/materials-quality-20261016-r3`, base **`main @ db01cd6`** (clean, verified).
- Prior smoke branch `test/materials-retry-20261016-r2 @ b3b7b4f` report/evidence re-read as prior
  fact, **not re-run**; its `/v1/models` metadata reused verbatim (sha256 `39edaab5…` matches r2).
- **ASR POST 0** this phase; LG-039 negative true-human-audio result **preserved unchanged**;
  **LG-041 remains locked**.

## 2. Health / capability (GET + reused metadata)

- GET `/health` → **HTTP 200**, `{"status":"ok"}`, time 0.0013 s, connects 1, retry 0 (raw in
  `private/health.body`, 0600). **GET used 1/1 planned (cap 2).**
- Reused r2 `/v1/models` metadata (`http/models.reused-from-r2.json`, sha256 `39edaab538…`,
  byte-identical to r2): llama.cpp **router** `b11641-843e7dcc1`, not Ollama. Actual model IDs:
  OCR = **`qwen3.8-27b`**; embedding = **`embeddinggemma-2-Q8_0`** (768-dim, text+image+audio
  input declared, mean pooling).

## 3. LG-035 OCR — real Z2 PDF page 2 (product `PdfiumRasterizer` + `OpenAICompatOcrBackend`)

- Input `private/LG035-ZH-Z2.pdf` sha256 `da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a`
  (392,964 B, Public domain, 18 pages, pure scan, no text layer). **Only page 2 rendered/OCR'd.**
- Rasterizer (product, unmodified), scale 2.0: page 2 → PNG **164,473 B**, grid 408×689,
  sha256 `15ca62198b90b2effee1ef5933f4104fb3d986637b040a0da0b0d89e7ddf3ac4`.
- OCR POST #1: `/v1/chat/completions`, model `qwen3.8-27b`, temp 0, stream false, cold timeout 120 s,
  **HTTP 200**, finish_reason `stop`, latency **37.80 s**, prompt 1240 / completion 857 tokens.
  **No truth in prompt.** Raw machine text in `evidence/ocr_post1.json`.
- Truth (human, unchanged): `TRUTH-PREP/truth/LG035-ZH-Z2.p2.txt` Wikisource ProofreadPage
  **level 3**, CC BY-SA 4.0, sha256 `8c6ad74b…` (verified).

### Score (frozen thresholds from TRUTH-PREP SCORING-PROTOCOL, not relaxed)

| metric | value | threshold | verdict |
|---|---|---|---|
| whole-page CER | 0.2948 | (context) | — |
| **segment/cell CER** (best-overlap match) | **0.3281** | ≤ 0.25 | **FAIL** |
| structural (rows 12/15, sections 5/5, merged-column lines 1, all field tokens exact) | **structure_pass = false** | rows AND sections AND cols preserved, no merge | **FAIL** |
| field/ID tokens byte-exact | pass (2/2) | required | pass |

**Honest defect observations (real product OCR limitation, recorded, product NOT edited):**
1. **Column structure collapsed** — section-2 and section-3 dialect columns were merged onto single
   output lines ("北風說… 世界上的東西…"), losing the 2-column table layout.
2. **Extraneous tokens** — machine emitted `A/C`, `H17`, and a trailing numeric row (`3 1763 2994 8`)
   not present as body text in the human truth.
3. **Dropped dialect prefixes** — leading `末 / 格 / 的` markers lost in the final section.
4. Glyph variants and character substitutions throughout (囘/回, 两/兩, 熱/𤍠, 沈/噲沈, 但/俚/佢).

→ A scanned **table/multi-column page is NOT reliably transcribed** by this path. Combined with the
r2 Z1 printed-page PASS (CER 0.0423 ≤ 0.15), the honest LG-035 picture is **class-dependent**:
single-column printed page pass; **table page fail**. **LG-035 stays `in-progress`.**

## 4. LG-037 retrieval — real Chinese corpus + frozen query set (product `VectorSearchService` + `EmbeddingGemma 2`)

### Corpus (real Chinese, license-clear, no synthesis)
7 documents = **real verbatim fragments** of two human Wikisource level-3 transcriptions
(CC BY-SA 4.0; underlying scans Public domain). Provenance + fragment sha256 in
`corpus.json` / `evidence/retrieval_results.json`. Synthetic Pillow-rendered probe fixtures
**excluded** (explicitly not real). Corpus/query details frozen in `PLAN.md` §3 **before** inference.

### Query set + labels
7 queries = 5 positive + 2 negative-control. **Relevance labels are executor-authored
(NOT independent or human review)** — declared in `corpus.json` and below.

### Results (frozen metric `recall@k = |relevant ∩ topk| / |relevant|`)

| metric | **vector** (`embeddinggemma-2-Q8_0`, 768-dim) | **lexical baseline** (product FTS) |
|---|---|---|
| Recall@1 | 0.9 | 0.7 |
| Recall@3 | 1.0 | 0.7 |
| Recall@5 | 1.0 | 0.7 |
| MRR | 1.0 | 0.8 |
| top-1 accuracy | 1.0 | 0.8 |
| **negative-control leakage (Q6,Q7)** | **5 + 5 = 10 hits** | **0 + 0 = 0 hits** |

- Per-query top-1: Q1→D2, Q2→D3, Q3→D4, Q4→D7, Q5→D7 (D6 at rank 2). All relevant docs found by k=3.
- **Negative controls**: the vector path has **no relevance threshold**, so both negative queries
  returned 5 unrelated docs each (semantic over-match); the lexical path returned 0. **This is a
  real vector-path limitation** and a **negative-control failure**, recorded — not dropped.
- **No dummy vectors, no single-vector pass**: 7 real doc vectors + 7 real query vectors, compared
  to a real lexical baseline. Results are **indicative on a small sample (7 docs / 7 queries)**, not
  a whole-product quality claim.

### Cross-modal / media
- One real Chinese image (Z1 page-10 jpg, PD, sha256 `5c73b9d07ba2…`) embedded **as media** via the
  product `EmbedInput.image` path: **HTTP 200, dim 768**, finite — the product path **can** produce a
  media vector. **This is NOT a cross-modal retrieval-quality result.** The product search path
  returns a single ranked list and does not implement a text↔image relevance comparison, so a
  **text-only** retrieval result **does NOT close multimodal acceptance** (declared honestly).

### Model-switch / dimension / rebuild (OFFLINE, frozen real vectors — no new POST)
- Cache header model `embeddinggemma-2-Q8_0`, dim 768, cache_version 1, 7 documents.
- `is_compatible(same model)` = true; **`is_compatible(other model)` = false**;
  same-model search returns 5, **other-model search returns 0** (no vector mixing). Self-query top-1
  = the entry itself. See `evidence/offline_model_switch.json`.
- **No actual second-model switch was executed** (would need a real alternate model → extra POSTs);
  this is stated as offline compatibility-guard evidence, **not** a real model-switch validation.

## 5. Counters (final, exact)

| Counter | Used / Cap |
|---|---|
| GET (`/health`) | **1 / 2** (planned 1) |
| inference POST total | **16 / 18** — OCR 1 + corpus text 7 + media image 1 + queries 7 |
| retries | **0** (none needed; no timeout/interruption) |
| ASR POST | **0** |
| concurrency | 1 (serial) |
| input size | all ≤ 2 MiB (largest 164,473 B page PNG) |
| public-truth GET | **0** (reused offline fixtures) |

**Actual vs unrun:** actual = the 16 POSTs above. **Unrun** = mixed born-digital+scan class
(still no license-clear sample), low-quality/rotation page, multi-page battery, real ASR (0 POST),
real second-model switch, cross-modal text↔image relevance (product path lacks it).

## 6. Prerequisites to LG-040 (named concentrated version gate) — honest status

- LG-035: **single-column printed page pass (r2), table page FAIL (this package).** Remaining:
  mixed born-digital+scan class sample; low-quality page; formal/machine separation reprocess check.
- LG-037: **vector beats lexical on recall/MRR on the small real corpus**, but **negative-control
  leakage** and **no cross-modal relevance path** remain. Remaining: relevance threshold/score-margin
  behaviour, larger corpus, image/audio query relevance, real model-switch rebuild.
- These are **prerequisites measured, not a gate passed**. **LG-040 not executed/not unlocked.**
  **LG-041** blocked on a real Chinese ASR backend (LG-039 negative preserved).

## 7. Immutability / preservation

- **Product code immutable:** `git status` in the worktree shows only
  `probes/materials-quality-20261016-r3/**`. `git diff db01cd6 -- backend/ frontend/ tests/
  contracts/` is empty; task files unchanged.
- All failed attempts (Z2 table FAIL, vector negative-control leakage) retained as evidence.
- Private originals (PDF, image) mode 600 in a mode-700 dir, `.gitignore`d; no secrets output.
- Contract `1.11.0`, SDK `0.1.22` unchanged. No push/deploy/publish.

## 8. Evidence index

- `STATUS.md`, `PLAN.md` (frozen pre-inference), this `REPORT.md`, `corpus.json`
- `http/health.raw.json` (to add), `http/models.reused-from-r2.json`
- `evidence/ocr_post1.py`, `evidence/ocr_post1.json`, `evidence/ocr_score_z2.py`,
  `evidence/ocr_z2_score.json`, `evidence/scoring.py`
- `evidence/retrieval_harness.py`, `evidence/retrieval_results.json`
- `evidence/offline_model_switch.py`, `evidence/offline_model_switch.json`
- `private/` (mode 700): raw health body, Z2 PDF, vector cache data
