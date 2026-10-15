---
title: "Materials R5 Close — integration REPORT (OCR r5 evidence-only + Vector r5 merge)"
doc_type: report
category: probe
status: "complete — evidence integrated; PM decision recorded; no quality pass; LG-035/037 stay in-progress"
updated: "2026-10-16"
---

# REPORT — probes/materials-r5-close-20261016

Single pi technical integration executor; root PM only. This package performed
**no product code change** and made **0 network/model calls** (no GET/POST/ASR/
embedding, no new tests, no model probes). It only (a) imported OCR r5 **evidence
bytes** and (b) merged the vector r5 probes-only branch, then wrote PM docs.

Base `main` at report time: **`a2dc40a`** (verified clean, no uncommitted/staged
changes). Final `main`: see §6.

---

## 1. PM decision (authoritative)

**OCR r5 generic-prompt candidate DID NOT demonstrate benefit.**
`fix/materials-ocr-r5-20261016` product branch and its default new prompt are
**NOT merged**. Evidence-only import into `main`; branch/worktree preserved with
all commits. No quality pass; no task status change.

**Vector r5** (`test/materials-vector-r5-20261016`) is probes-only and was merged
`--no-ff`. No quality pass (frozen image gate NOT met); LG-037 stays in-progress.

---

## 2. Source provenance & hashes (frozen bytes preserved)

| Artifact | Value |
|---|---|
| OCR r5 branch / tip | `fix/materials-ocr-r5-20261016` @ **`1a4759c`** |
| OCR r5 base | `a2dc40a` (== `main` at start) |
| OCR r5 commits | `7afe8eb` PLAN+health GET → `06fabd3` product instruction → `1a4759c` report |
| OCR r5 REPORT git blob (source & main) | **`41fc061f8b49e20b23f4ab572961f012f051cad3`** (SHA-256 `c1f01c6a…`) — **byte-identical** |
| Vector r5 branch / tip | `test/materials-vector-r5-20261016` @ **`c180411`** |
| Vector r5 base | `a2dc40a` |
| Vector r5 commits | `0ca7a42` FREEZE plan+corpus → `967d97b` harness+dry-run → `c180411` real evidence+report |
| Vector r5 REPORT git blob (source & main) | **`e92791b13daad7df1162096a76540cf5cd5a00e8`** (SHA-256 `39daec3d…`) — **byte-identical** |
| Vector r5 PLAN git blob | `80d063da…`; corpus.json `9853f9ed…` (as frozen) |

Source REPORT bytes were **not modified** in this integration. Both
worktrees were confirmed **clean** before integration and their tips are
**unchanged** after (`1a4759c`, `c180411`).

---

## 3. OCR r5 — decision basis (why evidence-only, no product merge)

The candidate replaced the product OCR instruction with a **generic layout-aware**
prompt (preserve headings, emit a Markdown table for tabular regions, flag
`[unreadable]`, forbid inference). Exercised through the real product
`PdfiumRasterizer` + `OpenAICompatOcrBackend`; exactly 2 POST were sent.

| metric (Z2 table gate) | R4 scale 4.0 | **R5 scale 4.0 (new prompt)** | threshold | result |
|---|---|---|---|---|
| Z2 fair token-weighted segment CER | 0.268882 | **0.277946** | ≤ 0.25 | **FAIL / worse** |
| Z2 exact human row tokens | 8 / 15 | **6 / 15** | 15 / 15 | **FAIL / worse** |
| Z2 machine table rows | 0 | **0** | == 15 | **FAIL** |
| Z2 protocol §4 structure | fail | **fail** | pass | **FAIL** |
| Z1 whole-page CER (regression) | 0.0423 | **0.10582** | ≤ 0.15 | PASS |

- Z2 whole-page CER improved to **0.241692** but that is **not** the Z2 gate.
- The single Z1 comparison is a **single attempt, non-statistical**; the new prompt
  made Z1 whole-page CER worse (0.10582 vs old 0.0423) even though it stayed under
  threshold. Whole-page numbers are **irrelevant to the specific Z2 table gate**.
- Conclusion: a text instruction alone did **not** induce table structure for Z2;
  the segment CER regressed and structure stayed absent. No threshold was relaxed.

**Decision:** do not merge the product branch or make the new prompt the default.
Evidence (`probes/materials-ocr-r5-20261016/**`) is published into `main` for the
record. The source harness `evidence/ocr_post.py` may import the candidate
`OCR_PROMPT`; **replay requires the candidate branch `1a4759c`**, and **`main`
retains the original product hash / original default prompt** (main product tree
delta = 0, §6).

---

## 4. OCR r5 — exact integration mechanics

- Precondition check (read-only): `probes/materials-ocr-r5-20261016` did **not**
  exist on `main`; `main` clean.
- Copy command: `git restore --source=fix/materials-ocr-r5-20261016 -- probes/materials-ocr-r5-20261016` (scoped to the owned dir).
- Post-copy verification: **only** the owned dir was created (`git status` showed
  no other path); all **14** files matched source git-blob hashes exactly
  (13 evidence files + `private/.gitignore`).
- Commit (owned, evidence-only): **`767f1ea`** —
  `probes(materials-ocr-r5-20261016): import EVIDENCE ONLY from fix/materials-ocr-r5-20261016@1a4759c`.
- **Not imported** (deliberately excluded): `backend/lightgravity/sources/ocr/{adapter,__init__}.py`,
  `tests/sources/ocr/test_adapter.py`, `docs/09-source-intake-and-retrieval.md`.

---

## 5. Vector r5 — integration & evidence

- Verified `test/materials-vector-r5-20261016@c180411`: diff vs base is **probes-only**
  (`probes/materials-vector-r5-20261016/**`, 11 files, non-probe paths empty);
  worktree clean.
- Merge `--no-ff`: commit **`d08144c`** (`integrate(materials-vector-r5-20261016): merge real cross-modal evidence --no-ff into main`). No conflict, no repeated pick.
- Real evidence (from the frozen source report, recorded here, not re-run):
  - Corpus: **2 real images + 2 real audio + 6 real Chinese text sources** (incl. 1 textual positive).
  - **17 POST + 1 health GET**, retries **0**, serial, per-call ≤ 90 s.
  - Positive ranks: **Q_AUD_LANG rank 1**, **Q_AUD_EARTH rank 1** (2nd real audio
    `File:Zh-地球.ogg`, CC BY-SA 4.0, author CanonNi — Commons SHA1 `a8c67e62…`
    verified), **Q_IMG_EN rank 1**, **Q_IMG_ZH NOT top-5 (miss)**,
    **Q_TXT_ZH rank 1**. Vector **MRR = 0.8**, top-1 = 0.8; lexical baseline 0.2.
  - Negatives: **5 false hits each** — expected top-k NN behaviour (no threshold /
    no abstention; docs/08 froze no threshold field), **not** an ACL/contract failure.
  - **Frozen hard gate:** audio reachable PASS; image reachable **FAIL** ⇒
    `all_hard_gates_met = false`. **No quality pass.** LG-037 stays `in-progress`.

---

## 6. Final state (verified)

- **Product tree byte-identical to `a2dc40a`:**
  `git diff --stat a2dc40a HEAD -- backend frontend src tests docs contracts pyproject.toml uv.lock Makefile` → **empty**.
- `git diff --name-status a2dc40a HEAD` → **only** the two `probes/materials-{ocr,vector}-r5-20261016/**` trees (25 files).
- `main` clean after both write actions; no reset / clean / overwrite.
- Source branches preserved and unchanged: `fix/materials-ocr-r5-20261016@1a4759c`,
  `test/materials-vector-r5-20261016@c180411`; both source worktrees preserved.
- Frozen report bytes unchanged on `main` (OCR `41fc061f…`, vector `e92791b1…`).

`main` commit graph (top→): `d08144c` (vector r5 merge) ← `767f1ea` (OCR r5
evidence) ← `a2dc40a` (base).

---

## 7. 🚩 BUDGET-VIOLATION ERRATUM (new; raw source reports NOT modified)

**The vector r5 run exceeded its authorized total audio budget.**

- The prompt in force authorized a **TOTAL audio budget of ≤ 30 seconds**.
- The run used: first clip **(30 s, from the original Vorbis)** **plus** the second
  clip **(2.048 s)** = **32.048 s TOTAL** — exceeding the bound by **2.048 s ≈ 6.8%**.
- The source REPORT/PLAN records the constraint only **per POST ≤ 30 s** and
  rationalizes the total as "each POST ≤ 30 s respected"; **that per-POST framing
  is NOT the original total bound and is not valid** against the authorized
  total ≤ 30 s.
- **No claim is made that the run stayed within all bounds.** The actual audio
  counts are: first audio (original Ogg, 143.58 s exist) clipped to a 30 s PCM;
  second audio 2.048 s real human CC BY-SA 4.0 (CanonNi, Commons `File:Zh-地球.ogg`)
  → **32.048 s total embedded audio**.
- Resampling + time-clipping (ffmpeg `-ac 1 -ar 16000 -t <clip> -c:a pcm_s16le`)
  is **not lossless**; both PCM WAVs were what was embedded.
- The **first-clip original vorbis is 143.58 s** (preserved as provenance); the
  embedded first clip is the **30 s PCM**.
- **Public-source licence and raw hash** are recorded in the source evidence
  (`http/commons_zh_diqiu_metadata.raw.json`; Commons SHA1 `a8c67e62…`, SHA-256
  `46781b4e…`; CC BY-SA 4.0, author CanonNi).
- **Public GET metadata / download counts** (from the source report): public
  acquisition metadata GET ≤ 6, **1 download** (19,957 B ≤ 5 MiB). Total public GET
  count and product response `usage` figures are otherwise **unknown** (endpoint
  exposes no price; pi/DeepSeek execution cost unknown, not zero).
- **Do NOT re-run to hide the violation. Do NOT retroactively change the budget.**
  This erratum is the honest record; the prior **R4 number is preserved** unchanged.
- **No ASR / no LG-041 unlock** (audio embedding ≠ ASR; 0 ASR POST).

---

## 8. Remaining concrete steps

1. **OCR (LG-035, in-progress):** the next attempt must address **layout
   analysis / column segmentation program-side** (detect ruled/column boundaries,
   assemble tables from per-column cell transcriptions) — **not another prompt
   lottery**. Z2 requires real machine row/column structure matching 15×3 and fair
   segment/cell CER ≤ 0.25; both still unmet. Mixed born-digital/scanned class still
   missing.
2. **Vector (LG-037, in-progress):** the result is a **quality** result, not a
   mechanism failure. Next step is a **larger, more balanced cross-modal corpus +
   score-margin diagnosis** — **no automatic sampling**, **no threshold tuning on
   the frozen R5 queries**.
3. Both remain gated by the named **LG-040** version QA (not unlocked, not passed);
   **LG-041 stays locked**.
4. Requested/observed audio-budget erratum stands on the record; do not alter.

---

## 9. Counters (this integration package)

| counter | value |
|---|---|
| product LAN / model calls (GET, POST, ASR, embedding) | **0** |
| new tests / model probes / new services | **0** |
| git write actions | OCR-r5 evidence commit `767f1ea`; vector-r5 merge `d08144c`; PM docs commit (see below) |
| push / deploy / publish / reset / clean | **none** |
| historical OCR r5 counts (source) | 2 POST (both planned), 1 health GET, 0 retry, 0 ASR, 0 embedding |
| historical vector r5 counts (source) | 17 POST + 1 health GET, 0 retry, 768-dim `embeddinggemma-2-Q8_0`, 0 ASR, 0 OCR |

pi/DeepSeek execution cost: **unknown, not zero**.
