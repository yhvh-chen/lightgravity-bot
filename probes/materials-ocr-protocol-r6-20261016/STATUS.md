# LG035 protocol-investigation R6 — STATUS

* Branch: `investigate/materials-ocr-protocol-r6-20261016`
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-protocol-r6-20261016`
* Base: `main@7c27f18` (**untouched**; verified this session).
* Owned scope written: `probes/materials-ocr-protocol-r6-20261016/**` **only**.
* Deliverable: `DECISION.md` (this package) + this `STATUS.md` + `evidence/` + `render/`.
* Date (UTC): 2026-10-16.

## State

| Item | Value |
|---|---|
| LG-035 | **in-progress** (NOT done; no self-QA) |
| LG-040 / LG-041 | locked (unchanged) |
| Product generation calls | 0 |
| Network / model / OCR / embedding / ASR calls | 0 |
| New investigation re-run | **none** (see provenance) |
| Push / deploy / publish / reset / clean | none |
| pi cost | **unknown, not 0** |

## Files in this package

| File | Role |
|---|---|
| `DECISION.md` | main decision memo (facts F1–F7, inference I1–I3, uncertainty U1–U4, decision, proposed future mapping, provenance) |
| `STATUS.md` | this status |
| `evidence/render_hashes.txt` | source PDF license + sha1/sha256; product-render sha; extra pdftoppm sha; truth sha |
| `evidence/z2_pixel_geometry.json` | independent pixel geometry on product render (content box [109,319,704,1039], 0 rulings, 13 lines) |
| `evidence/render_ascii_map.txt` | coarse 96×60 ink map of `render/product_scale2_p2.png` (offline stdlib decode) |
| `render/LG035-ZH-Z2.pdf` | source scan (18 pp) |
| `render/product_scale2_p2.png` | product `PdfiumRasterizer` output, sha `15ca6219…`, 817×1380 |
| `render/z2p2_r150-02.png`, `render/z2p2_r300-02.png` | independent pdftoppm cross-check renders |

## Session provenance (explicit)

The **first** attempt of this pi work package was terminated by the harness at
**exit 143** (`token_budget_exceeded`) at ~154 s, after it had written `DECISION.md`
(harness log `lightgravity-pi-bounded-b0rnlv0h.log`, last event = successful `write` of
`DECISION.md`) but **before** it created `STATUS.md` or committed.

Recovery was **NON-REPLAY**: no model/OCR/ASR/network/product call and no re-run of the
investigation. Actions taken: verified no live writer; read existing owned evidence +
log tail only; preserved `DECISION.md` and all evidence bytes; made two minimal owned
fixes — corrected a citation path in the evidence index (`render/`, not `evidence/`) and
materialized the already-cited-but-missing `render_ascii_map.txt` by deterministic
offline decode of the sha-verified product render; then added the `DECISION.md`
provenance section and this `STATUS.md`.

## Conclusion (short)

The predeclared **15×3** Z2 shape is a **mis-classification** introduced in R4 scoring
code (`score_r4.py:227`, `e9fd5e5`) and hardened in R5 PLAN (`7afe8eb`); it is **not** in
the original protocol (`SCORING-PROTOCOL.md` §4 is generic) nor in the human truth
(5 sections × 3 prefix-labelled dialect lines, a linear list). The product-rendered Z2
page-2 pixels carry **no table geometry** (content box [109,319,704,1039]; 0 horizontal
and 0 vertical rulings; all text lines start at the left margin and span most of the
width), so as a *geometric grid* the `15×3` assertion is **unsupported**. As a *semantic
dialect taxonomy* (5×3 groups) it is well-supported.

**Confidence:** HIGH that Z2 page 2 has no 15×3 grid geometry and that the truth is a
linear list. MEDIUM-HIGH that the original §4 grid check is unsatisfiable by any faithful
transcription of this page (protocol-class defect) — one page only.

**Distinguished certainty:** pixel/geometry + hashes + origin trace are **computed** facts
(reproducible, sha-pinned). **Visual** ("I saw the page") certainty was **not** obtained
(this session's model could not view images); the layout verdict rests on pixel
inference + the real model's own output, not on human eyes — recorded as U1.

**Historical state unchanged:** R3/R4/R5 Z2 results stay **FAIL** (structure_pass=false,
fair segment CER 0.2689/0.2779 > 0.25). **No retroactive pass, no gate lowered, no
threshold changed** (table cell CER **0.25** unchanged; printed page CER 0.15 unchanged).

**Remaining gaps (still UNMET):**
1. A genuine **grid table + human cell-level truth** sample with cell CER — Z2 cannot
   discharge the original "real table coverage" requirement.
2. **Mixed born-digital + scanned** coverage — still missing.
3. The **corrected protocol / new cohort must be frozen BEFORE any future model call**.
4. Proposed reclassification (Z2 → multi-column linear benchmark) is **append-only,
   forward-looking**, requires PM/user decision, and **does not reduce the original task
   scope** (the real-table hard requirement is preserved, not waived).

**No independent release QA / no self-done claim.** This is a partial, honest memo.
