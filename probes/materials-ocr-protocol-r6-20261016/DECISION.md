# LG035 — DECISION MEMO: the "15 rows × 3 columns" Z2 claim (protocol investigation, R6)

* Owner: pi technical requirements investigator (LG035), **not** release QA.
* Branch: `investigate/materials-ocr-protocol-r6-20261016` @ `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-protocol-r6-20261016`
* Base: clean `main@7c27f18` (verified `git status` clean before worktree add).
* Scope owned by this package: `probes/materials-ocr-protocol-r6-20261016/**` **only**.
* Product generation calls: **0**. Network calls: **0**. New model/OCR/embedding/ASR calls: **0**.
  No product source / docs08 / shared docs / frontend / backlog / PROJECT.md touched.
  No push / deploy / publish / reset / clean. All prior worktrees, raw evidence and history preserved.
* pi/DeepSeek execution cost: **unknown, not zero**. (No secrets read or printed.)
* Date (UTC): 2026-10-16.

---

## 0. Question addressed

> Is the predeclared **15 rows × 3 columns** Z2 structure supported by the original
> human truth / the real page — or is the truth actually **5 semantic sections × 3
> dialect linear paragraphs**? Where was `15×3` **first** declared? Does Z2 really
> contain a 15×3 cell grid, or side-by-side paragraphs?

Separately required by the original task: **real table coverage**. If Z2 is the wrong
class, it cannot discharge that requirement. This memo does **not** lower any gate,
does **not** relabel any result as passed, and does **not** rewrite history.

---

## 1. Facts (verifiable, with exact source citations)

### F1 — The **original protocol never states "15" or "3 columns"**.
`probes/lg035/TRUTH-PREP/protocol/SCORING-PROTOCOL.md`, §4 (committed `77596f4`, 2026-10-16 08:39):

```
## 4. Table structure check (Z2 class)
Against a pre-declared human structure:
1. machine table row count == human row count, and
2. machine table column count == human column count, and
3. every human cell/segment token appears byte-exact after NFKC.
```

It is **generic**: it compares machine counts to *whatever* the human structure is.
It never predeclares 15 or 3. The frozen manifest
(`manifest/truth_manifest.json`, committed `77596f4`) likewise contains **no** row/column
count; its only structural words are the unverified prose `"the row structure is a
genuine table-like layout in the scan"` in `samples[].pairing_basis`, written at
prep time **before** the binary was downloaded.

### F2 — `15×3` first appears in **R4 scoring code**, as an interpretation, not a protocol fact.
`probes/materials-ocr-r4-20261016/evidence/score_r4.py:227` (commit `e9fd5e5`, 2026-10-16 09:33:01):

```
Human truth is a 5-section × 3-dialect (column) table => 15 rows, 3 columns.
```

This line is the **earliest** appearance of the 15×3 shape anywhere in the repo.

### F3 — R5 later **hardened** it into an asserted "fact".
`probes/materials-ocr-r5-20261016/PLAN.md:84-93` (commit `7afe8eb`, 2026-10-16 10:05:32):

```
- 5 blank-line-separated sections.
- Each section has 3 dialect rows (國 / 蘇 / 廣 style), i.e. 3 columns.
- 15 human data rows, 3 human columns, heading line 語助詞北風跟太陽 above them.

The manual truth does support 15 rows × 3 columns; the manifest does not
mandate a different shape. No 15×3 is invented beyond what the manual truth contains.
```

Repeated as a requirement at `probes/materials-ocr-r5-20261016/REPORT.md:124` and
`probes/materials-r5-close-20261016/REPORT.md:171`.

**Trace of the claim's exact origin:** original protocol (generic, `77596f4`) → R4 code
comment that *equates* "5 sections × 3 dialects" with "3 **columns**" and multiplies to
"15 rows, 3 columns" (`e9fd5e5`) → R5 PLAN asserts "the manual truth does support 15×3"
(`7afe8eb`). The geometric word **"columns" was introduced by the scoring code, not by
the original protocol or by the human proofreader.**

### F4 — The human truth is **5 sections × 3 dialect lines**, a linear prefix-labelled list.
`truth/LG035-ZH-Z2.p2.txt` (sha256 `8c6ad74b…`, identical in all 17 worktree copies),
structure: 1 heading + 5 blank-line-separated sections, each with **3 lines**:

```
<h2>語助詞北風跟太陽</h2>

*國、有一囘，北風跟太陽兩個人在那兒爭論誰的本事大。
*蘇、有一轉，北風搭太陽两家頭勒浪爭啥人格本事大。
*廣、有一句，北風同𤍠頭兩個人喺處爭論邊個嘅本事大。
...
```

Every content line begins with `*` + a **dialect marker** (國/蘇/廣/北/世/船/末…). The
`3` is the number of **dialect variants per semantic section**, stored as separate
full-length lines distinguished by a **left-margin prefix** — not as cells in a column
grid. There is **no table markup** and **no raw wikitext with `{|` table syntax** stored
anywhere; the truth is a plain line list.

### F5 — The **real page has no table geometry** (measured on the product-rendered pixels).
Independent stdlib PNG decode of the **product rasterizer's** Z2 page-2 render
(`PdfiumRasterizer`, scale 2.0, PNG sha256 `15ca62198b90b2…`, 817×1380 — byte-identical to
the R4 OCR input and R6 analysis input). Evidence: `evidence/z2_pixel_geometry.json`.

| Measurement | Value | Implication |
|---|---|---|
| content box (px) | x **109..704**, y **319..1039** | single column block |
| horizontal ruling lines | **0** | no table row separators |
| vertical ruling lines | **0** | no table column separators |
| max horizontal dark run | **69 px** (≈8% of width) | no horizontal rule at all |
| max vertical dark run | **50 px** | no vertical rule at all |
| text lines detected | **13** bands | (1 title + content) |
| line left edge `x0` | 164,127,125,126,127,116,127,127,128,127,109,114,358 | lines start at the **left margin**, not 3 column positions |
| line width | 541,539,552,509,521,536,549,547,548,545,562,… | **near-full-width** lines stacked vertically |

A genuine 15×3 table would show column separators or consistent gutters and lines
starting at three distinct x-positions. Neither exists. The only genuine side-by-side
region is **one local pair** (section 2, middle rows: a measured gutter), consistent with
R6's `region_column_counts=[3,2,1,2]` and `column_model=multi_column_local`.

### F6 — The real model output corroborates the pixel measurement (not a substitute for it).
R5's actual OCR text (`evidence/ocr_call1_z2_scale4.json`) renders section 2's two
side-by-side blocks **on one line** (`北風說… 世界上的東西…`) and emits **no table**, i.e.
the model transcribed the page's real linear/2-D layout; the "15×3 grid" exists only in
the truth's normalised form, not on the page.

### F7 — Z2 gates were already recorded FAIL (unchanged here).
R4/R5 recorded `structure_pass=false`, machine rows `0`/`unverified`, fair segment CER
`0.2689`/`0.2779` > `0.25`. **Nothing in this memo changes any historical number, score,
threshold or report byte.**

---

## 2. Inference (reasoned from the facts; stated as inference, not fact)

* **I1.** The `15×3` is a **semantic dialect taxonomy** ("5 questions × 3 dialect
  varieties"), expressed in the human transcription as **prefix-labelled linear
  paragraphs**. It is *not* a geometric grid: F4 (truth text), F5 (no ruling, left-margin
  starts, full-width lines), F6 (model sees side-by-side blocks and merges them) agree.
* **I2.** The original protocol's §4 check is **geometric** ("machine row/column count
  == human row/column count"). Applying it to Z2 therefore compares **page geometry**
  against a **label taxonomy**. Under this reading, §4's pass condition is **not
  satisfiable by any faithful transcription** of this page — a protocol/classification
  defect, independently re-derived here (R6 reached a similar conclusion; this memo
  verifies it from the product-rendered pixels and the origin trace rather than adopting
  R6's conclusion).
* **I3.** Because Z2's page has **no 15×3 cell grid**, Z2 **cannot on its own discharge
  the original task's "real table coverage" requirement** under a genuine grid+truth
  interpretation. Z2 *can* legitimately serve as a **mutli-column / side-by-side
  reading-order** benchmark (F5 shows a real local 2-column region).

---

## 3. Uncertainty (explicitly not proven here)

* **U1 — visual confirmation not obtained by this investigator.** This session's model
  could **not view images** (image attach omitted: "model does not support images"), so
  the page was assessed by **deterministic pixel geometry** (F5) and the real model's
  output (F6), **not** by human/investigator *visual* inspection. The measurement is
  strong and reproduces R6's coordinates exactly, but "I looked at the page and saw X"
  is **not** claimed.
* **U2 — the raw Wikisource wikitext is not stored** in-repo (only the rendered truth
  line list). If the on-wiki page used a `{|` table template, the truth file would be a
  derived rendering; the stored artifact (F4) is nevertheless a linear line list, which
  is what R4/R5 scored.
* **U3 — one page.** Conclusions about Z2 page 2 do not establish the whole 方言調查表格
  work; other pages were not inspected.
* **U4 — "impossible" is not claimed.** It is **not proven impossible** that the source
  document's *design intent* was a dialect table; what is proven is that the **rendered
  page 2** carries no 15×3 grid geometry and the **stored human truth** is linear.

---

## 4. Decision

1. **The predeclared `15×3` Z2 shape is a mis-classification**, not an original-protocol
   predeclaration. Its origin is R4 scoring code (`score_r4.py:227`, `e9fd5e5`) and R5
   PLAN (`7afe8eb`), **not** `SCORING-PROTOCOL.md` or the human page. Reliability of the
   `15×3` claim as a *geometric* fact: **LOW**. As a *semantic dialect taxonomy*
   (5×3 groups of prefix-labelled lines): **HIGH**.
2. **Z2 is the wrong class for the "real table" hard requirement.** Reclassify Z2 as a
   **multi-column / side-by-side linear reading-order benchmark**, where the `0.25`
   threshold can legitimately measure segment CER **without** the geometric §4 grid gate.
3. **The printed pass stands** (Z1 page CER ≤0.15) and is untouched. **No gate is
   lowered, no previously-recorded FAIL is relabelled PASS.** Z2 remains FAIL under the
   original `15×3` geometric gate; that FAIL is a *protocol-class* artifact.
4. **The true table hard requirement is still UNMET and needs new evidence**: a real
   page that actually has a **grid (ruling or consistent gutters) + human cell-level
   truth**, with cell CER. No synthetic substitute is acceptable.
5. **Mixed born-digital + scanned coverage is also still missing** (per STATUS/Z2-BINARY-CLOSE));
   unchanged by this memo.

---

## 5. Proposed future acceptance mapping (append-only erratum; NOT applied here)

This is a **proposal for PM/user decision**. It must **not** be applied retroactively to
R3/R4/R5, and it must not edit `SCORING-PROTOCOL.md`, the manifest or any report byte.

**Erratum (append-only, forward-looking):**

| Class | Sample | Metric | Threshold (unchanged) | Change |
|---|---|---|---|---|
| Real Chinese printed page | Z1 | page CER | ≤ 0.15 | none |
| **Multi-column / side-by-side linear page** | Z2 (reclassified) | segment CER **+ reading-order reconciliation** | ≤ 0.25 | **reclassify**; drop the geometric grid gate |
| **Real table (grid + human cell truth)** | **NEW cohort only** | **cell CER** | **≤ 0.25 (unchanged)** | **new sample required**; §4 grid check applies here |
| Mixed born-digital + scan | NEW cohort | page/segment CER | per class | still BLOCKED; new sample required |

**Non-negotiable conditions for any future corrected protocol:**

* The corrected protocol must be a **NEW cohort, frozen BEFORE any future model call**;
  thresholds (table cell CER **0.25**, printed page CER 0.15) are **unchanged**.
* The new table sample must be a real scan/image with **actual grid geometry** and
  **human cell-level truth**; the human truth must be cells, not a linear list.
* Multicolumn reading order may be a **separate benchmark**; a real table still requires
  a real grid + human truth. Neither may be substituted for the other.
* **No synthetic image, synthetic scan, or machine output-as-truth** may fill any class.
* The errata record is **appended**; R4/R5 numbers and the `15×3` FAIL remain in history.

---

## 6. Evidence index (this package)

| File | What it proves |
|---|---|
| `evidence/render_hashes.txt` | source PDF license/sha1/sha256; product-render pixel sha; truth sha |
| `evidence/z2_pixel_geometry.json` | independent ink/line/ruling measurement on product-rendered pixels (F5) |
| `render/product_scale2_p2.png` | product rasterizer output, sha `15ca6219…` (reproducible) |
| `render/z2p2_r150-02.png`, `render/z2p2_r300-02.png` | independent pdftoppm renders (geometry cross-check) |
| `evidence/render_ascii_map.txt` | coarse ink map of the page (96×60 downsample of `render/product_scale2_p2.png`; text-form layout, for record) |

**Source citations:** `SCORING-PROTOCOL.md` §4 @ `77596f4`; `score_r4.py:227` @ `e9fd5e5`;
`materials-ocr-r5-20261016/PLAN.md:84-93` @ `7afe8eb`; `truth/LG035-ZH-Z2.p2.txt`
sha256 `8c6ad74b…`; Z2 PDF sha1 `fe557252…` / sha256 `da50c9f6…`.

---

## 7. Explicit non-claims

* No self-done / QA-pass claim. LG-035 stays **in-progress**; LG-040/041 stay locked.
* No product code change, no gate lowering, no relabelling, no history rewrite.
* No visual ("I saw") claim — see U1.
* No claim that a table is impossible in the source work — see U4.
* No network, OCR, embedding, ASR or model call was made by this package.

---

## 8. Session provenance — original budget exit and non-replay recovery (explicit)

This memo was produced by the **second** attempt of the same pi work package.

* **Original attempt:** a bounded pi wrapper on this same worktree/branch ran and was
  terminated by the harness at **exit code 143** (`token_budget_exceeded`) at ~154 s,
  **before** it could create `STATUS.md` or commit. Per the harness log
  (`lightgravity-pi-bounded-b0rnlv0h.log`, tail), its **last completed action was the
  successful `write` of this `DECISION.md`**.
* **Recovery method — NON-REPLAY.** No model/OCR/embedding/ASR/network call, no product
  call and no re-run of the original investigation was performed. Recovery = (a) read
  the **existing owned evidence files** already on disk, (b) read the **tail** of the
  harness log to confirm the exact state at exit, (c) verify **no live writer** (no
  pi/node/python process owned this worktree), (d) preserve the already-written
  `DECISION.md` and evidence bytes, and (e) make only the minimal owned corrections:
  fixed one **citation path error** in the evidence index (the product render lives in
  `render/`, not `evidence/`), materialized the cited-but-missing `render_ascii_map.txt`
  from the **already-present, sha-verified** product render (deterministic offline stdlib
  PNG decode), and added this section plus `STATUS.md`.
* **Preservation:** the substantive conclusions, facts, hashes and every existing
  evidence byte were **not** altered beyond the two cosmetic/once-described fixes above.
  No other worktree and no `main` (`7c27f18`) was touched.
* This section records the recovery honestly; it is **not** a QA/self-done claim.
