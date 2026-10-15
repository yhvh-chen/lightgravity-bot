---
title: "Materials Quality R3 — STATUS (written before any inference)"
doc_type: report
category: probe
status: "complete — 16/18 POST used; OCR Z2 table FAIL; retrieval vector vs lexical measured; ASR 0"
updated: "2026-10-16"
---

# STATUS — materials-quality-20261016-r3

## Authority & scope (this package only)

- User authorized **one bounded real-quality package** for LG-035 (OCR) and LG-037
  (retrieval) as **prerequisites to a named LG-040 concentrated version gate**.
  This is **not** a new independent gate for a tiny smoke and **does not mark any
  task done**.
- Owner = this single pi executor. **No nested agents.** No push / deploy / publish /
  merge / cherry-pick / reset / clean. Existing provider only (DeepSeek for the dev
  agent; the *product* adapters speak to the authorized LAN inference service).
- Persistence: persistent sibling worktree
  `/home/yhvh/code/lightgravity-bot-worktrees/materials-quality-20261016-r3`,
  branch `test/materials-quality-20261016-r3`, based on `main @ db01cd6` (clean, verified).
- **Sole writable owner:** `probes/materials-quality-20261016-r3/**` ONLY.
  Product/backend/tests/contracts/task files are **read-only**.
- Prior smoke branch `test/materials-retry-20261016-r2 @ b3b7b4f` report/evidence:
  absolute path
  `/home/yhvh/code/lightgravity-bot-worktrees/materials-retry-20261016-r2/probes/materials-retry-20261016-r2/`
  (GET3 all 200; OCR real Z1 CER 0.0423 ≤ 0.15 at `qwen3.8-27b`; text embed 768-dim at
  `embeddinggemma-2-Q8_0`). Its results are **reused as prior evidence**, not re-run.
- Task state **unchanged**: LG-035 `/` LG-037 stay `in-progress`; LG-040 / LG-041 stay
  `todo` and **LG-041 remains locked** (LG-039 negative true human-audio result preserved;
  **ASR POST = 0 this phase**).

## Authorized service (unchanged)

- Target: **`http://192.168.8.12:11434`** — llama.cpp **router** (`build_info=b11641-843e7dcc1`,
  not Ollama). Both model IDs actual and unchanged from r2 metadata:
  OCR/vision = **`qwen3.8-27b`**; embedding = **`embeddinggemma-2-Q8_0`** (768-dim).
- Product adapters **unmodified**: `OpenAICompatOcrBackend`, `PdfiumRasterizer`,
  `OpenAICompatEmbeddingBackend`, `VectorSearchService` / `VectorIndex`,
  `LexicalSearchService`. No product code edited.

## Hard budget (pre-registered, before the first POST)

| Item | Bound |
|---|---|
| inference POST **total** (OCR + embedding) | **≤ 18** (planned exact = 16) |
| concurrency | 1 |
| retries | **0** (no auto-replay after timeout/interruption; outcome unknown) |
| per inference request hard timeout | 120 s (cold OCR allowed 120 s) |
| metadata GET (health) | ≤ 2 total, 8 s total time / 3 s connect |
| public-truth acquisition GET | ≤ 2 additional (frozen source/licence before use) — **planned 0** (reuse downloaded fixtures) |
| input size per POST | ≤ 2 MiB |
| other providers / scans / DeepSeek runtime workers / TaskRun / autoupload | **none** |
| ASR POST | **0** |

**GET plan this phase: 1** (`/health` reachability only). `/v1/models` metadata is
**reused verbatim from r2** (`private/` there), so no second GET is spent.

## POST pre-registration (exact minimum, from actual product adapter cardinality)

Read from the actual product adapters:
- `OpenAICompatOcrBackend.transcribe()` issues **exactly 1 POST per page**.
- `OpenAICompatEmbeddingBackend.embed()` sends **exactly 1 input element per POST**
  (`"input": [_input_element(item)]`); `VectorSearchService.index_source()` loops inputs
  (text + original-media separately) ⇒ **1 POST per input**; `VectorSearchService.search()`
  embeds the query ⇒ **1 POST per query**. There is **no batch schema in the product path**
  and no alternate HTTP path is used.

Planned calls (total **16** ≤ 18):

| # | Purpose | Product path | POSTs |
|---|---|---|---|
| OCR | LG-035 Z2 PDF page 2 (rasterize → OCR) | `PdfiumRasterizer` + `OpenAICompatOcrBackend` | 1 |
| Embed corpus | 7 real Chinese text docs (`index_source`, text-only) | `VectorSearchService` + `OpenAICompatEmbeddingBackend` | 7 |
| Embed media | 1 real Chinese image (media-only source, cross-modal probe) | same | 1 |
| Query | 5 positive + 2 negative-control queries (`search`) | same | 7 |

If a call times out: **stop that line, record unknown, do not replay** (the 18 cap is not
consumed merely because it is allowed).

## Honesty / non-claims

- A single vector is **not** a relevance pass; reachability is **not** retrieval quality.
- **Text-only retrieval does NOT close multimodal acceptance.**
- If the corpus/labels are executor-authored, this is stated as such (not independent/human review).
- No post-hoc threshold relaxation. Failed attempts are kept.
- These results **do not** mark LG-035 / LG-037 / LG-040 `done`.

## Explicit counters at package close

- GET used: **1 / 2** (planned 1) · POST used: **16 / 18** (planned 16) · retries: 0 · ASR POST: 0
- Result: OCR Z2 table **FAIL**; Z1 printed page PASS (r2). Vector Recall@5 1.0/MRR 1.0 vs
  lexical 0.7/0.8, but vector negative-control leakage 10 hits vs lexical 0. See `REPORT.md`.
- Task state unchanged; LG-040 not unlocked; LG-041 locked.
