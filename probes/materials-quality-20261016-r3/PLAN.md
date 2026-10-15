---
title: "Materials Quality R3 — FROZEN PLAN (pre-registered before any inference POST)"
doc_type: report
category: probe
status: "frozen — written before the first POST; no result may change it"
updated: "2026-10-16"
---

# FROZEN PLAN — materials-quality-20261016-r3

**This plan is frozen before the first POST.** No result may change a threshold,
a corpus item, a query or its labels, or the call count. Failed attempts are kept.

## 0. Reused prior facts (no new GET)

From the r2 smoke (branch `test/materials-retry-20261016-r2 @ b3b7b4f`,
absolute path `/home/yhvh/code/lightgravity-bot-worktrees/materials-retry-20261016-r2/`),
recorded there in `probes/materials-retry-20261016-r2/http/models.raw.json`:

- Endpoint `http://192.168.8.12:11434` — llama.cpp **router** `b11641-843e7dcc1`, **not** Ollama.
- Active model IDs (verbatim): OCR = **`qwen3.8-27b`**; embedding = **`embeddinggemma-2-Q8_0`**
  (768-dim, mean pooling). `gemma4-mtp` vision chat; `bge-reranker-v2-m3-Q8_0` reranker.
- This package spends **1 GET only** (`/health`) to reconfirm reachability; **`/v1/models`
  is NOT re-fetched** (metadata reused). Total GET this phase = 1 (cap 2).

## 1. Transport & budget (hard)

| Item | Bound |
|---|---|
| inference POST total | **≤ 18**; planned exact **16** |
| concurrency | 1 (strictly serial) |
| retries | **0** — timeout/interruption ⇒ record unknown, **no replay** |
| per inference POST hard timeout | **120 s** |
| `/health` GET | 1, connect 3 s / total 8 s |
| input per POST | ≤ 2 MiB |
| ASR POST | **0** (LG-041 locked) |
| other providers / scans / TaskRun / DeepSeek runtime / autoupload | none |

Planned POSTs = 1 (OCR) + 7 (corpus text) + 1 (media image) + 7 (queries) = **16**.

## 2. LG-035 OCR — real Z2 PDF page 2 (product path, unmodified)

- **Input (private, 0600)**: `private/LG035-ZH-Z2.pdf`
  sha256 `da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a`, 392,964 B,
  **Public domain** (NLC416 `方言調查表格.pdf`, Wikimedia Commons). 18 pages, pure scan,
  no text layer (verified in TRUTH-PREP).
- **Rasterizer = product `PdfiumRasterizer`** (pypdfium2, unmodified), `scale=2.0`,
  page index 1 only. Local pre-check (no OCR): page 2 → PNG **164,473 B**, grid **408×689**,
  PNG sha256 `15ca62198b90b2effee1ef5933f4104fb3d986637b040a0da0b0d89e7ddf3ac4`.
  **Only page 2 is rendered/OCR'd — NOT all 18 pages.**
- **OCR backend = product `OpenAICompatOcrBackend`** (unmodified), model `qwen3.8-27b`,
  `/v1/chat/completions`, `temperature=0`, `stream=false`, `max_tokens=2000`, `cold=True`,
  timeout 120 s, retries 0. **No truth injected into the prompt.**
- **Truth (human, unchanged)**: `TRUTH-PREP/truth/LG035-ZH-Z2.p2.txt`
  (Wikisource ProofreadPage **level 3**, CC BY-SA 4.0, 1,042 B,
  sha256 `8c6ad74b3b647dd85aacb1db665ceafd262da579a0c65aac7e879488665862b0`). Same
  ProofreadPage record page 2 ↔ this scan page 2 (strict pairing, verified in TRUTH-PREP).
- **Pre-registered thresholds (frozen, do NOT relax)** — from TRUTH-PREP SCORING-PROTOCOL:
  - segment/cell **CER ≤ 0.25**, and
  - **structural pass** = machine row count == human row count **AND** machine column count
    == human column count **AND** every human cell/segment token present byte-exact after NFKC.
    If the model emits no table structure → `table_rows=0`, metric **failed**, never "n/a".
  - Number/ID-like tokens in truth must appear byte-exact after NFKC (field truth, §3).
- Normalisation: NFKC, whitespace stripped before Levenshtein (exactly as cohort A/B).

## 3. LG-037 retrieval — real Chinese corpus + frozen query set

### 3.1 Corpus provenance (real Chinese, license-clear, no synthesis)

The only **real** (non-synthetic) Chinese texts available offline are the two human
Wikisource transcriptions (both **CC BY-SA 4.0**, scan underlying is **Public domain**).
Synthetic Pillow-rendered probe fixtures are **excluded** (they are explicitly not real).

The corpus documents are **real paragraph/section fragments** of those two texts, each
carrying its true provenance. This is genuine real Chinese content, not invented text.

| doc id | source | real fragment (verbatim human truth) |
|---|---|---|
| D1 | Z1 (老解老 p10) | lines 1–3 (其功也…會其通) |
| D2 | Z1 | lines 4–6 (聰明才力…然後歎猶) |
| D3 | Z1 | lines 7–9 (龍之妙…八百有四) |
| D4 | Z2 (方言調查表格 p2) | heading + 國/蘇/廣 第一段 |
| D5 | Z2 | 第二段 (北風說…) ×3 方言 |
| D6 | Z2 | 第三段 (世界上的東西…) ×3 方言 |
| D7 | Z2 | 第四段 (船碰見了…) ×3 方言 |

**Provenance per doc**: Z1 `File:10-13老解老.pdf` p10 (PD scan) ↔ Wikisource
`Page:` level-3 human transcription (CC BY-SA 4.0); Z2
`NLC416-14jh004627-68702 方言調查表格.pdf` p2 (PD scan) ↔ Wikisource level-3 human
transcription (CC BY-SA 4.0). Fragment hashes recorded in `evidence/corpus.json`.

### 3.2 Query set + relevance labels (executor-authored — declared as such)

**These labels are executor-authored relevance judgements, NOT independent or human review.**
No whole-product retrieval-quality claim is made from them.

Fixed **7 queries** (5 positive + 2 negative-control). Relevance = the doc contains the
answer span. Labels frozen here, before any embedding:

| q | query (Chinese) | relevant docs | type |
|---|---|---|---|
| Q1 | 老氏學說 鑽研 淬礪 | D2 | positive |
| Q2 | 批郤導竅 經文 串珠之編 | D3 | positive |
| Q3 | 北風 太陽 爭論 本事 | D4 | positive |
| Q4 | 船碰見 翻 坍 倒 | D7 | positive |
| Q5 | 貓 狗 花 草 怕 | D6+D7 (D7 primary) | positive |
| Q6 | 量子色動力學 膠子 強相互作用 | **none** | negative control |
| Q7 | 2024年 財務報表 淨利潤 萬元 | **none** | negative control |

### 3.3 Metrics & criteria (frozen)

- **Recall@k** for k ∈ {1,3,5} over positive queries: for each positive query, fraction of
  its relevant docs present in the top-k (ties beyond k not counted). **Fixed** definition:
  `recall@k(q) = |relevant(q) ∩ topk(q)| / |relevant(q)|`.
- **MRR** and **top-1 accuracy** over positive queries.
- **Negative-control / no-leakage**: for Q6, Q7 the vector search top-k must contain **0**
  real corpus docs (a hit = leakage/over-broad semantic match). Report the count; any hit is a
  recorded negative-control failure (not silently dropped).
- **Lexical baseline** = product `LexicalSearchService` on the **same** corpus/queries
  (rebuildable cache, no exclusive permission state). Report the same metrics; vector must be
  compared to this baseline, never asserted alone.
- **Minimum sample size declared**: corpus ≥ 7 real docs, ≥ 5 positive + ≥ 2 negative queries.
  These are **small**; results are **indicative, not a full-product quality claim.** Limits stated.
- **Model-switch / dimension / rebuild** behaviour: verified **offline** against the frozen
  real responses where possible; if not verifiable without extra POSTs, recorded as unrun
  (NOT feigned as actual model-switch validation).

### 3.4 Media (cross-modal) probe

- One **real Chinese image** (Z1 page-10 jpg, PD scan, sha256
  `5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f`) is embedded **as media**
  via the product `EmbedInput.image` path (1 POST). This tests **that the product path can
  produce a media vector**, nothing more. **It is not a cross-modal retrieval-quality result.**
  Report whether a text↔image retrieval comparison is even **supported** by the product path;
  a **text-only** result **does NOT close multimodal acceptance.**

## 4. Counters at PLAN freeze

- GET used 0/1 (planned) · POST used **0/16** (planned, cap 18) · retries 0 · ASR 0.
