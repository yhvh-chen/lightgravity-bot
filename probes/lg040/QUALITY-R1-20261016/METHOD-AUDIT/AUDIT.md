---
title: "LG-040 QUALITY-R1-20261016 METHOD-AUDIT — independent classification of provisional QA outcomes"
doc_type: audit
category: qa
status: "independent method audit of EXISTING frozen bytes — 0 model calls, 0 POST, no gate/score change"
updated: "2026-10-16"
---

# METHOD-AUDIT — LG-040 QUALITY-R1-20261016

## 0. Scope, authority and immutability

- Owner: independent pi **method-audit** of the prior QUALITY slice, within the **same named LG-040
  milestone**. Root PM only. **Not** a product repair and **not** a new QA gate.
- Write scope: **only** `probes/lg040/QUALITY-R1-20261016/METHOD-AUDIT/**` (new subdir). The original
  `PLAN.md` / `frozen/LABELS.json` / `REPORT.md` / `STATUS.md` / `evidence/**` **were not touched**.
- Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/lg040-quality-r1-20261016`,
  branch `qa/lg040-quality-r1-20261016`, base `cc09a98`. Previous quality worker EXITED normally.
- Product candidate: `main@2f277fa` (`2f277faf39364232f01c7a02f5a44db3d8b27301`);
  `git diff 2f277fa -- backend frontend tests` is **empty** ⇒ product tree byte-identical.
- Activity: **offline only**. 0 network, 0 POST, 0 model calls, 0 new experiment, no ASR, no nested
  agents, no product writes, no push/deploy/publish/reset/clean. Model-call quota left exactly as it
  was: OCR 2/2, embedding 17/18 (**1 spare UNSPENT**), inference 19/≤20.

### Original source bytes proven immutable (sha256 before == after)

| Artifact | sha256 (before audit) | after |
|---|---|---|
| `REPORT.md` | `18460952ec18f4b31c66b0451103445f48b141473db1f010a683b41b6ee4fb6d` | unchanged |
| `PLAN.md` | `79f7503d64f0b25c250145d7c8a0c4ef551c7a989bed9097b375c93b92151909` | unchanged |
| `STATUS.md` | `eaa16357afb5558acab8e019ee5a3a1cbf5a4e07d7bcea8038198ee1410bd74b` | unchanged |
| `frozen/LABELS.json` | `87cf2eecb9bc35fd4d488e8932152c280f0d9373002b3038748c196e1687a940` | unchanged |
| `evidence/phase1/ocr_cer.json` | `a88ed607d34727ad21ee302c5897189ac4a55d251d736c3ff2c054edde207ec8` | unchanged |
| `evidence/phase2_analysis.json` | `34215845b1ea4e707c5cdf2e472684723a8a149ef2f0084a7d7347d68e59d1e6` | unchanged |

- Frozen provisional outcomes are **retained as historical** (CER 2.79 page-1, G2 image FAIL). They are
  **not rewritten and not relabelled PASS**. This audit adds a *separate diagnostic*, computed with
  the **same unchanged NFKC / lowercase / collapsed-whitespace normalization**, against a
  **prior-published human truth that predates this QA**. No score/gate tuning. Safety / cross-Task /
  integrity gates remain unchanged and always block.

## 1. Finding table (classification)

| # | Provisional finding | Supporting facts | Classification | Evidence / next step |
|---|---|---|---|---|
| F1 | OCR page-1 "CER 2.79" (reported as a product OCR defect) | OCR output `norm=2272` chars; frozen "truth" `norm=600` chars taken from `p16.index("Table 1 gives the seven base quantities")`→`p16.index("4.2 SI derived units")`, i.e. a **mid-page slice** of `d1_si_units.txt`-region prose. The **full** NIST SP 811 p.16 native text layer normalized = **2272** chars. OCR hyp vs **full page** = edit distance **6**, **CER 0.0026**. The hyp legitimately contains `4.2 SI derived units` + `Table 2` (content **beyond** the 600-slice). Prior published R7 (predates QA) scored the **same input image** (`265f187a…`) at CER **0.0295 PASS** against the **full** page native text. Harness compared FULL-page output to a 600-char SUBSET reference ⇒ inflated CER. | **BENCHMARK_DEFECT** (not a product OCR defect) | `METHOD-AUDIT/recompute_output.json` F1; `run_quality.py` lines 144–150 (slice extraction); `probes/materials-ocr-cohort-r7-20261016/evidence/scores.json` (`truth_len_norm=1898`, `page_cer=0.0295`, `pass=true`). Frozen case stays **FAIL/INVALID_REFERENCE (historical)**. Next: root may record the gold standard as full-page native text; **no retroactive gate change**. |
| F2 | Image TIFF embed HTTP 500 vs PNG success | `IMAGE_MEDIA_TYPES` for OCR = png/jpeg/webp/gif/bmp; the **embedding** service accepts any `image/*` and forwards to the backend. D3 was submitted as `image/tiff` (raw `phototest.tif`, `d2241a1e…`); backend answered **HTTP 500** `{"code":500,"message":"Failed to load image or audio file"}` — surfaced honestly (no empty-success body). Phase-2 re-submitted the **same content** as `image/png` (`5aff7e21…`) which embedded and entered the index. | **KNOWN_LIMIT** (honest unsupported-format / unavailable; **not** false success, **not** product bug) | `METHOD-AUDIT/recompute_output.json` F2; `evidence/phase1/raw_responses/05_embedding_POST.json`; `backend/lightgravity/sources/processing.py:65-71`; `backend/lightgravity/sources/vectors/service.py:157-183`. Source D3 byte hash may change per phase by design; the failure was never hidden. |
| F3 | G2 image top-1 FAIL; PNG image rank **2** | Rebuilt 5-doc index Q3′ order: **D2 (0.807764) > D3 (0.762977) > MIX (0.722642) > D1 (0.672681) > D4 (0.642477)**, margin 1→2 = **0.044787**. Rank-1 **D2** (`phototest.gold.txt`) is the **human text of the same phototest page** that D3 (`phototest.tif/png`) is the **image of**: D2 gold literally contains "This is a lot of 12 point text…" and "The quick brown dog jumped over the lazy fox." So Q3 is a **same-content cross-modal relevant duplicate**, not a wrong/unrelated document. Independent cosine recompute reproduces the service order exactly. | **KNOWN_LIMIT** (same-content cross-modal ordering) — **G2 top-1 stays FAIL as an experiment result**; the metric's reference relevance is not wrong-document | `METHOD-AUDIT/recompute_output.json` F3; `evidence/phase2_analysis.json`; `evidence/phase2.json` Q3_rebuilt. Rank-1 was **D2, a relevant duplicate** (not D1/D4 unrelated). No `k` was raised after seeing results. |
| F3b | Was "image top-1" a release-hard requirement? | LG-040 acceptance requires verifying the **image/PDF/lexical + optional vector paths** and *reviewing* retrieval-quality data; docs/08 has no top-1 gate; docs/09 §7 has no top-1 gate. The frozen **G2** "Q3 vector top-1 == D3" and the Recall@k/MRR/rank/negative battery are **QA-owner metrics declared in `PLAN.md` §4 / `frozen/LABELS.json`**, not a user/PM release-hard condition. | **NOT a product release-hard defect by itself** — G2 is an *owner analysis metric*; **UNVERIFIED as a hard gate** (root decides future acceptance) | `backlog/tasks/LG-040.md` 验收条件; `docs/09` §7/§9; `PLAN.md` §4; `frozen/LABELS.json`. |

## 2. Corrected diagnostics (AUDIT diagnostic only — NOT a rewrite of the frozen gate)

- **OCR page-1, full-page human truth comparison:** hyp `2272` norm chars vs full p.16 native
  **`2272`** norm chars → **CER = 0.0026**, edit distance **6**
  (3 minor typographic deltas: a stray page-number `4`, curly-vs-straight quotes).
  Independent recompute of the prior R7 hyp vs the same full-page truth = CER **0.0277** (consistent
  with the prior published **0.0295 PASS**; small delta from R7's own norm variant). **Both** confirm
  the full-page reference is right and the 600-char subset reference is the anomaly.
- **Image path:** PNG image vector **works** (embedded, indexed, rank 2). TIFF `image/tiff` embed is
  **unsupported by the backend and failed honestly (HTTP 500)**; it is not a false success and not a
  product defect. The D3 TIFF byte hash (`d2241a1e…`) is preserved and may change per phase.
- **G2 top-1:** remains **FAIL** as an experiment result (D2 rank 1 with cosine margin 0.0448). The
  rank-1 winner is a **semantically relevant duplicate** (same content, text modality), not an
  unrelated document. No excuse is made for genuine unrelated retrieval: here D1/D4 (truly unrelated)
  scored clearly lower (0.673 / 0.642).

## 3. What this audit does NOT do

- No re-scoring of frozen gates, no threshold/`k` change, no relabelling of old results to PASS.
- No assertion that the OCR output is "correct" beyond the measured full-page comparison (the
  comparison was actually performed; CER 0.0026 is the measured result).
- No product defect claim is promoted from the inflated CER 2.79 artifact.
- Does not touch safety / cross-Task / integrity gates (unchanged, always block).
- Does not merge any candidate fix; no product writes; no full suite.

## 4. Evidence

- `METHOD-AUDIT/recompute.py` + `METHOD-AUDIT/recompute_output.json` (offline, reproducible).
- Immutable inputs: `evidence/phase1/ocr_machine_content.json`,
  `evidence/phase1/raw_responses/01_ocr_POST.json`, `evidence/phase1/ocr_cer.json`,
  `evidence/phase2.json`, `evidence/phase2_analysis.json`, `frozen/LABELS.json`,
  `probes/materials-ocr-cohort-r7-20261016/evidence/scores.json`,
  `probes/materials-fixtures-r7-20261016/truth/TRUTH-MANIFEST.json`.
- Product tree `backend/ frontend/ tests/` == `2f277fa` (unchanged).

## 5. Counters

- Network 0 · POST 0 · model calls 0 · product inference 0 · product writes 0 · new experiments 0.
- Embedding quota: **17/18 used, 1 spare UNSPENT**; OCR 2/2. Retries 0.
- pi cost: **unknown, not 0**.
